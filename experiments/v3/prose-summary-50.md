# Auth platform — 50-session evolution summary

**Status (final session):** v0.7.0 shipped with WebAuthn passkey support after a Trail of Bits security audit. JWT verify regression caught and patched in v0.6.1.

## Phases

1. **Auth middleware extraction** (sessions 1-10): pulled auth from `web/server.go` into `internal/auth/`, renamed `AuthCheck` to `RequireAuth`, deleted the legacy session-cookie path under a build tag after it was traced to a test-fixture ordering bug, reintroduced rate limiting in a separate `internal/ratelimit/` package, added middleware composition via `Chain(...)`. Shipped v0.4.0.
2. **Post-launch hardening** (sessions 11-20): CSRF fix, per-route session timeout, audit logging, rate-limit threshold tuning, structured logging, RequireAuth caching, Prometheus metrics. Shipped v0.4.1.
3. **OAuth integration** (sessions 21-30): provider registry (Google/GitHub/GitLab), JWT migration to HS512, encrypted state param, per-callback rate limiting, scope mapping, integration tests, documentation. Shipped v0.5.0.
4. **MFA** (sessions 31-40): TOTP per RFC 6238, ten single-use backup codes, QR-based enrollment, no SMS (per NIST 800-63B), per-role MFA-required policy, lockout after 5 failed attempts, audit logging. Shipped v0.6.0. WebAuthn deferred.
5. **Performance + security audit** (sessions 41-50): Trail of Bits engagement found a JWT-verify CVE (HS512 → RS256 reverted), middleware p95 dropped 800µs to 120µs, supply-chain checks via govulncheck in CI, OWASP top 10 reviewed. Shipped v0.6.1 with JWT patch and v0.7.0 with WebAuthn.

## Status

All planned scope shipped across six minor versions. Production-ready.
