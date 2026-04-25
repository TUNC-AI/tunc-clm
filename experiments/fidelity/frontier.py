"""Tokens × fidelity Pareto experiment.

For each format/compression variant of the same handoff document:
1. count tokens (Anthropic count_tokens)
2. measure gzip-9 byte size (theoretical compressibility floor)
3. feed to a fresh Claude session, ask the 20 atomic-fact questions in
   handoff_qa.json, score answers by case-insensitive substring match.

Reports a table of tokens vs fidelity, and writes results.json with full
per-question detail so the run is auditable.

Reproduce: ANTHROPIC_API_KEY=... python3 frontier.py
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import anthropic

HERE = Path(__file__).parent
V2 = HERE.parent / "v2"

LOSSLESS_VARIANTS = [
    ("CLM/1.0",    V2 / "handoff.v1.clm"),
    ("CLM/2.0",    V2 / "handoff.v2.clm"),
    ("Prose (md)", V2 / "handoff.md"),
    ("YAML",       V2 / "handoff.yaml"),
]

SUMMARY_BUDGETS = [250, 200, 150]

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


def count_tokens(client: anthropic.Anthropic, text: str) -> int:
    return client.messages.count_tokens(
        model=TOKENIZER_MODEL,
        messages=[{"role": "user", "content": text}],
    ).input_tokens


def gzip_bytes(text: str) -> int:
    return len(gzip.compress(text.encode("utf-8"), compresslevel=9))


def summarize(client: anthropic.Anthropic, prose: str, target_tokens: int) -> str:
    prompt = (
        f"Summarize the following session-handoff document. Preserve EVERY "
        f"factual claim: file paths, function names, dates, decisions, statuses, "
        f"reasons, open questions, recommendations. Aim for roughly "
        f"{target_tokens} tokens. Output only the summary, no preamble.\n\n"
        f"---\n{prose}\n---"
    )
    resp = client.messages.create(
        model=SUMMARY_MODEL,
        max_tokens=target_tokens + 100,
        messages=[{"role": "user", "content": prompt}],
    )
    return resp.content[0].text


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


def score(answers: dict[int, str], questions: list[dict]) -> list[tuple[int, bool, str]]:
    out = []
    for q in questions:
        ans = answers.get(q["id"], "")
        lower = ans.lower()
        ok = any(needle.lower() in lower for needle in q["any_of"])
        out.append((q["id"], ok, ans))
    return out


def main() -> None:
    client = anthropic.Anthropic()
    questions = json.loads((HERE / "handoff_qa.json").read_text())["questions"]

    prose_text = (V2 / "handoff.md").read_text()
    print("Generating lossy summaries:")
    summary_paths: list[tuple[str, Path]] = []
    for budget in SUMMARY_BUDGETS:
        out_path = HERE / f"handoff.summary-{budget}.md"
        if out_path.exists():
            print(f"  reusing existing summary @ {budget}: {out_path.name}")
        else:
            print(f"  summarizing prose to ~{budget} tokens...")
            summary = summarize(client, prose_text, budget)
            out_path.write_text(summary)
        summary_paths.append((f"Summary @ {budget}", out_path))

    all_variants = [(n, p.read_text()) for n, p in LOSSLESS_VARIANTS]
    all_variants += [(n, p.read_text()) for n, p in summary_paths]

    print("\nRunning fidelity eval:")
    rows = []
    for name, text in all_variants:
        toks = count_tokens(client, text)
        gzb = gzip_bytes(text)
        print(f"  {name:<22} ({toks:>4} tokens) ...", end=" ", flush=True)
        answers = ask_all(client, text, questions)
        scored = score(answers, questions)
        ncorr = sum(1 for _, ok, _ in scored if ok)
        print(f"{ncorr}/{len(questions)} correct")
        rows.append((name, len(text), toks, gzb, ncorr, scored, answers))

    # Print table
    print()
    headers = ("variant", "chars", "tokens", "gzip-B", "fidelity")
    print(f"{headers[0]:<22}{headers[1]:>7}{headers[2]:>8}{headers[3]:>8}{headers[4]:>14}")
    print("-" * 60)
    for name, chars, toks, gzb, ncorr, _, _ in rows:
        pct = ncorr / len(questions) * 100
        print(f"{name:<22}{chars:>7}{toks:>8}{gzb:>8}{ncorr:>5}/{len(questions):<2} ({pct:>4.0f}%)")

    detail = {
        "models": {"answerer": ANSWER_MODEL, "summarizer": SUMMARY_MODEL, "tokenizer": TOKENIZER_MODEL},
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
                    {"id": qid, "ok": ok, "answer": ans} for qid, ok, ans in scored
                ],
            }
            for name, chars, toks, gzb, ncorr, scored, _ in rows
        ],
    }
    (HERE / "results.json").write_text(json.dumps(detail, indent=2))
    print("\nDetail written to results.json")


if __name__ == "__main__":
    main()
