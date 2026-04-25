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
});
