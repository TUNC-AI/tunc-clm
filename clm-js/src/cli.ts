#!/usr/bin/env node
/**
 * Tiny CLI: `clm validate path/to/file.clm`
 *
 *   $ clm validate MANIFESTO.clm
 *   OK: 13 sections, 0 errors, 0 warnings.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

import { Document, ParseError } from "./document.js";
import { validateV3WithFilesystem } from "./validate.js";

function usage(): void {
  process.stderr.write("usage: clm <command> <file.clm>\n");
  process.stderr.write("commands:\n");
  process.stderr.write("  parse     parse the file; report section count\n");
  process.stderr.write("  validate  parse + run v3.0 trim-aware validation (with filesystem checks)\n");
}

function main(argv: string[]): number {
  if (argv.length < 2 || (argv[0] !== "validate" && argv[0] !== "parse")) {
    usage();
    return 2;
  }
  const cmd = argv[0]!;
  const path = argv[1]!;
  let text: string;
  try {
    text = readFileSync(path, "utf8");
  } catch (e) {
    process.stderr.write(`error: cannot read ${path}: ${(e as Error).message}\n`);
    return 2;
  }

  let doc: Document;
  try {
    doc = Document.parse(text);
  } catch (e) {
    process.stderr.write(`parse error: ${(e as ParseError).message}\n`);
    return 1;
  }

  if (cmd === "parse") {
    process.stdout.write(`OK: parsed ${doc.sections.length} sections, header has ${doc.header.length} lines.\n`);
    return 0;
  }

  const baseDir = dirname(resolve(path));
  const report = validateV3WithFilesystem(doc, baseDir);
  for (const w of report.warnings) {
    process.stderr.write(`warning: ${w.message}\n`);
  }
  for (const e of report.errors) {
    process.stderr.write(`error: ${e.message}\n`);
  }
  if (report.isValid()) {
    process.stdout.write(
      `OK: ${doc.sections.length} sections, ${report.errors.length} errors, ${report.warnings.length} warnings.\n`
    );
    return 0;
  }
  process.stderr.write(
    `FAIL: ${report.errors.length} error(s), ${report.warnings.length} warning(s).\n`
  );
  return 1;
}

process.exit(main(process.argv.slice(2)));
