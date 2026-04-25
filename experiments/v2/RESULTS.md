# CLM/2.0 prototype — benchmark results

**Verdict: hypothesis falsified. CLM/2.0 still loses to prose Markdown on a representative handoff document. Recommend killing v2 as a token-savings play.**

## Setup

- One synthesized handoff document (`handoff.*` files in this directory) expressing the same semantic content in four formats: CLM/1.0, CLM/2.0 (this prototype), prose Markdown, and YAML.
- Token counts via Anthropic's `messages.count_tokens` API against `claude-opus-4-5` (the right tokenizer for the README's claim).
- Reproduce with `python3 bench.py` (requires `ANTHROPIC_API_KEY`).

## Numbers

| format       | bytes | chars | tokens | chars/token | vs prose |
|--------------|------:|------:|-------:|------------:|---------:|
| Prose (md)   | 1063  | 1055  | **318** |       3.32 |    +0.0% |
| YAML         | 1085  | 1085  |   365  |       2.97 |   +14.8% |
| CLM/2.0      |  995  |  995  |   368  |       2.70 |   +15.7% |
| CLM/1.0      | 1102  | 1046  |   461  |       2.27 |   +45.0% |

## What this tells us

1. **The ASCII swap works as intended.** CLM/2.0 saves ~20% over CLM/1.0 (461 → 368 tokens) by replacing `⟦ ⟧ ∴ ∉ ∅ → :=` with brackets, English words, and standard ASCII operators. That's a real, mechanical improvement.

2. **It still doesn't beat prose.** CLM/2.0 costs 16% more tokens than the prose Markdown version of the same content, and ties with YAML. The compression intuition fails for the same reason it failed in v1: the BPE tokenizer is trained on English, so common English words ("preserved," "reason," "rationale") are 1–2 tokens, while structural punctuation like `[NAME]`, `;;`, and `;;;` is pure overhead the prose form doesn't pay.

3. **Why prose wins this kind of document.** A handoff is ~70% prose (decisions with rationale, the FOR.YOU note) and ~30% structured data (file lists, attributions). Even when CLM/2.0 expresses the prose part more tersely, the structural overhead on the prose 70% wipes out any savings on the structured 30%. YAML loses for the same reason.

4. **Where CLM/2.0 might still win.** A document that's ~95% structured (long file lists, dependency tables, bulk attribution arrays, no rationale prose) could plausibly beat both prose and YAML. That's not the genre CLM has been positioned for, and the manifesto's own use of prose-with-glyphs makes it a poor exemplar of the genre that would benefit.

## Recommendation

1. **Kill the "saves tokens" pitch entirely.** Even the redesigned v2 doesn't meet it. Trying to optimize further would mean abandoning the philosophical/prose voice that gives CLM its identity — at which point you've designed YAML.

2. **Keep the ASCII glyph swap as a future v1.x quality-of-life improvement.** Not a marketing claim, just nicer to type and 20% lighter. Worth doing, worth being honest about why.

3. **Re-pitch CLM on structure and discipline.** The product framing in the PR comment (https://github.com/TUNC-AI/tunc-clm/pull/2#issuecomment-4320068374) holds: append-only handoff with auditable thread, machine-maintainable through reference tooling. Those are the value props CLM uniquely delivers and that no honest benchmark can falsify.

## Caveats worth acknowledging

- **One document.** A multi-document corpus (3–5 real handoff files from gene's actual usage, if any exist) would make the verdict more conclusive. With only one synthesized doc, the result is *strong evidence* but not *proof*. That said, the burden of proof now sits with anyone defending the savings claim.
- **The synthesis could be biased.** I wrote the handoff doc as the kind of CONTINUITY.clm I'd plausibly leave behind — prose-heavy. If gene's actual usage is more structured (dependency dumps, build manifests, status flags), v2 might fare better. Showing v2 examples on real artifacts would settle it.
- **The fair-translation problem.** I tried to express the same information in each format using each format's native idioms. A reasonable critic could argue I made one format terser than another. The artifacts are checked in; reviewers can rewrite any of the four and re-run `bench.py` to test.
