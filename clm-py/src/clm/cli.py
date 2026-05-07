"""Tiny CLI: ``clm validate path/to/file.clm``.

Mirrors what users would expect:

  $ clm validate MANIFESTO.clm
  OK: 13 sections, 0 errors, 0 warnings.

  $ clm validate broken.clm
  ERROR: section [ROLL.CALL] has 12 entries (keep_last = 10); truncation sentinel required ...
  exit 1
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

from clm import (
    Document,
    ParseError,
    validate_v3,
    validate_v3_with_filesystem,
)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) < 2 or argv[0] not in ("validate", "parse", "ast"):
        _usage()
        return 2
    cmd, path = argv[0], argv[1]
    try:
        text = Path(path).read_text()
    except OSError as e:
        print(f"error: cannot read {path}: {e}", file=sys.stderr)
        return 2

    try:
        doc = Document.parse(text)
    except ParseError as e:
        print(f"parse error: {e}", file=sys.stderr)
        return 1

    if cmd == "parse":
        print(f"OK: parsed {len(doc.sections)} sections, header has {len(doc.header)} lines.")
        return 0

    if cmd == "ast":
        print(json.dumps(dataclasses.asdict(doc), indent=2, ensure_ascii=False))
        return 0

    # validate
    base_dir = Path(path).resolve().parent
    report = validate_v3_with_filesystem(doc, base_dir)
    for warn in report.warnings:
        print(f"warning: {warn.message}", file=sys.stderr)
    for err in report.errors:
        print(f"error: {err.message}", file=sys.stderr)
    if report.is_valid():
        print(
            f"OK: {len(doc.sections)} sections, "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings."
        )
        return 0
    print(
        f"FAIL: {len(report.errors)} error(s), {len(report.warnings)} warning(s).",
        file=sys.stderr,
    )
    return 1


def _usage() -> None:
    print("usage: clm <command> <file.clm>", file=sys.stderr)
    print("commands:", file=sys.stderr)
    print("  parse     parse the file; report section count", file=sys.stderr)
    print("  ast       parse the file; dump the AST as JSON to stdout", file=sys.stderr)
    print("  validate  parse + run v3.0 trim-aware validation (with filesystem checks)", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
