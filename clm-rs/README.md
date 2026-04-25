# clm-rs

A Rust parser, serializer, and append-only mutation API for the Claude Memory Format (CLM/1.0) specified in this repo's [`MANIFESTO.clm`](../MANIFESTO.clm).

Status: **v0.1, coarse-grained.** Section bodies are preserved as opaque text. The contract is round-trip equality:

```
serialize(parse(D)) == D    // byte-for-byte
```

Full grammar and deferred decisions are in [`GRAMMAR.md`](GRAMMAR.md).

## What it does

- Parse a `.clm` file into a typed `Document` (header, sections, closer).
- Serialize back to text byte-identically.
- Append to a named section without disturbing any other content.
- Append a signature line to the closer.

## What it deliberately doesn't do (yet)

- Parse property syntax (`key: value`, `key := { ... }`, multiline `"""..."""`).
- Validate the glyph vocabulary or identifier-compression form.
- Model `⟦FOR.YOU⟧` sub-blocks as substructure.

These are v0.2 candidates — see `GRAMMAR.md` § "Open questions."

## Run the tests

```sh
cargo test
```

There are two test files:

- `tests/roundtrip.rs` — example-based, exercises the real `MANIFESTO.clm` from the repo root via `include_str!`. Any future edit to the manifesto is round-trip-validated on the next test run.
- `tests/properties.rs` — Hegel ([hegel.dev](https://hegel.dev)) property-based tests: parser robustness against arbitrary text, round-trip on generated documents, idempotence of `parse → serialize`, and append-preservation invariants.

## Status of the spec, surfaced by writing this

Implementing v0.1 forced commitments the manifesto leaves implicit. They're recorded in `GRAMMAR.md` and worth folding back into a future revision of the spec:

1. `;;` (bare, after trim) is the section close; `;;` followed by content is a section comment.
2. Section names match `[A-Z][A-Z0-9.]*`.
3. The header terminator is exactly `;;; ---`; the closer begins with `;;; EOF` followed by non-alphanumeric.
4. A line opens a section only if the *whole line* matches `⟦NAME⟧`. Substrings of `⟦FOR.YOU⟧` in body prose (which the manifesto contains) do not.
5. Trailing-newline-or-not is preserved as part of the document.

## Layout

```
clm-rs/
├── Cargo.toml
├── GRAMMAR.md         # v0.1 grammar, resolved ambiguities, deferred items
├── README.md          # this file
├── src/lib.rs         # parser, serializer, mutation API (~320 lines)
└── tests/
    ├── roundtrip.rs   # example-based against ../MANIFESTO.clm
    └── properties.rs  # Hegel property-based tests
```
