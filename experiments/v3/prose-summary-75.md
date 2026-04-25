# Auth platform — 75-session evolution summary

**Status (final session, session 75):** Cdx.5.4 on 2026-07-05 closed with `OAuth state param: encrypted user-intent payload (cycle 2)`. Across 8 phases (2× cycles), the project shipped v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1+v0.7.0 plus repeated re-shipping in cycles 2-2.

## Phases

1. **auth middleware extraction** (sessions 1-10, cycle 1): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition.
2. **post-launch hardening** (sessions 11-20, cycle 1): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, `RequireAuth` caching, Prometheus metrics.
3. **OAuth integration** (sessions 21-30, cycle 1): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests.
4. **MFA support** (sessions 31-40, cycle 1): TOTP per RFC 6238, ten single-use backup codes, QR-based enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 failed attempts.
5. **performance + security audit** (sessions 41-50, cycle 1): Trail of Bits engagement found a JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, supply-chain checks via `govulncheck`, OWASP top 10 reviewed.
6. **auth middleware extraction** (sessions 51-60, cycle 2): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition.
7. **post-launch hardening** (sessions 61-70, cycle 2): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, `RequireAuth` caching, Prometheus metrics.
8. **OAuth integration** (sessions 71-75, cycle 2): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests.

## Status

All planned scope shipped across 8 phases over 75 sessions. Production-ready.
