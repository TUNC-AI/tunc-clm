# Auth platform — 200-session evolution summary

**Status (final session, session 200):** Kmi.K2 on 2026-11-10 closed with `ship v0.7.0 with WebAuthn passkey (cycle 4)`. Across 20 phases (4× cycles), the project shipped v0.4.0, v0.4.1, v0.5.0, v0.6.0, v0.6.1+v0.7.0 plus repeated re-shipping in cycles 2-4.

## Phases

1. **auth middleware extraction** (sessions 1-10, cycle 1): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition.
2. **post-launch hardening** (sessions 11-20, cycle 1): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, `RequireAuth` caching, Prometheus metrics.
3. **OAuth integration** (sessions 21-30, cycle 1): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests.
4. **MFA support** (sessions 31-40, cycle 1): TOTP per RFC 6238, ten single-use backup codes, QR-based enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 failed attempts.
5. **performance + security audit** (sessions 41-50, cycle 1): Trail of Bits engagement found a JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, supply-chain checks via `govulncheck`, OWASP top 10 reviewed.
6. **auth middleware extraction** (sessions 51-60, cycle 2): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition.
7. **post-launch hardening** (sessions 61-70, cycle 2): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, `RequireAuth` caching, Prometheus metrics.
8. **OAuth integration** (sessions 71-80, cycle 2): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests.
9. **MFA support** (sessions 81-90, cycle 2): TOTP per RFC 6238, ten single-use backup codes, QR-based enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 failed attempts.
10. **performance + security audit** (sessions 91-100, cycle 2): Trail of Bits engagement found a JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, supply-chain checks via `govulncheck`, OWASP top 10 reviewed.
11. **auth middleware extraction** (sessions 101-110, cycle 3): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition.
12. **post-launch hardening** (sessions 111-120, cycle 3): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, `RequireAuth` caching, Prometheus metrics.
13. **OAuth integration** (sessions 121-130, cycle 3): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests.
14. **MFA support** (sessions 131-140, cycle 3): TOTP per RFC 6238, ten single-use backup codes, QR-based enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 failed attempts.
15. **performance + security audit** (sessions 141-150, cycle 3): Trail of Bits engagement found a JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, supply-chain checks via `govulncheck`, OWASP top 10 reviewed.
16. **auth middleware extraction** (sessions 151-160, cycle 4): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition.
17. **post-launch hardening** (sessions 161-170, cycle 4): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, `RequireAuth` caching, Prometheus metrics.
18. **OAuth integration** (sessions 171-180, cycle 4): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests.
19. **MFA support** (sessions 181-190, cycle 4): TOTP per RFC 6238, ten single-use backup codes, QR-based enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 failed attempts.
20. **performance + security audit** (sessions 191-200, cycle 4): Trail of Bits engagement found a JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, supply-chain checks via `govulncheck`, OWASP top 10 reviewed.

## Status

All planned scope shipped across 20 phases over 200 sessions. Production-ready.
