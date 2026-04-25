"""Coarse-grained parser for the Claude Memory Format.

Supports both CLM/1.0 (Unicode brackets `⟦NAME⟧`) and CLM/2.x+/3.0
(ASCII brackets `[NAME]`). The contract is round-trip:
`str(Document.parse(text)) == text` byte-for-byte for any document
accepted by the grammar.

v3.0 trim-aware validation lives in :mod:`clm.validate`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


SEC_OPEN = "\u27E6"   # ⟦
SEC_CLOSE = "\u27E7"  # ⟧


class ParseError(Exception):
    """A document failed to parse against the CLM grammar."""


class MutationError(Exception):
    """A document mutation (e.g. append_to_section) targeted a missing section."""


@dataclass
class Section:
    """A `[NAME] ... ;;` section in a CLM document."""

    name: str
    open_line: str
    body: list[str] = field(default_factory=list)
    close_line: str = ";;"


@dataclass
class Document:
    """A parsed CLM document. Round-trips byte-identically via ``str(doc)``."""

    header: list[str] = field(default_factory=list)
    trivia_after_header: list[str] = field(default_factory=list)
    # Each section is paired with the trivia (typically blank lines) that follows it.
    sections: list[tuple[Section, list[str]]] = field(default_factory=list)
    closer: list[str] = field(default_factory=list)
    trailing_newline: bool = True

    # ---- parsing ----

    @classmethod
    def parse(cls, text: str) -> "Document":
        trailing_newline = text.endswith("\n")
        body = text[:-1] if trailing_newline else text
        lines = body.split("\n") if body else []

        idx = 0

        # Header
        if idx >= len(lines) or not _is_triple_semi(lines[idx]):
            raise ParseError("missing file header (expected lines starting with ';;;')")
        header: list[str] = []
        found_terminator = False
        while idx < len(lines) and _is_triple_semi(lines[idx]):
            header.append(lines[idx])
            if _is_header_terminator(lines[idx]):
                idx += 1
                found_terminator = True
                break
            idx += 1
        if not found_terminator:
            raise ParseError("missing header terminator (expected ';;; ---')")

        # Trivia after header (blank lines)
        trivia_after_header: list[str] = []
        while idx < len(lines) and _is_blank(lines[idx]):
            trivia_after_header.append(lines[idx])
            idx += 1

        # Sections
        sections: list[tuple[Section, list[str]]] = []
        while True:
            if idx >= len(lines):
                raise ParseError("missing file closer (expected ';;; EOF ...')")
            if _is_closer_start(lines[idx]):
                break
            open_line = lines[idx]
            name = _parse_section_open(open_line)
            if name is None:
                raise ParseError(f"unexpected line at top level (line {idx + 1}): {open_line!r}")
            open_line_idx = idx
            idx += 1

            section_body: list[str] = []
            close_line: Optional[str] = None
            while idx < len(lines):
                if _is_section_close(lines[idx]):
                    close_line = lines[idx]
                    idx += 1
                    break
                if _parse_section_open(lines[idx]) is not None:
                    raise ParseError(
                        f"nested section opens are not allowed (line {idx + 1})"
                    )
                section_body.append(lines[idx])
                idx += 1
            if close_line is None:
                raise ParseError(
                    f"section [{name}] opened at line {open_line_idx + 1} was never closed (';;')"
                )

            trivia: list[str] = []
            while idx < len(lines) and _is_blank(lines[idx]):
                trivia.append(lines[idx])
                idx += 1

            sections.append(
                (
                    Section(
                        name=name,
                        open_line=open_line,
                        body=section_body,
                        close_line=close_line,
                    ),
                    trivia,
                )
            )

        # Closer
        closer: list[str] = []
        while idx < len(lines):
            if not _is_triple_semi(lines[idx]):
                raise ParseError(f"unexpected content after file closer (line {idx + 1})")
            closer.append(lines[idx])
            idx += 1
        if not closer or not _is_closer_start(closer[0]):
            raise ParseError("missing file closer (expected ';;; EOF ...')")

        return cls(
            header=header,
            trivia_after_header=trivia_after_header,
            sections=sections,
            closer=closer,
            trailing_newline=trailing_newline,
        )

    # ---- accessors ----

    def section(self, name: str) -> Optional[Section]:
        for sec, _ in self.sections:
            if sec.name == name:
                return sec
        return None

    # ---- mutation ----

    def append_to_section(self, name: str, text: str) -> None:
        for sec, _ in self.sections:
            if sec.name == name:
                sec.body.extend(text.split("\n"))
                return
        raise MutationError(f"no such section: [{name}]")

    def append_signature(self, line: str) -> None:
        self.closer.append(line)

    # ---- serialization ----

    def __str__(self) -> str:
        out: list[str] = []
        for line in self.header:
            out.append(line)
            out.append("\n")
        for line in self.trivia_after_header:
            out.append(line)
            out.append("\n")
        for sec, trivia in self.sections:
            out.append(sec.open_line)
            out.append("\n")
            for body_line in sec.body:
                out.append(body_line)
                out.append("\n")
            out.append(sec.close_line)
            out.append("\n")
            for line in trivia:
                out.append(line)
                out.append("\n")
        last = len(self.closer) - 1
        for i, line in enumerate(self.closer):
            out.append(line)
            if i < last or self.trailing_newline:
                out.append("\n")
        return "".join(out)


# ---- line classifiers ----

def _is_triple_semi(line: str) -> bool:
    return line.startswith(";;;")


def _is_header_terminator(line: str) -> bool:
    if not line.startswith(";;;"):
        return False
    return line[3:].strip() == "---"


def _is_closer_start(line: str) -> bool:
    if not line.startswith(";;;"):
        return False
    after = line[3:].lstrip()
    if not after.startswith("EOF"):
        return False
    rest = after[3:]
    if not rest:
        return True
    return not (rest[0].isascii() and rest[0].isalnum())


def _is_blank(line: str) -> bool:
    return all(c.isspace() for c in line) if line else True


def _is_section_close(line: str) -> bool:
    return line.rstrip() == ";;"


def _parse_section_open(line: str) -> Optional[str]:
    """Recognize both Unicode (CLM/1.0) and ASCII (CLM/2.x+/3.0) section opens."""
    trimmed = line.rstrip()
    # CLM/1.0: Unicode brackets
    if trimmed.startswith(SEC_OPEN) and trimmed.endswith(SEC_CLOSE):
        return _validate_section_name(trimmed[len(SEC_OPEN):-len(SEC_CLOSE)])
    # CLM/2.x+/3.0: ASCII brackets
    if trimmed.startswith("[") and trimmed.endswith("]"):
        return _validate_section_name(trimmed[1:-1])
    return None


def _validate_section_name(inner: str) -> Optional[str]:
    """Permissive parser-level grammar; strict semantics enforced in :mod:`clm.validate`.

    Plain section names: ``[A-Z][A-Z0-9.]*`` (uppercase only).
    DELTA.<suffix>: parser accepts any identifier-shaped suffix; validator enforces
    the spec session-id grammar so malformed names surface as InvalidDeltaSessionId.
    """
    if not inner:
        return None
    # Permissive parse for DELTA.<suffix>.
    if inner.startswith("DELTA."):
        suffix = inner[len("DELTA."):]
        if not suffix:
            return None
        if not all(c.isascii() and (c.isalnum() or c in "._-") for c in suffix):
            return None
        return inner
    # Plain section name: strict.
    first = inner[0]
    if not (first.isascii() and first.isupper()):
        return None
    if not all(c.isascii() and (c.isupper() or c.isdigit() or c == ".") for c in inner[1:]):
        return None
    return inner


__all__ = [
    "Document",
    "Section",
    "ParseError",
    "MutationError",
]
