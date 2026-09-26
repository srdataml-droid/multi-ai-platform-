# ADR 0003: Row Level Security is the tenancy boundary

- Status: accepted
- Date: 2026-09-26
- Chunk: 1

## Context
Every tenant table carries `tenant_id`. The question is who enforces that a request for
tenant A never touches tenant B: application code on every query, or the database.

## Decision
Postgres Row Level Security, enabled and forced on every tenant table and on `tenants`
itself. One policy per table: `tenant_id = current_setting('app.tenant_id', true)::uuid`,
for both USING and WITH CHECK, granted to the role `novaxis_app`.

The application connects with the owner role (which runs migrations) and, inside
`tenant_session(tenant_id)`, issues `SET LOCAL ROLE novaxis_app` plus
`set_config('app.tenant_id', ..., true)` at the start of every transaction. RLS applies to
`novaxis_app` because it is neither superuser nor the table owner. `service_session()`
skips both statements and is reserved for migrations, seeds and roll-ups.

`messages` and `audit_log` grant only SELECT and INSERT to `novaxis_app`, so they are
append-only for the application.

## Alternatives considered
- A `WHERE tenant_id = ?` in every query: one forgotten filter is a data breach. Rejected.
- A second login role with its own password: a second secret to rotate and a second
  pool for no isolation gain, because SET ROLE gives the same RLS behaviour. Rejected.
- Schema per tenant: migrations multiply by tenant count. Rejected for Phase 1.

## Consequences
- Every new tenant table needs `tenant_id`, an RLS policy and a grant in the same
  migration. `test_rls.py` fails if a table with `tenant_id` lacks forced RLS or if the
  migration's table list drifts from `novaxis_core.models.TENANT_TABLES`.
- A session with no `app.tenant_id` set sees zero rows, never all rows. Tested.
- On Supabase, the `postgres` role is not a superuser but can create roles and grant
  membership, so the same migration runs unchanged. Verify on first deploy.
