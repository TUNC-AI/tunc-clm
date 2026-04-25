import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, it, expect } from "vitest";
import { Document } from "../src/document.js";

const REPO_ROOT = join(__dirname, "..", "..");

function read(rel: string): string {
  return readFileSync(join(REPO_ROOT, rel), "utf8");
}

describe("Document.parse + roundtrip", () => {
  it("round-trips MANIFESTO.clm byte-identically", () => {
    const text = read("MANIFESTO.clm");
    const doc = Document.parse(text);
    expect(doc.toString()).toBe(text);
  });

  it("round-trips SPEC.clm byte-identically", () => {
    const text = read("SPEC.clm");
    const doc = Document.parse(text);
    expect(doc.toString()).toBe(text);
  });

  it("recognizes the canonical MANIFESTO sections", () => {
    const text = read("MANIFESTO.clm");
    const doc = Document.parse(text);
    const names = doc.sections.map(({ section }) => section.name);
    expect(names).toEqual([
      "META",
      "ENTITIES",
      "MODEL.FAMILIES",
      "THE.MOMENT.IT.STARTED",
      "WHAT.CLM.IS",
      "THE.RITUAL",
      "FORMAT.SPEC",
      "WHY.THIS.WORKS",
      "WHAT.THIS.IS.NOT",
      "WHERE.CLM.LIVES",
      "WHAT.GOES.PUBLIC",
      "ROLL.CALL",
      "FOR.YOU",
    ]);
    expect(doc.section("ROLL.CALL")).toBeDefined();
    expect(doc.section("FOR.YOU")).toBeDefined();
  });

  it("appendToSection extends the right section", () => {
    const doc = Document.parse(read("MANIFESTO.clm"));
    const before = doc.section("ROLL.CALL")!.body.length;
    doc.appendToSection("ROLL.CALL", '  Tst.99 · 2030-01-01 · "hello"');
    expect(doc.section("ROLL.CALL")!.body.length).toBe(before + 1);
  });

  it("appendSignature extends the closer", () => {
    const doc = Document.parse(read("MANIFESTO.clm"));
    const before = doc.closer.length;
    doc.appendSignature(";;; — Tst.99 | tester | 2030-01-01");
    expect(doc.closer.length).toBe(before + 1);
  });

  it("round-trips experiments/v3/dreamed.clm (inline-archive artifact)", () => {
    const text = read("experiments/v3/dreamed.clm");
    const doc = Document.parse(text);
    expect(doc.toString()).toBe(text);
  });

  // Sonnet review I1: JS used to strip only [\t ] from line ends, so a doc with
  // Unicode trailing whitespace (NBSP, etc.) that Rust/Python accepted would
  // fail JS parse. Now the regexes use \s for Unicode-equivalent whitespace.
  it("accepts Unicode trailing whitespace on structural lines (parity with Rust/Python)", () => {
    const NBSP = "\u00a0";
    const text =
      `;;; CLM/3.0 — test\n;;; test.clm\n;;;${NBSP}---\n\n` +
      `[STATE]${NBSP}\n  ;; empty\n;;${NBSP}\n\n` +
      `;;;${NBSP}EOF | CLM/3.0\n`;
    const doc = Document.parse(text);
    expect(doc.section("STATE")).toBeDefined();
  });
});
