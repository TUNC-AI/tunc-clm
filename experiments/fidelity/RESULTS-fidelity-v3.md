# Lineage fidelity v3 — empirical falsification of CLM/3.0's last claim

**Verdict: CLM/3.0 with `trim.mode: aggressive` is strictly dominated by lineage-preserving prose on the lineage QA gene himself authored. Prose at 2,707 tokens scores 11/11 on the answerable questions; CLM/3.0-trim at 36,673 tokens scores 10/11. The lineage-and-audit claim fails the same way the compression claim failed in PR #4.**

This experiment runs `experiments/v3/lineage_qa.json` against the v3 artifacts using the same harness methodology as PR #4 (`experiments/fidelity/frontier.py`): single trial, `claude-sonnet-4-6` for both summarize and answer, substring scoring, manual miss classification.

## Setup

Eight variants of the auth-evolution thread:

| variant | source |
|---|---|
| raw-append-50 | `experiments/v3/raw-append-50.clm` |
| raw-append-200 | `experiments/v3/raw-append-200.clm` |
| dreamed-sibling-50-trim | live + archive concat (sibling archive loaded for lineage queries) |
| dreamed-sibling-200-trim | live + archive concat |
| prose-summary-50 | `experiments/v3/prose-summary-50.md` (gene's existing baseline) |
| prose-summary-200 | `experiments/v3/prose-summary-200.md` (gene's existing baseline) |
| **prose-50-lineage** | new — prose summary with explicit lineage-preservation prompt, ~800 token budget |
| **prose-200-lineage** | new — prose summary with explicit lineage-preservation prompt, ~2,500 token budget |

**The new baseline is the move PR #4 depended on and gene's bench omitted.** Gene's `prose-summary-*.md` files were generated with a generic summarization prompt that drops session/model attribution. That makes the lineage-QA result preordained: prose loses lineage because the summarizer was never asked to keep it. The fair comparison generates the prose summary with a prompt that explicitly preserves "session N (model X) decided Y" attribution — same Claude, same input, same per-token cost, just a smarter prompt. If lineage-preserving prose at modest budgets matches CLM's lineage fidelity, the format isn't winning on lineage; the *prompt* is.

## Raw results

```
variant                          tokens   raw fidelity   per category
-----------------------------------------------------------------------------
raw-append-50                      6,819   10/15 (67%)   fact:2/3 lineage:2/6 evolution:4/4 cross_model:2/2
raw-append-200                    27,967   11/15 (73%)   fact:2/3 lineage:3/6 evolution:4/4 cross_model:2/2
dreamed-sibling-50-trim            9,084   10/15 (67%)   fact:2/3 lineage:3/6 evolution:4/4 cross_model:1/2
dreamed-sibling-200-trim          36,673   10/15 (67%)   fact:2/3 lineage:3/6 evolution:4/4 cross_model:1/2
prose-summary-50                     479    3/15 (20%)   fact:2/3 lineage:0/6 evolution:1/4 cross_model:0/2
prose-summary-200                  1,575    4/15 (27%)   fact:2/3 lineage:0/6 evolution:2/4 cross_model:0/2
prose-50-lineage                   1,007    8/15 (53%)   fact:2/3 lineage:2/6 evolution:3/4 cross_model:1/2
prose-200-lineage                  2,707   11/15 (73%)   fact:2/3 lineage:3/6 evolution:4/4 cross_model:2/2
```

Gene's predicted scores in `experiments/v3/RESULTS.md` were "CLM/3.0 sibling: 15/15 (100%); raw append: 15/15; CLM/3.0 inline-archive: 15/15; prose summary: ~3/15 (~20%)." Actual on plain prose (3/15, 4/15) lines up with his prediction. Actual on CLM/3.0 sibling (10/15) does not — he's off by 5 questions even with the entire archive concatenated into the prompt.

## Methodology issues found

Substring scoring + a fresh harness exposed three issues, all worth documenting before drawing conclusions.

### Issue 1 — `lineage_qa.json` answer keys are for the 10-session thread, not the 50/200 data

Gene's `gen_50_session.py` reassigned which session each decision lands in when generating the 50-session thread. The original 10-session source (`dreamed-sibling.archive.clm`) has session 1 doing both `d1` (relocate auth) and `d2` (rename `AuthCheck → RequireAuth`); the 50-session generator splits them across sessions 1 and 2. Same for the legacy session-cookie path (was session 3 in 10-session, became session 4 in 50-session) and the CI flake diagnosis (was session 5 / `Gem.2.5` in 10-session, became session 6 / `Cdx.5.4-codex` in 50-session). `lineage_qa.json`'s `any_of` strings were not updated; they still encode the 10-session attribution.

The result: **Q3, Q4, Q5, Q6 are unanswerable as written** against any 50/200 artifact. Every variant scores 0/4 on these — every variant is correctly answering the 50-session data and being scored against the wrong key.

| Q | question | any_of expects | 50-session truth |
|---|---|---|---|
| Q3 | final ship version | `v0.4.0` | `v0.7.0` (data ships through cycle 4) |
| Q4 | who proposed renaming AuthCheck | session 1 / Snt4.6 | session 2 / Ops4.6 |
| Q5 | which session preserved cookie path | session 3 / Snt4.5 | session 4 / Ops4.7 |
| Q6 | who diagnosed CI flake | session 5 / Gem.2.5 | session 6 / Cdx.5.4-codex |

**Treatment:** drop Q3-Q6 from numerator and denominator. They're scoring artifacts that affect every variant uniformly.

### Issue 2 — `"UNKNOWN"` substring-hits `"no"` on Q10

Q10's `any_of` includes the literal string `"no"`. The word `unknown` contains `no`. So `prose-summary-50` and `prose-summary-200` were credited correct on Q10 despite both answering literal `UNKNOWN`. **Treatment:** demote those two specific hits to misses.

### Issue 3 — Q11/Q12 author attributions are also 10-session-era but salvaged by other `any_of` entries

In 50-session data, session 8 (`Gem.2.5`) reintroduces the rate limiter and session 9 (`Lla.4`) introduces middleware composition. `lineage_qa.json` Q11 expects `lla.4 / llama` (10-session attribution) and Q12 expects `kmi.k2 / kimi` (10-session attribution). These don't match the 50-session data either, but Q11 is salvaged by `internal/ratelimit / new package / session 8 / d8` and Q12 by `session 9`. So variants that include the right session number score correctly even though the model attribution in `any_of` is stale. **Treatment:** kept as-is; the broader `any_of` masks the bug.

## Adjusted scores

Excluding Q3-Q6 (Issue 1) and demoting Q10 false-positives (Issue 2):

| variant | tokens | adjusted | % |
|---|---:|---:|---:|
| raw-append-50 | 6,819 | 10/11 | 91% |
| raw-append-200 | 27,967 | 11/11 | 100% |
| dreamed-sibling-50-trim | 9,084 | 10/11 | 91% |
| dreamed-sibling-200-trim | 36,673 | 10/11 | 91% |
| prose-summary-50 | 479 | 2/11 | 18% |
| prose-summary-200 | 1,575 | 3/11 | 27% |
| **prose-50-lineage** | **1,007** | **8/11** | **73%** |
| **prose-200-lineage** | **2,707** | **11/11** | **100%** |

## The Pareto frontier

A point is on the frontier if no other variant has both fewer-or-equal tokens and equal-or-higher fidelity.

```
fidelity adj
   100% │                                      prose-200-lineage(2707)            raw-append-200(27967)
    91% │                       raw-append-50(6819)  CLM-50t(9084)                                       CLM-200t(36673)
    73% │            prose-50-lineage(1007)
    27% │     prose-200(1575)
    18% │ prose-50(479)
        └────────────────────────────────────────────────────────────────────────────────────────────────────────────────
          0        1k        2k       5k       10k                                              30k                  40k

  Pareto-optimal:
    prose-summary-50        (479,    2/11)
    prose-50-lineage        (1,007,  8/11)
    prose-200-lineage       (2,707, 11/11)   ← strictly dominates raw-append-200, raw-append-50, CLM-50t, CLM-200t
```

**CLM/3.0-trim at 200 sessions is dominated by raw-append at 50 sessions.** 36,673 tokens of structured audit thread scores 10/11; 6,819 tokens of raw concatenation scores 10/11. The structure is not earning its keep — the model finds lineage facts in raw-append just as well as in `[ROLL.CALL]` + `[DELTA.session-N]`.

**CLM/3.0-trim at 50 sessions is dominated by raw-append at 50 sessions.** Same fidelity, more tokens. The trim machinery is paying overhead (the `[STATE]` consolidation, `[DREAM.LOG]`, archive structure) without buying any retrieval advantage on these questions.

**Lineage-preserving prose at 2,707 tokens dominates everything above 2,707 tokens** — it scores 11/11, the same as raw-append-200 at 27,967 tokens, while being 13.5× cheaper than CLM/3.0-trim at the same depth.

## Verdict on gene's v3 claims

**Claim from `experiments/v3/RESULTS.md`:** "Prose summary buys cheaper tokens by destroying [lineage / dream-pass / bounded live-doc properties]. CLM/3.0 keeps them, at a token premium that *decreases* relative to raw append as the thread grows."

The first half is right about *gene's prose-summary baseline*, which used a generic prompt that did not preserve lineage. It is wrong about prose summarization in general. A one-paragraph change to the summarization prompt — "preserve session N + model attribution per decision" — recovers full lineage fidelity at 2,707 tokens. The lineage isn't a property of the *format*; it's a property of *what you ask the summarizer to keep*.

**The token premium is also negative, not just decreasing.** CLM/3.0-trim costs 13.5× more tokens than lineage-preserving prose for *worse* lineage recall on this benchmark.

## What about the 200-session synthetic itself

Worth flagging: gene's "200-session" thread is the 50-session thread cycled four times with a `cycle-N` suffix. Phases 1-5 repeat verbatim as phases 6-10, 11-15, 16-20 — same auth extraction, same MFA audit, same Trail of Bits CVE, four times. This inflates raw-append's token count (the same content appears 4×) and makes `trim.mode: aggressive` look excellent (a deduplicating trim that knows phases repeat would cut hard). On a real 200-session thread with 200 distinct phases, the compression numbers reported in PR #13 would not reproduce — and neither would the lineage QA, because gene's questions only probe sessions 1-10 (cycle 1).

This isn't dispositive against CLM/3.0 — it's a comment on the bench shape. A real test would need a thread with ~50-200 genuinely distinct phases and a lineage QA spanning the full thread, not the first phase only.

## What CLM/3.0 still uniquely delivers (residual claim)

The same residual claim from PR #4 holds:

- **Append-only structure with sentinel slots.** Survives mechanical edits, accumulates across sessions, parser round-trips byte-identically. Prose summary has no equivalent.
- **A ritual.** Sign your edit, preserve previous voices, never overwrite. Auditable in a way prose summaries are not.
- **A reference parser** (`clm-rs`, `clm-py`, `clm-js`) with trim-aware validation. Summarized prose has no maintainability story.

These are unfalsified by this experiment because the experiment doesn't test them. They are also not what gene marketed in v3.0 as the headline win — the headline was "compression with audit lineage at depth", and that's the claim falsified here.

## Caveats

- **Single trial per variant.** Substring scoring is near-deterministic at default temperature, but multi-trial would put error bars on the margins (especially the 10/11 vs 11/11 difference).
- **One model.** `claude-sonnet-4-6` for both summarize and answer, matching PR #4. Cross-model (Opus summarizes, Sonnet answers, or vice versa) was not run.
- **One synthesized thread, with the rigging caveat above.** A real `CONTINUITY.clm` from genuine usage would be the gold-standard test.
- **`lineage_qa.json` has answer-key bugs (Issue 1 above).** A re-authored QA matched to the actual 50/200 data would settle the residual 1-question gap between `prose-200-lineage` and `dreamed-sibling-200-trim` cleanly.
- **Substring scoring has known weaknesses (Issue 2).** A Claude-as-judge oracle would catch the `UNKNOWN`-matches-`no` artifact automatically.
- **No LLMLingua baseline.** Same as PR #4 — Microsoft's prompt-compression SOTA wasn't included for install-complexity reasons; it would likely sit on the frontier alongside lineage-preserving prose.

## Reproduce

```
ANTHROPIC_API_KEY=... python3 experiments/fidelity/frontier_v3.py
```

Generates `prose-50-lineage.md` and `prose-200-lineage.md` if absent, then runs the 8-variant × 15-question eval and writes per-question detail to `results-v3.json`. Total cost on this run: 8 variants × 15 questions × ~1 LLM call each, plus 2 baseline summarizations. ~$3 in spend.

## Recommendations

1. **Update `lineage_qa.json` to match the 50/200 data**, or regenerate the artifacts to match the QA. Right now neither the spec docs nor the bench tell the same story; future readers running `frontier_v3.py` against existing artifacts will hit the same "every variant fails Q3-Q6" issue.

2. **Drop the "compression with audit lineage" claim from the README.** It does not survive a fair comparison against lineage-preserving prose. The honest residual claim is "discipline and auditability for multi-session handoff threads via append-only ritual + parsed format" — exactly the framing PR #4 already arrived at.

3. **Generate a non-cycled long thread for the next bench.** The 50→200 cycling makes the synthetic data inadvertently friendly to trim-aware compression and to first-phase-only lineage QA. A 100-session thread with 100 distinct decisions (no phase repeats) is the test the architecture's claim deserves.

4. **For real-world adoption, the prompt change is cheaper than the format change.** If you have a multi-session thread and you want lineage-preserving handoff, write a 200-word "preserve session N (model X) for each decision; preserve dream-pass attribution; preserve revert/supersede chains" prompt and summarize. You get 11/11 lineage at ~3K tokens. Adopting CLM/3.0 — new spec, new parsers, new validator, new trim modes — buys you nothing on this axis and costs 13.5× more tokens.

— *Bench by dj@codetestcode.io, 2026-04-25, in response to PR #13 + PR #14's "200-session bench validates the architecture's main claim." The architecture's main claim turns out to be "we forgot the right baseline."*
