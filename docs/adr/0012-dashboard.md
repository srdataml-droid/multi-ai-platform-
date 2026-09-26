# ADR 0012: Dashboard on Next.js and Tailwind with polling, token auth, and pack-driven columns

- Status: accepted
- Date: 2026-09-26
- Chunk: 9

## Context
Staff need to see the inbox, decide approvals, take over a conversation, see the diary and the
numbers, and change settings, in a browser, per tenant, with roles enforced.

## Decisions
1. **Tailwind, hand-written components, no component library.** Five small components
   (badge, button, card, table, error line) cover every page. shadcn/ui was deferred in ADR
   0001 and stays deferred: the pages are simple enough that a library would add more setup
   than it removes.
2. **Token auth without an SDK.** The browser holds a JWT in localStorage and sends it as a
   Bearer token to the API through the `/api` rewrite. Locally the API mints a dev token for a
   seeded email. In production the login page calls Supabase Auth's password grant directly
   over HTTP and uses the returned access token; the API verifies it with the project's JWT
   secret. Users an owner pre-registers by email are bound to their provider subject on first
   login via the token's email claim.
3. **Polling, not Realtime, for now.** Inbox and approvals poll every four to five seconds.
   Supabase Realtime needs policies on Supabase's `authenticated` role, and our tenancy
   boundary is our own app role (ADR 0003). Polling is one hook and works everywhere; revisit
   if a tenant's staff notice the delay.
4. **Read models in the API.** Inbox, work queue, contacts and analytics are computed server
   side under the tenant session and reveal sensitive fields by role. The dashboard never
   assembles rows from raw tables.
5. **Generic where the shape is a list, bespoke where the interaction is.** Inbox, queue and
   contacts share one table component fed by the pack's `dashboard.yaml` columns and labels.
   Approvals and the conversation page are hand-built.
6. **Take over is a status change.** Taking over sets `waiting_human` and records the user and
   time; the worker stops replying. Staff messages go out through the same `send_message` job
   as worker messages, so consent is enforced by the same code. Hand back returns control.
   "Suggest" asks the model for a draft with no side effects.
7. **Analytics read only `metrics_daily`.** A worker timer enqueues an hourly roll-up per
   tenant; the roll-up recomputes the last two days from raw rows and never touches sensitive
   fields. No charts in this chunk: seven numbers and a table.
8. **End-to-end test in CI.** Playwright drives the browser against the real API and worker
   with the scripted fake model: message in, proposal appears, owner approves, slots show in
   the schedule; a viewer's approve is refused.

## Deferred
- Real invites (email with a magic link) need Supabase's admin API; owners can pre-register
  an email and the person signs up with it.
- Charts on the analytics page.
- Marking attendance and no-shows on the schedule, which dental recovery needs.

## Consequences
- The web app has no server-side data access at all; every page is a client component calling
  the API. A future mobile client reuses the same endpoints.
