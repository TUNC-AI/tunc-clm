//! v3.0 trim-aware validation per `SPEC.clm` (`validation.posture.v3.0`).
//!
//! A v3.0 document MAY declare:
//!   ;;; trim.mode: aggressive
//!   ;;; trim.config: roll_call=10, dream_log=3, decisions_live=8
//!   ;;; archive.mode: sibling
//!   ;;; archive.path: <relative-or-absolute-path>
//!
//! When `trim.mode != none`, archive.path MUST be declared and archive.mode MUST be
//! `sibling`. When the document has overflowed any trim threshold, the affected section
//! MUST contain a `;;` truncation sentinel BEFORE the kept entries.
//!
//! This module returns a [`ValidationReport`] with errors (block conformance) and
//! warnings (don't block, but a validator should surface them).

use crate::Document;
use std::collections::HashMap;
use std::fmt;
use std::path::{Path, PathBuf};

/// Trim mode declared in the file header.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TrimMode {
    None,
    Aggressive,
}

/// Archive mode declared in the file header.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArchiveMode {
    Sibling,
    Inline,
}

/// Trim-config keys recognized by the spec.
const TRIM_CONFIG_KEYS: &[&str] = &["roll_call", "dream_log", "decisions_live"];

/// Default trim-config values when keys are absent.
pub const DEFAULT_ROLL_CALL_KEEP: usize = 10;
pub const DEFAULT_DREAM_LOG_KEEP: usize = 3;
pub const DEFAULT_DECISIONS_LIVE_KEEP: usize = 8;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TrimConfig {
    pub roll_call: usize,
    pub dream_log: usize,
    pub decisions_live: usize,
}

impl Default for TrimConfig {
    fn default() -> Self {
        Self {
            roll_call: DEFAULT_ROLL_CALL_KEEP,
            dream_log: DEFAULT_DREAM_LOG_KEEP,
            decisions_live: DEFAULT_DECISIONS_LIVE_KEEP,
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct HeaderDeclarations {
    pub trim_mode: Option<TrimMode>,
    pub trim_config: Option<TrimConfig>,
    pub archive_mode: Option<ArchiveMode>,
    pub archive_path: Option<String>,
    pub archive_path_naming_convention: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ValidationError {
    /// trim.mode != none but archive.path header is missing.
    /// Resolution per spec: ERROR (no silent derivation from convention).
    MissingArchivePathUnderTrim,
    /// trim.mode = aggressive combined with archive.mode = inline (unsupported).
    AggressiveTrimWithInlineArchive,
    /// trim.config has duplicate keys (within a single header line).
    DuplicateTrimConfigKey { key: String },
    /// trim.config has a key with no value (e.g. `roll_call=`).
    MissingTrimConfigValue { key: String },
    /// trim.config value can't be parsed as a non-negative integer.
    InvalidTrimConfigValue { key: String, raw: String },
    /// A section declared as trimmed has overflowed its keep_last but lacks the
    /// `;;` truncation sentinel before its kept entries.
    /// Note: detection is heuristic — see [`overflow_estimate`].
    SentinelMissingInTrimmedSection { section: String, entries: usize, keep: usize },
    /// trim.mode header value is not one of the recognized values.
    UnknownTrimMode { raw: String },
    /// archive.mode header value is not one of the recognized values.
    UnknownArchiveMode { raw: String },
    /// [DELTA.<session-id>] section name uses an invalid session-id grammar.
    /// Per spec: session-id matches `[a-z0-9][a-z0-9._-]*`.
    InvalidDeltaSessionId { section_name: String, session_id: String },
    /// trim.mode is aggressive AND the doc is in state.C (sentinel present in some trimmed
    /// section, indicating overflow has occurred), but the resolved archive.path file does
    /// not exist on disk. Per spec: state.C requires the archive file to exist.
    ArchiveFileMissingInStateC { resolved_path: PathBuf },
}

impl fmt::Display for ValidationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use ValidationError::*;
        match self {
            MissingArchivePathUnderTrim => write!(
                f,
                "trim.mode is set but ';;; archive.path: ...' header is missing (required when trim.mode != none)"
            ),
            AggressiveTrimWithInlineArchive => write!(
                f,
                "trim.mode: aggressive cannot be combined with archive.mode: inline (unsupported per spec)"
            ),
            DuplicateTrimConfigKey { key } => write!(f, "trim.config has duplicate key: {key:?}"),
            MissingTrimConfigValue { key } => {
                write!(f, "trim.config key {key:?} has no value")
            }
            InvalidTrimConfigValue { key, raw } => {
                write!(f, "trim.config[{key:?}] = {raw:?} is not a non-negative integer")
            }
            SentinelMissingInTrimmedSection { section, entries, keep } => write!(
                f,
                "section [{section}] has {entries} entries (keep_last = {keep}); \
                 truncation sentinel is required before kept entries (\
                 e.g. `;; (oldest N entries offloaded to [{section}.ARCHIVE] in sibling)`)"
            ),
            UnknownTrimMode { raw } => write!(f, "unknown trim.mode value: {raw:?} (expected: none, aggressive)"),
            UnknownArchiveMode { raw } => write!(f, "unknown archive.mode value: {raw:?} (expected: sibling, inline)"),
            InvalidDeltaSessionId { section_name, session_id } => write!(
                f,
                "section [{section_name}]: session-id {session_id:?} does not match `[a-z0-9][a-z0-9._-]*`"
            ),
            ArchiveFileMissingInStateC { resolved_path } => write!(
                f,
                "doc is in state.C (overflow occurred — sentinel present) but archive.path resolves to {resolved_path:?} which does not exist"
            ),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ValidationWarning {
    UnknownTrimConfigKey { key: String },
    DuplicateDeltaSessionId { session_id: String },
    /// trim.mode = aggressive but archive.mode is not declared (defaults to sibling).
    ArchiveModeUnspecifiedUnderTrim,
    /// A line in [ROLL.CALL] or [DREAM.LOG] doesn't match the expected entry shape
    /// (e.g. ROLL.CALL line missing the `·` separator). Per spec malformed.entry.behavior:
    /// QUARANTINE + WARNING (preserve verbatim, surface, exclude from trim accounting).
    MalformedEntry { section: String, content: String },
    /// trim.mode is aggressive and the doc is in state.B (no overflow yet), but the
    /// declared archive.path doesn't exist on disk. State.B permits this (file appears
    /// at first offload), so it's a warning, not an error.
    ArchiveFileNotYetCreatedInStateB { resolved_path: PathBuf },
}

impl fmt::Display for ValidationWarning {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        use ValidationWarning::*;
        match self {
            UnknownTrimConfigKey { key } => write!(
                f,
                "unknown trim.config key {key:?} (recognized: roll_call, dream_log, decisions_live); preserved but ignored"
            ),
            DuplicateDeltaSessionId { session_id } => {
                write!(f, "duplicate [DELTA.session-id] {session_id:?}; line order remains authoritative")
            }
            ArchiveModeUnspecifiedUnderTrim => write!(
                f,
                "trim.mode is set but archive.mode is not declared; defaulting to sibling"
            ),
            MalformedEntry { section, content } => write!(
                f,
                "[{section}] entry does not match expected shape: {content:?} (quarantined; not counted for trim)"
            ),
            ArchiveFileNotYetCreatedInStateB { resolved_path } => write!(
                f,
                "archive.path resolves to {resolved_path:?} which does not exist; OK for state.B (file appears at first offload)"
            ),
        }
    }
}

#[derive(Debug, Clone, Default)]
pub struct ValidationReport {
    pub header: HeaderDeclarations,
    pub errors: Vec<ValidationError>,
    pub warnings: Vec<ValidationWarning>,
}

impl ValidationReport {
    pub fn is_valid(&self) -> bool {
        self.errors.is_empty()
    }
}

/// Run v3.0 trim-aware validation against a parsed [`Document`]. No filesystem access.
/// Use [`validate_v3_with_filesystem`] when you can resolve `archive.path` against a base dir.
///
/// The validator runs in two modes determined by the doc's shape:
///   - **Live doc**: declares `trim.mode` in the header. Trim-section sentinel checks +
///     header consistency + delta-session-id checks apply.
///   - **Sibling archive file**: contains `[ROLL.CALL.ARCHIVE]`, `[DREAM.LOG.ARCHIVE]`,
///     and/or `[DECISIONS.ARCHIVE]` sections; lacks a `trim.mode` header. Per-entry
///     shape validation applies to those archive sections (so malformed offloaded
///     entries surface as warnings instead of validating silently).
pub fn validate_v3(doc: &Document) -> ValidationReport {
    let mut report = ValidationReport::default();
    report.header = parse_header_declarations(doc, &mut report.errors, &mut report.warnings);
    check_trim_mode_consistency(&report.header, &mut report.errors, &mut report.warnings);
    check_delta_session_ids(doc, &mut report.errors, &mut report.warnings);

    if matches!(report.header.trim_mode, Some(TrimMode::Aggressive)) {
        let trim_config = report.header.trim_config.clone().unwrap_or_default();
        check_section_sentinels(doc, &trim_config, &mut report.errors, &mut report.warnings);
    }

    // Archive-section validation runs regardless of trim.mode (sibling archive files
    // don't carry a trim.mode header). Per SPEC.clm validation.posture.v3.0 these MUST
    // be validated when present.
    check_archive_section_entries(doc, &mut report.warnings);

    report
}

/// Inspect `[ROLL.CALL.ARCHIVE]`, `[DREAM.LOG.ARCHIVE]`, `[DECISIONS.ARCHIVE]` sections
/// (typically present in sibling archive files) and apply the same per-line shape checks
/// as their live counterparts. Malformed lines are quarantined as warnings.
fn check_archive_section_entries(doc: &Document, warnings: &mut Vec<ValidationWarning>) {
    for (section, _) in &doc.sections {
        match section.name.as_str() {
            "ROLL.CALL.ARCHIVE" => {
                let _ = count_valid_entries(&section.body, "ROLL.CALL.ARCHIVE", warnings);
            }
            "DREAM.LOG.ARCHIVE" => {
                let _ = count_valid_entries(&section.body, "DREAM.LOG.ARCHIVE", warnings);
            }
            "DECISIONS.ARCHIVE" => {
                // decisions entries look like `dN: text [session N]`; loose check — must
                // start with `d<digit>` after trim. Other shapes get a MalformedEntry warning.
                for line in &section.body {
                    let trimmed = line.trim();
                    if trimmed.is_empty() || trimmed.starts_with(";;") {
                        continue;
                    }
                    let well_formed = looks_like_decision_entry(trimmed);
                    if !well_formed {
                        warnings.push(ValidationWarning::MalformedEntry {
                            section: "DECISIONS.ARCHIVE".to_string(),
                            content: trimmed.to_string(),
                        });
                    }
                }
            }
            _ => {}
        }
    }
}

/// `dN: text [session N]` shape check (loose — just `d<digit>` prefix and `:` separator).
fn looks_like_decision_entry(line: &str) -> bool {
    let mut chars = line.chars();
    if chars.next() != Some('d') {
        return false;
    }
    let Some(second) = chars.next() else {
        return false;
    };
    if !second.is_ascii_digit() {
        return false;
    }
    line.contains(':')
}

/// Like [`validate_v3`] plus a filesystem check on `archive.path`.
///
/// `base_dir` is the directory the archive.path is resolved against (per spec:
/// relative to live file's directory).
///
/// Behavior:
///   - state.A (no trim): no filesystem check.
///   - state.B (trim declared, no overflow yet): missing archive file → WARNING
///     (file may not yet exist; appears at first offload per spec).
///   - state.C (trim declared, overflow occurred — sentinel detected in some
///     trimmed section): missing archive file → ERROR (spec requires existence).
pub fn validate_v3_with_filesystem(doc: &Document, base_dir: &Path) -> ValidationReport {
    let mut report = validate_v3(doc);

    if !matches!(report.header.trim_mode, Some(TrimMode::Aggressive)) {
        return report;
    }
    let Some(archive_path_str) = report.header.archive_path.clone() else {
        return report;
    };
    let resolved = base_dir.join(&archive_path_str);
    // Per spec the archive must be a *file*; .exists() returns true for directories,
    // so a stray `archive.path: .` would otherwise validate clean.
    if resolved.is_file() {
        return report;
    }

    if is_state_c(doc) {
        report.errors.push(ValidationError::ArchiveFileMissingInStateC { resolved_path: resolved });
    } else {
        report
            .warnings
            .push(ValidationWarning::ArchiveFileNotYetCreatedInStateB { resolved_path: resolved });
    }

    report
}

/// State.C is "post-first-trim-offload" — i.e., at least one trimmed section contains
/// either a sentinel OR a `decisions.live (... of ... archived)` header that itself
/// declares offload occurred. Looks at [ROLL.CALL], [DREAM.LOG], and [STATE].decisions.live.
///
/// The declared-offload check matters because a state.C doc with a missing sentinel is
/// still state.C — the validator surfaces the missing-sentinel error, AND the filesystem
/// check should still demand the archive file exist (per spec).
fn is_state_c(doc: &Document) -> bool {
    for (section, _) in &doc.sections {
        match section.name.as_str() {
            "ROLL.CALL" if has_sentinel(&section.body, "ROLL.CALL") => return true,
            "DREAM.LOG" if has_sentinel(&section.body, "DREAM.LOG") => return true,
            "STATE" => {
                let stats = decisions_live_stats(&section.body);
                if stats.sentinel_present || stats.declared_offload_count.unwrap_or(0) > 0 {
                    return true;
                }
            }
            _ => {}
        }
    }
    false
}

/// Parse header `;;;` lines for trim/archive declarations.
fn parse_header_declarations(
    doc: &Document,
    errors: &mut Vec<ValidationError>,
    warnings: &mut Vec<ValidationWarning>,
) -> HeaderDeclarations {
    let mut decls = HeaderDeclarations::default();
    for raw in &doc.header {
        let Some(content) = raw.strip_prefix(";;;") else {
            continue;
        };
        // Iterate `key: value` clauses separated by `|`.
        for clause in content.split('|') {
            let clause = clause.trim();
            if clause.is_empty() || clause == "---" {
                continue;
            }
            let Some((key, value)) = clause.split_once(':') else {
                continue;
            };
            let key = key.trim();
            let value = value.trim();
            match key {
                "trim.mode" => match value {
                    "none" => decls.trim_mode = Some(TrimMode::None),
                    "aggressive" => decls.trim_mode = Some(TrimMode::Aggressive),
                    other => {
                        errors.push(ValidationError::UnknownTrimMode { raw: other.to_string() });
                    }
                },
                "trim.config" => {
                    decls.trim_config = Some(parse_trim_config(value, errors, warnings));
                }
                "archive.mode" => match value {
                    "sibling" => decls.archive_mode = Some(ArchiveMode::Sibling),
                    "inline" => decls.archive_mode = Some(ArchiveMode::Inline),
                    other => {
                        errors.push(ValidationError::UnknownArchiveMode { raw: other.to_string() });
                    }
                },
                "archive.path" => {
                    decls.archive_path = Some(value.to_string());
                }
                "archive.path.naming.convention" => {
                    decls.archive_path_naming_convention = Some(value.to_string());
                }
                _ => {}
            }
        }
    }
    decls
}

fn parse_trim_config(
    value: &str,
    errors: &mut Vec<ValidationError>,
    warnings: &mut Vec<ValidationWarning>,
) -> TrimConfig {
    let mut cfg = TrimConfig::default();
    let mut seen: HashMap<String, ()> = HashMap::new();
    for entry in value.split(',') {
        let entry = entry.trim();
        if entry.is_empty() {
            continue;
        }
        let Some((key, val)) = entry.split_once('=') else {
            errors.push(ValidationError::MissingTrimConfigValue { key: entry.to_string() });
            continue;
        };
        let key = key.trim();
        let val = val.trim();
        if seen.insert(key.to_string(), ()).is_some() {
            errors.push(ValidationError::DuplicateTrimConfigKey { key: key.to_string() });
            continue;
        }
        if val.is_empty() {
            errors.push(ValidationError::MissingTrimConfigValue { key: key.to_string() });
            continue;
        }
        let parsed: Result<usize, _> = val.parse();
        match parsed {
            Err(_) => {
                errors.push(ValidationError::InvalidTrimConfigValue {
                    key: key.to_string(),
                    raw: val.to_string(),
                });
                continue;
            }
            Ok(n) => match key {
                "roll_call" => cfg.roll_call = n,
                "dream_log" => cfg.dream_log = n,
                "decisions_live" => cfg.decisions_live = n,
                other => {
                    warnings.push(ValidationWarning::UnknownTrimConfigKey {
                        key: other.to_string(),
                    });
                }
            },
        }
        let _ = TRIM_CONFIG_KEYS;
    }
    cfg
}

fn check_trim_mode_consistency(
    decls: &HeaderDeclarations,
    errors: &mut Vec<ValidationError>,
    warnings: &mut Vec<ValidationWarning>,
) {
    let trim_mode = decls.trim_mode.unwrap_or(TrimMode::None);
    if trim_mode == TrimMode::None {
        return;
    }
    if decls.archive_path.is_none() {
        errors.push(ValidationError::MissingArchivePathUnderTrim);
    }
    match decls.archive_mode {
        Some(ArchiveMode::Inline) => errors.push(ValidationError::AggressiveTrimWithInlineArchive),
        None => warnings.push(ValidationWarning::ArchiveModeUnspecifiedUnderTrim),
        Some(ArchiveMode::Sibling) => {}
    }
}

/// Count entries in a section's body, filtering out malformed lines and emitting a
/// `MalformedEntry` warning for each.
///
/// Per `SPEC.clm` `malformed.entry.behavior`: QUARANTINE + WARNING (preserve verbatim,
/// surface, exclude from trim accounting). This means a single broken line MUST NOT
/// trigger a hard `SentinelMissingInTrimmedSection` once the section crosses keep_last.
///
/// Per-section entry shape:
///   `[ROLL.CALL]`: `<Family>.<Model.Version> · <YYYY-MM-DD> · "<note>"` — must contain `·`.
///   `[DREAM.LOG]`: `<YYYY-MM-DD> | <Family>.<Model.Version> | <message>` — must contain `|`.
fn count_valid_entries(
    body: &[String],
    section_name: &str,
    warnings: &mut Vec<ValidationWarning>,
) -> usize {
    let mut count = 0;
    for line in body {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with(";;") {
            continue;
        }
        let well_formed = match section_name {
            "ROLL.CALL" | "ROLL.CALL.ARCHIVE" => well_formed_roll_call_line(trimmed),
            "DREAM.LOG" | "DREAM.LOG.ARCHIVE" => well_formed_dream_log_line(trimmed),
            _ => true,
        };
        if well_formed {
            count += 1;
        } else {
            warnings.push(ValidationWarning::MalformedEntry {
                section: section_name.to_string(),
                content: trimmed.to_string(),
            });
        }
    }
    count
}

/// Check whether a section's body has a sentinel comment that mentions an offload
/// to its corresponding `.ARCHIVE` sibling section, AND that the sentinel appears
/// BEFORE the first non-comment entry (per SPEC.clm sentinel.placement).
fn has_sentinel(body: &[String], section_name: &str) -> bool {
    let archive_marker = format!("{section_name}.ARCHIVE");
    let mut seen_entry = false;
    for line in body {
        let t = line.trim();
        if t.is_empty() {
            continue;
        }
        if t.starts_with(";;") {
            if !seen_entry && t.contains(&archive_marker) && t.contains("offloaded") {
                return true;
            }
            continue;
        }
        // Non-comment, non-blank line — that's an entry.
        seen_entry = true;
    }
    false
}

fn check_section_sentinels(
    doc: &Document,
    trim: &TrimConfig,
    errors: &mut Vec<ValidationError>,
    warnings: &mut Vec<ValidationWarning>,
) {
    for (section, _trivia) in &doc.sections {
        match section.name.as_str() {
            "ROLL.CALL" => {
                let entries = count_valid_entries(&section.body, "ROLL.CALL", warnings);
                if entries > trim.roll_call && !has_sentinel(&section.body, "ROLL.CALL") {
                    errors.push(ValidationError::SentinelMissingInTrimmedSection {
                        section: section.name.clone(),
                        entries,
                        keep: trim.roll_call,
                    });
                }
            }
            "DREAM.LOG" => {
                let entries = count_valid_entries(&section.body, "DREAM.LOG", warnings);
                if entries > trim.dream_log && !has_sentinel(&section.body, "DREAM.LOG") {
                    errors.push(ValidationError::SentinelMissingInTrimmedSection {
                        section: section.name.clone(),
                        entries,
                        keep: trim.dream_log,
                    });
                }
            }
            "STATE" => {
                // decisions.live is an indented sub-block inside [STATE]; the spec requires
                // a truncation sentinel before kept entries when offload has occurred.
                //
                // Two ways offload is detected:
                //   - visible entries > keep_last (the writer hasn't trimmed yet), OR
                //   - the header `(X of Y archived)` parenthetical declares Y > X (the writer
                //     trimmed down to keep_last and the sentinel must still be emitted to
                //     preserve audit visibility per SPEC.clm).
                let stats = decisions_live_stats(&section.body);
                let visible_overflow = stats.visible_entries > trim.decisions_live;
                let declared_offload = stats.declared_offload_count.unwrap_or(0) > 0;
                if (visible_overflow || declared_offload) && !stats.sentinel_present {
                    errors.push(ValidationError::SentinelMissingInTrimmedSection {
                        section: "STATE.decisions.live".to_string(),
                        entries: stats.visible_entries,
                        keep: trim.decisions_live,
                    });
                }
            }
            _ => continue,
        }
    }
}

#[derive(Debug, Default)]
struct DecisionsLiveStats {
    visible_entries: usize,
    sentinel_present: bool,
    /// If the header parens declare `(X of Y archived)`, the difference Y - X tells us
    /// how many decisions have been offloaded. None if the header didn't declare it.
    declared_offload_count: Option<usize>,
}

/// Inspect a `[STATE]` body, find the `decisions.live` sub-block, and return its stats.
///
/// Per `SPEC.clm` `decisions.live.delimitation`:
///   - begins at a line matching `\s*decisions\.live[:( ]`
///   - contains entries indented deeper than the `decisions.live:` line itself
///   - ends at the next un-indented key OR the section close
///   - sentinel placement: BEFORE the kept entries (a comment naming `DECISIONS.ARCHIVE`)
///
/// Also parses an optional `(X of Y archived)` annotation on the header line:
/// if Y > X, the doc declares that decisions have been offloaded — sentinel is required
/// EVEN IF the visible entry count == keep_last (state.C with already-trimmed body).
fn decisions_live_stats(state_body: &[String]) -> DecisionsLiveStats {
    let mut stats = DecisionsLiveStats::default();
    let mut in_block = false;
    let mut block_indent: usize = 0;
    let mut seen_entry_yet = false;

    for raw in state_body {
        let leading = raw.chars().take_while(|c| *c == ' ').count();
        let trimmed = raw.trim_start();

        if !in_block {
            if let Some(rest) = trimmed.strip_prefix("decisions.live") {
                let next = rest.chars().next();
                if matches!(next, Some(':') | Some('(') | Some(' ')) {
                    in_block = true;
                    block_indent = leading;
                    stats.declared_offload_count = parse_decisions_live_header_paren(rest);
                }
            }
            continue;
        }

        if trimmed.is_empty() {
            continue;
        }
        if leading <= block_indent {
            break;
        }

        if trimmed.starts_with(";;") {
            if !seen_entry_yet
                && trimmed.contains("DECISIONS.ARCHIVE")
                && trimmed.contains("offloaded")
            {
                stats.sentinel_present = true;
            }
            continue;
        }

        stats.visible_entries += 1;
        seen_entry_yet = true;
    }

    stats
}

/// Parse the parenthetical after `decisions.live`. Accepts both forms used in the wild:
///   `(X of Y archived)`           — numeric first token
///   `(last X of Y archived)`      — "last" prefix, then X (per SPEC.clm example)
/// Returns `Some(Y - X)` when offload occurred (Y > X); otherwise None.
fn parse_decisions_live_header_paren(after_key: &str) -> Option<usize> {
    let open = after_key.find('(')?;
    let close = after_key[open..].find(')')?;
    let inner = &after_key[open + 1..open + close];
    let mut tokens = inner.split_whitespace().peekable();
    // Optional "last" prefix.
    if matches!(tokens.peek().copied(), Some("last")) {
        tokens.next();
    }
    let x: usize = tokens.next()?.parse().ok()?;
    let of_kw = tokens.next()?;
    if of_kw != "of" {
        return None;
    }
    let y: usize = tokens.next()?.parse().ok()?;
    if y > x { Some(y - x) } else { None }
}

/// Check `[DELTA.<session-id>]` section names for grammar conformance.
///
/// `[DELTA.ARCHIVE]` is a structural section name used by inline-archive mode
/// (per `archive.lifecycle` in `SPEC.clm`) and is NOT a session-id; skip it.
fn check_delta_session_ids(
    doc: &Document,
    errors: &mut Vec<ValidationError>,
    warnings: &mut Vec<ValidationWarning>,
) {
    let mut seen: HashMap<String, usize> = HashMap::new();
    for (section, _) in &doc.sections {
        let Some(session_id) = section.name.strip_prefix("DELTA.") else {
            continue;
        };
        // Reserved structural section name; not a session-id.
        if session_id == "ARCHIVE" {
            continue;
        }
        if !is_valid_session_id(session_id) {
            errors.push(ValidationError::InvalidDeltaSessionId {
                section_name: section.name.clone(),
                session_id: session_id.to_string(),
            });
            continue;
        }
        let count = seen.entry(session_id.to_string()).or_insert(0);
        *count += 1;
        if *count == 2 {
            warnings.push(ValidationWarning::DuplicateDeltaSessionId {
                session_id: session_id.to_string(),
            });
        }
    }
}

/// Per spec: session-id matches `[a-z0-9][a-z0-9._-]*`.
fn is_valid_session_id(s: &str) -> bool {
    let mut chars = s.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    if !(first.is_ascii_lowercase() || first.is_ascii_digit()) {
        return false;
    }
    chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '.' || c == '_' || c == '-')
}

/// Stricter shape check for a `[ROLL.CALL]` entry line.
///
/// Per spec: `<Family>.<Model.Version> · <YYYY-MM-DD> · "<note>"`.
/// Heuristic: must have at least 3 `·`-separated parts; the second part must look like
/// an ISO date (YYYY-MM-DD); the third must contain a `"` (the note delimiter).
fn well_formed_roll_call_line(line: &str) -> bool {
    let parts: Vec<&str> = line.split('·').collect();
    if parts.len() < 3 {
        return false;
    }
    let date = parts[1].trim();
    let note = parts[2..].join("·");
    looks_like_iso_date(date) && note.contains('"')
}

/// Stricter shape check for a `[DREAM.LOG]` entry line.
///
/// Per spec: `<YYYY-MM-DD[ <session-tag>]?> | <Family>.<Model.Version> | <message>`.
/// Heuristic: at least 3 `|`-separated parts; the first part starts with an ISO date.
fn well_formed_dream_log_line(line: &str) -> bool {
    let parts: Vec<&str> = line.split('|').collect();
    if parts.len() < 3 {
        return false;
    }
    let first = parts[0].trim();
    // First part may be `YYYY-MM-DD` alone or `YYYY-MM-DD <session-tag>`.
    let date_token = first.split_whitespace().next().unwrap_or("");
    looks_like_iso_date(date_token)
}

fn looks_like_iso_date(s: &str) -> bool {
    let bytes = s.as_bytes();
    if bytes.len() != 10 {
        return false;
    }
    let pat = b"NNNN-NN-NN";
    for (i, b) in bytes.iter().enumerate() {
        match pat[i] {
            b'N' => {
                if !b.is_ascii_digit() {
                    return false;
                }
            }
            b'-' => {
                if *b != b'-' {
                    return false;
                }
            }
            _ => unreachable!(),
        }
    }
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Document;

    fn doc_with_header(header_extra: &[&str]) -> Document {
        let mut text = String::from(";;; CLM/3.0 — test\n;;; test.clm\n");
        for line in header_extra {
            text.push_str(";;; ");
            text.push_str(line);
            text.push('\n');
        }
        text.push_str(";;; ---\n\n[STATE]\n  ;; empty\n;;\n\n;;; EOF | CLM/3.0\n");
        Document::parse(&text).expect("parse failed")
    }

    #[test]
    fn no_trim_no_errors() {
        let doc = doc_with_header(&[]);
        let report = validate_v3(&doc);
        assert!(report.errors.is_empty(), "errors: {:?}", report.errors);
    }

    #[test]
    fn trim_aggressive_without_archive_path_is_error() {
        let doc = doc_with_header(&["trim.mode: aggressive", "archive.mode: sibling"]);
        let report = validate_v3(&doc);
        assert!(report
            .errors
            .iter()
            .any(|e| matches!(e, ValidationError::MissingArchivePathUnderTrim)));
    }

    #[test]
    fn trim_aggressive_with_inline_archive_is_error() {
        let doc = doc_with_header(&[
            "trim.mode: aggressive",
            "archive.mode: inline",
            "archive.path: foo.archive.clm",
        ]);
        let report = validate_v3(&doc);
        assert!(report
            .errors
            .iter()
            .any(|e| matches!(e, ValidationError::AggressiveTrimWithInlineArchive)));
    }

    #[test]
    fn trim_aggressive_archive_mode_unspecified_warns() {
        let doc = doc_with_header(&["trim.mode: aggressive", "archive.path: foo.archive.clm"]);
        let report = validate_v3(&doc);
        assert!(report
            .warnings
            .iter()
            .any(|w| matches!(w, ValidationWarning::ArchiveModeUnspecifiedUnderTrim)));
    }

    #[test]
    fn duplicate_trim_config_key_is_error() {
        let doc = doc_with_header(&[
            "trim.mode: aggressive",
            "archive.mode: sibling",
            "archive.path: foo.archive.clm",
            "trim.config: roll_call=10, roll_call=12",
        ]);
        let report = validate_v3(&doc);
        assert!(report
            .errors
            .iter()
            .any(|e| matches!(e, ValidationError::DuplicateTrimConfigKey { key } if key == "roll_call")));
    }

    #[test]
    fn unknown_trim_config_key_warns() {
        let doc = doc_with_header(&[
            "trim.mode: aggressive",
            "archive.mode: sibling",
            "archive.path: foo.archive.clm",
            "trim.config: roll_call=10, mystery=99",
        ]);
        let report = validate_v3(&doc);
        assert!(report
            .warnings
            .iter()
            .any(|w| matches!(w, ValidationWarning::UnknownTrimConfigKey { key } if key == "mystery")));
    }

    #[test]
    fn unknown_trim_mode_is_error() {
        let doc = doc_with_header(&["trim.mode: yolo"]);
        let report = validate_v3(&doc);
        assert!(report
            .errors
            .iter()
            .any(|e| matches!(e, ValidationError::UnknownTrimMode { raw } if raw == "yolo")));
    }

    #[test]
    fn missing_sentinel_when_overflowing_is_error() {
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[ROLL.CALL]\n");
        text.push_str("  CLd.Snt4.6 · 2026-04-07 · \"a\"\n");
        text.push_str("  CLd.Ops4.6 · 2026-04-07 · \"b\"\n");
        text.push_str("  CLd.Snt4.5 · 2026-04-24 · \"c\"\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(report
            .errors
            .iter()
            .any(|e| matches!(e, ValidationError::SentinelMissingInTrimmedSection { section, .. } if section == "ROLL.CALL")));
    }

    #[test]
    fn sentinel_present_when_overflowing_is_ok() {
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[ROLL.CALL]\n");
        text.push_str("  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n");
        text.push_str("  CLd.Ops4.6 · 2026-04-07 · \"b\"\n");
        text.push_str("  CLd.Snt4.5 · 2026-04-24 · \"c\"\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            !report.errors.iter().any(|e| matches!(e, ValidationError::SentinelMissingInTrimmedSection { .. })),
            "errors: {:?}",
            report.errors
        );
    }

    #[test]
    fn invalid_delta_session_id_is_error() {
        let mut text = String::from(";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n");
        text.push_str("[DELTA.UPPER]\n  body\n;;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(report
            .errors
            .iter()
            .any(|e| matches!(e, ValidationError::InvalidDeltaSessionId { session_id, .. } if session_id == "UPPER")));
    }

    #[test]
    fn duplicate_delta_session_id_warns() {
        let mut text = String::from(";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n");
        text.push_str("[DELTA.session-1]\n  body\n;;\n\n");
        text.push_str("[DELTA.session-1]\n  body\n;;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(report
            .warnings
            .iter()
            .any(|w| matches!(w, ValidationWarning::DuplicateDeltaSessionId { session_id } if session_id == "session-1")));
    }

    #[test]
    fn full_v3_spec_parses_and_validates() {
        let text = include_str!("../../SPEC.clm");
        let doc = Document::parse(text).expect("parse failed");
        let report = validate_v3(&doc);
        // The spec is in state.B (declared trim, no overflow yet) — should validate clean.
        assert!(
            report.errors.is_empty(),
            "SPEC.clm validation errors: {:?}",
            report.errors
        );
    }

    #[test]
    fn missing_decisions_live_sentinel_is_error() {
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=10, dream_log=3, decisions_live=2\n;;; ---\n\n",
        );
        text.push_str("[STATE]\n");
        text.push_str("  decisions.live (last 2 of 5 archived):\n");
        text.push_str("    d3: keep me [session 30]\n");
        text.push_str("    d4: keep me too [session 40]\n");
        text.push_str("    d5: keep me also [session 50]\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            report.errors.iter().any(|e| matches!(
                e,
                ValidationError::SentinelMissingInTrimmedSection { section, .. }
                    if section == "STATE.decisions.live"
            )),
            "expected decisions.live sentinel error; got: {:?}",
            report.errors
        );
    }

    #[test]
    fn decisions_live_sentinel_present_is_ok() {
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=10, dream_log=3, decisions_live=2\n;;; ---\n\n",
        );
        text.push_str("[STATE]\n");
        text.push_str("  decisions.live (last 2 of 5 archived):\n");
        text.push_str("    ;; (oldest 3 live decisions offloaded to [DECISIONS.ARCHIVE] in sibling)\n");
        text.push_str("    d4: keep me [session 40]\n");
        text.push_str("    d5: keep me too [session 50]\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            !report.errors.iter().any(|e| matches!(
                e,
                ValidationError::SentinelMissingInTrimmedSection { section, .. }
                    if section == "STATE.decisions.live"
            )),
            "did not expect decisions.live sentinel error; got: {:?}",
            report.errors
        );
    }

    #[test]
    fn delta_archive_section_is_not_session_id_validated() {
        // [DELTA.ARCHIVE] is a structural section in inline-archive mode; must not be
        // mistaken for a session-id with an invalid (uppercase) form.
        let mut text = String::from(";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n");
        text.push_str("[STATE]\n  ;; empty\n;;\n\n");
        text.push_str("[DELTA.ARCHIVE]\n");
        text.push_str("  [DELTA.session-1]\n");
        text.push_str("    ;; older delta archived inline\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            !report.errors.iter().any(|e| matches!(
                e,
                ValidationError::InvalidDeltaSessionId { session_id, .. }
                    if session_id == "ARCHIVE"
            )),
            "DELTA.ARCHIVE incorrectly flagged as invalid session-id: {:?}",
            report.errors
        );
    }

    #[test]
    fn dreamed_inline_archive_artifact_validates() {
        // Regression: experiments/v3/dreamed.clm uses inline archive with [DELTA.ARCHIVE]
        // and trim.mode: none. The validator must accept it.
        let text = include_str!("../../experiments/v3/dreamed.clm");
        let doc = Document::parse(text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            report.errors.is_empty(),
            "dreamed.clm validation errors: {:?}",
            report.errors
        );
    }

    #[test]
    fn dreamed_sibling_50_trim_artifact_validates() {
        // Regression: the bench's actual aggressive-trim artifact must validate clean.
        // (Codex round-2 caught that an earlier version had archive.file: instead of
        // archive.path: and a misplaced decisions.live sentinel; both fixed.)
        let text = include_str!("../../experiments/v3/dreamed-sibling-50-trim.clm");
        let doc = Document::parse(text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            report.errors.is_empty(),
            "dreamed-sibling-50-trim.clm validation errors: {:?}",
            report.errors
        );
    }

    #[test]
    fn dreamed_sibling_200_trim_artifact_validates() {
        let text = include_str!("../../experiments/v3/dreamed-sibling-200-trim.clm");
        let doc = Document::parse(text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            report.errors.is_empty(),
            "dreamed-sibling-200-trim.clm validation errors: {:?}",
            report.errors
        );
    }

    #[test]
    fn malformed_roll_call_entry_quarantined() {
        // A line that doesn't contain the `·` separator should be flagged as malformed
        // and NOT counted toward the trim threshold (per spec malformed.entry.behavior).
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[ROLL.CALL]\n");
        text.push_str("  CLd.Snt4.6 · 2026-04-07 · \"a\"\n");
        text.push_str("  CLd.Ops4.6 · 2026-04-07 · \"b\"\n");
        text.push_str("  this is a junk line that doesn't match the format\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        // The two valid entries equal the keep_last threshold (2); the malformed line is
        // quarantined; therefore no SentinelMissingInTrimmedSection error should be emitted.
        assert!(
            !report.errors.iter().any(|e| matches!(
                e,
                ValidationError::SentinelMissingInTrimmedSection { section, .. } if section == "ROLL.CALL"
            )),
            "malformed line should not trigger sentinel error; got: {:?}",
            report.errors
        );
        assert!(
            report.warnings.iter().any(|w| matches!(
                w,
                ValidationWarning::MalformedEntry { section, .. } if section == "ROLL.CALL"
            )),
            "malformed line should produce MalformedEntry warning; got: {:?}",
            report.warnings
        );
    }

    #[test]
    fn filesystem_check_state_b_missing_archive_warns() {
        // Build a state.B doc (no overflow → no sentinel) referencing a nonexistent archive.
        // Should produce a WARNING (state.B permits missing archive), not an error.
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[STATE]\n  ;; empty\n;;\n\n");
        text.push_str("[ROLL.CALL]\n  CLd.Snt4.6 · 2026-04-07 · \"only one entry, no overflow\"\n;;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3_with_filesystem(&doc, std::path::Path::new("/tmp"));
        assert!(report.errors.is_empty(), "state.B with missing archive should be warning, not error: {:?}", report.errors);
        assert!(
            report.warnings.iter().any(|w| matches!(
                w,
                ValidationWarning::ArchiveFileNotYetCreatedInStateB { .. }
            )),
            "expected ArchiveFileNotYetCreatedInStateB warning; got: {:?}",
            report.warnings
        );
    }

    #[test]
    fn parser_permissive_validator_strict_for_delta_session_id() {
        // Per Codex round-5 P2: parser must accept DELTA.<anything-identifier-shaped>
        // so the validator can surface InvalidDeltaSessionId, instead of dying with
        // UnexpectedTopLevelLine at parse time.
        let mut text = String::from(";;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n");
        text.push_str("[STATE]\n  ;; empty\n;;\n\n");
        text.push_str("[DELTA.session-X]\n  ;; X is uppercase, malformed session-id\n;;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parser should accept DELTA.<suffix>; let validator decide");
        let report = validate_v3(&doc);
        assert!(
            report.errors.iter().any(|e| matches!(
                e,
                ValidationError::InvalidDeltaSessionId { session_id, .. } if session_id == "session-X"
            )),
            "expected InvalidDeltaSessionId for session-X; got: {:?}",
            report.errors
        );
    }

    #[test]
    fn declared_offload_marks_state_c_for_filesystem_check() {
        // Per Codex round-5 P2: a doc with `(last X of Y archived)` header but missing
        // sentinel is still state.C — the filesystem check should ERROR (not warn) when
        // the archive file is absent.
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[STATE]\n");
        text.push_str("  decisions.live (last 8 of 23 archived):\n");
        for i in 16..=23 {
            text.push_str(&format!("    d{i}: keep me [session {}]\n", i * 2));
        }
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3_with_filesystem(&doc, std::path::Path::new("/tmp"));
        // Should have BOTH the missing-sentinel error AND the missing-archive-file error
        // (state.C). The filesystem variant must not downgrade to state.B warning.
        assert!(
            report.errors.iter().any(|e| matches!(e, ValidationError::ArchiveFileMissingInStateC { .. })),
            "expected ArchiveFileMissingInStateC (declared offload → state.C); got: {:?}",
            report.errors
        );
    }

    #[test]
    fn archive_path_pointing_to_directory_errors_in_state_c() {
        // Per Codex round-5 P3: .exists() returns true for directories; archive.path must
        // resolve to a *file*. State.C with archive.path pointing at a dir should error.
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: .\n;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[ROLL.CALL]\n");
        text.push_str("  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n");
        text.push_str("  CLd.Ops4.6 · 2026-04-07 · \"b\"\n");
        text.push_str("  CLd.Snt4.5 · 2026-04-24 · \"c\"\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3_with_filesystem(&doc, std::path::Path::new("/tmp"));
        assert!(
            report.errors.iter().any(|e| matches!(
                e,
                ValidationError::ArchiveFileMissingInStateC { .. }
            )),
            "expected ArchiveFileMissingInStateC when archive.path points to a directory; got: {:?}",
            report.errors
        );
    }

    #[test]
    fn last_x_of_y_archived_form_triggers_sentinel_check() {
        // Per Codex round-4 P1: parse_decisions_live_header_paren must accept the
        // SPEC's `(last X of Y archived)` form. Without "last" support, an
        // already-trimmed state.C doc with exactly keep_last visible entries
        // bypassed the sentinel check entirely.
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[STATE]\n");
        text.push_str("  decisions.live (last 8 of 23 archived):\n");
        for i in 16..=23 {
            text.push_str(&format!("    d{i}: keep me [session {}]\n", i * 2));
        }
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        // 8 visible entries, keep_last=8 → no overflow. But header declares Y=23 > X=8,
        // so the validator MUST detect the offload and require a sentinel.
        assert!(
            report.errors.iter().any(|e| matches!(
                e,
                ValidationError::SentinelMissingInTrimmedSection { section, .. }
                    if section == "STATE.decisions.live"
            )),
            "expected sentinel error from `last X of Y archived` form; got: {:?}",
            report.errors
        );
    }

    #[test]
    fn sentinel_after_kept_entries_is_not_accepted() {
        // Per Codex round-4 P2: has_sentinel must require placement BEFORE entries.
        // A sentinel comment AFTER the kept entries should NOT count as valid placement.
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[ROLL.CALL]\n");
        text.push_str("  CLd.Ops4.6 · 2026-04-07 · \"b\"\n");
        text.push_str("  CLd.Snt4.5 · 2026-04-24 · \"c\"\n");
        text.push_str("  CLd.Ops4.7 · 2026-04-25 · \"d\"\n");
        // Sentinel placed AFTER the kept entries (wrong position):
        text.push_str("  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            report.errors.iter().any(|e| matches!(
                e,
                ValidationError::SentinelMissingInTrimmedSection { section, .. } if section == "ROLL.CALL"
            )),
            "expected sentinel error when sentinel placed AFTER entries; got: {:?}",
            report.errors
        );
    }

    #[test]
    fn archive_section_entries_are_validated() {
        // Per Codex round-4 P1: sibling archive files don't carry trim.mode header,
        // but [ROLL.CALL.ARCHIVE], [DREAM.LOG.ARCHIVE], [DECISIONS.ARCHIVE] in them MUST
        // still validate per-line shape.
        let mut text = String::from(";;; CLM/3.0 — archive sibling\n;;; t.archive.clm\n;;; ---\n\n");
        text.push_str("[ROLL.CALL.ARCHIVE]\n");
        text.push_str("  CLd.Snt4.6 · 2026-04-07 · \"valid line\"\n");
        text.push_str("  this is a malformed archive line with no separator\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | archive\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3(&doc);
        assert!(
            report.warnings.iter().any(|w| matches!(
                w,
                ValidationWarning::MalformedEntry { section, .. } if section == "ROLL.CALL.ARCHIVE"
            )),
            "expected MalformedEntry warning for malformed line in [ROLL.CALL.ARCHIVE]; got: {:?}",
            report.warnings
        );
    }

    #[test]
    fn filesystem_check_state_c_missing_archive_errors() {
        // Build a state.C doc (sentinel present in [ROLL.CALL]) referencing a nonexistent archive.
        // Should ERROR per spec (state.C requires the archive file).
        let mut text = String::from(
            ";;; CLM/3.0 — test\n;;; test.clm\n;;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n",
        );
        text.push_str("[ROLL.CALL]\n");
        text.push_str("  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n");
        text.push_str("  CLd.Ops4.6 · 2026-04-07 · \"b\"\n");
        text.push_str("  CLd.Snt4.5 · 2026-04-24 · \"c\"\n");
        text.push_str(";;\n\n");
        text.push_str(";;; EOF | CLM/3.0\n");
        let doc = Document::parse(&text).expect("parse failed");
        let report = validate_v3_with_filesystem(&doc, std::path::Path::new("/tmp"));
        assert!(
            report.errors.iter().any(|e| matches!(
                e,
                ValidationError::ArchiveFileMissingInStateC { .. }
            )),
            "expected ArchiveFileMissingInStateC error; got: {:?}",
            report.errors
        );
    }
}
