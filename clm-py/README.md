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

## What it validates

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

This package is a port of [`clm-rs`](https://github.com/TUNC-AI/tunc-clm/tree/main/clm-rs). The two implementations validate the same set of behaviors against the same canonical artifacts (`MANIFESTO.clm`, `SPEC.clm`, the `experiments/v3/` bench docs).

## Known limitations (v0.1, parity with `clm-rs`)

Three follow-ups documented in `experiments/v3/RESULTS.md` apply equally to this implementation:

1. `[DECISIONS.ARCHIVE]` cross-doc sentinel check is missing (symmetric gap to `[ROLL.CALL.ARCHIVE]` / `[DREAM.LOG.ARCHIVE]`).
2. Malformed lines in `decisions.live` aren't quarantined (counted toward overflow).
3. Generator (`experiments/v3/gen_50_session.py`) emits nonsense metadata for depths ≤ 5.

These will be fixed across all three implementations together.

## License

MIT.

## Audit thread

CLM is an append-only audit-thread format. The thread for `MANIFESTO.clm` and `SPEC.clm` is at https://github.com/TUNC-AI/tunc-clm — read it like any CLM file: open, sign, append.
