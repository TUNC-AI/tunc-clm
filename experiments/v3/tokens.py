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

VARIANTS_10 = [
    ("Raw append (CLM/2.1)",       "raw-append.clm"),
    ("CLM/3.0 inline-archive",     "dreamed.clm"),
    ("CLM/3.0 sibling (live)",     "dreamed-sibling.clm"),
    ("  + sibling archive file",   "dreamed-sibling.archive.clm"),
    ("Prose summary",              "prose-summary.md"),
]

VARIANTS_50 = [
    ("Raw append (CLM/2.1)",          "raw-append-50.clm"),
    ("CLM/3.0 sibling (live)",        "dreamed-sibling-50.clm"),
    ("  + sibling archive file",      "dreamed-sibling-50.archive.clm"),
    ("CLM/3.0 trim aggressive (live)",   "dreamed-sibling-50-trim.clm"),
    ("  + trim archive file",         "dreamed-sibling-50-trim.archive.clm"),
    ("Prose summary",                 "prose-summary-50.md"),
]


def count_tokens(text: str) -> int:
    return len(ENC.encode(text))


def measure(variants: list[tuple[str, str]]) -> list[tuple[str, int, int]]:
    rows = []
    for label, name in variants:
        text = (HERE / name).read_text()
        rows.append((label, len(text), count_tokens(text)))
    return rows


def print_table(title: str, rows: list[tuple[str, int, int]]) -> None:
    print(f"\n=== {title} ===")
    headers = ("variant", "chars", "tokens")
    print(f"{headers[0]:<32}{headers[1]:>8}{headers[2]:>10}")
    print("-" * 53)
    for label, chars, toks in rows:
        print(f"{label:<32}{chars:>8}{toks:>10}")


def deltas(rows: list[tuple[str, int, int]], depth: int) -> None:
    raw = next(t for label, _, t in rows if label.startswith("Raw"))
    sibling_live = next(t for label, _, t in rows if label == "CLM/3.0 sibling (live)")
    sibling_archive_label = "  + sibling archive file"
    sibling_archive = next(
        (t for label, _, t in rows if label == sibling_archive_label), None
    )
    summary = next(t for label, _, t in rows if label.startswith("Prose"))

    trim_live = next(
        (t for label, _, t in rows if label == "CLM/3.0 trim aggressive (live)"), None
    )
    trim_archive = next(
        (t for label, _, t in rows if label == "  + trim archive file"), None
    )

    print(f"\n--- live-context cost @ {depth} sessions ---")
    print(f"  Prose summary (lossy):          {summary:>5} tokens")
    if trim_live is not None:
        print(f"  CLM/3.0 trim aggressive (live):    {trim_live:>5} tokens")
    print(f"  CLM/3.0 sibling (live):         {sibling_live:>5} tokens")
    print(f"  Raw append:                     {raw:>5} tokens")
    if sibling_archive is not None:
        print(f"  CLM/3.0 sibling (live+archive): {sibling_live + sibling_archive:>5} tokens (archive loaded on demand)")
    if trim_live is not None and trim_archive is not None:
        print(f"  CLM/3.0 trim (live+archive):    {trim_live + trim_archive:>5} tokens (archive loaded on demand)")

    print()
    if sibling_live < raw:
        pct = (raw - sibling_live) / raw * 100
        print(f"  v3.0 sibling-live vs raw append: -{pct:.1f}%")
    if trim_live is not None and trim_live < raw:
        pct = (raw - trim_live) / raw * 100
        print(f"  v3.0 trim-live   vs raw append: -{pct:.1f}%")
    if trim_live is not None and trim_live < sibling_live:
        pct = (sibling_live - trim_live) / sibling_live * 100
        print(f"  v3.0 trim-live   vs v3.0 live:  -{pct:.1f}%  (the trim mode's incremental win)")


def main() -> None:
    rows10 = measure(VARIANTS_10)
    rows50 = measure(VARIANTS_50)

    print_table("10-session thread", rows10)
    deltas(rows10, 10)

    print_table("50-session thread", rows50)
    deltas(rows50, 50)

    # Scaling comparison
    raw_10 = next(t for label, _, t in rows10 if label.startswith("Raw"))
    raw_50 = next(t for label, _, t in rows50 if label.startswith("Raw"))
    live_10 = next(t for label, _, t in rows10 if label == "CLM/3.0 sibling (live)")
    live_50 = next(t for label, _, t in rows50 if label == "CLM/3.0 sibling (live)")
    trim_50 = next(
        (t for label, _, t in rows50 if label == "CLM/3.0 trim aggressive (live)"), None
    )

    print("\n=== scaling ===")
    print(f"  Raw append:           10 sessions = {raw_10:>5} tokens   →   50 sessions = {raw_50:>5} tokens   (×{raw_50/raw_10:.2f})")
    print(f"  CLM/3.0 sibling-live: 10 sessions = {live_10:>5} tokens   →   50 sessions = {live_50:>5} tokens   (×{live_50/live_10:.2f})")
    if trim_50 is not None:
        print(f"  CLM/3.0 trim-live:                                       50 sessions = {trim_50:>5} tokens")
    print()
    print(f"  Raw growth ratio: ×{raw_50/raw_10:.2f}")
    print(f"  v3.0 growth ratio: ×{live_50/live_10:.2f}")
    if trim_50 is not None:
        print(f"  v3.0 trim absolute @ 50: {trim_50} tokens ({(raw_50 - trim_50) / raw_50 * 100:.1f}% smaller than raw)")

    print()
    print("Caveat: o200k_base differs from Anthropic's BPE by ~5-15% in absolute count.")
    print("Run experiments/v2/bench.py + experiments/fidelity/frontier.py for authoritative numbers.")


if __name__ == "__main__":
    main()
