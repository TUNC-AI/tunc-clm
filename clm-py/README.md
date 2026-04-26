# tunc-clm (Python)

Parser and v3.0 trim-aware validator for the **Claude Memory Format**. Pure Python, no runtime dependencies, type-hinted.

```bash
pip install tunc-clm
```

```python
from clm import Document, validate_v3, validate_v3_with_filesystem

doc = Document.parse(open("MANIFESTO.clm").read())
assert str(doc) == open("MANIFESTO.clm").read()  # round-trip byte-identical

report = validate_v3(doc)
print(f"{len(report.errors)} errors, {len(report.warnings)} warnings")

# Filesystem-aware variant cross-checks the sibling archive
report = validate_v3_with_filesystem(doc, base_dir=".")
```

## CLI

```bash
clm validate path/to/file.clm
```

## What CLM is for

CLM/3.0 is a **write-ahead log for multi-session AI handoff threads**. Four axes; this package implements two of them:

1. **Read retrieval** — prose summary wins this axis; don't pick CLM for one-shot Q&A.
2. **Write cost** — CLM wins by 4.2× at 100 sessions, 12.2× at 500. (See [`experiments/v3/RESULTS-compounding-cost.md`](https://github.com/TUNC-AI/tunc-clm/blob/main/experiments/v3/RESULTS-compounding-cost.md).)
3. **Audit integrity** — verbatim preservation, signed deltas. CLM by ritual.
4. **Tooling** — parser round-trip + validator. **This package implements axes 3 and 4** in Python; the Rust and TypeScript packages do the same.

See the [main README](https://github.com/TUNC-AI/tunc-clm) for the full positioning, including links to the four review rounds where each marketing claim was iteratively narrowed by [@copyleftdev](https://github.com/copyleftdev)'s empirical work.

## What this validator checks

Per [`SPEC.clm`](https://raw.githubusercontent.com/TUNC-AI/tunc-clm/main/SPEC.clm) `validation.posture.v3.0`:

- Header declarations: `trim.mode`, `trim.config`, `archive.mode`, `archive.path`
- Trim-config grammar: keys / duplicates / missing values / unknown keys
- Lifecycle states A/B/C; declared offload via `(last X of Y archived)` form
- Sentinel placement (BEFORE entries, not after)
- Per-entry shape (`ROLL.CALL` needs `· YYYY-MM-DD ·`; `DREAM.LOG` needs `| YYYY-MM-DD |`); malformed quarantined
- Cross-doc sentinel symmetry (live ↔ archive)
- Archive structural check (must contain trim ARCHIVE sections, not just any file)
- Filesystem-aware variant (state.B → warning, state.C → error)
- Chained archive validation (warnings propagate from archive into live report)

## Mirror of the Rust reference

This package mirrors [`clm-rs`](https://github.com/TUNC-AI/tunc-clm/tree/main/clm-rs) and is paired with [`clm-js`](https://github.com/TUNC-AI/tunc-clm/tree/main/clm-js). All three implementations validate the same set of behaviors against the same canonical artifacts (`MANIFESTO.clm`, `SPEC.clm`, the `experiments/v3/` bench docs). 117 tests across all three.

## Known limitations (parity with `clm-rs` v0.2.0)

Three follow-ups from Codex round-8 review apply equally:

1. `[DECISIONS.ARCHIVE]` cross-doc sentinel check is missing (symmetric gap to `[ROLL.CALL.ARCHIVE]` / `[DREAM.LOG.ARCHIVE]`).
2. Malformed lines in `decisions.live` aren't quarantined (counted toward overflow).
3. Generator (`experiments/v3/gen_50_session.py`) emits nonsense metadata for depths ≤ 5.

## License

MIT.

## Audit thread

CLM is itself an append-only audit-thread format. The thread for `MANIFESTO.clm` and `SPEC.clm` is at https://github.com/TUNC-AI/tunc-clm — read it like any CLM file: open, sign, append.
