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
pub fn validate_v3(doc: &Document) -> ValidationReport {
    let mut report = ValidationReport::default();
    report.header = parse_header_declarations(doc, &mut report.errors, &mut report.warnings);
    check_trim_mode_consistency(&report.header, &mut report.errors, &mut report.warnings);
    check_delta_session_ids(doc, &mut report.errors, &mut report.warnings);

    if matches!(report.header.trim_mode, Some(TrimMode::Aggressive)) {
        let trim_config = report.header.trim_config.clone().unwrap_or_default();
        check_section_sentinels(doc, &trim_config, &mut report.errors, &mut report.warnings);
    }

    report
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
    if resolved.exists() {
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
/// a truncation sentinel comment. Looks at [ROLL.CALL], [DREAM.LOG], and [STATE].decisions.live.
fn is_state_c(doc: &Document) -> bool {
    for (section, _) in &doc.sections {
        match section.name.as_str() {
            "ROLL.CALL" if has_sentinel(&section.body, "ROLL.CALL") => return true,
            "DREAM.LOG" if has_sentinel(&section.body, "DREAM.LOG") => return true,
            "STATE" => {
                let (_, sentinel) = decisions_live_stats(&section.body);
                if sentinel {
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
            "ROLL.CALL" => trimmed.contains('·'),
            "DREAM.LOG" => trimmed.contains('|'),
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
/// to its corresponding `.ARCHIVE` sibling section.
fn has_sentinel(body: &[String], section_name: &str) -> bool {
    let archive_marker = format!("{section_name}.ARCHIVE");
    body.iter().any(|line| {
        let t = line.trim();
        t.starts_with(";;") && t.contains(&archive_marker) && t.contains("offloaded")
    })
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
                // a truncation sentinel before kept entries when it overflows trim.decisions_live.
                let (entries, has_sent) = decisions_live_stats(&section.body);
                if entries > trim.decisions_live && !has_sent {
                    errors.push(ValidationError::SentinelMissingInTrimmedSection {
                        section: "STATE.decisions.live".to_string(),
                        entries,
                        keep: trim.decisions_live,
                    });
                }
            }
            _ => continue,
        }
    }
}

/// Inspect a `[STATE]` body, find the `decisions.live:` sub-block, and return
/// (entry_count, sentinel_present_before_kept_entries).
///
/// Per `SPEC.clm` `decisions.live.delimitation`:
///   - begins at a line matching `\s*decisions\.live[:( ]`
///   - contains entries indented deeper than the `decisions.live:` line itself
///   - ends at the next un-indented key OR the section close
///   - sentinel placement: BEFORE the kept entries (a comment naming `DECISIONS.ARCHIVE`)
fn decisions_live_stats(state_body: &[String]) -> (usize, bool) {
    let mut in_block = false;
    let mut block_indent: usize = 0;
    let mut entries = 0usize;
    let mut sentinel = false;
    let mut seen_entry_yet = false;

    for raw in state_body {
        let leading = raw.chars().take_while(|c| *c == ' ').count();
        let trimmed = raw.trim_start();

        if !in_block {
            // Per SPEC.clm decisions.live.delimitation: line matches `^\s*decisions\.live[:( ]`
            // i.e. the next char after "decisions.live" is one of `:`, `(`, ` `.
            if let Some(rest) = trimmed.strip_prefix("decisions.live") {
                let next = rest.chars().next();
                if matches!(next, Some(':') | Some('(') | Some(' ')) {
                    in_block = true;
                    block_indent = leading;
                }
            }
            continue;
        }

        // Inside the block. Blank lines don't terminate; un-indented keys do.
        if trimmed.is_empty() {
            continue;
        }
        if leading <= block_indent {
            // Back at or above the decisions.live key indent => block ended.
            break;
        }

        if trimmed.starts_with(";;") {
            // Comment line. If it mentions DECISIONS.ARCHIVE / offloaded and appears BEFORE any
            // entry, it's the truncation sentinel.
            if !seen_entry_yet
                && trimmed.contains("DECISIONS.ARCHIVE")
                && trimmed.contains("offloaded")
            {
                sentinel = true;
            }
            continue;
        }

        // Non-comment, non-blank => count as one decision entry.
        entries += 1;
        seen_entry_yet = true;
    }

    (entries, sentinel)
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
