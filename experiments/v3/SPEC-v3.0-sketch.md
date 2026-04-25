# CLM/3.0 — sketch (memory protocol, not just a format)

Status: design-stage. Worked example in this directory; spec validated *from* the example, not the other way around. Do not promote until the bench (this directory's `RESULTS.md`) confirms the architecture's claims.

## What changes from v2.1

CLM/2.1 is a serialization format: each `.clm` document is a self-contained handoff message read once and replied to.

CLM/3.0 reframes the document as a **stateful, append-only data structure** with periodic consolidation — the same architecture used by:

- Biological memory (short-term → sleep → long-term consolidation).
- Git (commit log + occasional repack/squash).
- Distributed databases (write-ahead log + checkpoint).
- The `dream` skill in Claude Code's own memory system (scattered markdown → consolidated `MEMORY.md` index).

Three new section types are added to v2.1; everything from v2.1 is preserved.

## New section types

### `[STATE]` — consolidated current truth

The output of the most recent dream pass. Contains the project's current state in compact form. Always exactly one `[STATE]` section per file. **Replaceable** — a dream pass writes a new `[STATE]` and discards the old one (which is preserved in the archive).

```
[STATE]
  ;; consolidated as of last.dream:2026-04-23 evening
  ;; written.by: CLd.Ops4.7 during dream pass over sessions 1-5
  
  project: Continuity / TUNC Hub
  current.phase: 4 (embedded IDE)
  decisions.live: [d1, d2, d3, d4, d5, d6]
  files.touched: [web/server.go, internal/auth/middleware.go, ...]
  status: in-progress; flake diagnosed; fix planned next session
;;
```

### `[DELTA.<session-id>]` — append-only change record

Each session that modifies the document writes a `[DELTA.<session-id>]` section instead of editing `[STATE]` directly. The session-id is a sortable label like `2026-04-26-morning` or just a session counter. Append-only: deltas are never edited or deleted (only archived during a dream pass).

```
[DELTA.2026-04-24-a]
  ;; CLd.Snt4.6 | append-only | 2026-04-24 morning:
  fix.ordering.bug d6: isolated test fixtures (TestSessionCleanup no longer depends on TestAuthMiddleware state)
  revert d4: deleted legacy session-cookie path under build tag
  reason.for.revert: the legacy path was the source of the ordering bug
  status.update: ordering.bug -> resolved
;;
```

Operation vocabulary (minimum set):

- `add.<key>` — introduce a new fact.
- `update.<key>` — modify an existing fact (last-write-wins for `[STATE]` consolidation).
- `remove.<key>` — retire a fact (still preserved in archive).
- `revert <previous-id>` — explicitly undo a prior decision; both kept.
- `fix <previous-id>` — correct a prior delta; both kept.
- `note: <prose>` — free prose for context that doesn't fit a key.

### `[DREAM.LOG]` — record of consolidation passes

Append-only log of dream passes. One line per pass.

```
[DREAM.LOG]
  2026-04-23 evening | CLd.Ops4.7 | consolidated 5 deltas (sessions 1-5) | live → 1 [STATE] block
  2026-04-30 morning | Cdx.5.4    | consolidated 7 deltas (sessions 6-12) | live → updated [STATE]
  ...
;;
```

## The dream-pass protocol

When `count(active [DELTA.*]) > N` (suggested heuristic: 5–10 deltas, or when the active deltas exceed the `[STATE]` block in tokens), any AI opening the file MAY run a dream pass:

1. **Read** `[STATE]` and all active `[DELTA.*]` blocks in chronological order.
2. **Apply** each delta to a working copy of `[STATE]`. Operations are well-defined; conflicts resolved chronologically (later wins for `[STATE]` value; both preserved in archive).
3. **Write** the new `[STATE]` block, replacing the old one in-place.
4. **Archive** the merged `[DELTA.*]` blocks. Two options:
   - **Inline archive** — append to a `[DELTA.ARCHIVE]` section in the same file. Audit thread stays unified; file grows.
   - **Sibling archive** — move to `<basename>.archive.clm`. Live doc stays small.
   v3.0 supports both; the doc's own header declares which (`archive.mode: inline | sibling`).
5. **Append** a line to `[DREAM.LOG]` recording who ran the pass, when, how many deltas were merged, and how (inline/sibling).
6. **Sign** in `[ROLL.CALL]` and the file closer (per the v1+ ritual; unchanged).

A dream pass is **interpretive** — different AIs may produce slightly different `[STATE]` from the same deltas. The pass is signed; reviewers can disagree with prior consolidations and run a fresh dream over a wider window.

## Conflict resolution

Two deltas conflict when they update the same key. Resolution is chronological:

- The newer delta's value wins for `[STATE]`.
- Both deltas are preserved in `[DELTA.ARCHIVE]` (or the sibling archive file).
- A reader querying "who decided X and when?" reads the archive for full lineage.

Explicit `revert <id>` and `fix <id>` operations make the relationship between deltas auditable: the lineage shows X was decided in delta Y, then reverted in delta Z, with reasons attached to both.

## Why prose summary can't do this

Prose summarization compresses by destroying lineage. A 300-token summary of a 50-session thread can preserve current decisions but cannot answer:

- "Who first proposed renaming `AuthCheck` to `RequireAuth`?"
- "In which session was the legacy session-cookie path reverted, and why?"
- "Who diagnosed the test flake, and as what kind of bug?"

CLM/3.0's `[DREAM.LOG]` and `[DELTA.ARCHIVE]` answer these questions cheaply because they preserve the audit trail by construction. The active `[STATE]` is compact (not the summary's prose, but a structured key-value snapshot); the lineage migrates to archive but stays *queryable* in the same format.

## What v3.0 doesn't claim

- **Not cheaper than prose summary on token count.** Prose summary @ 300 tokens always wins on raw count. v3.0's win is **on the Pareto frontier of tokens × lineage-fidelity**, where prose summary is dominated.
- **Not deterministic.** A dream pass is interpretive. Two AIs may produce slightly different `[STATE]` from the same deltas. The signed dream-pass record lets reviewers disagree.
- **Not a replacement for v1/v2.1.** Single-handoff documents don't need this machinery. v3.0 is for **long-running multi-session threads** — `CONTINUITY.clm` files, ongoing project handoffs, accumulated audit logs.

## Open design questions

1. **Trigger heuristic** — count vs token-budget vs explicit only.
2. **Archive location default** — inline (unified thread) vs sibling (live doc small).
3. **Operation vocabulary granularity** — is `add/update/remove/revert/fix/note` enough, or do we need JSON Patch / CRDT op set?
4. **`[STATE]` schema** — free-form, key-value, or structured-JSON-in-prose? The bench in this directory uses key-value; richer schemas TBD.
5. **Cross-model consistency** — does Claude vs Gemini vs Codex produce the same `[STATE]` from the same deltas? Probably approximately. v3.0 spec accepts this is interpretive.

## See also

- `RESULTS.md` — worked example: 10-session thread in three formats (raw append, v3.0 dreamed, prose summary), with token counts and lineage-recall questions.
- `raw-append.clm`, `dreamed.clm`, `prose-summary.md` — the three artifacts.
- `lineage_qa.json` — 15 lineage-recall questions; the bench v3.0 was built to win.
- `tokens.py` — local tiktoken probe (no API).

— *Drafted by CLd.Ops4.7 (1M-context), 2026-04-25, in response to genie's "what if [DELTA] blocks dream-merge once in a while?"*
