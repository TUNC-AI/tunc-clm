# auth-evolution.clm — Handoff Thread Summary
## 200 Sessions · 4 Cycles · 6 Shipped Versions · 2026-04-21 → 2026-11-10

---

## Thread Structure

The thread contains **no dream-pass consolidations**. The archive mode is `none (raw)`, meaning no session compressed or consolidated any prior range. Every session is a raw append; there is no dream-pass attribution to record.

The 200 sessions are organized as **four identical cycles** of 50 sessions each (cycle 1: sessions 1–50; cycle 2: sessions 51–100; cycle 3: sessions 101–150; cycle 4: sessions 151–200). Each cycle traverses the same four work phases—auth extraction → hardening → OAuth → MFA → security audit—and ships the same six versions: v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1, v0.7.0. Decisions within each cycle are structurally identical to their cycle-1 originals; all cycle annotations are noted below where relevant.

---

## Distinct AI Families Contributing

Ten distinct model instances across five families authored sessions in strict 10-session rotation throughout all four cycles:

| Family | Instances | Sessions (cycle 1 examples) |
|---|---|---|
| **Claude (CLd)** | CLd.Snt4.6, CLd.Ops4.6, CLd.Snt4.5, CLd.Ops4.7 | 1, 2, 3, 4, 11–14, 21–24, 31–34, 41–44 |
| **Codex (Cdx)** | Cdx.5.4, Cdx.5.4-codex | 5, 6, 15, 16, 25, 26, 35, 36, 45, 46 |
| **GPT** | GPT.5.4 | 7, 17, 27, 37, 47 |
| **Gemini (Gem)** | Gem.2.5 | 8, 18, 28, 38, 48 |
| **Llama (Lla)** | Lla.4 | 9, 19, 29, 39, 49 |
| **Kimi (Kmi)** | Kmi.K2 | 10, 20, 30, 40, 50 |

---

## Phase 1 — Auth Extraction (Sessions 1–10 / 51–60 / 101–110 / 151–160)

**Session 1 (CLd.Snt4.6)** proposed relocating auth logic from `web/server.go` to `internal/auth/middleware.go` (d1 / repeated as d51, d101, d151).

**Session 2 (CLd.Ops4.6)** proposed renaming `AuthCheck` → `RequireAuth` to match new naming conventions (d2 / d52, d102, d152).

**Session 3 (CLd.Snt4.5)** formally scoped out rate-limiter refactoring, declaring it out-of-scope for this phase (d3 / d53, d103, d153). This decision was **superseded** in each cycle by session 8 / 58 / 108 / 158 (Gem.2.5), which moved the rate-limiter into a new package `internal/ratelimit` rather than leaving it untouched (d8 supersedes d3; d58 supersedes d53; d108 supersedes d103; d158 supersedes d153).

**Session 4 (CLd.Ops4.7)** proposed preserving the legacy session-cookie path in middleware, deferring its removal (d4 / d54, d104, d154). This decision was **reverted** in each cycle by session 7 / 57 / 107 / 157 (GPT.5.4), which deleted the legacy path under a build tag (d7 reverts d4; d57 reverts d54; d107 reverts d104; d157 reverts d154).

**Session 5 (Cdx.5.4)** flagged a CI flake requiring investigation before merge (d5 / d55, d105, d155).

**Session 6 (Cdx.5.4-codex)** resolved the flake by isolating test fixtures (d6 / d56, d106, d156).

**Session 9 (Lla.4)** introduced middleware composition via a `Chain(...)` helper (d9 / d59, d109, d159).

**Session 10 (Kmi.K2)** shipped **v0.4.0** (d10 / d60, d110, d160).

---

## Phase 2 — Hardening (Sessions 11–20 / 61–70 / 111–120 / 161–170)

**Session 11 (CLd.Snt4.6)** fixed a CSRF token regression in `/api/login` (d11 / d61, d111, d161).

**Session 12 (CLd.Ops4.6)** expanded session timeout configuration to per-route granularity (d12 / d62, d112, d162).

**Session 13 (CLd.Snt4.5)** added an audit log for failed auth attempts (d13 / d63, d113, d163).

**Session 14 (CLd.Ops4.7)** proposed reducing the rate-limit threshold from 100/min to 60/min (d14 / d64, d114, d164). This decision was **reverted** in each cycle by session 15 / 65 / 115 / 165 (Cdx.5.4) due to false positives in production (d15 reverts d14; d65 reverts d64; d115 reverts d114; d165 reverts d164). The threshold therefore remained at 100/min across all cycles.

**Session 16 (Cdx.5.4-codex)** added structured logging for the auth path using zerolog (d16 / d66, d116, d166).

**Session 17 (GPT.5.4)** benchmarked middleware chain hot-path latency (d17 / d67, d117, d167).

**Session 18 (Gem.2.5)** introduced caching of the `RequireAuth` result for the duration of each request (d18 / d68, d118, d168).

**Session 19 (Lla.4)** added Prometheus metrics `auth_success_total` and `auth_failure_total` (d19 / d69, d119, d169).

**Session 20 (Kmi.K2)** closed post-launch bugs and shipped **v0.4.1** (d20 / d70, d120, d170).

---

## Phase 3 — OAuth (Sessions 21–30 / 71–80 / 121–130 / 171–180)

**Session 21 (CLd.Snt4.6)** established an OAuth provider registry for Google, GitHub, and GitLab (d21 / d71, d121, d171).

**Session 22 (CLd.Ops4.6)** defined the OAuth callback URL pattern as `/auth/oauth/<provider>/callback` (d22 / d72, d122, d172).

**Session 23 (CLd.Snt4.5)** proposed switching session tokens from opaque random values to JWTs signed with **RS256** (d23 / d73, d123, d173). This decision was **reverted** in each cycle by session 24 / 74 / 124 / 174 (CLd.Ops4.7), which substituted **HS512** on grounds of operational simplicity (d24 reverts d23; d74 reverts d73; d124 reverts d123; d174 reverts d173).

The HS512 decision was itself **subsequently reverted** in each cycle by the security audit phase: session 42 / 92 / 142 / 192 (CLd.Ops4.6) found a CVE-class vulnerability in the HS512 JWT verification path and forced migration back to RS256 (d42 reverts d24; d92 reverts d74; d142 reverts d124; d192 reverts d174). The final net state across all cycles is **RS256**.

**Session 25 (Cdx.5.4)** secured the OAuth state parameter with an encrypted user-intent payload (d25 / d75, d125, d175).

**Session 26 (Cdx.5.4-codex)** applied a separate rate limit of 5/min/IP to OAuth callbacks (d26 / d76, d126, d176).

**Session 27 (GPT.5.4)** added provider-specific scope mapping (d27 / d77, d127, d177).

**Session 28 (Gem.2.5)** wrote integration tests against mock OAuth servers (d28 / d78, d128, d178).

**Session 29 (Lla.4)** wrote OAuth provider onboarding documentation (d29 / d79, d129, d179).

**Session 30 (Kmi.K2)** shipped **v0.5.0** (d30 / d80, d130, d180).

---

## Phase 4 — MFA (Sessions 31–40 / 81–90 / 131–140 / 181–190)

**Session 31 (CLd.Snt4.6)** introduced TOTP-based MFA via authenticator apps (RFC 6238) (d31 / d81, d131, d181).

**Session 32 (CLd.Ops4.6)** added 10 single-use backup codes per user (d32 / d82, d132, d182).

**Session 33 (CLd.Snt4.5)** defined the MFA enrollment flow: scan QR code, enter 6-digit code twice (d33 / d83, d133, d183).

**Session 34 (CLd.Ops4.7)** defined the recovery flow as backup code or support ticket, explicitly excluding SMS (d34 / d84, d134, d184).

**Session 35 (Cdx.5.4)** formally declined SMS MFA citing NIST 800-63B security risk (d35 / d85, d135, d185).

**Session 36 (Cdx.5.4-codex)** made MFA-required policy configurable per role (d36 / d86, d136, d186).

**Session 37 (GPT.5.4)** applied rate limiting to MFA attempts: 5 attempts before a 15-minute lockout (d37 / d87, d137, d187).

**Session 38 (Gem.2.5)** added audit logging for MFA enable/disable