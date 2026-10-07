# Persistent website enquiries and manual callbacks

This extends the account-free `/demo` prototype with a real, deliberately small workflow. It does not place calls, send email/SMS, use an AI model, book engineers or connect a calendar.

## User flow

1. Sign in as an existing owner. Open Schedule → Callback requests.
2. Enable the website form for this business. It is disabled by default for every tenant. The change is audited. Owners and operators can configure it; staff can review; viewers cannot access the callback queue or decide.
3. Share `/enquire/<tenant-slug>` once its deployment is accessible. Customers need no app account. The page states that it is for routine enquiries and captures consent to respond.
4. Submitted contact details, encrypted job notes and a callback proposal persist in the existing Postgres tables. The owner sees these in `/callbacks` and the existing approval queue. No model or worker is needed to create the request.
5. Review the requested date/time/time zone; edit it if necessary, then approve or decline. Approval creates a durable **manual callback task**, not a promise sent to the customer. An engineer visit must be agreed separately.
6. After doing the callback yourself, record Completed, No answer or Cancelled. Outcomes persist and are audited. An outcome is final for this first version; there is no retry scheduler or automatic follow-up.

## Existing architecture reused

`Contact` + `Conversation` + encrypted `Message` → `ActionProposal(kind=schedule_callback)` → existing `/approvals/{id}` → registered executor → proposal result (`scheduled`) → `/callbacks/{id}/outcome`.

No new database schema or customer store. Existing RLS and tenant-scoped sessions apply. Callbacks remain linked to the conversation and therefore to the existing privacy export/erasure path. Free-text job notes use the existing encrypted summary/message fields; contact names/numbers/email follow the existing contact storage policy.

Public submission requires tenant opt-in, validates bounded inputs, checks the existing widget origin policy, and uses existing database-backed rate limits outside local/test. A transaction advisory lock keyed by tenant + request UUID makes concurrent retries idempotent. It never returns existing customer data. Approval now locks the proposal row so concurrent decisions cannot both execute. Outcome changes also lock the proposal row. The action's medium risk floor prevents tenant settings from removing human approval.

The public form is hosted within the Novaxis web app and calls same-origin `/api`; embed/link the page rather than making cross-origin requests to the API. Origin checks are not authentication or a substitute for spam protection.

## Local run

Use a dedicated local database, never a production database for tests: the shared pytest migration fixture drops and recreates its schema.

```sh
uv sync --all-packages --frozen
# Set NOVAXIS_DATABASE_URL to your isolated local Postgres database.
uv run alembic -c packages/db/alembic.ini upgrade head
uv run python -m novaxis_db.seed
uv run uvicorn novaxis_api.main:app --host 127.0.0.1 --port 8107
```

In `apps/web`:

```sh
npm ci
NOVAXIS_API_URL=http://127.0.0.1:8107 npm run build
npx next start -p 3108
```

Open `http://localhost:3108/login`, use the local seeded `owner@demo-hvac.test` account, then `/callbacks`. Local demo login is existing behavior; never enable local environment mode on a public deployment. Configure `NOVAXIS_PUBLIC_WEB_URL` to the web URL when enforcing origin restrictions.

## Verification

```sh
uv run ruff check .
uv run ruff format --check .
uv run mypy
NOVAXIS_TEST_DATABASE_URL=<isolated-test-db> uv run pytest -q
```

Frontend: lint, typecheck, unit tests and production build. `playwright.demo.config.ts` tests the fake account-free demo without a backend. `playwright.workflow.config.ts` tests the real form/owner flow against the running local API on 8107 with a frontend built for that URL. It runs on 3108 and records video. Set `PW_CHROMIUM_PATH` when using a preinstalled browser. The ordinary CI browser suite also includes the persistent workflow test.

## Deployment and limitations

Keep this draft isolated from `production`. Before public testing: point the web preview at the matching API, supply the existing hosted auth/database/encryption settings, use a dedicated test tenant/database, and grant testers access through Vercel's supported preview sharing. Enabling a business form does not bypass Vercel deployment protection. The frontend/API/database connection for a remote preview is not verified just by green deployment checks.

This is useful for manual enquiry handling, not a complete receptionist service. No background notifications, callback reminders, automatic time-zone parsing, slot availability calculation, multi-user assignment or pagination beyond the latest 100 requests is provided. Supply a business-approved privacy notice and retention settings before collecting real customer data. Configure spam controls for the expected public traffic; the existing limiter assumes a trusted hosting proxy for forwarded IP headers.

Piper speech output and speech recognition are separate future integrations. Neither is connected. Telephone work also needs a provider/streaming service and failure handling; no paid account or real customer number has been connected by this change.
