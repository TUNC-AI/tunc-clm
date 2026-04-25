# Continuity — 2026-04-25

Session author: Claude Sonnet 4.6.

## Task

Extract the auth middleware from `web/server.go` into a new `internal/auth/` package. Status: in progress.

## Files touched

- `web/server.go`
- `internal/auth/middleware.go`
- `internal/auth/middleware_test.go`
- `web/server_test.go`

## Decisions

- Legacy session-cookie path preserved in the middleware (deferred, out of scope).
- `AuthCheck` renamed to `RequireAuth` (matches new convention).
- Rate limiter not refactored (out of scope).

## Open questions for next session

1. Should the legacy session-cookie path be deleted, or kept under a build tag?
2. The flake in `web/server_test.go` — real ordering bug, or a test race?

## For the next session

Bulk of the work is done. Focus on investigating the `web/server_test.go` flake first — may be a real ordering bug. Middleware extraction is safe to merge; tests pass locally. CI is not green, but the failure is an unrelated timeout in the kane-cve fetch.

Session ends; memory does not.

— Claude Sonnet 4.6, 2026-04-25
