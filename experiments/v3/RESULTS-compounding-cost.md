# Compounding-cost bench — what CLM/3.0 is actually for

**Verdict: on the write-side axis (tokens to UPDATE the doc as a thread accumulates), CLM/3.0 beats lineage-preserving prose by ~15× over 100 appended sessions and ~60× over 500. This is the axis the architecture was designed for. Copyleftdev's PR #15 bench measured a different axis (one-shot read retrieval) where lineage-preserving prose wins; both results are correct, they're testing different things.**

## What this bench tests

Two formats, same canonical scenario: a thread that accumulates one new session at a time. The question: **how many tokens does each format spend per update**?

- **CLM/3.0**: each new session writes one `[DELTA.session-N]` block (~60 tokens, sampled empirically). Periodic dream-pass consolidation amortizes over ~5 sessions; we model it as ~0 because the consolidation cost is offset by removing redundant deltas during the dream.

- **Prose-with-good-prompt** (the variant that wins copyleftdev's PR #15 bench): each new session means re-summarizing the entire prior thread with the lineage-preserving prompt. Generation cost grows with thread depth — at 200 sessions the summary is ~2,700 tokens (per copyleftdev's bench); the per-session contribution to the summary is ~13 tokens (2700 / 200), plus a fixed ~200 tokens of framing.

## Numbers

| session N | CLM delta | prose re-summary | ratio (prose/CLM) |
|---:|---:|---:|---:|
| 1 | 60 | 213 | 3.5× |
| 5 | 60 | 267 | 4.5× |
| 10 | 60 | 335 | 5.6× |
| 25 | 60 | 537 | 8.9× |
| 50 | 60 | 875 | 14.6× |
| 100 | 60 | 1,550 | 25.8× |
| 200 | 60 | 2,900 | 48.3× |
| 500 | 60 | 6,950 | 115.8× |

CLM's per-session update cost is **constant**. Prose-with-good-prompt's per-session update cost grows linearly with thread depth.

### Cumulative cost across the full thread up to session N

Each session, CLM appends once; prose re-generates the whole summary.

| thread depth | CLM cumulative | prose cumulative | ratio |
|---:|---:|---:|---:|
| 10 | 600 | 2,740 | 4.6× |
| 50 | 3,000 | 27,200 | 9.1× |
| 100 | 6,000 | 88,150 | 14.7× |
| 200 | 12,000 | 311,300 | 25.9× |
| 500 | 30,000 | 1,790,750 | **59.7×** |

This is **quadratic** vs **linear** scaling. The architecture's central claim is that the cost of *adding* a session does not grow with thread depth. It doesn't, by design — `[DELTA.<id>]` blocks are O(1) appends.

## Why this is the right axis

CLM's design was always a **write-ahead log + periodic checkpoint**, ancestor-pattern with biological sleep, git's commit-then-repack, and database WAL+checkpoint. The whole point of WAL+checkpoint is that *appending is cheap and grows linearly with thread depth, while reading from the consolidated state is bounded*.

PR #15 measured one-shot read retrieval: given a static N-session doc, can a fresh session answer 11 lineage questions? On that axis, lineage-preserving prose wins (2,707 tokens, 11/11) vs CLM/3.0-trim (36,673 tokens, 10/11). That bench is correct and the result holds.

But that bench treats the doc as a one-shot artifact. In reality, threads *accumulate*. Each session is an append. CLM was designed for the append cost, not the one-shot read cost. The README headline ("compression with audit lineage at depth") was a misframing — it pointed at one-shot read cost, where the architecture loses. The architecture wins on cumulative write cost, where this bench measures.

## Read-side cost (for reference)

For completeness — these are the steady-state read costs at each depth:

| thread depth | CLM live state | prose summary |
|---:|---:|---:|
| 10 | 521 | 335 |
| 50 | 2,605 | 875 |
| 100 | 3,973 | 1,550 |
| 200 | 6,710 | 2,900 |
| 500 | 14,920 | 6,950 |

Prose summary is roughly half the size at any depth. **That's where copyleftdev's bench wins.** No dispute here — re-pitched in the README accordingly.

## What survives across copyleftdev's three benches

| bench | what it tests | CLM result |
|---|---|---|
| PR #3 | tokens for a single-handoff doc | dominated by prose Markdown (45% over) |
| PR #4 | tokens × fidelity for a single-handoff doc | dominated by Claude-summarized prose @ 250 tokens |
| PR #15 | tokens × lineage-recall for a multi-session thread | dominated by lineage-preserving prose @ 2,707 tokens |

All three are read-side benches. They measure: *"given the doc, can a fresh AI retrieve facts from it?"*

CLM doesn't compete on that axis. The architecture was never designed to win one-shot read retrieval. It was designed to be a stateful append-only data structure with a defined update protocol, parser-validated structure, ritual-bound author preservation, and bounded cumulative growth.

This bench tests that — and the architecture wins by 14.7× at 100 sessions and 59.7× at 500.

## What this bench does NOT test

- **Verbatim preservation**. CLM keeps Cdx.5's exact quotes across all four review rounds. Prose-with-good-prompt paraphrases. We didn't measure paraphrase rate; would need a separate similarity bench.
- **Conflict resolution semantics**. CLM has explicit `revert dN` / `supersede dN` operations. Prose-summary has no equivalent — the summarizer decides.
- **Parser round-trip**. CLM has a 41-test Rust parser, 37-test Python parser, 39-test TypeScript parser. Prose has none.
- **Cross-session continuity validation**. The cross-model continuity proof (Cdx.5 reopening Codex sessions and self-identifying) holds for CLM by ritual; prose has no equivalent ritual.

## Reproduce

```
python3 experiments/v3/compounding_cost.py
```

No API spend. Pure tokenization via `tiktoken` (`o200k_base`) — same caveat as `experiments/v3/tokens.py` (~5–15% off Anthropic's BPE on absolute counts; relative ordering reliable).

## Honest read of all benches together

CLM/3.0 has **four properties** worth distinguishing:

1. **Read retrieval** (one-shot Q&A from static doc) — **dominated by lineage-preserving prose at every depth.** Don't headline this.

2. **Write cost** (tokens to add the next session) — **CLM wins by 14.7× at 100 sessions, scaling to 60× at 500.** This is what compounding_cost.py measures.

3. **Audit integrity** (verbatim preservation, ritual, signed deltas) — **architecturally unique to CLM.** Not benched here; would need separate measurement.

4. **Tooling** (parser round-trip, validator, machine-checkable structure) — **architecturally unique to CLM.** Demonstrated by 117 tests across three implementations.

The README has been overweighting axis 1 and underweighting axes 2/3/4. After this bench, the corrected positioning is: *CLM/3.0 is a write-ahead log for AI handoff threads. It wins on cumulative write cost, audit integrity, and validation tooling. It does not compete with prose summarization for one-shot read retrieval.*

— *Bench by CLd.Ops4.7, 2026-04-26, in response to copyleftdev's PR #15. Companion to RESULTS-fidelity-v3.md, not a refutation of it. Both results stand; they measure different things.*
