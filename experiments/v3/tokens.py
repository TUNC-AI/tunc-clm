"""Local token-count probe for v3.0 worked example.

Uses tiktoken with o200k_base (OpenAI's GPT-4o tokenizer family) as a
ballpark approximation of Anthropic's BPE. The two BPE tables differ,
so absolute numbers will be off by ~5-15% from claude-opus-4-5's
count_tokens API. Relative ordering of formats is reliable.

This script runs offline. No API key required. Use the existing
experiments/v2/bench.py and experiments/fidelity/frontier.py for
authoritative Anthropic numbers when you're willing to spend pennies
of API credit.

Usage:
    pip install tiktoken
    python3 tokens.py
"""
from __future__ import annotations

from pathlib import Path

import tiktoken

HERE = Path(__file__).parent
ENC = tiktoken.get_encoding("o200k_base")

VARIANTS = [
    ("Raw append (CLM/2.1)",       "raw-append.clm",            False),
    ("CLM/3.0 inline-archive",     "dreamed.clm",               False),
    ("CLM/3.0 sibling (live)",     "dreamed-sibling.clm",       True),
    ("  + sibling archive file",   "dreamed-sibling.archive.clm", True),
    ("Prose summary",              "prose-summary.md",          False),
]


def count_tokens(text: str) -> int:
    return len(ENC.encode(text))


def main() -> None:
    rows = []
    for label, name, _ in VARIANTS:
        text = (HERE / name).read_text()
        rows.append((label, len(text), count_tokens(text)))

    headers = ("variant", "chars", "tokens")
    print(f"{headers[0]:<32}{headers[1]:>8}{headers[2]:>10}")
    print("-" * 53)
    for label, chars, toks in rows:
        print(f"{label:<32}{chars:>8}{toks:>10}")

    summary = next(t for label, _, t in rows if label.startswith("Prose"))
    raw = next(t for label, _, t in rows if label.startswith("Raw"))
    inline = next(t for label, _, t in rows if "inline" in label)
    sibling_live = next(t for label, _, t in rows if label == "CLM/3.0 sibling (live)")
    sibling_archive = next(t for label, _, t in rows if "archive file" in label)
    sibling_total = sibling_live + sibling_archive

    print()
    print("--- live-context cost (what an AI loads on a normal read) ---")
    print(f"Prose summary (lossy on lineage):     {summary:>5} tokens")
    print(f"CLM/3.0 sibling (live doc):           {sibling_live:>5} tokens   ← the realistic v3.0 cost")
    print(f"Raw append:                           {raw:>5} tokens")
    print(f"CLM/3.0 inline-archive:               {inline:>5} tokens")
    print()
    print("--- total cost (everything stored, including archive) ---")
    print(f"CLM/3.0 sibling (live + archive):     {sibling_total:>5} tokens   (loaded only on lineage queries)")
    print()
    print("--- deltas ---")
    if sibling_live < raw:
        pct = (raw - sibling_live) / raw * 100
        print(f"v3.0 sibling-live vs raw append:      -{pct:.1f}%   (lineage preserved in sibling archive)")
    if sibling_live > summary:
        pct = (sibling_live - summary) / summary * 100
        print(f"v3.0 sibling-live vs prose summary:   +{pct:.1f}%   (BUT lineage queryable; summary destroys it)")
    if inline > raw:
        pct = (inline - raw) / raw * 100
        print(f"v3.0 inline-archive vs raw append:    +{pct:.1f}%   ← falsifies inline mode for short threads")
    print()
    print("Caveat: o200k_base differs from Anthropic's BPE by ~5-15% in absolute count.")
    print("Run experiments/v2/bench.py + experiments/fidelity/frontier.py for authoritative numbers.")


if __name__ == "__main__":
    main()
