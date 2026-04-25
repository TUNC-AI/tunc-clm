# CLM/2.0 — sketch

Status: prototype, hypothesis-testing only. The point is to find out whether a redesigned CLM can actually beat prose on per-token cost. If it can't, this branch goes nowhere.

## What changes from v1

| v1 | v2 | Why |
|---|---|---|
| `⟦NAME⟧ ... ;;` | `[NAME] ... ;;` | ASCII brackets tokenize as 1 token each; `⟦`/`⟧` are 2–3 each in BPE. |
| `:=` | `:` | YAML/TOML idiom; one fewer token per property. |
| `→` | `->` | ASCII arrow; usually 1 token. |
| `←` | dropped | Re-express with prose where rare; not worth a glyph. |
| `∉` | `not` (English) or `!` | Words tokenize cheaper than glyphs. |
| `∅` | `none` | Same. |
| `∴` | dropped | Causation is usually implicit from juxtaposition; spend tokens elsewhere. |
| `∧ ∨` | `,` `or` | Comma for AND in lists; `or` as a word when needed. |
| `∀ ∃ ∈ ≠ ~ ↑↓ ‖` | dropped or English | Rare; not worth a special glyph. |
| `CLd.Snt4.6` | `Snt4.6` | The `CLd.` prefix is contextually redundant in `;;; signers:` and signature lines. Keep `CLd.` only when ambiguity is real. |
| `;; CLd.X → Y \| <date>:` (FOR.YOU sub-block marker) | `> X -> Y \| <date>:` | `>` is a single ASCII char. |
| Refrain `"session.ends∣memory∅ends"` | `"session ends; memory does not"` | The `∣` glyph is 2 tokens; English with a semicolon is cheaper and clearer. |

## What stays the same from v1

- File header opens with `;;;` lines, terminator `;;; ---`.
- Section close is bare `;;` on a line.
- File closer starts with `;;; EOF`.
- `[FOR.YOU]` and `[ROLL.CALL]` are load-bearing and append-only.
- Self-bootstrapping: a v2 reader can derive the format from one file.
- Round-trip is a contract for any v2 parser.

## Property syntax (v2)

```
key: value                          # simple
key: [a, b, c]                      # list
key: |                              # multiline (YAML-style block scalar)
  free text spanning
  multiple lines
nested:
  sub-a: x
  sub-b: y
```

No `:= { ... }` form. Indentation defines nesting (2 spaces).

## What v2 deliberately keeps minimal

- No formal type system. Values are strings unless a parser chooses to interpret.
- No glyph vocabulary expansion. If you find yourself wanting a new glyph, write a word.
- No execution semantics. Same as v1.

## Open question this prototype must answer

**Does CLM/2.0 actually beat prose Markdown and YAML on per-token cost for a representative handoff document?**

If yes: v2 is worth specifying and parsing.
If no: kill this branch. The honest move is to keep v1 as a notation people like and fix the README claim.
