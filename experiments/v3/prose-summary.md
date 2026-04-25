# Auth middleware refactor — handoff summary

**Status (2026-04-25):** ready to merge as v0.4.0; all tests pass, CI green.

## Work done

Auth middleware extracted from `web/server.go` into `internal/auth/` package. `AuthCheck` renamed to `RequireAuth` per new convention. Rate limiting introduced in a separate `internal/ratelimit/` package with composable middleware via `internal/middleware/chain.go`. Integration tests added covering happy path, expired session, and malformed token. Legacy session-cookie path was deleted under a build tag after a CI flake was traced to test-fixture contamination from that path. Files touched: `web/server.go`, `internal/auth/middleware.go`, `internal/auth/middleware_test.go`, `internal/auth/integration_test.go`, `web/server_test.go`, `internal/ratelimit/middleware.go`, `internal/ratelimit/middleware_test.go`, `internal/middleware/chain.go`.

## Status

Ten sessions across multiple AI assistants. All tests pass locally and in CI. Ship as v0.4.0.
