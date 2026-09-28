# ADR 0013: Host on Vercel (web and API) with Supabase Postgres

- Status: accepted
- Date: 2026-09-26

## Context
The founder wants the platform on Vercel. The original plan put the API and worker on
Railway or Render because the worker is an always-on loop. Vercel runs Python as
short-lived functions.

## Decisions
1. **Two Vercel projects from one repo.** `novaxis-web` builds `apps/web` (Next.js).
   `novaxis-api` builds the repo root as a FastAPI function via `vercel_app.py`, which puts
   the workspace packages on `sys.path`; the root `pyproject.toml` lists the flat runtime
   dependencies Vercel installs. Both deploy on every push to `main`, functions in London
   (`lhr1`).
2. **No worker process.** With `NOVAXIS_INLINE_WORKER=true` the API drains the job queue
   for up to 20 seconds after every POST or PUT, using exactly the worker's code (leasing,
   backoff, hand-off). A web-chat reply is therefore ready when the message request returns.
   Scheduled work (follow-ups, reminders, roll-ups) runs when a timer calls
   `POST /internal/tick` once a minute; Supabase `pg_cron` with `pg_net` makes that call.
3. **Database: a dedicated Supabase project** (`novaxis-worker`, London), separate from any
   other app. The API logs in as a dedicated role `novaxis_service` (BYPASSRLS, CREATEROLE)
   through the transaction-mode pooler on port 6543, with no connection pool and prepared
   statements off (`NOVAXIS_DB_POOLER=true`). Tenant isolation is unchanged: it uses only
   transaction-scoped settings, which the pooler supports.
4. **Migrations and seed run from the deployed code** via `POST /internal/migrate` and
   `POST /internal/seed`, protected by `NOVAXIS_CRON_SECRET`. Migration 0007 keeps
   Supabase's public API roles (`anon`, `authenticated`) off every table.
5. **Demo sign-in by passcode.** Outside local, the passwordless login works only with
   `NOVAXIS_DEMO_PASSCODE`. Remove the variable to close it. Supabase Auth sign-in replaces
   it when the first real tenant arrives.
6. **Vercel Authentication on previews only.** Production must be reachable by the widget,
   provider webhooks and the web app's server-side calls; it has its own sign-in.

## Known limits of this hosting
- Media: `/tmp` does not survive between function instances, so production uses
  `NOVAXIS_STORAGE_BACKEND=db` (photos and voice notes in the `media_objects` table,
  migration 0021, no extra keys). Move to `supabase` Storage with a service key when
  that table passes a few GB.
- Replies come from the scripted fake model until `ANTHROPIC_API_KEY` is set and
  `NOVAXIS_LLM_PROVIDER=anthropic`.
- A job that needs longer than the function limit fails and backs off like any other failure.

## Amendment (2026-09-26): migrations run when a deployment starts
The audit found that each deploy served about a minute of 500 errors. New code went live
before anyone called `/internal/migrate`, and the ORM selected columns that did not exist
yet. With `NOVAXIS_AUTO_MIGRATE=true`, `vercel_app.py` now brings the schema to head when a
new deployment's function first starts, before it serves a request. Concurrent cold starts
are serialised by a transaction-level advisory lock in `migrations/env.py`, which works
through the transaction pooler. Migrations must therefore stay additive: a column the old
code does not know about must not break it. `/internal/migrate` remains for manual use.
`/internal/tick` now returns 500 when the job loop itself fails, so the timer's history
shows an outage instead of "0 jobs".
