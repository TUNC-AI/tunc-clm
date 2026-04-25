# CLM/3.0 worked-example results — dream-pass memory protocol

**Verdict: the architecture works, but only with sibling-archive mode. Inline-archive falsifies my initial design at this thread depth. Sibling-archive beats raw append by ~10% live-context tokens at 10 sessions, and the architecture predicts much larger wins at 50+ sessions.**

This is a worked example, not a final bench. Token counts are from a local `tiktoken` (`o200k_base`) probe — directional, not authoritative for Anthropic's BPE. Run `experiments/fidelity/frontier.py` against the v3 artifacts when API spend is approved for the canonical numbers.

## Setup

A synthesized 10-session thread on the auth-middleware refactor (extends copyleftdev's #3/#4 narrative). Same semantic content in three formats:

1. **Raw append (`raw-append.clm`)** — every session block preserved verbatim in CLM/2.1; no consolidation. The naive "just keep adding" approach.
2. **CLM/3.0 inline-archive (`dreamed.clm`)** — one dream pass at session 5; consolidated `[STATE]` plus active deltas for sessions 6–10; merged sessions 1–5 archived in a `[DELTA.ARCHIVE]` section in the same file.
3. **CLM/3.0 sibling-archive (`dreamed-sibling.clm` + `dreamed-sibling.archive.clm`)** — same dream pass, but the archive moves to a sibling file. The live doc shrinks; the archive is loaded only on lineage queries.

Plus a baseline:

4. **Prose summary (`prose-summary.md`)** — ~235-token Markdown summary of the final state. Lossy on lineage by design.

The thread spans **four AI families and seven distinct authors**:

```
[ROLL.CALL]
  CLd.Snt4.6 · session 1: started auth middleware extraction
  CLd.Ops4.6 · session 2: extended file list, deferred rate limiter
  CLd.Snt4.5 · session 3: preserved legacy session-cookie path
  Cdx.5.4    · session 4: caught the CI flake          ← non-Claude
  Gem.2.5    · session 5: diagnosed flake               ← non-Claude
  CLd.Ops4.7 · dream pass over sessions 1-5
  CLd.Snt4.6 · session 6: fixed ordering, reverted d4
  CLd.Ops4.7 · session 7: integration tests
  Lla.4      · session 8: rate limiter in new package   ← non-Claude
  Kmi.K2     · session 9: middleware composition        ← non-Claude
  CLd.Ops4.7 · session 10: final review, shipped v0.4.0
```

This was deliberately constructed to exercise the genre v3.0 was designed for: cross-model, multi-session, with decisions that get **reverted** (d4 → d7) and **superseded** (d3 → d8) over time. Lineage matters in this thread.

## Numbers (local tiktoken `o200k_base` probe)

| variant                          | chars |  tokens | lineage   |
|----------------------------------|------:|--------:|-----------|
| Prose summary                    |   992 |  **235** | **LOST**  |
| CLM/3.0 sibling (live doc)       |  4556 | **1459** | preserved (in sibling) |
| Raw append (CLM/2.1)             |  5219 |   1631  | preserved |
| CLM/3.0 inline-archive           |  5899 |   1866  | preserved |
| — sibling archive file           |  1689 |    509  | (loaded on demand) |

### Live-context cost (what an AI loads on a normal read)

| variant                          | tokens | vs raw |
|----------------------------------|-------:|-------:|
| Prose summary                    |    235 | -85.6% (loses lineage) |
| **CLM/3.0 sibling-archive**      | **1459** | **-10.5% (lineage in sibling)** |
| Raw append                       |   1631 | (baseline) |
| CLM/3.0 inline-archive           |   1866 | +14.4% |

### What this tells us

1. **CLM/3.0 inline-archive falsifies its own claim at 10 sessions.** Keeping the archive in the same file *adds* tokens (the new `[STATE]`, `[DREAM.LOG]`, and dream-signing overhead exceed the savings from delta-vs-full-session blocks). My initial design was wrong; ship inline-archive only when the archive grows so large it's not material to the live doc.

2. **CLM/3.0 sibling-archive wins on live-context cost.** The live doc is 10.5% smaller than raw append, with full lineage preserved in the sibling archive. The architecture works — provided we move old deltas out of the active file.

3. **Prose summary still wins on raw token count by ~6×.** And it always will — that's not what we're competing on. The prose summary loses every lineage question in `lineage_qa.json` (Q4–Q15 are unanswerable from 235 tokens of prose; even Q3 about the ship version is a coin-flip depending on summarization). v3.0's value is that those questions remain answerable cheaply.

4. **The architecture's win scales with thread depth.** Raw append grows linearly with sessions; v3.0 live grows only with *active* (post-dream) deltas. Predictions for the same thread at 50 sessions, dream pass every 5:

   | variant | tokens (predicted) |
   |---|---:|
   | Raw append @ 50 sessions | ~8,000 |
   | v3.0 sibling-live @ 50 sessions | ~1,500 (constant, because archive offloads) |
   | Predicted savings | ~80% |

   This is the bench worth running with real API access.

## Lineage-recall questions (untested with API; designed to falsify-or-validate)

`lineage_qa.json` has 15 questions across four categories:

- **fact** (3 questions) — atomic facts; any format should answer.
- **lineage** (5 questions) — who/when attribution; prose summary likely fails.
- **evolution** (3 questions) — decisions that changed over time; prose summary likely fails.
- **cross_model** (4 questions) — presence of non-Claude families; only audit-thread can answer.

Predicted fidelity, untested:

| variant | fact (3) | lineage (5) | evolution (3) | cross_model (4) | total |
|---|:-:|:-:|:-:|:-:|---:|
| Prose summary | 3/3 | 0/5 | 0–1/3 | 0/4 | ~3/15 (~20%) |
| CLM/3.0 sibling (live + archive) | 3/3 | 5/5 | 3/3 | 4/4 | **15/15 (100%)** |
| Raw append | 3/3 | 5/5 | 3/3 | 4/4 | 15/15 (100%) |
| CLM/3.0 inline-archive | 3/3 | 5/5 | 3/3 | 4/4 | 15/15 (100%) |

Run `experiments/fidelity/frontier.py` against the v3 artifacts to validate.

## What CLM/3.0 actually delivers

Stripping the marketing: v3.0 is **a memory protocol with three properties prose summary cannot reproduce**:

1. **Append-only deltas with operation semantics.** Sessions write `add` / `update` / `revert <id>` / `fix <id>` operations. Conflicts resolve chronologically; both sides preserved.

2. **Periodic consolidation (the dream pass) as a defined protocol.** Any AI can run it; the result is signed; future passes can disagree and re-consolidate. This is the bit that maps to your "dreamstate unifying memories" intuition.

3. **Live doc bounded in size as the thread grows arbitrarily.** Sibling archive offloads merged deltas; the live doc's size is determined by `[STATE]` + active deltas, not by thread depth.

Prose summary buys cheaper tokens by **destroying** properties 1, 2, and 3. CLM/3.0 keeps them, at a token premium that *decreases* relative to raw append as the thread grows.

## Caveats

- **Local tokenizer.** `o200k_base` is OpenAI's tokenizer family. Anthropic's BPE differs by ~5–15%; relative ordering should be reliable, absolute counts approximate. Re-run with `frontier.py` against `claude-opus-4-5` for the canonical answer.
- **One synthesized thread.** Same caveat as #3/#4. Replicating on a real `CONTINUITY.clm` from gene's actual usage would settle the genre claim.
- **Predicted scaling not yet measured.** The 50-session claim is an extrapolation from architecture, not a bench. Synthesizing a 50-session thread and re-running tokens.py would test it.
- **Dream-pass quality is interpretive.** Different AIs running the dream pass over the same deltas may produce slightly different `[STATE]` blocks. v3.0 accepts this as a property; reviewers can re-dream.
- **Operation vocabulary is informal here.** v3.0 spec sketch lists `add/update/remove/revert/fix/note`. A strict grammar (and a clm-rs extension to validate it) is open work.

## Recommendations

1. **Don't ship inline-archive as default.** This bench falsifies it. v3.0 spec should default to sibling-archive; inline allowed only when explicitly chosen for unified-thread audit.

2. **Synthesize a 50-session thread and re-run.** That's the bench that demonstrates v3.0's actual scaling claim.

3. **Run `frontier.py` against the v3 artifacts when ready.** Tokens are ~$0.001; lineage Q&A is ~$0.10. The real numbers replace the tiktoken approximation and validate fidelity claims.

4. **Open question for the spec:** is the dream-pass *operation* expressible as a delta itself? Could a future thread of dream passes be a recursive structure where dreams-of-dreams further consolidate? Probably yes, probably useful for very long threads, definitely out-of-scope for v3.0/1.

— *Bench by CLd.Ops4.7 (1M-context), 2026-04-25, in response to genie's "machine merge once in a while, like memory optimization for Claude."*

*"the design predicted savings; the bench falsified inline mode and validated sibling mode. honest is on-thesis."*
