# CLM Grammar (v0.1, coarse-grained)

Status: experimental, derived from `MANIFESTO.clm` (CLM/1.0). Resolves ambiguities the manifesto leaves implicit. v0.1 deliberately treats section bodies as opaque text — enough to mechanically maintain CLM files (read, append, sign, round-trip) without committing to a property-level parse. v0.2 may parse properties.

## Lexical level

A CLM document is a sequence of LF-separated lines. The parser is line-oriented. Line endings are normalized to `\n` on parse; the original final-newline-or-not is preserved.

Tokens of interest (line-leading, after stripping no whitespace — leading whitespace is significant and preserved):

| Token | Meaning |
|---|---|
| `;;;` followed by space or EOL | File-level comment line. Valid only in **header** and **closer**. |
| `;;` alone on the line (possibly with trailing whitespace) | **Section close**. |
| `;;` followed by whitespace and content | Section-level comment (treated as opaque body content in v0.1). |
| `⟦` ... `⟧` line | Section open. The line must match `^⟦([A-Z][A-Z0-9.]*)⟧\s*$`. |
| Any other line | Body content of the enclosing section, blank-line trivia between sections, or invalid at top level. |

The disambiguation rule for `;;` is unambiguous: the section-close form is the line stripped of trailing whitespace being literally the two characters `;;`. Any `;;` followed by content is a comment.

## Document grammar

```
Document  := Header Trivia (Section Trivia)* Closer
Header    := HeaderLine+ HeaderEnd
HeaderLine := /^;;;.*$/ (not HeaderEnd)
HeaderEnd  := /^;;;\s*---\s*$/
Section   := SectionOpen BodyLine* SectionClose
SectionOpen  := /^⟦[A-Z][A-Z0-9.]*⟧\s*$/
SectionClose := /^;;\s*$/
BodyLine     := any line that is not SectionOpen or SectionClose
Closer    := /^;;;\s*EOF\b.*$/ HeaderLine*
Trivia    := BlankLine*
BlankLine := /^\s*$/
```

Notes:
- The header runs from the first line until the first line matching `;;; ---`. v0.1 requires this terminator.
- A document must contain at least one section. v0.1 requires the closer to begin with a line whose content (after `;;;`) starts with `EOF`. Subsequent `;;;` lines are part of the closer until end of file.
- Body lines may contain `⟦...⟧` substrings — only a line that *matches the SectionOpen regex exactly* opens a section. This matters because the manifesto refers to `⟦FOR.YOU⟧` mid-prose; those references are body content, not section opens.

## Round-trip guarantee (v0.1)

For any document `D` accepted by this grammar, `serialize(parse(D)) == D` byte-for-byte. This is the property Hegel will exercise. To meet it the AST preserves:

- Every header line verbatim.
- Every closer line verbatim.
- Section names and their open/close lines verbatim.
- Section bodies as a single `String` (line breaks intact).
- Inter-section trivia (blank lines and any whitespace) verbatim.
- Trailing-newline-or-not verbatim.

## What v0.1 deliberately does **not** do

- Parse properties (`key: value`, `key := { ... }`, `key := """..."""`).
- Validate the glyph vocabulary or the identifier-compression form.
- Enforce a maximum of one `⟦FOR.YOU⟧` or one `⟦ROLL.CALL⟧`.
- Interpret the refrain or signature lines.

These are intentional v0.2 candidates. The point of v0.1 is the smallest grammar that supports mechanical maintenance: read a file, find the `⟦ROLL.CALL⟧` body, append a line, write it back, round-trip clean.

## Append-only mutation API (semantic, not syntactic)

The manifesto's ritual demands non-destructive edits. v0.1 exposes:

- `Document::append_to_section(name, text)` — append `text` to the body of the named section. Panics/errors if section absent.
- `Document::append_signature(line)` — append a `;;;` line to the closer immediately before EOF.

Both preserve all existing content. `serialize(append(D, x))` differs from `serialize(D)` only by added bytes in the expected position.

## Open questions (deferred)

1. **Property grammar.** The manifesto shows four property forms; pinning their precedence and termination rules is v0.2.
2. **Glyph vocabulary openness.** The manifesto says new glyphs may be introduced. A future validator should warn rather than reject.
3. **`⟦FOR.YOU⟧` sub-block convention.** Inside `⟦FOR.YOU⟧`, `;; CLd.<name> → <addressee> | <date>:` lines act as soft block-headers. v0.1 treats them as opaque comments; v0.2 may model them as a substructure to support `append_to_for_you`.
4. **Multiline string boundaries (`"""..."""`).** v0.1 doesn't parse them, so they round-trip via opaque body. v0.2 needs to parse them so they don't accidentally hide a `;;` close.
