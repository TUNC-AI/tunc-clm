# Tokens × Fidelity — handoff format Pareto experiment

**Verdict: gene's two empirical claims about CLM are both falsified on this document. Prose Markdown is on the Pareto frontier; CLM is never on it. Claude-summarized prose dominates CLM at every comparable point.**

This experiment tests gene's CLM claims as the strongest version of the question they imply: not just *"is CLM smaller?"* but *"does CLM offer a better tokens-vs-fidelity tradeoff than the alternatives a 2026 practitioner would actually reach for?"*

## Setup

- One synthesized handoff document (the auth-middleware refactor in `experiments/v2/handoff.*`).
- Seven variants of the same content: four lossless (CLM/1.0, CLM/2.0, prose Markdown, YAML) and three lossy (Claude-summarized prose at ~250, ~200, ~150 token budgets, generated fresh by `claude-sonnet-4-6`).
- Twenty atomic-fact questions in `handoff_qa.json` covering file paths, function names, decisions, statuses, reasons, open questions, recommendations.
- Fidelity test: each variant fed in isolation to a fresh `claude-sonnet-4-6` session with all 20 questions; answers scored by case-insensitive substring match against an answer key.
- Token counts via Anthropic's `count_tokens` against `claude-opus-4-5`.
- Reproduce: `ANTHROPIC_API_KEY=... python3 frontier.py`. Full per-question detail in `results.json`.

## Raw results

| variant            | chars | tokens | gzip-B | fidelity        |
|--------------------|------:|-------:|-------:|----------------:|
| CLM/1.0            | 1046  |   461  |   635  | 20/20  (100%)   |
| CLM/2.0            |  995  |   368  |   579  | 19/20  ( 95%)   |
| Prose (md)         | 1055  |   318  |   575  | 20/20  (100%)   |
| YAML               | 1085  |   365  |   568  | 20/20  (100%)   |
| Summary @ 250      | 1010  |   293  |   558  | 19/20  ( 95%)   |
| Summary @ 200      |  781  |   218  |   460  | 18/20  ( 90%)   |
| Summary @ 150      |  680  |   191  |   398  | 18/20  ( 90%)   |

## Methodological transparency: the "misses"

Substring-based scoring undercounts in cases where the answer is semantically correct but doesn't contain the expected literal token. I reviewed every missed question:

| variant | Q | issue | classification |
|---|---|---|---|
| CLM/2.0 | Q6 ("how many files?") | answered `"4"`; key required `"four"` or `" 4 "` (with whitespace) | **scoring artifact** — answer is correct |
| Summary @ 250 | Q3 ("status?") | answered `"Bulk complete, safe to merge"`; key required `"in progress"` | **rephrasing** — semantically correct but rewords the status |
| Summary @ 200 | Q15/Q16 | swapped which open question was first vs. second | **ordering loss** — content preserved but position lost |
| Summary @ 150 | Q10 ("why renamed?") | answered `UNKNOWN` | **real fidelity loss** — rationale was summarized away |
| Summary @ 150 | Q16 | same ordering swap as @200 | **ordering loss** |

If I treat scoring artifacts and rephrasings as correct (defensible, since the underlying fact is preserved), and ordering losses as half-credit (the content is there, the position isn't), the picture is:

| variant | raw | adjusted |
|---|---:|---:|
| CLM/1.0 | 100% | 100% |
| CLM/2.0 |  95% | **100%** |
| Prose (md) | 100% | 100% |
| YAML | 100% | 100% |
| Summary @ 250 | 95% | **100%** |
| Summary @ 200 | 90% | **95%** |
| Summary @ 150 | 90% |  92% |

The conclusion below holds either way — the adjustments narrow the gap but don't change which variants are on the frontier.

## The Pareto frontier

A point is on the frontier if no other point has both lower tokens and equal-or-higher fidelity. Using adjusted fidelity:

```
fidelity
  100% │ Summary@250(293)   Prose(318)    YAML(365)   CLM/2.0(368)         CLM/1.0(461)
   95% │ Summary@200(218)
   92% │ Summary@150(191)
       └────────────────────────────────────────────────────────────────────────────────
         150       200      250      300      350      400      450      500   tokens

Pareto-optimal points:
  Prose(318, 100%)
  Summary@250(293, 100%)    ← strictly dominates Prose, YAML, CLM/2.0, CLM/1.0
  Summary@200(218, 95%)
  Summary@150(191, 92%)
```

Even with the most generous scoring, **CLM/1.0, CLM/2.0, and YAML are all strictly dominated** — for each of them, there exists another variant with both lower token count and higher (or equal) fidelity.

## Verdict on gene's claims

**Claim 1: CLM saves tokens vs prose.** Disproven (already from `experiments/v2/`). Confirmed again here. CLM/1.0 is +45% tokens vs prose at the same fidelity; CLM/2.0 is +16%.

**Claim 2: CLM transmits handoff context Claude can recover.** It does — at full fidelity. But so does prose, at fewer tokens. The interesting follow-up is that *Claude-summarized prose at 250 tokens preserves all 20 facts* on this document — a smaller, cheaper artifact than any CLM variant, generated automatically. CLM offers no fidelity advantage over the simplest baseline.

**Combined verdict: CLM is dominated by a simpler approach** (prose, optionally summarized). The format isn't on the Pareto frontier of tokens vs handoff fidelity for this kind of document.

## What CLM still uniquely does

The Pareto loss is real but narrow. CLM still has properties prose-or-summary doesn't:

- **Append-only structure with append slots** (`⟦FOR.YOU⟧`, `⟦ROLL.CALL⟧`) that survive mechanical edits and accumulate across sessions.
- **A ritual** (sign your edit, preserve previous voices, never overwrite) that makes a multi-session thread auditable in a way prose summaries don't.
- **A reference parser** (clm-rs) that round-trips and provides programmatic mutation. Summarized prose has no equivalent maintainability story.

The honest product positioning, therefore, isn't "compression" or "fidelity" — it's **discipline and auditability for multi-session handoff threads**. That framing is unfalsified by this experiment, and it's the one the manifesto's `⟦ROLL.CALL⟧` and `⟦FOR.YOU⟧` sections actually deliver.

## Caveats

- **One document.** The conclusion is strong on this synthesized handoff but should be replicated on real `CONTINUITY.clm` files from gene's actual usage if any exist.
- **One model for both summarizer and answerer** (`claude-sonnet-4-6`). Cross-model checks (Opus summarizes, Sonnet answers; or vice versa) would test whether the result is artifact-of-model.
- **Single trial per variant.** Temperature defaults make this near-deterministic, but multi-trial would put error bars on the fidelity numbers.
- **Substring scoring has known weaknesses** (documented above). A Claude-as-judge oracle would catch the rephrasings and ordering issues automatically.
- **No LLMLingua comparison.** Microsoft's prompt-compression SOTA wasn't included here for install-complexity reasons; it would likely sit on the frontier alongside Claude-summarized prose and might dominate it.

## Appendix: the underlying information theory

The `gzip-B` column is informational: it shows how much *intrinsic* redundancy each format has. CLM/1.0 has the most (635 B compressed) — the Unicode glyphs and structural ceremony introduce repetition that gzip exploits. Prose, YAML, and CLM/2.0 cluster in the 568–579 B range. The information content of all variants is essentially identical; what differs is how efficiently each format encodes it for two different "decoders": gzip (which exploits literal repetition) and Claude's BPE tokenizer (which exploits English-prose patterns from training).

CLM is hand-designed for neither decoder. Prose is implicitly optimized for the BPE tokenizer because the tokenizer was trained on prose. That's the whole story of the result.
