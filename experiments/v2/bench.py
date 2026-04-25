"""Token-count benchmark for CLM/1.0 vs CLM/2.0 vs prose vs YAML.

Uses Anthropic's count_tokens API against claude-opus-4-5 — the right
tokenizer to settle the README's compression claim.
"""
from pathlib import Path
import anthropic

HERE = Path(__file__).parent
FILES = [
    ("CLM/1.0",     "handoff.v1.clm"),
    ("CLM/2.0",     "handoff.v2.clm"),
    ("Prose (md)",  "handoff.md"),
    ("YAML",        "handoff.yaml"),
]

def main() -> None:
    client = anthropic.Anthropic()
    rows = []
    for label, name in FILES:
        text = (HERE / name).read_text()
        n_tokens = client.messages.count_tokens(
            model="claude-opus-4-5",
            messages=[{"role": "user", "content": text}],
        ).input_tokens
        rows.append((label, len(text.encode("utf-8")), len(text), n_tokens))

    headers = ("format", "bytes", "chars", "tokens", "chars/tok", "vs prose")
    prose_tokens = next(t for label, _, _, t in rows if label.startswith("Prose"))
    print(f"{headers[0]:<12}{headers[1]:>8}{headers[2]:>8}{headers[3]:>9}{headers[4]:>12}{headers[5]:>10}")
    print("-" * 60)
    for label, b, c, t in rows:
        delta = (t - prose_tokens) / prose_tokens * 100
        sign = "+" if delta >= 0 else ""
        print(f"{label:<12}{b:>8}{c:>8}{t:>9}{c/t:>12.2f}{sign + f'{delta:.1f}%':>10}")

if __name__ == "__main__":
    main()
