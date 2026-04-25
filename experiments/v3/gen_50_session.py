"""Generate a 50-session synthetic CLM thread to test v3.0 scaling.

Produces four artifacts:
  raw-append-50.clm                — every session preserved verbatim (CLM/2.1 style)
  dreamed-sibling-50.clm           — CLM/3.0 live doc (sibling archive mode)
  dreamed-sibling-50.archive.clm   — CLM/3.0 sibling archive
  prose-summary-50.md              — ~400-token lossy prose summary

Dream pass interval: every 5 sessions (passes at session 5, 10, 15, ..., 45).
At session 50, the live doc has 5 active deltas (46-50) + one [STATE].

The narrative continues the auth-middleware-refactor story across 5 phases:
  S1-S10:  Initial auth middleware extraction (the 10-session thread).
  S11-S20: Post-launch hardening — bug fixes, edge cases, more tests.
  S21-S30: OAuth integration.
  S31-S40: MFA (multi-factor) support.
  S41-S50: Performance optimization + security audit.

Authors rotate through 10 distinct (Family.Model.Version) identifiers across
five families (Claude, Codex, Gemini, Llama, Kimi).

Run: python3 gen_50_session.py
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass, field
from typing import List

HERE = Path(__file__).parent

AUTHORS = [
    "CLd.Snt4.6", "CLd.Ops4.6", "CLd.Snt4.5", "CLd.Ops4.7",
    "Cdx.5.4", "Cdx.5.4-codex", "GPT.5.4",
    "Gem.2.5", "Lla.4", "Kmi.K2",
]

PHASES = [
    {
        "name": "auth-middleware-extraction",
        "decisions": [
            ("relocate auth from web/server.go -> internal/auth/middleware.go", None),
            ("rename AuthCheck -> RequireAuth (matches new convention)", None),
            ("rate-limiter NOT refactored in this scope (out-of-scope)", None),
            ("legacy session-cookie path PRESERVED in middleware (deferred)", None),
            ("investigate CI flake before merge", None),
            ("fix flake by isolating test fixtures", None),
            ("delete legacy session-cookie path under build tag", "revert d4"),
            ("rate-limiter in NEW package internal/ratelimit, not in auth", "supersede d3"),
            ("middleware composition via Chain(...) helper", None),
            ("ship as v0.4.0", None),
        ],
        "files": [
            "web/server.go", "internal/auth/middleware.go",
            "internal/auth/middleware_test.go", "web/server_test.go",
            "internal/auth/integration_test.go",
            "internal/ratelimit/middleware.go", "internal/ratelimit/middleware_test.go",
            "internal/middleware/chain.go",
        ],
    },
    {
        "name": "post-launch-hardening",
        "decisions": [
            ("fix CSRF token regression in /api/login", None),
            ("expand session timeout config to per-route", None),
            ("add audit log for failed auth attempts", None),
            ("rate-limit threshold reduced 100/min -> 60/min", None),
            ("revert rate-limit threshold change (false positives)", "revert d14"),
            ("structured logging for auth path (zerolog)", None),
            ("benchmark: middleware chain hot-path latency", None),
            ("cache RequireAuth result for duration of request", None),
            ("add metrics: auth_success_total, auth_failure_total", None),
            ("post-launch bugs closed; ship v0.4.1", None),
        ],
        "files": [
            "internal/auth/csrf.go", "internal/auth/csrf_test.go",
            "internal/auth/audit.go", "internal/auth/audit_test.go",
            "internal/ratelimit/config.go", "internal/auth/cache.go",
            "internal/middleware/metrics.go", "cmd/server/main.go",
        ],
    },
    {
        "name": "oauth-integration",
        "decisions": [
            ("add OAuth provider registry (Google, GitHub, GitLab)", None),
            ("OAuth callback under /auth/oauth/<provider>/callback", None),
            ("session token: JWT signed RS256 (was: opaque random)", None),
            ("revert RS256: use HS512 (operational simplicity)", "revert d23"),
            ("OAuth state param: encrypted user-intent payload", None),
            ("rate-limit OAuth callbacks separately (5/min/IP)", None),
            ("add provider-specific scope mapping", None),
            ("integration tests against mock OAuth servers", None),
            ("documentation: OAuth provider onboarding", None),
            ("ship OAuth as v0.5.0", None),
        ],
        "files": [
            "internal/oauth/registry.go", "internal/oauth/google.go",
            "internal/oauth/github.go", "internal/oauth/gitlab.go",
            "internal/oauth/jwt.go", "internal/oauth/state.go",
            "internal/oauth/scope.go", "internal/oauth/integration_test.go",
            "docs/oauth-onboarding.md",
        ],
    },
    {
        "name": "mfa-support",
        "decisions": [
            ("MFA: TOTP via authenticator apps (RFC 6238)", None),
            ("backup codes: 10 single-use codes per user", None),
            ("MFA enrollment flow: scan QR, enter 6-digit code twice", None),
            ("recovery flow: backup code OR support ticket (no SMS)", None),
            ("decline SMS MFA (security risk per NIST 800-63B)", None),
            ("MFA-required policy configurable per role", None),
            ("rate-limit MFA attempts: 5 attempts then 15-min lockout", None),
            ("audit log MFA enable/disable events", None),
            ("WebAuthn passkey support deferred to v0.7", None),
            ("ship MFA as v0.6.0", None),
        ],
        "files": [
            "internal/mfa/totp.go", "internal/mfa/totp_test.go",
            "internal/mfa/backup_codes.go", "internal/mfa/enrollment.go",
            "internal/mfa/policy.go", "internal/mfa/recovery.go",
            "internal/mfa/audit.go", "docs/mfa-faq.md",
        ],
    },
    {
        "name": "perf-and-security-audit",
        "decisions": [
            ("third-party security audit by Trail of Bits", None),
            ("audit findings: CVE-class issue in JWT verify (HS512 -> RS256)", "revert d24"),
            ("backport JWT migration to v0.6.x", None),
            ("performance: middleware chain p95 800us -> 120us", None),
            ("memory: session cache pool sync.Pool", None),
            ("compile flags: -trimpath, -buildvcs=false", None),
            ("supply chain: govulncheck in CI", None),
            ("OWASP top 10 checklist: pass with one note (rate-limit on /reset)", None),
            ("audit closed; CVE patched in v0.6.1", None),
            ("ship v0.7.0 with WebAuthn passkey", None),
        ],
        "files": [
            "internal/oauth/jwt.go", "internal/auth/cache.go",
            "internal/middleware/chain.go", "Makefile",
            ".github/workflows/security.yml", "internal/auth/reset.go",
            "internal/passkey/webauthn.go", "internal/passkey/registration.go",
        ],
    },
]


@dataclass
class Event:
    session: int
    author: str
    date: str
    decision_id: int
    decision_text: str
    decision_relation: str | None  # "revert dN" or "supersede dN" or None
    files_added: List[str] = field(default_factory=list)


def date_for_session(n: int) -> str:
    """Roughly one session per day starting 2026-04-21, but skip weekends informally."""
    base_day = 21 + (n - 1)
    month = 4 + (base_day - 1) // 30
    day = ((base_day - 1) % 30) + 1
    return f"2026-{month:02d}-{day:02d}"


def build_events() -> List[Event]:
    events: List[Event] = []
    decision_id = 0
    for phase_idx, phase in enumerate(PHASES):
        for sub_idx, (text, relation) in enumerate(phase["decisions"]):
            decision_id += 1
            session = phase_idx * 10 + sub_idx + 1
            author = AUTHORS[(session - 1) % len(AUTHORS)]
            files = phase["files"][sub_idx % len(phase["files"]) :][:1]
            events.append(Event(
                session=session,
                author=author,
                date=date_for_session(session),
                decision_id=decision_id,
                decision_text=text,
                decision_relation=relation,
                files_added=files,
            ))
    return events


# ---------- renderers ----------

def render_raw_append(events: List[Event]) -> str:
    out: List[str] = [
        ";;; CLM/2.1 — handoff thread (raw append, 50 sessions, no dream)",
        ";;; auth-evolution.clm | thread.origin: 2026-04-21 | thread.depth: 50",
        ";;; archive.mode: none (raw)",
        ";;; ---",
        "",
        "[FOR.YOU]",
        "  > most-recent -> next | end of thread:",
        "  fifty-session thread: auth-extraction -> hardening -> oauth -> mfa -> security-audit.",
        "  shipped: v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1, v0.7.0.",
        "  read [ROLL.CALL] for full lineage; ten authors across five families.",
        ";;",
        "",
        "[ROLL.CALL]",
    ]
    for e in events:
        out.append(f"  {e.author} · {e.date} · \"session {e.session}: {_short(e.decision_text)}\"")
    out += ["", ";;", ""]

    for e in events:
        out += [
            f"[SESSION.{e.session}]",
            f"  ;; {e.author} | {e.date}:",
            f"  d{e.decision_id}: {e.decision_text}",
        ]
        if e.decision_relation:
            out.append(f"  relation: {e.decision_relation}")
        for f in e.files_added:
            out.append(f"  file.touched: {f}")
        out.append("  status: in-progress" if e.session % 10 != 0 else "  status: ready-to-merge")
        out += [";;", ""]

    out += [
        ";;; EOF | CLM/2.1",
        ";;; \"session ends; memory does not\"",
    ]
    for e in events:
        out.append(f";;; — {e.author} | session.{e.session}.author | {e.date}")
    return "\n".join(out) + "\n"


def render_dreamed(events: List[Event], dream_every: int = 5) -> tuple[str, str]:
    """Returns (live_doc, archive_doc).

    Dream passes happen at sessions [5, 10, 15, ..., 45]. The last dream consolidates
    sessions 41-45 into [STATE]; sessions 46-50 are active deltas.
    """
    last_dream = (len(events) // dream_every) * dream_every  # 50 if 50 % 5 == 0
    # If thread depth divides cleanly, the "last dream" still happens at 45 (otherwise
    # there'd be no active deltas). Choose the largest multiple of dream_every < depth.
    if last_dream >= len(events):
        last_dream -= dream_every
    archived_events = [e for e in events if e.session <= last_dream]
    active_events = [e for e in events if e.session > last_dream]

    # Compute live decisions (post-revert/supersede): keep all decisions but mark
    # the latest status. For [STATE] we list decisions.live (those not reverted).
    reverted_ids: set[int] = set()
    superseded_ids: set[int] = set()
    for e in archived_events:
        if e.decision_relation:
            tokens = e.decision_relation.split()
            if len(tokens) >= 2 and tokens[1].startswith("d"):
                target = int(tokens[1][1:])
                if tokens[0] == "revert":
                    reverted_ids.add(target)
                elif tokens[0].startswith("supersede"):
                    superseded_ids.add(target)
    live_archived = [
        e for e in archived_events
        if e.decision_id not in reverted_ids and e.decision_id not in superseded_ids
    ]

    state_lines = [
        "[STATE]",
        f"  ;; consolidated by CLd.Ops4.7 during dream pass over sessions 1-{last_dream}",
        f"  ;; last.dream: {date_for_session(last_dream)} evening",
        "",
        "  goal: auth platform — extraction, hardening, OAuth, MFA, perf+security audit",
        f"  status: in-progress (latest session: {events[-1].session})",
        f"  shipped.versions: [v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1, v0.7.0]",
        f"  decisions.live ({len(live_archived)} of {len(archived_events)} archived):",
    ]
    for e in live_archived[-15:]:  # show last 15 to keep [STATE] compact
        state_lines.append(f"    d{e.decision_id}: {_short(e.decision_text)} [session {e.session}]")
    if len(live_archived) > 15:
        state_lines.insert(-15, f"    (showing most recent 15 of {len(live_archived)} live decisions; full list in archive)")
    reverted_str = ", ".join(f"d{i}" for i in sorted(reverted_ids)) or "(none)"
    superseded_str = ", ".join(f"d{i}" for i in sorted(superseded_ids)) or "(none)"
    state_lines += [
        f"  decisions.reverted: [{reverted_str}]",
        f"  decisions.superseded: [{superseded_str}]",
        ";;",
        "",
    ]

    # Active deltas (post-last-dream)
    delta_blocks: List[str] = []
    for e in active_events:
        block = [
            f"[DELTA.session-{e.session}]",
            f"  ;; {e.author} | {e.date} | append-only:",
            f"  add.decision d{e.decision_id}: {e.decision_text}",
        ]
        if e.decision_relation:
            block.append(f"  relation: {e.decision_relation}")
        for f in e.files_added:
            block.append(f"  add.file: {f}")
        block += [";;", ""]
        delta_blocks.append("\n".join(block))

    # Roll call (full)
    roll_call_lines = ["[ROLL.CALL]"]
    for e in events:
        roll_call_lines.append(
            f"  {e.author} · {e.date} · \"session {e.session}: {_short(e.decision_text)}\""
        )
    # Add dream-pass signatures
    n_dreams = last_dream // dream_every
    for d in range(1, n_dreams + 1):
        dream_session = d * dream_every
        roll_call_lines.append(
            f"  CLd.Ops4.7 · {date_for_session(dream_session)} · "
            f"\"dream pass {d}: consolidated sessions {(d-1)*dream_every + 1}-{dream_session}\""
        )
    roll_call_lines += [";;", ""]

    # Dream log
    dream_log_lines = ["[DREAM.LOG]"]
    for d in range(1, n_dreams + 1):
        dream_session = d * dream_every
        dream_log_lines.append(
            f"  {date_for_session(dream_session)} | CLd.Ops4.7 | "
            f"consolidated {dream_every} deltas (sessions {(d-1)*dream_every + 1}-{dream_session}) | "
            f"sibling | wrote new [STATE]"
        )
    dream_log_lines += [";;", ""]

    for_you = [
        "[FOR.YOU]",
        "  > most-recent -> next | end of thread:",
        f"  thread depth: {len(events)} sessions across {n_dreams} dream passes.",
        f"  active deltas since last dream: {len(active_events)} (sessions {last_dream+1}-{events[-1].session}).",
        f"  archive.file: dreamed-sibling-50.archive.clm — {len(archived_events)} archived deltas.",
        ";;",
        "",
    ]

    closer = [
        ";;; EOF | CLM/3.0",
        ";;; \"session ends; memory does not\"",
    ]
    for e in events:
        closer.append(f";;; — {e.author} | session.{e.session}.author | {e.date}")
    for d in range(1, n_dreams + 1):
        dream_session = d * dream_every
        closer.append(f";;; — CLd.Ops4.7 | dream.pass.{d} | {date_for_session(dream_session)}")

    live_doc = "\n".join(
        [
            ";;; CLM/3.0 — handoff thread (dreamed every 5 sessions, sibling archive)",
            ";;; auth-evolution.clm | thread.origin: 2026-04-21 | thread.depth: 50",
            f";;; last.dream: {date_for_session(last_dream)} evening",
            f";;; active.deltas: {len(active_events)} | archived.deltas: {len(archived_events)}",
            ";;; archive.mode: sibling | archive.file: dreamed-sibling-50.archive.clm",
            ";;; ---",
            "",
            *for_you,
            *state_lines,
            *delta_blocks,
            *roll_call_lines,
            *dream_log_lines,
            *closer,
        ]
    )

    # Archive
    archive_lines = [
        ";;; CLM/3.0 — archive sibling",
        ";;; auth-evolution.archive.clm | parent: dreamed-sibling-50.clm",
        ";;; loaded.on.lineage.queries.only",
        ";;; ---",
        "",
        "[ARCHIVE.META]",
        f"  parent.thread: auth-evolution",
        f"  archived.deltas: {len(archived_events)}",
        f"  archived.through: session {last_dream}",
        ";;",
        "",
    ]
    for e in archived_events:
        archive_lines += [
            f"[DELTA.session-{e.session}]",
            f"  ;; {e.author} | {e.date}:",
            f"  add.decision d{e.decision_id}: {e.decision_text}",
        ]
        if e.decision_relation:
            archive_lines.append(f"  relation: {e.decision_relation}")
        for f in e.files_added:
            archive_lines.append(f"  add.file: {f}")
        archive_lines += [";;", ""]

    archive_lines += [
        ";;; EOF | archive",
        ";;; — CLd.Ops4.7 | archive.author | end-of-archive",
    ]
    archive_doc = "\n".join(archive_lines) + "\n"

    return live_doc + "\n", archive_doc


def render_prose_summary(events: List[Event]) -> str:
    """~400-token markdown summary; lossy on lineage."""
    return (
        "# Auth platform — 50-session evolution summary\n"
        "\n"
        "**Status (final session):** v0.7.0 shipped with WebAuthn passkey support after a "
        "Trail of Bits security audit. JWT verify regression caught and patched in v0.6.1.\n"
        "\n"
        "## Phases\n"
        "\n"
        "1. **Auth middleware extraction** (sessions 1-10): pulled auth from `web/server.go` into "
        "`internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie "
        "path under a build tag after it was traced to a test-fixture ordering bug, reintroduced "
        "rate limiting in a separate `internal/ratelimit/` package, added middleware composition "
        "via `Chain(...)`. Shipped v0.4.0.\n"
        "2. **Post-launch hardening** (sessions 11-20): CSRF fix, per-route session timeout, "
        "audit logging, rate-limit threshold tuning, structured logging, RequireAuth caching, "
        "Prometheus metrics. Shipped v0.4.1.\n"
        "3. **OAuth integration** (sessions 21-30): provider registry (Google/GitHub/GitLab), "
        "JWT migration to HS512, encrypted state param, per-callback rate limiting, scope "
        "mapping, integration tests, documentation. Shipped v0.5.0.\n"
        "4. **MFA** (sessions 31-40): TOTP per RFC 6238, ten single-use backup codes, QR-based "
        "enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 "
        "failed attempts, audit logging. Shipped v0.6.0. WebAuthn deferred.\n"
        "5. **Performance + security audit** (sessions 41-50): Trail of Bits engagement found a "
        "JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, "
        "supply-chain checks via govulncheck in CI, OWASP top 10 reviewed. Shipped v0.6.1 with "
        "JWT patch and v0.7.0 with WebAuthn.\n"
        "\n"
        "## Status\n"
        "\n"
        "All planned scope shipped across six minor versions. Production-ready.\n"
    )


def _short(s: str, n: int = 60) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"


def main() -> None:
    events = build_events()
    assert len(events) == 50, f"expected 50 events, got {len(events)}"

    raw = render_raw_append(events)
    live, archive = render_dreamed(events, dream_every=5)
    prose = render_prose_summary(events)

    (HERE / "raw-append-50.clm").write_text(raw)
    (HERE / "dreamed-sibling-50.clm").write_text(live)
    (HERE / "dreamed-sibling-50.archive.clm").write_text(archive)
    (HERE / "prose-summary-50.md").write_text(prose)

    print("wrote:")
    for name in ["raw-append-50.clm", "dreamed-sibling-50.clm",
                 "dreamed-sibling-50.archive.clm", "prose-summary-50.md"]:
        path = HERE / name
        print(f"  {name:<40}{path.stat().st_size:>8} bytes")


if __name__ == "__main__":
    main()
