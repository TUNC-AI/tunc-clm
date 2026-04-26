"""Compounding-cost bench: tokens to UPDATE across N appended sessions.

This is the bench that maps to the axis CLM/3.0 was actually designed for —
write-side / append cost — which copyleftdev's PR #15 read-side Q&A bench
explicitly does not measure.

The thesis: as a thread accumulates one new session at a time, how many
tokens does each format spend per update?

Two strategies:

  CLM/3.0:    each new session writes one [DELTA.session-N] block plus a
              [ROLL.CALL] line. Periodic dream-pass consolidation rewrites
              the [STATE] keys (bounded by trim.config.decisions_live=8 by
              default) and appends a [DREAM.LOG] entry.

  Prose-with- each new session means re-summarizing the entire prior thread
  good-prompt: with the lineage-preserving prompt, then writing the new
              summary. Generation cost grows with thread depth.

This is a tokenization bench — no API spend. We use tiktoken (o200k_base)
the same way as `tokens.py`. Caveats apply (Anthropic's BPE differs ~5-15%
in absolute counts; relative ordering reliable).

CALIBRATION NOTES (per Codex PR-16 review round-1):

  The prose model is calibrated to copyleftdev's PR #15 empirical points:
    N=50  → 1,007 tokens (prose-50-lineage with explicit lineage prompt)
    N=200 → 2,707 tokens (prose-200-lineage)
  Power-law fit: tokens ≈ 53.2 × N^0.713. Sub-linear in N (matches Don's
  observation: 50→200 = ×4 sessions but only ×2.69 output, because the
  summarizer paraphrases as content grows).

  The CLM total includes dream-pass output (NOT zero as in the v0.1 bench).
  Per-session CLM output:
    - one delta block (~60 tokens, sampled empirically)
    - one [ROLL.CALL] entry (~50 tokens)
    - amortized dream-pass cost: state rewrite + DREAM.LOG entry
      (state under trim.aggressive is bounded by decisions_live=8)

Run: python3 experiments/v3/compounding_cost.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import tiktoken

HERE = Path(__file__).parent
ENC = tiktoken.get_encoding("o200k_base")


def count_tokens(text: str) -> int:
    return len(ENC.encode(text))


# ---- empirical samples ----

def sample_clm_delta() -> str:
    return (
        "[DELTA.session-47]\n"
        "  ;; CLd.Ops4.7 | 2026-06-06 | append-only:\n"
        "  add.decision d47: rate-limit threshold reduced 100/min -> 60/min\n"
        "  add.file: internal/ratelimit/config.go\n"
        ";;\n\n"
    )


def sample_roll_call_line() -> str:
    return '  CLd.Ops4.7 · 2026-06-06 · "session 47: rate-limit threshold reduced"\n'


def sample_dream_log_entry() -> str:
    return "  2026-06-06 evening | CLd.Ops4.7 | consolidated 5 deltas (sessions 41-45) | sibling | wrote new [STATE]\n"


def sample_state_keys_under_trim() -> str:
    """Under trim.mode aggressive with decisions_live=8, the [STATE].decisions.live
    sub-block holds at most 8 decision lines. The rest of [STATE] is keys (project,
    status, shipped.versions, decisions.reverted/superseded).

    Note (per Codex PR-16 round-4 P2): trim.mode aggressive does NOT trim
    decisions.reverted or decisions.superseded — those grow with thread depth.
    This sample is a realistic mid-depth (~200 sessions) snapshot. For deeper
    threads, [STATE] grows with the reverted/superseded lists. We model this
    growth in `dream_pass_cost_at_depth()` below."""
    return (
        "[STATE]\n"
        "  ;; consolidated by CLd.Ops4.7 during dream pass over sessions 1-195\n"
        "  ;; last.dream: 2026-06-06 evening\n"
        "\n"
        "  goal: auth platform — extraction, hardening, OAuth, MFA, perf+security audit\n"
        "  status: in-progress (latest session: 200)\n"
        "  shipped.versions: [v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1, v0.7.0]\n"
        "  decisions.live (175 of 195 archived):\n"
        "    ;; (oldest 167 live decisions offloaded to [DECISIONS.ARCHIVE] in sibling)\n"
        "    d188: audit log MFA enable/disable events (cycle 4) [session 188]\n"
        "    d189: WebAuthn passkey support deferred to v0.7 (cycle 4) [session 189]\n"
        "    d190: ship MFA as v0.6.0 (cycle 4) [session 190]\n"
        "    d191: third-party security audit by Trail of Bits (cycle 4) [session 191]\n"
        "    d192: audit findings: CVE-class issue in JWT verify [session 192]\n"
        "    d193: backport JWT migration to v0.6.x (cycle 4) [session 193]\n"
        "    d194: performance: middleware chain p95 800us -> 120us [session 194]\n"
        "    d195: memory: session cache pool sync.Pool (cycle 4) [session 195]\n"
        "  decisions.reverted: [d4, d14, d23, d24, d54, d64, d73, d74]\n"
        "  decisions.superseded: [d3, d53, d103, d153]\n"
        ";;\n"
    )


# ---- prose model (calibrated to PR #15) ----

def prose_summary_size(n_sessions: int) -> int:
    """Power-law fit to PR #15's two empirical measurements:
        N=50  → 1,007 tokens
        N=200 → 2,707 tokens

    Solving log(2707/1007) = p × log(200/50) gives p ≈ 0.7133.
    Then a × 50^0.7133 = 1007 ⇒ a ≈ 61.82.

    Verifies: 61.82 × 50^0.7133  = 1,007 (matches measurement exactly)
              61.82 × 200^0.7133 = 2,707 (matches measurement exactly)

    Codex PR-16 round-2 P1 caught: a previous version had a = 53.2 which
    produced 866 at N=50 (vs measured 1,007) — the constant was wrong.
    """
    if n_sessions <= 0:
        return 0
    return int(round(61.82 * (n_sessions ** 0.7133)))


# ---- main ----

def dream_pass_cost_at_depth(n_at_dream: int, base_state: int, dream_log: int, roll_call: int, delta: int) -> int:
    """Dream-pass output cost at a specific depth. Includes:
      - Rewriting [STATE] (base + decisions.reverted/superseded growth)
      - One [DREAM.LOG] entry (~30 tokens)
      - One [ROLL.CALL] line for dream signing (~50 tokens)
      - Sibling archive writes: 5 merged deltas relocated to <basename>.archive.clm
        (per Codex PR-16 round-4 P1: archive writes were missing from v0.2)

    State growth (per Codex PR-16 round-4 P2): decisions.reverted/superseded
    accumulate ~5 entries per 50 sessions in the canonical generator, ~3 tokens
    each. Linear in depth: ~0.3 × N tokens of growth.
    """
    state_growth = int(0.3 * n_at_dream)
    state_at_depth = base_state + state_growth
    archive_write = 5 * delta  # 5 deltas merged → relocated to sibling archive
    return state_at_depth + dream_log + roll_call + archive_write


def main() -> None:
    delta_tokens = count_tokens(sample_clm_delta())
    roll_call_tokens = count_tokens(sample_roll_call_line())
    state_tokens = count_tokens(sample_state_keys_under_trim())
    dream_log_tokens = count_tokens(sample_dream_log_entry())

    # Per-dream cost depends on depth; we sample at a few points for the table.
    def dream_cost(n: int) -> int:
        return dream_pass_cost_at_depth(n, state_tokens, dream_log_tokens, roll_call_tokens, delta_tokens)

    print("=" * 78)
    print("COMPOUNDING-COST BENCH — tokens spent per session UPDATE")
    print("=" * 78)
    print()
    print("Each session that adds to a thread, the AI must produce the new doc state.")
    print("CLM appends a delta + roll-call line; every 5th session also runs a dream")
    print("pass (rewrite [STATE] + DREAM.LOG entry + sibling archive writes).")
    print("Prose-with-good-prompt re-summarizes the entire prior thread each time.")
    print()
    print("(o200k_base tokenizer; ~5-15% off Anthropic's BPE; relative ordering")
    print(" reliable. Prose model power-law-calibrated to PR #15's two empirical")
    print(" points: N=50→1,007 and N=200→2,707, fit gives 61.82 × N^0.7133.)")
    print()
    print(f"  Sampled CLM delta block:        {delta_tokens:>4} tokens")
    print(f"  Sampled [ROLL.CALL] line:       {roll_call_tokens:>4} tokens")
    print(f"  Sampled [STATE] base (~200 sessions):  {state_tokens:>4} tokens (decisions.reverted/superseded grow with depth)")
    print(f"  Sampled [DREAM.LOG] entry:      {dream_log_tokens:>4} tokens")
    print(f"  Sibling archive writes/dream:   {5 * delta_tokens:>4} tokens (5 merged deltas relocated)")
    print()
    print(f"  Dream-pass cost at N=10:        {dream_cost(10):>4} tokens")
    print(f"  Dream-pass cost at N=200:       {dream_cost(200):>4} tokens")
    print(f"  Dream-pass cost at N=500:       {dream_cost(500):>4} tokens")
    print()

    per_session_basic = delta_tokens + roll_call_tokens

    print(f"  CLM per-session basic:          {per_session_basic:>4} tokens (delta + roll-call)")
    print(f"  Plus dream cost amortized over 5 sessions, growing with depth.")
    print()

    print("=" * 78)
    print("Per-update cost at thread depth N — CLM is constant; prose grows")
    print("=" * 78)
    print()
    print(f"{'session N':>10}  {'CLM update':>11}  {'prose summary':>15}  {'ratio':>10}")
    print("-" * 55)

    for n in [1, 5, 10, 25, 50, 100, 200, 500]:
        clm_amortized = per_session_basic + (dream_cost(n) / 5.0)
        prose = prose_summary_size(n)
        ratio = prose / clm_amortized
        print(f"{n:>10}  {clm_amortized:>11.1f}  {prose:>15}  {ratio:>9.1f}x")

    print()
    print("=" * 78)
    print("Cumulative cost across the FULL thread up to session N")
    print("=" * 78)
    print()
    print("Each session: CLM appends delta + roll-call. Dream passes occur on the")
    print("schedule the canonical generator uses — at sessions 5, 10, 15, ... up to")
    print("but not including the final batch (the last 1-5 sessions stay live).")
    print("So at depth N, n_dreams = (N-1) // 5 — matches the v3 generator output.")
    print("(Codex PR-16 round-2 P2 caught the previous version overcounted dreams.)")
    print()
    print("Prose re-summarizes from scratch every session.")
    print()
    print(f"{'thread depth':>13}  {'n_dreams':>9}  {'CLM cumulative':>16}  {'prose cumulative':>18}  {'ratio':>10}")
    print("-" * 75)

    for n in [10, 50, 100, 200, 500]:
        n_dreams = (n - 1) // 5  # matches gen_50_session.py cadence
        # Each dream's cost depends on the depth at which it happens.
        dream_cum = sum(dream_cost(d) for d in range(5, n_dreams * 5 + 1, 5))
        clm_cum = n * per_session_basic + dream_cum
        prose_cum = sum(prose_summary_size(i) for i in range(1, n + 1))
        ratio = prose_cum / clm_cum
        print(f"{n:>13}  {n_dreams:>9}  {clm_cum:>16}  {prose_cum:>18}  {ratio:>9.1f}x")

    print()
    print("=" * 78)
    print("Reading the result")
    print("=" * 78)
    print()
    print("CLM is designed for the WRITE-side axis. On reads (PR #15), lineage-")
    print("preserving prose wins. On writes across many sessions, CLM still wins")
    print("but by a more measured margin once dream-pass output is honestly counted.")
    print()
    print("Caveats:")
    print(" - Power-law prose model fit to two measurement points; extrapolation")
    print("   beyond 200 sessions is a model, not a bench.")
    print(" - CLM dream-pass cost modeled as a typical [STATE] under trim.aggressive")
    print("   (~280 tokens, bounded by decisions_live=8). State without trim grows")
    print("   linearly with depth and the advantage shrinks accordingly.")
    print(" - Output tokens only. Input/read tokens are real but ~5x cheaper at")
    print("   Anthropic rates and roughly proportional in both formats.")


if __name__ == "__main__":
    main()
