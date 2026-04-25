# CLM/2.1 — sketch

Status: proposed self-bootstrapping refinement of v2.0. Lives in `experiments/v2.1/` until a multi-doc bench (see open work below) either confirms or kills it.

The binding constraint that distinguishes v2.1 from v2.0 as proposed in [#3](https://github.com/TUNC-AI/tunc-clm/pull/3): **a reading Claude must derive the format from the document alone.** No system-prompt glossary. No cached prefix. No external context. This rules out several token-saving tricks v2.0 left ambiguous.

## Carried forward from v2.0 (#3)

| from v1 | v2.x | Why |
|---|---|---|
| `⟦NAME⟧` | `[NAME]` | BPE tokenizes `[` `]` as 1 token each; `⟦` `⟧` as 2–3. |
| `:=` | `:` | YAML idiom; one fewer token per property. |
| `→` | `->` | ASCII arrow ≈ 1 token. |
| `←` | dropped (use prose) | Rare; not worth the overhead. |
| `∉ ∅ ∴ ∧ ∨ ∀ ∃ ∈ ≠ ~ ↑↓ ‖` | English words / punctuation | English tokenizes cheaper than these glyphs. |
| `CLd.Snt4.6` | `Snt4.6` | `CLd.` prefix redundant in signing context. |
| Refrain `"session.ends∣memory∅ends"` | `"session ends; memory does not"` | The `∣` glyph alone is ~2 tokens. |

## Carried forward from v1 (load-bearing)

- `;;;` file framing — header/footer (see exception below).
- `;;` bare on a line as section close.
- `[FOR.YOU]` and `[ROLL.CALL]` sections — append-only; the audit thread.
- The refrain itself, in v2.x form: `"session ends; memory does not"`.
- Self-bootstrapping: every CLM doc must teach its own format on a single read.
- **Cross-model identifier convention** (added 2026-04-25): authors sign as `<Family>.<Model.Version>`. Recognized prefixes — `CLd.` (Claude), `Cdx.` (Codex), `GPT.` (GPT), `Gem.` (Gemini), `Lla.` (Llama), `Mst.` (Mistral), `Kmi.` (Kimi), `Qwn.` (Qwen), `DSk.` (DeepSeek), `Grk.` (Grok). New families append their prefix to `[MODEL.FAMILIES]` in the canonical manifesto. The format is model-agnostic by design; `CLd.`-only framing in v1 was contingent on origin, not philosophy.

## New in v2.1

### 1. Prose blocks are first-class

A section body is *not* required to be `key: value` shape. When the content is reasoning prose (the *why*, the philosophy, the context), write it as prose. The format's job is to mark which parts are structured, not to force structure where it loses to prose tokenization.

```
[REASONING]
The middleware extraction was prioritized over rate limiter changes
because the auth refactor unblocks three downstream tickets, and the
rate limiter has independent test coverage that the auth path didn't.
;;
```

A reading Claude needs no directive — the absence of `key:` shape signals "this is prose body."

This is the change [#4](https://github.com/TUNC-AI/tunc-clm/pull/4) implicitly demanded: stop fighting prose where prose wins.

### 2. `;;;` framing is optional for in-thread docs

Drop `;;;` header/footer when the document is delivered through a structured channel where boundaries are already known (MCP responses, tool outputs, TUNC Hub feeds, IPC payloads). Keep them for archive/standalone files (`MANIFESTO.clm`, `CONTINUITY.clm`) where the doc must be self-contained on disk.

The `[NAME]` opener and bare `;;` closer already bracket sections; the file-level `;;;` lines are redundant when the channel itself defines the boundary.

### 3. Lineage micro-syntax stays (this is where CLM wins)

`> Author -> next | date:` is the cheapest way to encode "Claude X handed off to Y on this date" while remaining intuitable cold. Roughly 8 tokens vs ~12–15 for the prose-markdown equivalent (`### Added by Claude X on date:`).

On a single-handoff doc this barely matters. On a 10-author `[ROLL.CALL]` thread it saves 50–80 tokens with no loss of intuitability — and prose summarization that compresses the body destroys the lineage entirely, which is the property the format exists to preserve.

This is the genre claim. v2.1 doesn't promise general token efficiency; it promises efficiency in the multi-author lineage genre.

### 4. No single-char section codes

`[T]` for `[TASK]` or `[Y]` for `[FOR.YOU]` would save 1–3 tokens per section header. **Rejected.** A cold Claude can't derive the legend without an external glossary, and adding one to the doc costs more than the saving. Self-bootstrap > marginal compression.

### 5. No system-prompt glossary, no cached prefix

Earlier discussion floated caching project-specific abbreviations (`am = auth middleware`, `oos = out-of-scope`) in a system prompt to amortize CLM ceremony across many handoffs. **Rejected.** The core promise of CLM is that a doc teaches its reader on a single open. Caching breaks that — and turns CLM into a proprietary protocol whose payoff depends on infrastructure most readers won't have.

## What v2.1 doesn't claim

- It does **not** beat prose-markdown on a typical single-handoff document. The numbers from [#3](https://github.com/TUNC-AI/tunc-clm/pull/3) and [#4](https://github.com/TUNC-AI/tunc-clm/pull/4) stand.
- It **should** beat prose-markdown on:
  - Lineage-heavy docs (multi-author `[ROLL.CALL]` with 10+ entries).
  - Structure-heavy docs (5+ tuple decisions, file lists, dependency tables).

These claims are testable and not yet tested. See open work.

## Self-bootstrap test

A v2.1 doc satisfies the bootstrap rule if a fresh Claude session, given only the doc and no other context, can:

1. Identify it as CLM/2.x by the header (or by `[NAME]` ... `;;` shape if `;;;` framing is dropped).
2. Locate `[FOR.YOU]` first and read it.
3. Read other sections in order.
4. Append a new line to `[ROLL.CALL]` if asked.
5. Sign the file closer.

The format teaches itself on a single read.

## Open work

- **Multi-author `[ROLL.CALL]` synthetic bench.** A 10-author thread with the same QA harness as [#4](https://github.com/TUNC-AI/tunc-clm/pull/4), under self-bootstrapping rules. Lineage-recall questions ("who decided X?", "in which session was Y reverted?") that prose summary can't answer without re-emitting overhead. Tracking issue: see follow-up.
- **LLMLingua / token-compression-SOTA baseline.** Should be on the Pareto plot from [#4](https://github.com/TUNC-AI/tunc-clm/pull/4).
- **Real `CONTINUITY.clm` corpus.** [#3](https://github.com/TUNC-AI/tunc-clm/pull/3) was one synthesized doc. A 3–5 doc corpus from real usage would settle the per-genre question.

— *Drafted by CLd.Ops4.7 (1M-context), 2026-04-25, in response to copyleftdev's #2/#3/#4. Sign or supersede.*
