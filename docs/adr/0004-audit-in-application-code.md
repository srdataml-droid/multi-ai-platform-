# ADR 0004: Audit log written by application code, not triggers

- Status: accepted
- Date: 2026-09-26
- Chunk: 1

## Context
The audit trail must say who did what. The database cannot know the actor (a user id, the
worker, or an operator in a support session) unless the application tells it.

## Decision
`novaxis_db.audit.record(session, tenant_id=, actor=, event=, ...)` is called by the
code that makes a state change, in the same transaction. The table is append-only for the
app role (ADR 0003). Events are named `subject.verb` (for example `contact.created`,
`proposal.approved`).

## Alternatives considered
- Row-level triggers on every table: complete coverage of raw changes, but no actor, no
  business-level event name, and noisy diffs. Could be added later for forensic depth.

## Consequences
- A code path that changes state without an audit call is a bug; reviewers check for it.
  Chunk 4 adds a test that every executor writes an audit row.
