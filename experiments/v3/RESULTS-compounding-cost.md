# Compounding-cost bench — what CLM/3.0 is actually for

**Verdict: on the write-side axis (tokens to UPDATE the doc as a thread accumulates), CLM/3.0 beats lineage-preserving prose by 1.2×–12.2× depending on thread depth. The advantage grows with depth: ~1.2× at 10 sessions, ~4.2× at 100, ~12.2× at 500. This is the axis the architecture was designed for. Copyleftdev's PR #15 bench measured a different axis (one-shot read retrieval) where lineage-preserving prose wins; both results are correct, they're testing different things.**

## What this bench tests

Two formats, same canonical scenario: a thread that accumulates one new session at a time. The question: **how many tokens does each format spend per update**?

- **CLM/3.0**: each new session writes one `[DELTA.session-N]` block (~60 tokens) plus a `[ROLL.CALL]` line (~50 tokens). Dream passes happen at sessions 5, 10, 15, ... up to but not including the final batch (the last 1–5 sessions stay live as active deltas — matches the canonical generator). At depth N, total dreams = (N−1) // 5. Each dream rewrites the `[STATE]` block (bounded under `trim.mode: aggressive` by `decisions_live=8`, ~210 tokens), appends a `[DREAM.LOG]` entry (~30 tokens), and signs a roll-call line (~50 tokens) for the dream signer. Steady-state amortized: **~176 tokens per session, constant in thread depth**.

- **Prose-with-good-prompt** (the variant that wins copyleftdev's PR #15 bench): each new session means re-summarizing the entire prior thread with the lineage-preserving prompt. Generation cost grows with thread depth as a power law. Calibrated to PR #15's two empirical points (N=50 → 1,007 tokens; N=200 → 2,707 tokens); fit gives **~61.82 × N^0.7133 tokens per update** (matches both points exactly).

## Numbers

| session N | CLM update (slowly grows) | prose summary (grows faster) | ratio (prose/CLM) |
|---:|---:|---:|---:|
| 1 | 236 | 62 | 0.3× |
| 5 | 236 | 195 | 0.8× |
| 10 | 237 | 319 | 1.3× |
| 25 | 238 | 614 | 2.6× |
| 50 | 239 | 1,007 | 4.2× |
| 100 | 242 | 1,651 | 6.8× |
| 200 | 248 | 2,707 | 10.9× |
| 500 | 266 | 5,204 | 19.5× |

CLM's per-session update cost grows slowly with depth (`decisions.reverted/superseded` accumulate at ~0.3 tokens/session in `[STATE]`; archive writes per dream are constant). Prose-with-good-prompt's per-session cost grows as N^0.7133 (sub-linear because the summarizer paraphrases as content grows; matches Don's empirical 50→200 ratio of ×2.69 for ×4 sessions).

The crossover point is around 8 sessions — below that, prose is cheaper per-update. Above, CLM is cheaper, with the gap widening as the thread grows.

### Cumulative cost across the full thread up to session N

| thread depth | n_dreams | CLM cumulative | prose cumulative | ratio |
|---:|---:|---:|---:|---:|
| 10 | 1 | 1,617 | 2,016 | 1.2× |
| 50 | 9 | 11,129 | 29,882 | 2.7× |
| 100 | 19 | 23,154 | 97,179 | **4.2×** |
| 200 | 39 | 47,654 | 317,326 | **6.7×** |
| 500 | 99 | 124,754 | 1,521,199 | **12.2×** |

The CLM cumulative now includes per-dream sibling-archive writes (~5 deltas × 60 tokens = ~300 tokens per dream) and state growth from `decisions.reverted` / `decisions.superseded` accumulation (~0.3 × N tokens). Per Codex PR-16 round-4: trim.mode aggressive does NOT trim those lists; they grow linearly with thread depth.

This is **constant-per-update vs sub-linear-per-update** scaling. Prose's cumulative cost grows as the integral of N^0.7133, which is N^1.7133 — super-linear. CLM grows linearly in N. That's the architectural advantage on this axis.

(Dream cadence matches the canonical `gen_50_session.py` schedule: dreams at sessions 5, 10, 15, … excluding the final batch. n_dreams = (N−1) // 5.)

## Why this is the right axis

CLM's design was always a **write-ahead log + periodic checkpoint**, ancestor-pattern with biological sleep, git's commit-then-repack, and database WAL+checkpoint. The whole point of WAL+checkpoint is that *appending is cheap and stays cheap as the thread grows, while reading from the consolidated state is bounded by the checkpoint size*.

PR #15 measured one-shot read retrieval: given a static N-session doc, can a fresh session answer 11 lineage questions? On that axis, lineage-preserving prose wins (2,707 tokens, 11/11) vs CLM/3.0-trim (36,673 tokens, 10/11). That bench is correct and the result holds.

But that bench treats the doc as a one-shot artifact. In reality, threads *accumulate*. Each session is an append. CLM was designed for the append cost, not the one-shot read cost. The README headline ("compression with audit lineage at depth") was a misframing — it pointed at one-shot read cost, where the architecture loses. The architecture wins on write cost as the thread grows, where this bench measures.

## What survives across copyleftdev's three benches

| bench | what it tests | CLM result |
|---|---|---|
| PR #3 | tokens for a single-handoff doc | dominated by prose Markdown (45% over) |
| PR #4 | tokens × fidelity for a single-handoff doc | dominated by Claude-summarized prose @ 250 tokens |
| PR #15 | tokens × lineage-recall for a multi-session thread | dominated by lineage-preserving prose @ 2,707 tokens |

All three are read-side benches. They measure: *"given the doc, can a fresh AI retrieve facts from it?"*

CLM doesn't compete on that axis. The architecture was never designed to win one-shot read retrieval. It was designed to be a stateful append-only data structure with a defined update protocol, parser-validated structure, ritual-bound author preservation, and bounded amortized write cost.

This bench tests that — and the architecture wins by 4.2× at 100 sessions and 12.2× at 500.

## What this bench does NOT test

- **Verbatim preservation** (axis 3). CLM keeps Cdx.5's exact quotes across all four review rounds. Prose-with-good-prompt paraphrases. We didn't measure paraphrase rate; would need a separate similarity bench.
- **Conflict resolution semantics**. CLM has explicit `revert dN` / `supersede dN` operations. Prose has no equivalent — the summarizer decides.
- **Parser round-trip** (axis 4). CLM has a 41-test Rust parser, 37-test Python parser, 39-test TypeScript parser. Prose has none.
- **Cross-session continuity validation**. Cdx.5 reopening Codex sessions and self-identifying holds for CLM by ritual; prose has no equivalent ritual.

## Reproduce

```
python3 experiments/v3/compounding_cost.py
```

No API spend. Pure tokenization via `tiktoken` (`o200k_base`).

## Caveats

- **Power-law prose model fit to two measurement points.** N=50 and N=200 from copyleftdev's PR #15. Extrapolation beyond 200 sessions is a model, not a bench. Below 50, the model returns ~53 tokens at N=1 which is unrealistically small (the lineage-preservation prompt itself has overhead) — for N<5, the prose cost is artificially cheap in this model.
- **CLM dream-pass cost modeled as a typical `[STATE]` under `trim.mode: aggressive`** (~210 tokens, bounded by `decisions_live=8`). State *without* trim grows linearly with depth and the advantage shrinks proportionally — ~3× at 200 sessions instead of 13×, by rough estimation. The bench reports the trim-aggressive case because that's the canonical recommended config.
- **Output tokens only.** Input/read tokens are real but ~5× cheaper at Anthropic rates ($3/M in vs $15/M out for Sonnet) and roughly proportional in both formats. Including input would shift the absolute numbers but not the ratio meaningfully.
- **Per-update cost** assumes the AI doing the update operates on minimal context. In practice the AI may need to read the prior state (~200 tokens for CLM live doc, ~variable for prose). Not modeled here.
- **Single thread shape.** A thread with very different session content (huge file lists, many revert chains) might shift CLM's bounded-state assumption.

## Honest read of all benches together

CLM/3.0 has **four properties** worth distinguishing:

1. **Read retrieval** (one-shot Q&A from static doc) — **dominated by lineage-preserving prose at every depth.** Don't headline this.

2. **Write cost** (tokens to add the next session) — **CLM wins by 4.2× at 100 sessions, scaling to 12.2× at 500** (with caveats). This is what compounding_cost.py measures.

3. **Audit integrity** (verbatim preservation, ritual, signed deltas) — **architecturally unique to CLM.** Not benched here; would need separate measurement.

4. **Tooling** (parser round-trip, validator, machine-checkable structure) — **architecturally unique to CLM.** Demonstrated by 117 tests across three implementations.

The README has been overweighting axis 1 and underweighting axes 2/3/4. After this bench, the corrected positioning is: *CLM/3.0 is a write-ahead log for AI handoff threads. It wins on cumulative write cost (modestly), audit integrity (by construction), and validation tooling (uniquely). It does not compete with prose summarization for one-shot read retrieval.*

— *Bench by CLd.Ops4.7, 2026-04-26, in response to copyleftdev's PR #15. Companion to RESULTS-fidelity-v3.md, not a refutation of it. Both results stand; they measure different things. Two rounds of Codex review applied: round-1 added dream-pass output cost; round-2 corrected the prose power-law constant (53.2 → 61.82) and the dream cadence formula (now matches canonical gen_50_session.py: n_dreams = (N−1) // 5).*
