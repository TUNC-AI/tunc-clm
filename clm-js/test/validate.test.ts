import { mkdtempSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { Document } from "../src/document.js";
import {
  validateV3,
  validateV3WithFilesystem,
  ValidationReport,
  ValidationErrorKind,
  ValidationWarningKind,
} from "../src/validate.js";

const REPO_ROOT = join(__dirname, "..", "..");
const read = (rel: string): string => readFileSync(join(REPO_ROOT, rel), "utf8");

function docWithHeader(extra: string[]): Document {
  let text = ";;; CLM/3.0 — test\n;;; test.clm\n";
  for (const line of extra) text += `;;; ${line}\n`;
  text += ";;; ---\n\n[STATE]\n  ;; empty\n;;\n\n;;; EOF | CLM/3.0\n";
  return Document.parse(text);
}

const hasError = (r: ValidationReport, kind: ValidationErrorKind): boolean =>
  r.errors.some((e) => e.kind === kind);
const hasWarn = (r: ValidationReport, kind: ValidationWarningKind): boolean =>
  r.warnings.some((w) => w.kind === kind);

describe("validateV3 — header / structural", () => {
  it("no trim → no errors", () => {
    expect(validateV3(docWithHeader([])).errors).toEqual([]);
  });

  it("aggressive trim without archive.path → error", () => {
    const r = validateV3(docWithHeader(["trim.mode: aggressive", "archive.mode: sibling"]));
    expect(hasError(r, "missing_archive_path_under_trim")).toBe(true);
  });

  it("aggressive trim + inline archive → error", () => {
    const r = validateV3(
      docWithHeader([
        "trim.mode: aggressive",
        "archive.mode: inline",
        "archive.path: foo.archive.clm",
      ])
    );
    expect(hasError(r, "aggressive_trim_with_inline_archive")).toBe(true);
  });

  it("aggressive trim, archive.mode unspecified → warning", () => {
    const r = validateV3(docWithHeader(["trim.mode: aggressive", "archive.path: foo.archive.clm"]));
    expect(hasWarn(r, "archive_mode_unspecified_under_trim")).toBe(true);
  });

  it("duplicate trim.config key → error", () => {
    const r = validateV3(
      docWithHeader([
        "trim.mode: aggressive",
        "archive.mode: sibling",
        "archive.path: foo.archive.clm",
        "trim.config: roll_call=10, roll_call=12",
      ])
    );
    expect(hasError(r, "duplicate_trim_config_key")).toBe(true);
  });

  it("unknown trim.config key → warning", () => {
    const r = validateV3(
      docWithHeader([
        "trim.mode: aggressive",
        "archive.mode: sibling",
        "archive.path: foo.archive.clm",
        "trim.config: roll_call=10, mystery=99",
      ])
    );
    expect(hasWarn(r, "unknown_trim_config_key")).toBe(true);
  });

  it("unknown trim.mode → error", () => {
    const r = validateV3(docWithHeader(["trim.mode: yolo"]));
    expect(hasError(r, "unknown_trim_mode")).toBe(true);
  });
});

describe("validateV3 — sentinels", () => {
  it("missing sentinel when overflowing → error", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  CLd.Snt4.6 · 2026-04-07 · "a"\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "c"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    expect(hasError(validateV3(Document.parse(text)), "sentinel_missing_in_trimmed_section")).toBe(true);
  });

  it("sentinel present (BEFORE entries) → ok", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "c"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    expect(hasError(validateV3(Document.parse(text)), "sentinel_missing_in_trimmed_section")).toBe(false);
  });

  it("sentinel placed AFTER entries → not accepted", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "c"\n` +
      `  CLd.Ops4.7 · 2026-04-25 · "d"\n` +
      `  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    expect(hasError(validateV3(Document.parse(text)), "sentinel_missing_in_trimmed_section")).toBe(true);
  });
});

describe("validateV3 — DELTA session ids", () => {
  it("invalid session id → error", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n` +
      `[DELTA.UPPER]\n  body\n;;\n\n` +
      `;;; EOF | CLM/3.0\n`;
    expect(hasError(validateV3(Document.parse(text)), "invalid_delta_session_id")).toBe(true);
  });

  it("duplicate session id → warning", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n` +
      `[DELTA.session-1]\n  body\n;;\n\n` +
      `[DELTA.session-1]\n  body\n;;\n\n` +
      `;;; EOF | CLM/3.0\n`;
    expect(hasWarn(validateV3(Document.parse(text)), "duplicate_delta_session_id")).toBe(true);
  });

  it("[DELTA.ARCHIVE] is not session-id validated", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n` +
      `[DELTA.ARCHIVE]\n  [DELTA.session-1]\n    ;; older delta archived inline\n;;\n\n` +
      `;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(
      r.errors.some(
        (e) =>
          e.kind === "invalid_delta_session_id" &&
          (e.details as { sessionId: string }).sessionId === "ARCHIVE"
      )
    ).toBe(false);
  });

  it("parser permissive, validator strict for DELTA.<id>", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n` +
      `[DELTA.session-X]\n  ;; X is uppercase, malformed\n;;\n\n` +
      `;;; EOF | CLM/3.0\n`;
    const doc = Document.parse(text); // must NOT throw
    const r = validateV3(doc);
    expect(
      r.errors.some(
        (e) =>
          e.kind === "invalid_delta_session_id" &&
          (e.details as { sessionId: string }).sessionId === "session-X"
      )
    ).toBe(true);
  });
});

describe("validateV3 — decisions.live", () => {
  it("missing sentinel for trimmed decisions.live → error", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=2\n;;; ---\n\n` +
      `[STATE]\n` +
      `  decisions.live (last 2 of 5 archived):\n` +
      `    d3: keep me [session 30]\n` +
      `    d4: keep me too [session 40]\n` +
      `    d5: keep me also [session 50]\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(
      r.errors.some(
        (e) =>
          e.kind === "sentinel_missing_in_trimmed_section" &&
          (e.details as { section: string }).section === "STATE.decisions.live"
      )
    ).toBe(true);
  });

  it("`(last X of Y archived)` form triggers sentinel check", () => {
    const entries = Array.from({ length: 8 }, (_, i) => i + 16)
      .map((i) => `    d${i}: keep me [session ${i * 2}]\n`)
      .join("");
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[STATE]\n  decisions.live (last 8 of 23 archived):\n${entries};;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(
      r.errors.some(
        (e) =>
          e.kind === "sentinel_missing_in_trimmed_section" &&
          (e.details as { section: string }).section === "STATE.decisions.live"
      )
    ).toBe(true);
  });
});

describe("validateV3 — canonical artifacts", () => {
  it("SPEC.clm validates clean", () => {
    expect(validateV3(Document.parse(read("SPEC.clm"))).errors).toEqual([]);
  });

  it("dreamed.clm (inline archive, trim.mode none) validates clean", () => {
    expect(validateV3(Document.parse(read("experiments/v3/dreamed.clm"))).errors).toEqual([]);
  });

  it("dreamed-sibling-50-trim.clm validates clean", () => {
    expect(validateV3(Document.parse(read("experiments/v3/dreamed-sibling-50-trim.clm"))).errors).toEqual([]);
  });

  it("dreamed-sibling-200-trim.clm validates clean", () => {
    expect(validateV3(Document.parse(read("experiments/v3/dreamed-sibling-200-trim.clm"))).errors).toEqual([]);
  });
});

describe("validateV3 — quarantine", () => {
  it("malformed roll-call entry quarantined (not counted)", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  CLd.Snt4.6 · 2026-04-07 · "a"\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  this is junk that doesn't match the format\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(hasError(r, "sentinel_missing_in_trimmed_section")).toBe(false);
    expect(hasWarn(r, "malformed_entry")).toBe(true);
  });

  it("archive section entries also validated (and malformed warned)", () => {
    const text =
      `;;; CLM/3.0 — archive sibling\n;;; t.archive.clm\n;;; ---\n\n` +
      `[ROLL.CALL.ARCHIVE]\n` +
      `  CLd.X · 2026-01-01 · "valid line"\n` +
      `  this is a malformed archive line with no separator\n` +
      `;;\n\n;;; EOF | archive\n`;
    const r = validateV3(Document.parse(text));
    expect(
      r.warnings.some(
        (w) => w.kind === "malformed_entry" && (w.details as { section: string }).section === "ROLL.CALL.ARCHIVE"
      )
    ).toBe(true);
  });
});

describe("validateV3 — strict integer parsing (parity with Rust usize::parse)", () => {
  it("trim.config rejects '3.0' (not an integer)", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=3.0\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(hasError(r, "invalid_trim_config_value")).toBe(true);
  });

  it("trim.config rejects '3e0' (scientific)", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=3e0\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(hasError(r, "invalid_trim_config_value")).toBe(true);
  });

  it("decisions.live header `(last 2.0 of 5.0 archived)` is rejected", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=2\n;;; ---\n\n` +
      `[STATE]\n` +
      `  decisions.live (last 2.0 of 5.0 archived):\n` +
      `    d4: keep me [session 40]\n` +
      `    d5: keep me too [session 50]\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    // Non-integer header parens → declaredOffloadCount stays undefined → no offload claim.
    // With keep_last=2 and 2 visible entries (no overflow), no sentinel error.
    expect(hasError(r, "sentinel_missing_in_trimmed_section")).toBe(false);
  });
});

describe("validateV3WithFilesystem", () => {
  let tmpDir: string;
  beforeEach(() => {
    tmpDir = mkdtempSync(join(tmpdir(), "clm-js-test-"));
  });
  afterEach(() => {
    rmSync(tmpDir, { recursive: true, force: true });
  });

  it("state.B with missing archive → warning", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[STATE]\n  ;; empty\n;;\n\n` +
      `[ROLL.CALL]\n  CLd.Snt4.6 · 2026-04-07 · "only one"\n;;\n\n` +
      `;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(r.errors).toEqual([]);
    expect(hasWarn(r, "archive_file_not_yet_created_in_state_b")).toBe(true);
  });

  it("state.C with missing archive → error", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "c"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(hasError(r, "archive_file_missing_in_state_c")).toBe(true);
  });

  it("declared offload marks state.C for filesystem check", () => {
    const entries = Array.from({ length: 8 }, (_, i) => i + 16)
      .map((i) => `    d${i}: keep me [session ${i * 2}]\n`)
      .join("");
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: definitely-not-here.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[STATE]\n  decisions.live (last 8 of 23 archived):\n${entries};;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(hasError(r, "archive_file_missing_in_state_c")).toBe(true);
  });

  it("archive.path → directory in state.C errors", () => {
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: .\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "c"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(hasError(r, "archive_file_missing_in_state_c")).toBe(true);
  });

  it("live section without sentinel + archive proves offload → error", () => {
    const archivePath = join(tmpDir, "x.archive.clm");
    writeFileSync(
      archivePath,
      `;;; CLM/3.0 — archive\n;;; ---\n\n[ROLL.CALL.ARCHIVE]\n  CLd.X · 2026-01-01 · "first"\n;;\n\n;;; EOF | archive\n`
    );
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: x.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "only one entry visible"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "another"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(
      r.errors.some(
        (e) =>
          e.kind === "sentinel_missing_in_trimmed_section" &&
          (e.details as { section: string }).section === "ROLL.CALL"
      )
    ).toBe(true);
  });

  it("archive doc warnings propagate to live report", () => {
    const archivePath = join(tmpDir, "x.archive.clm");
    writeFileSync(
      archivePath,
      `;;; CLM/3.0 — archive\n;;; ---\n\n[ROLL.CALL.ARCHIVE]\n  CLd.X · 2026-01-01 · "valid"\n  bogus line missing the separator\n;;\n\n;;; EOF | archive\n`
    );
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: x.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "recent"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(
      r.warnings.some(
        (w) =>
          w.kind === "malformed_entry" &&
          (w.details as { section: string }).section === "ROLL.CALL.ARCHIVE"
      )
    ).toBe(true);
  });

  it("archive points at wrong-shape file in state.C → error", () => {
    const stalePath = join(tmpDir, "stale.clm");
    writeFileSync(
      stalePath,
      `;;; CLM/3.0 — not an archive\n;;; ---\n\n[META]\n  ;; nope\n;;\n\n;;; EOF | CLM/3.0\n`
    );
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: stale.clm\n` +
      `;;; trim.config: roll_call=2, dream_log=3, decisions_live=8\n;;; ---\n\n` +
      `[ROLL.CALL]\n` +
      `  ;; (oldest 1 entries offloaded to [ROLL.CALL.ARCHIVE] in sibling)\n` +
      `  CLd.Ops4.6 · 2026-04-07 · "b"\n` +
      `  CLd.Snt4.5 · 2026-04-24 · "c"\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(hasError(r, "archive_file_wrong_shape_in_state_c")).toBe(true);
  });

  it("decisions.live archive cross-check demands sentinel (P2-A regression)", () => {
    // Codex PR-13 round-8 P2-A. Symmetric to the live-section-without-sentinel
    // test above but for [DECISIONS.ARCHIVE]. Live doc has bare
    // `decisions.live:` (no parens), exactly keep_last visible decisions, no
    // sentinel — but the sibling archive contains [DECISIONS.ARCHIVE] proving
    // offload happened. The intra-doc check stays silent (no overflow, no
    // declared offload), so before the fix this validated clean. Now the
    // cross-doc check demands the sentinel.
    const archivePath = join(tmpDir, "decisions.archive.clm");
    writeFileSync(
      archivePath,
      `;;; CLM/3.0 — archive\n;;; ---\n\n[DECISIONS.ARCHIVE]\n  d1: original decision [session 1]\n  d2: another decision [session 2]\n;;\n\n;;; EOF | archive\n`
    );
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: decisions.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=10, decisions_live=3\n;;; ---\n\n` +
      // bare `decisions.live:`, exactly keep_last=3 visible decisions, no sentinel
      `[STATE]\n` +
      `  decisions.live:\n` +
      `    d3: kept decision [session 3]\n` +
      `    d4: kept decision [session 4]\n` +
      `    d5: kept decision [session 5]\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(
      r.errors.some(
        (e) =>
          e.kind === "sentinel_missing_in_trimmed_section" &&
          (e.details as { section: string }).section === "STATE.decisions.live"
      )
    ).toBe(true);
  });

  it("decisions.live archive cross-check skips when no decisions.live block (review follow-up)", () => {
    // Code-review follow-up: P2-A must NOT fire if the live doc has no
    // `decisions.live:` sub-block at all (e.g. a [STATE] that only carries
    // `progress:` / `next_steps:`). Otherwise we'd emit a ghost sentinel-missing
    // error against a section that doesn't exist.
    const archivePath = join(tmpDir, "decisions-ghost.archive.clm");
    writeFileSync(
      archivePath,
      `;;; CLM/3.0 — archive\n;;; ---\n\n[DECISIONS.ARCHIVE]\n  d1: stale decision from prior phase [session 1]\n;;\n\n;;; EOF | archive\n`
    );
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: decisions-ghost.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=10, decisions_live=3\n;;; ---\n\n` +
      // [STATE] exists but has NO decisions.live: sub-block.
      `[STATE]\n` +
      `  progress: phase 2 underway\n` +
      `  next_steps: ship 0.2.1\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3WithFilesystem(Document.parse(text), tmpDir);
    expect(
      r.errors.some(
        (e) =>
          e.kind === "sentinel_missing_in_trimmed_section" &&
          (e.details as { section: string }).section === "STATE.decisions.live"
      )
    ).toBe(false);
  });

  it("malformed decisions.live entry quarantined (P2-B regression)", () => {
    // Codex PR-13 round-8 P2-B. A malformed line inside the decisions.live
    // block (anything not matching `dN: ...`) must be quarantined: emit a
    // MalformedEntry warning and EXCLUDE from the visible-entries count.
    // Before the fix, the malformed line counted toward the threshold and
    // could trigger a false sentinel-missing error.
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n` +
      `;;; trim.mode: aggressive | archive.mode: sibling | archive.path: t.archive.clm\n` +
      `;;; trim.config: roll_call=10, dream_log=10, decisions_live=3\n;;; ---\n\n` +
      // 3 valid (== keep_last=3) + 1 malformed `note:` line.
      // Pre-fix: visibleEntries=4 > 3 → sentinel error.
      // Post-fix: malformed quarantined, visibleEntries=3 → no error,
      // MalformedEntry warning emitted.
      `[STATE]\n` +
      `  decisions.live:\n` +
      `    d1: first decision [session 1]\n` +
      `    d2: second decision [session 2]\n` +
      `    note: this is an explanatory note, not a real decision\n` +
      `    d3: third decision [session 3]\n` +
      `;;\n\n;;; EOF | CLM/3.0\n`;
    const r = validateV3(Document.parse(text));
    expect(
      r.errors.some(
        (e) =>
          e.kind === "sentinel_missing_in_trimmed_section" &&
          (e.details as { section: string }).section === "STATE.decisions.live"
      )
    ).toBe(false);
    expect(
      r.warnings.some(
        (w) =>
          w.kind === "malformed_entry" &&
          (w.details as { section: string }).section === "STATE.decisions.live"
      )
    ).toBe(true);
  });
});
