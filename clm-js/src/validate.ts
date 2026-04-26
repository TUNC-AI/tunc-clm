/**
 * v3.0 trim-aware validation per `SPEC.clm` `validation.posture.v3.0`.
 *
 * Mirrors `clm-rs/src/validate.rs` and `clm-py/src/clm/validate.py`. A v3.0
 * document MAY declare in its header:
 *
 *     ;;; trim.mode: aggressive
 *     ;;; trim.config: roll_call=10, dream_log=3, decisions_live=8
 *     ;;; archive.mode: sibling
 *     ;;; archive.path: <relative-or-absolute-path>
 *
 * Two entry points:
 *   - `validateV3(doc)` — structural validation, no filesystem access.
 *   - `validateV3WithFilesystem(doc, baseDir)` — additionally resolves and
 *     validates the sibling archive file (cross-doc sentinel check,
 *     archive-shape verification, chained archive validation).
 */
import { existsSync, statSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { Document, ParseError } from "./document.js";

export type TrimMode = "none" | "aggressive";
export type ArchiveMode = "sibling" | "inline";

export const DEFAULT_ROLL_CALL_KEEP = 10;
export const DEFAULT_DREAM_LOG_KEEP = 3;
export const DEFAULT_DECISIONS_LIVE_KEEP = 8;

const TRIM_CONFIG_KEYS = ["roll_call", "dream_log", "decisions_live"] as const;

export interface TrimConfig {
  roll_call: number;
  dream_log: number;
  decisions_live: number;
}

export interface HeaderDeclarations {
  trimMode?: TrimMode;
  trimConfig?: TrimConfig;
  archiveMode?: ArchiveMode;
  archivePath?: string;
  archivePathNamingConvention?: string;
}

export type ValidationErrorKind =
  | "missing_archive_path_under_trim"
  | "aggressive_trim_with_inline_archive"
  | "duplicate_trim_config_key"
  | "missing_trim_config_value"
  | "invalid_trim_config_value"
  | "sentinel_missing_in_trimmed_section"
  | "unknown_trim_mode"
  | "unknown_archive_mode"
  | "invalid_delta_session_id"
  | "archive_file_missing_in_state_c"
  | "archive_file_wrong_shape_in_state_c";

export type ValidationWarningKind =
  | "unknown_trim_config_key"
  | "duplicate_delta_session_id"
  | "archive_mode_unspecified_under_trim"
  | "malformed_entry"
  | "archive_file_not_yet_created_in_state_b";

export interface ValidationError {
  kind: ValidationErrorKind;
  message: string;
  details?: Record<string, unknown>;
}

export interface ValidationWarning {
  kind: ValidationWarningKind;
  message: string;
  details?: Record<string, unknown>;
}

export interface ValidationReport {
  header: HeaderDeclarations;
  errors: ValidationError[];
  warnings: ValidationWarning[];
  isValid: () => boolean;
}

function makeReport(): ValidationReport {
  const errors: ValidationError[] = [];
  const warnings: ValidationWarning[] = [];
  return {
    header: {},
    errors,
    warnings,
    isValid: () => errors.length === 0,
  };
}

// ---- public API ----

export function validateV3(doc: Document): ValidationReport {
  const report = makeReport();
  report.header = parseHeaderDeclarations(doc, report.errors, report.warnings);
  checkTrimModeConsistency(report.header, report.errors, report.warnings);
  checkDeltaSessionIds(doc, report.errors, report.warnings);

  if (report.header.trimMode === "aggressive") {
    const trim = report.header.trimConfig ?? defaultTrimConfig();
    checkSectionSentinels(doc, trim, report.errors, report.warnings);
  }

  // Archive-section validation runs regardless of trim.mode (sibling archive files
  // don't carry a trim.mode header). Per SPEC.clm validation.posture.v3.0 these
  // MUST be validated when present.
  checkArchiveSectionEntries(doc, report.warnings);

  return report;
}

export function validateV3WithFilesystem(doc: Document, baseDir: string): ValidationReport {
  const report = validateV3(doc);

  if (report.header.trimMode !== "aggressive") return report;
  if (!report.header.archivePath) return report;

  const resolved = join(baseDir, report.header.archivePath);
  const stateCDoc = isStateC(doc);

  // Per spec: archive must be a *file*; existsSync returns true for directories.
  let isFile = false;
  try {
    isFile = statSync(resolved).isFile();
  } catch {
    isFile = false;
  }

  if (!isFile) {
    if (stateCDoc) {
      report.errors.push({
        kind: "archive_file_missing_in_state_c",
        message: `doc is in state.C (overflow occurred — sentinel present) but archive.path resolves to ${JSON.stringify(resolved)} which does not exist`,
        details: { resolvedPath: resolved },
      });
    } else {
      report.warnings.push({
        kind: "archive_file_not_yet_created_in_state_b",
        message: `archive.path resolves to ${JSON.stringify(resolved)} which does not exist; OK for state.B (file appears at first offload)`,
        details: { resolvedPath: resolved },
      });
    }
    return report;
  }

  let archiveText: string;
  try {
    archiveText = readFileSync(resolved, "utf8");
  } catch {
    if (stateCDoc) {
      report.errors.push({
        kind: "archive_file_missing_in_state_c",
        message: `archive.path file at ${JSON.stringify(resolved)} could not be read`,
        details: { resolvedPath: resolved },
      });
    }
    return report;
  }

  let archiveDoc: Document;
  try {
    archiveDoc = Document.parse(archiveText);
  } catch (err) {
    if (stateCDoc) {
      report.errors.push({
        kind: "archive_file_wrong_shape_in_state_c",
        message: `archive.path resolves to ${JSON.stringify(resolved)} but the file does not parse as a CLM document; state.C requires a real trim archive`,
        details: { resolvedPath: resolved, parseError: (err as ParseError).message },
      });
    }
    return report;
  }

  // Cross-doc sentinel check: if the archive contains <NAME>.ARCHIVE, the live
  // doc's <NAME> MUST carry the sentinel.
  crossCheckLiveAgainstArchive(doc, archiveDoc, report.errors);

  // Chain validateV3 on archive_doc; propagate diagnostics.
  const archiveReport = validateV3(archiveDoc);
  for (const w of archiveReport.warnings) report.warnings.push(w);
  for (const e of archiveReport.errors) report.errors.push(e);

  if (stateCDoc) {
    const hasTrimArchive = archiveDoc.sections.some(({ section }) =>
      ["ROLL.CALL.ARCHIVE", "DREAM.LOG.ARCHIVE", "DECISIONS.ARCHIVE"].includes(section.name)
    );
    if (!hasTrimArchive) {
      report.errors.push({
        kind: "archive_file_wrong_shape_in_state_c",
        message: `archive.path resolves to ${JSON.stringify(resolved)} but the file contains no trim ARCHIVE sections ([ROLL.CALL.ARCHIVE] / [DREAM.LOG.ARCHIVE] / [DECISIONS.ARCHIVE]); state.C requires a real trim archive`,
        details: { resolvedPath: resolved },
      });
    }
  }

  return report;
}

function defaultTrimConfig(): TrimConfig {
  return {
    roll_call: DEFAULT_ROLL_CALL_KEEP,
    dream_log: DEFAULT_DREAM_LOG_KEEP,
    decisions_live: DEFAULT_DECISIONS_LIVE_KEEP,
  };
}

// ---- header parsing ----

function parseHeaderDeclarations(
  doc: Document,
  errors: ValidationError[],
  warnings: ValidationWarning[]
): HeaderDeclarations {
  const decls: HeaderDeclarations = {};
  for (const raw of doc.header) {
    if (!raw.startsWith(";;;")) continue;
    const content = raw.slice(3);
    for (const clause of content.split("|")) {
      const trimmed = clause.trim();
      if (!trimmed || trimmed === "---") continue;
      const colon = trimmed.indexOf(":");
      if (colon < 0) continue;
      const key = trimmed.slice(0, colon).trim();
      const value = trimmed.slice(colon + 1).trim();
      switch (key) {
        case "trim.mode":
          if (value === "none" || value === "aggressive") {
            decls.trimMode = value;
          } else {
            errors.push({
              kind: "unknown_trim_mode",
              message: `unknown trim.mode value: ${JSON.stringify(value)} (expected: none, aggressive)`,
              details: { raw: value },
            });
          }
          break;
        case "trim.config":
          decls.trimConfig = parseTrimConfig(value, errors, warnings);
          break;
        case "archive.mode":
          if (value === "sibling" || value === "inline") {
            decls.archiveMode = value;
          } else {
            errors.push({
              kind: "unknown_archive_mode",
              message: `unknown archive.mode value: ${JSON.stringify(value)} (expected: sibling, inline)`,
              details: { raw: value },
            });
          }
          break;
        case "archive.path":
          decls.archivePath = value;
          break;
        case "archive.path.naming.convention":
          decls.archivePathNamingConvention = value;
          break;
      }
    }
  }
  return decls;
}

function parseTrimConfig(
  value: string,
  errors: ValidationError[],
  warnings: ValidationWarning[]
): TrimConfig {
  const cfg = defaultTrimConfig();
  const seen = new Set<string>();
  for (const entry of value.split(",")) {
    const e = entry.trim();
    if (!e) continue;
    const eq = e.indexOf("=");
    if (eq < 0) {
      errors.push({
        kind: "missing_trim_config_value",
        message: `trim.config key ${JSON.stringify(e)} has no value`,
        details: { key: e },
      });
      continue;
    }
    const k = e.slice(0, eq).trim();
    const v = e.slice(eq + 1).trim();
    if (seen.has(k)) {
      errors.push({
        kind: "duplicate_trim_config_key",
        message: `trim.config has duplicate key: ${JSON.stringify(k)}`,
        details: { key: k },
      });
      continue;
    }
    seen.add(k);
    if (!v) {
      errors.push({
        kind: "missing_trim_config_value",
        message: `trim.config key ${JSON.stringify(k)} has no value`,
        details: { key: k },
      });
      continue;
    }
    // Strict integer check: reject "3.0", "3e0", "0x10", etc. that Number() would
    // happily coerce. Rust's usize::parse and Python's int() both reject these.
    if (!/^\d+$/.test(v)) {
      errors.push({
        kind: "invalid_trim_config_value",
        message: `trim.config[${JSON.stringify(k)}] = ${JSON.stringify(v)} is not a non-negative integer`,
        details: { key: k, raw: v },
      });
      continue;
    }
    const n = parseInt(v, 10);
    if (k === "roll_call") cfg.roll_call = n;
    else if (k === "dream_log") cfg.dream_log = n;
    else if (k === "decisions_live") cfg.decisions_live = n;
    else {
      warnings.push({
        kind: "unknown_trim_config_key",
        message: `unknown trim.config key ${JSON.stringify(k)} (recognized: ${TRIM_CONFIG_KEYS.join(", ")}); preserved but ignored`,
        details: { key: k },
      });
    }
  }
  return cfg;
}

// ---- section / entry checks ----

function checkTrimModeConsistency(
  decls: HeaderDeclarations,
  errors: ValidationError[],
  warnings: ValidationWarning[]
): void {
  const mode = decls.trimMode ?? "none";
  if (mode === "none") return;
  if (!decls.archivePath) {
    errors.push({
      kind: "missing_archive_path_under_trim",
      message: "trim.mode is set but ';;; archive.path: ...' header is missing (required when trim.mode != none)",
    });
  }
  if (decls.archiveMode === "inline") {
    errors.push({
      kind: "aggressive_trim_with_inline_archive",
      message: "trim.mode: aggressive cannot be combined with archive.mode: inline (unsupported per spec)",
    });
  } else if (decls.archiveMode === undefined) {
    warnings.push({
      kind: "archive_mode_unspecified_under_trim",
      message: "trim.mode is set but archive.mode is not declared; defaulting to sibling",
    });
  }
}

function checkDeltaSessionIds(
  doc: Document,
  errors: ValidationError[],
  warnings: ValidationWarning[]
): void {
  const seen = new Map<string, number>();
  for (const { section } of doc.sections) {
    if (!section.name.startsWith("DELTA.")) continue;
    const sessionId = section.name.slice("DELTA.".length);
    if (sessionId === "ARCHIVE") continue;
    if (!isValidSessionId(sessionId)) {
      errors.push({
        kind: "invalid_delta_session_id",
        message: `section [${section.name}]: session-id ${JSON.stringify(sessionId)} does not match \`[a-z0-9][a-z0-9._-]*\``,
        details: { sectionName: section.name, sessionId },
      });
      continue;
    }
    const count = (seen.get(sessionId) ?? 0) + 1;
    seen.set(sessionId, count);
    if (count === 2) {
      warnings.push({
        kind: "duplicate_delta_session_id",
        message: `duplicate [DELTA.session-id] ${JSON.stringify(sessionId)}; line order remains authoritative`,
        details: { sessionId },
      });
    }
  }
}

function checkSectionSentinels(
  doc: Document,
  trim: TrimConfig,
  errors: ValidationError[],
  warnings: ValidationWarning[]
): void {
  for (const { section } of doc.sections) {
    const name = section.name;
    if (name === "ROLL.CALL") {
      const entries = countValidEntries(section.body, "ROLL.CALL", warnings);
      if (entries > trim.roll_call && !hasSentinel(section.body, "ROLL.CALL")) {
        errors.push(sentinelMissing(name, entries, trim.roll_call));
      }
    } else if (name === "DREAM.LOG") {
      const entries = countValidEntries(section.body, "DREAM.LOG", warnings);
      if (entries > trim.dream_log && !hasSentinel(section.body, "DREAM.LOG")) {
        errors.push(sentinelMissing(name, entries, trim.dream_log));
      }
    } else if (name === "STATE") {
      const stats = decisionsLiveStats(section.body);
      // Surface any malformed (quarantined) lines as warnings — same shape as
      // the [ROLL.CALL] / [DREAM.LOG] handling. Already excluded from
      // `visibleEntries` per spec.
      for (const content of stats.malformed) {
        warnings.push({
          kind: "malformed_entry",
          message: `[STATE.decisions.live] entry does not match expected shape: ${JSON.stringify(content)} (quarantined; not counted for trim)`,
          details: { section: "STATE.decisions.live", content },
        });
      }
      const visibleOverflow = stats.visibleEntries > trim.decisions_live;
      const declaredOffload = (stats.declaredOffloadCount ?? 0) > 0;
      if ((visibleOverflow || declaredOffload) && !stats.sentinelPresent) {
        errors.push(sentinelMissing("STATE.decisions.live", stats.visibleEntries, trim.decisions_live));
      }
    }
  }
}

function checkArchiveSectionEntries(doc: Document, warnings: ValidationWarning[]): void {
  for (const { section } of doc.sections) {
    if (section.name === "ROLL.CALL.ARCHIVE") {
      countValidEntries(section.body, "ROLL.CALL.ARCHIVE", warnings);
    } else if (section.name === "DREAM.LOG.ARCHIVE") {
      countValidEntries(section.body, "DREAM.LOG.ARCHIVE", warnings);
    } else if (section.name === "DECISIONS.ARCHIVE") {
      for (const line of section.body) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith(";;")) continue;
        if (!looksLikeDecisionEntry(trimmed)) {
          warnings.push({
            kind: "malformed_entry",
            message: `[DECISIONS.ARCHIVE] entry does not match expected shape: ${JSON.stringify(trimmed)} (quarantined; not counted for trim)`,
            details: { section: "DECISIONS.ARCHIVE", content: trimmed },
          });
        }
      }
    }
  }
}

function crossCheckLiveAgainstArchive(
  live: Document,
  archive: Document,
  errors: ValidationError[]
): void {
  const archiveNames = new Set(archive.sections.map(({ section }) => section.name));

  const liveBody = (name: string): string[] | undefined => {
    return live.sections.find((e) => e.section.name === name)?.section.body;
  };

  if (archiveNames.has("ROLL.CALL.ARCHIVE")) {
    const body = liveBody("ROLL.CALL");
    if (body && !hasSentinel(body, "ROLL.CALL")) {
      const entries = body.filter((l) => l.trim() && !l.trim().startsWith(";;")).length;
      errors.push(sentinelMissing("ROLL.CALL", entries, 0));
    }
  }
  if (archiveNames.has("DREAM.LOG.ARCHIVE")) {
    const body = liveBody("DREAM.LOG");
    if (body && !hasSentinel(body, "DREAM.LOG")) {
      const entries = body.filter((l) => l.trim() && !l.trim().startsWith(";;")).length;
      errors.push(sentinelMissing("DREAM.LOG", entries, 0));
    }
  }

  // DECISIONS.ARCHIVE: symmetric to ROLL.CALL.ARCHIVE / DREAM.LOG.ARCHIVE.
  // The intra-doc check in `checkSectionSentinels` only fires on
  // `visibleOverflow || declaredOffload`, so a state.C doc with bare
  // `decisions.live:` (no `(X of Y archived)`), exactly keep_last visible
  // decisions, and no sentinel — but with a populated sibling
  // [DECISIONS.ARCHIVE] proving offload — would otherwise pass. The archive's
  // existence is stronger evidence than the header parens.
  // (Codex PR-13 round-8 P2-A; resolved in 0.2.1.)
  if (archiveNames.has("DECISIONS.ARCHIVE")) {
    const stateBody = liveBody("STATE");
    if (stateBody) {
      const stats = decisionsLiveStats(stateBody);
      // Guard: only fire if a decisions.live: sub-block actually exists in the
      // live doc. Otherwise (e.g. a [STATE] that only carries progress: /
      // next_steps:, or no [STATE] at all), we'd emit a ghost sentinel-missing
      // error against a section that isn't there — a real false positive
      // caught in code review.
      if (stats.blockFound && !stats.sentinelPresent) {
        errors.push(sentinelMissing("STATE.decisions.live", stats.visibleEntries, 0));
      }
    }
  }
}

// ---- helpers ----

function isStateC(doc: Document): boolean {
  for (const { section } of doc.sections) {
    if (section.name === "ROLL.CALL" && hasSentinel(section.body, "ROLL.CALL")) return true;
    if (section.name === "DREAM.LOG" && hasSentinel(section.body, "DREAM.LOG")) return true;
    if (section.name === "STATE") {
      const stats = decisionsLiveStats(section.body);
      if (stats.sentinelPresent || (stats.declaredOffloadCount ?? 0) > 0) return true;
    }
  }
  return false;
}

function countValidEntries(
  body: string[],
  sectionName: string,
  warnings: ValidationWarning[]
): number {
  let count = 0;
  for (const line of body) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(";;")) continue;
    let wellFormed = true;
    if (sectionName === "ROLL.CALL" || sectionName === "ROLL.CALL.ARCHIVE") {
      wellFormed = wellFormedRollCallLine(trimmed);
    } else if (sectionName === "DREAM.LOG" || sectionName === "DREAM.LOG.ARCHIVE") {
      wellFormed = wellFormedDreamLogLine(trimmed);
    }
    if (wellFormed) {
      count++;
    } else {
      warnings.push({
        kind: "malformed_entry",
        message: `[${sectionName}] entry does not match expected shape: ${JSON.stringify(trimmed)} (quarantined; not counted for trim)`,
        details: { section: sectionName, content: trimmed },
      });
    }
  }
  return count;
}

function hasSentinel(body: string[], sectionName: string): boolean {
  const archiveMarker = `${sectionName}.ARCHIVE`;
  let seenEntry = false;
  for (const line of body) {
    const t = line.trim();
    if (!t) continue;
    if (t.startsWith(";;")) {
      if (!seenEntry && t.includes(archiveMarker) && t.includes("offloaded")) return true;
      continue;
    }
    seenEntry = true;
  }
  return false;
}

function sentinelMissing(section: string, entries: number, keep: number): ValidationError {
  // The sub-block `STATE.decisions.live` archives to `[DECISIONS.ARCHIVE]`,
  // not `[STATE.decisions.live.ARCHIVE]`. Naive `${section}.ARCHIVE` produced
  // the wrong example in the hint. Caught in code review.
  const archiveMarker =
    section === "STATE.decisions.live" ? "DECISIONS.ARCHIVE" : `${section}.ARCHIVE`;
  return {
    kind: "sentinel_missing_in_trimmed_section",
    message: `section [${section}] has ${entries} entries (keep_last = ${keep}); truncation sentinel is required before kept entries (e.g. \`;; (oldest N entries offloaded to [${archiveMarker}] in sibling)\`)`,
    details: { section, entries, keep },
  };
}

interface DecisionsLiveStats {
  visibleEntries: number;
  sentinelPresent: boolean;
  declaredOffloadCount?: number;
  /**
   * Lines in the decisions.live block that don't match the `dN: ...` shape.
   * Per SPEC.clm `malformed.entry.behavior`: QUARANTINE + WARNING — they are
   * excluded from `visibleEntries` so a single broken line cannot push the
   * block over `trim.config.decisions_live` and trigger a false sentinel-missing
   * error. Callers (specifically `checkSectionSentinels`) emit MalformedEntry
   * warnings for each.
   */
  malformed: string[];
  /**
   * Whether a `decisions.live:` header was found in the [STATE] body. Used by
   * the P2-A cross-doc check to avoid emitting a false sentinel-missing error
   * against a sub-block that doesn't exist (e.g. a [STATE] that only carries
   * `progress:` / `next_steps:` but whose sibling archive contains a stale
   * `[DECISIONS.ARCHIVE]` from a prior phase).
   */
  blockFound: boolean;
}

function decisionsLiveStats(stateBody: string[]): DecisionsLiveStats {
  const stats: DecisionsLiveStats = {
    visibleEntries: 0,
    sentinelPresent: false,
    malformed: [],
    blockFound: false,
  };
  let inBlock = false;
  let blockIndent = 0;
  let seenEntry = false;

  for (const raw of stateBody) {
    const leading = raw.length - raw.replace(/^[ ]+/, "").length;
    const trimmed = raw.replace(/^[ ]+/, "");

    if (!inBlock) {
      if (trimmed.startsWith("decisions.live")) {
        const next = trimmed.charAt("decisions.live".length);
        if (next === ":" || next === "(" || next === " ") {
          inBlock = true;
          blockIndent = leading;
          stats.blockFound = true;
          stats.declaredOffloadCount =
            parseDecisionsLiveHeaderParen(trimmed.slice("decisions.live".length)) ?? undefined;
        }
      }
      continue;
    }

    if (!trimmed.trim()) continue;
    if (leading <= blockIndent) break;

    if (trimmed.startsWith(";;")) {
      if (!seenEntry && trimmed.includes("DECISIONS.ARCHIVE") && trimmed.includes("offloaded")) {
        stats.sentinelPresent = true;
      }
      continue;
    }

    // Quarantine malformed lines (anything not `dN: ...`). Per spec they are
    // preserved verbatim, surfaced as warnings, and excluded from the count
    // so a single broken line cannot push the block over the keep_last
    // threshold. (Codex PR-13 round-8 P2-B; resolved in 0.2.1.)
    if (!looksLikeDecisionEntry(trimmed)) {
      stats.malformed.push(trimmed);
      continue;
    }

    // Note the deliberate asymmetry with `hasSentinel`: there, ANY non-comment
    // non-blank line terminates the "before-entries" zone. Here, only
    // WELL-FORMED entries do. Spec rationale: the sentinel requirement is
    // `BEFORE the kept entries`, and quarantined malformed lines are not "kept
    // entries." So a sentinel placed after a quarantined line but before any
    // well-formed entry is still valid.
    stats.visibleEntries++;
    seenEntry = true;
  }
  return stats;
}

function parseDecisionsLiveHeaderParen(afterKey: string): number | undefined {
  const open = afterKey.indexOf("(");
  if (open < 0) return undefined;
  const rest = afterKey.slice(open);
  const close = rest.indexOf(")");
  if (close < 0) return undefined;
  const inner = rest.slice(1, close);
  const tokens = inner.split(/\s+/).filter(Boolean);
  let i = 0;
  if (tokens[i] === "last") i++;
  if (i + 2 >= tokens.length) return undefined;
  const xStr = tokens[i]!;
  const ofKw = tokens[i + 1];
  const yStr = tokens[i + 2]!;
  // Strict integer check (Rust's usize::parse / Python's int()) — reject "2.0", "3e0", etc.
  if (!/^\d+$/.test(xStr) || !/^\d+$/.test(yStr) || ofKw !== "of") return undefined;
  const x = parseInt(xStr, 10);
  const y = parseInt(yStr, 10);
  return y > x ? y - x : undefined;
}

function wellFormedRollCallLine(line: string): boolean {
  const parts = line.split("·");
  if (parts.length < 3) return false;
  const date = parts[1]!.trim();
  const note = parts.slice(2).join("·");
  return looksLikeIsoDate(date) && note.includes('"');
}

function wellFormedDreamLogLine(line: string): boolean {
  const parts = line.split("|");
  if (parts.length < 3) return false;
  const first = parts[0]!.trim();
  const dateToken = first.split(/\s+/)[0] ?? "";
  return looksLikeIsoDate(dateToken);
}

function looksLikeIsoDate(s: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(s);
}

function looksLikeDecisionEntry(line: string): boolean {
  return /^d\d/.test(line) && line.includes(":");
}

function isValidSessionId(s: string): boolean {
  return /^[a-z0-9][a-z0-9._-]*$/.test(s);
}

// Re-export existsSync for tests / consumers that want to peek at the helper.
export const _internals = { existsSync };
