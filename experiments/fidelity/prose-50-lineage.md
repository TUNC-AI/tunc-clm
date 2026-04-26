## auth-evolution.clm — 50-Session Handoff Summary

### Thread Metadata
- **Origin:** 2026-04-21 | **Depth:** 50 sessions | **Archive mode:** none (raw append)
- **Dream-pass consolidation:** none performed across this thread (no dream sessions recorded)
- **Releases shipped:** v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1, v0.7.0

---

### Distinct AI Families (10 authors, 5 families)
| Family | Members |
|---|---|
| Claude (CLd) | CLd.Snt4.6, CLd.Ops4.6, CLd.Snt4.5, CLd.Ops4.7 |
| Codex (Cdx) | Cdx.5.4, Cdx.5.4-codex |
| GPT | GPT.5.4 |
| Gemini (Gem) | Gem.2.5 |
| Llama (Lla) | Lla.4 |
| Kimi (Kmi) | Kmi.K2 |

---

### Phase 1 — Auth Extraction → v0.4.0 (Sessions 1–10)

- **Session 1 (CLd.Snt4.6):** Relocated auth logic from `web/server.go` → `internal/auth/middleware.go`.
- **Session 2 (CLd.Ops4.6):** Renamed `AuthCheck` → `RequireAuth` to match new convention.
- **Session 3 (CLd.Snt4.5):** Declared rate-limiter refactor out-of-scope (d3).
- **Session 4 (CLd.Ops4.7):** Preserved legacy session-cookie path in middleware (deferred, d4).
- **Session 5 (Cdx.5.4):** Investigated CI flake before merge.
- **Session 6 (Cdx.5.4-codex):** Fixed flake by isolating test fixtures.
- **Session 7 (GPT.5.4):** Deleted legacy session-cookie path under build tag — **reverts d4**.
- **Session 8 (Gem.2.5):** Placed rate-limiter in new package `internal/ratelimit` — **supersedes d3**.
- **Session 9 (Lla.4):** Added `Chain(...)` middleware composition helper.
- **Session 10 (Kmi.K2):** Shipped **v0.4.0**.

---

### Phase 2 — Hardening → v0.4.1 (Sessions 11–20)

- **Session 11 (CLd.Snt4.6):** Fixed CSRF token regression in `/api/login`.
- **Session 12 (CLd.Ops4.6):** Expanded session timeout config to per-route.
- **Session 13 (CLd.Snt4.5):** Added audit log for failed auth attempts.
- **Session 14 (CLd.Ops4.7):** Reduced rate-limit threshold 100/min → 60/min (d14).
- **Session 15 (Cdx.5.4):** Reverted threshold change due to false positives — **reverts d14**.
- **Session 16 (Cdx.5.4-codex):** Added structured logging via zerolog.
- **Session 17 (GPT.5.4):** Benchmarked middleware chain hot-path latency.
- **Session 18 (Gem.2.5):** Cached `RequireAuth` result for duration of request.
- **Session 19 (Lla.4):** Added Prometheus metrics: `auth_success_total`, `auth_failure_total`.
- **Session 20 (Kmi.K2):** Closed post-launch bugs; shipped **v0.4.1**.

---

### Phase 3 — OAuth → v0.5.0 (Sessions 21