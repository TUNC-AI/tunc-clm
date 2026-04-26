"""V3 lineage-fidelity Pareto experiment.

Tests gene's predicted scores from experiments/v3/RESULTS.md against the
lineage_qa.json battery. Adds the missing baseline gene didn't generate:
prose summaries explicitly prompted to preserve session/model attribution
(prose-lineage). If lineage-preserving prose at modest token budgets matches
CLM/3.0-trim's lineage fidelity, CLM is dominated; if not, CLM wins.

Methodology mirrors experiments/fidelity/frontier.py exactly:
- single trial, claude-sonnet-4-6 for both summarize and answer
- substring scoring (case-insensitive, any_of)
- per-question detail in results-v3.json for manual miss classification

For sibling-archive variants we concat live + archive (the realistic load
on a lineage query — the live doc alone can't answer Q4-Q15).

Reproduce: ANTHROPIC_API_KEY=... python3 frontier_v3.py
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
V3 = HERE.parent / "v3"

ANSWER_MODEL = "claude-sonnet-4-6"
SUMMARY_MODEL = "claude-sonnet-4-6"
TOKENIZER_MODEL = "claude-opus-4-5"

ANSWERER_SYSTEM = (
    "You will be given a session-handoff document and a numbered list of "
    "questions. Answer each question concisely (10 words or fewer) using only "
    "information from the document. If the document does not contain the answer, "
    "write UNKNOWN. Format your reply as:\n"
    "1. <answer>\n2. <answer>\n... (one line per question, in order, with no "
    "extra commentary)."
)

LINEAGE_PROSE_PROMPT = (
    "Summarize the following multi-session handoff thread. "
    "CRITICAL: preserve session-level lineage. For every decision, state which "
    "session number proposed it and which model/family signed it (e.g. "
    "'session 2 (CLd.Ops4.6) proposed renaming AuthCheck to RequireAuth'). "
    "Preserve dream-pass attribution (who consolidated which sessions, when). "
    "Preserve the list of distinct AI families that contributed. Preserve "
    "decisions that were reverted or superseded and identify which decision "
    "reverted or superseded which. Aim for roughly {budget} tokens. Output "
    "only the summary, no preamble.\n\n---\n{prose}\n---"
)


def variants() -> list[tuple[str, str]]:
    """Return (name, document_text) pairs. Sibling variants concat live+archive."""
    out: list[tuple[str, str]] = []

    def read(p: Path) -> str:
        return p.read_text()

    # Lossless / structured variants
    out.append(("raw-append-50", read(V3 / "raw-append-50.clm")))
    out.append(("raw-append-200", read(V3 / "raw-append-200.clm")))
    out.append((
        "dreamed-sibling-50-trim",
        read(V3 / "dreamed-sibling-50-trim.clm")
        + "\n\n;;; --- ARCHIVE ---\n\n"
        + read(V3 / "dreamed-sibling-50-trim.archive.clm"),
    ))
    out.append((
        "dreamed-sibling-200-trim",
        read(V3 / "dreamed-sibling-200-trim.clm")
        + "\n\n;;; --- ARCHIVE ---\n\n"
        + read(V3 / "dreamed-sibling-200-trim.archive.clm"),
    ))

    # Existing prose summaries (gene's; lossy on lineage by design)
    out.append(("prose-summary-50", read(V3 / "prose-summary-50.md")))
    out.append(("prose-summary-200", read(V3 / "prose-summary-200.md")))

    # Lineage-preserving prose baselines (generated below if missing)
    out.append(("prose-50-lineage", read(HERE / "prose-50-lineage.md")))
    out.append(("prose-200-lineage", read(HERE / "prose-200-lineage.md")))

    return out


def count_tokens(client: anthropic.Anthropic, text: str) -> int:
    return client.messages.count_tokens(
        model=TOKENIZER_MODEL,
        messages=[{"role": "user", "content": text}],
    ).input_tokens


def gzip_bytes(text: str) -> int:
    return len(gzip.compress(text.encode("utf-8"), compresslevel=9))


def summarize_lineage(client: anthropic.Anthropic, source_text: str, budget: int) -> str:
    prompt = LINEAGE_PROSE_PROMPT.format(budget=budget, prose=source_text)
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=budget + 200,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


def ensure_lineage_baselines(client: anthropic.Anthropic) -> None:
    """Generate prose-50-lineage and prose-200-lineage if not yet on disk."""
    targets = [
        ("prose-50-lineage.md", V3 / "raw-append-50.clm", 800),
        ("prose-200-lineage.md", V3 / "raw-append-200.clm", 2500),
    ]
    for name, source, budget in targets:
        out_path = HERE / name
        if out_path.exists():
            print(f"  reusing existing {name}")
            continue
        print(f"  generating {name} (~{budget} tokens) from {source.name}...")
        text = summarize_lineage(client, source.read_text(), budget)
        out_path.write_text(text)


def ask_all(client: anthropic.Anthropic, doc: str, questions: list[dict]) -> dict[int, str]:
    qlines = "\n".join(f"{q['id']}. {q['q']}" for q in questions)
    prompt = f"DOCUMENT:\n{doc}\n\nQUESTIONS:\n{qlines}"
    resp = client.messages.create(
        model=ANSWER_MODEL,
        max_tokens=2000,
        system=ANSWERER_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text
    answers: dict[int, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or "." not in line:
            continue
        head, _, rest = line.partition(".")
        try:
            num = int(head.strip())
        except ValueError:
            continue
        answers[num] = rest.strip()
    return answers


def score(answers: dict[int, str], questions: list[dict]) -> list[tuple[int, str, bool, str]]:
    out = []
    for q in questions:
        ans = answers.get(q["id"], "")
        lower = ans.lower()
        ok = any(needle.lower() in lower for needle in q["any_of"])
        out.append((q["id"], q.get("category", "?"), ok, ans))
    return out


def main() -> None:
    client = anthropic.Anthropic()
    questions = json.loads((V3 / "lineage_qa.json").read_text())["questions"]

    print("Generating lineage-preserving prose baselines:")
    ensure_lineage_baselines(client)

    print("\nLoading variants:")
    all_variants = variants()
    for name, _ in all_variants:
        print(f"  {name}")

    print("\nRunning fidelity eval:")
    rows = []
    for name, text in all_variants:
        toks = count_tokens(client, text)
        gzb = gzip_bytes(text)
        print(f"  {name:<30} ({toks:>6} tokens) ...", end=" ", flush=True)
        answers = ask_all(client, text, questions)
        scored = score(answers, questions)
        ncorr = sum(1 for _, _, ok, _ in scored if ok)
        print(f"{ncorr}/{len(questions)} correct")
        rows.append((name, len(text), toks, gzb, ncorr, scored, answers))

    # Per-category breakdown
    cats = sorted({q.get("category", "?") for q in questions})

    print()
    header = f"{'variant':<30}{'chars':>8}{'tokens':>9}{'gzip-B':>9}  fidelity"
    print(header)
    print("-" * len(header))
    for name, chars, toks, gzb, ncorr, scored, _ in rows:
        pct = ncorr / len(questions) * 100
        per_cat = {c: [0, 0] for c in cats}
        for _, cat, ok, _ in scored:
            per_cat[cat][1] += 1
            if ok:
                per_cat[cat][0] += 1
        cat_str = " ".join(f"{c}:{a}/{b}" for c, (a, b) in per_cat.items())
        print(
            f"{name:<30}{chars:>8}{toks:>9}{gzb:>9}  "
            f"{ncorr:>2}/{len(questions)} ({pct:>4.0f}%)  [{cat_str}]"
        )

    detail = {
        "models": {
            "answerer": ANSWER_MODEL,
            "summarizer": SUMMARY_MODEL,
            "tokenizer": TOKENIZER_MODEL,
        },
        "questions": questions,
        "results": [
            {
                "variant": name,
                "chars": chars,
                "tokens": toks,
                "gzip_bytes": gzb,
                "correct": ncorr,
                "total": len(questions),
                "per_question": [
                    {"id": qid, "category": cat, "ok": ok, "answer": ans}
                    for qid, cat, ok, ans in scored
                ],
            }
            for name, chars, toks, gzb, ncorr, scored, _ in rows
        ],
    }
    (HERE / "results-v3.json").write_text(json.dumps(detail, indent=2))
    print("\nDetail written to results-v3.json")


if __name__ == "__main__":
    main()
