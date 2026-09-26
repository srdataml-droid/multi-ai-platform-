# Novaxis AI Worker Platform


## What this is

A multitenant AI worker for small service businesses. It answers messages (and later calls),
does intake, books or escalates, confirms and reminds, and writes back into the business's own
system of record, with a human approving anything risky. Three vertical packs on one core:

- **HVAC** (heating, ventilation, air conditioning, plumbing, electrical contractors)
- **Dental** (general dental practices, UK first, then US)
- **Restoration** (water, fire, mould and storm damage contractors)

One core. One dashboard. Per-industry packs that load different vocabulary, intake forms,
risk rules, workflows and integrations. The business keeps the software it already uses; the
worker sits in front of it and feeds it.

## What it is not

- Not a generic chatbot. Every conversation has a job: qualify, book, confirm, remind, recover, or hand off.
- Not autonomous. Anything that spends money, changes a booking, contacts someone first, or touches
  health information goes through the approval gate until the tenant relaxes that rule in writing.
- Not a scraper. The worker never harvests personal data from social media or third-party sites.
  Outbound is to people who have already contacted the business or opted in, plus a separate,
  human-run prospecting process for finding business customers.

## The pipeline this repo builds

```
inbound event  ->  normalise  ->  worker turn (LLM + pack rules)  ->  proposed actions
             ->  risk classifier  ->  auto-run | approval queue | refused
             ->  executed action  ->  audit log  ->  metrics
```

Every stage is a table in Postgres and a function you can call from a test. No stage is
skipped, even in demos.

## Stack (fixed, do not swap without an ADR)

| Layer | Choice | Why |
|---|---|---|
| API and worker | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 | Founder's strongest stack |
| Database | Postgres via Supabase, Row Level Security on every tenant table | Multitenancy at the database, not in application code |
| Queue | Postgres table `jobs` polled by a worker process (no Redis in Phase 1) | One fewer service to run |
| LLM | Anthropic API. Default `claude-sonnet-5` for worker turns, `claude-haiku-4-5-20251001` for classification and extraction, `claude-opus-5-5` only for evals and hard cases | Cost vs quality per task |
| Web | Next.js (App Router), TypeScript, Tailwind, shadcn/ui | Founder already uses it |
| Auth | Supabase Auth, one `tenant_id` claim per user | Ships with the database |
| Messaging | Twilio for SMS and voice, Resend or SMTP for email, Meta WhatsApp Cloud API later | Standard, documented |
| Payments | Stripe subscriptions plus metered usage | Standard |
| Hosting | API and worker on Railway or Render, web on Vercel, Postgres on Supabase | Founder already deploys here |
| Observability | Langfuse (self-hosted or cloud) for LLM traces, structured JSON logs, Sentry | Debug conversations, not guess |
| Tests | pytest, pytest-asyncio, Playwright for the web, golden-conversation evals in `evals/` | Nothing merges red |

Local dev runs on Docker Compose: Postgres, API, worker, web. No GPU is ever required.

## Repo layout

```
apps/
  api/          FastAPI app: HTTP routes, webhooks, auth, tenancy middleware
  worker/       The job runner: picks jobs, runs worker turns, executes approved actions
  web/          Next.js dashboard
packages/
  core/         Domain models, risk rules, approval gate, action executors, integrations SDK
  packs/        One folder per vertical: hvac/, dental/, restoration/. Config + prompts + tests
  db/           Alembic migrations, RLS policies, seed data
evals/          Golden conversations per pack, scoring scripts, regression thresholds
docs/
  ARCHITECTURE.md   The design. Read before touching packages/core
  adr/              Architecture Decision Records, one file per decision
  research/         Market, workflow and policy research
  demo/             The old demo, for reuse only
```

## Working rules for every session

1. **Read first.** `docs/ARCHITECTURE.md` and the last three files in `docs/adr/` before writing code.
2. **One chunk per session.** The chunk prompt names the goal, the files, the tests and the
   definition of done. Do not start the next chunk. Do not "while I'm here" into other areas.
3. **Tests before done.** A chunk is done when its tests pass in `docker compose run test`
   and the founder can run the demo step named in the chunk.
4. **Small diffs.** Prefer three commits of 150 lines to one of 500. Stop and summarise if a
   change would exceed roughly 600 lines; propose a split.
5. **Decide, then record.** When the chunk leaves a choice open, choose the simplest option
   that satisfies the tests, write a one-page ADR in `docs/adr/NNNN-title.md`, and move on.
   Ask the founder only when two options lead to materially different products.
6. **Never bypass the gate.** No code path may execute a `medium` or `high` risk action
   without an `approvals` row in state `approved`. Tests assert this. A PR that weakens it is rejected.
7. **Tenant isolation is not optional.** Every query goes through the tenant-scoped session.
   Every new table gets `tenant_id NOT NULL` and an RLS policy in the same migration.
   A test in `packages/db/tests/test_rls.py` tries to read another tenant's rows and must fail.
8. **Secrets** live in environment variables, loaded through `packages/core/settings.py`.
   Per-tenant integration credentials are encrypted at rest with a key from the environment.
   Never log a credential, a token, a phone number in full, or health details at INFO level.
9. **No model training.** If a task seems to need a trained model, use an LLM call with a
   few-shot prompt and write the eval. Revisit only if evals fail.
10. **Explain to a judge.** Every module has a docstring a non-engineer could read that says
    what it does and why it exists. The founder must be able to defend every design choice.

## Commands

```
make up          # docker compose up: postgres, api, worker, web
make test        # all unit and integration tests
make evals       # golden-conversation evals, prints pass rate per pack
make migrate     # alembic upgrade head
make seed        # seed one demo tenant per pack (idempotent)
make dev-token u=owner@demo-hvac   # mint a local JWT for a seeded user
make demo        # runs the demo script for the current chunk
```

## Definition of done for the whole Phase 1

A visitor to the demo tenant's website chat, SMS number or email:
1. gets a reply within 10 seconds,
2. is taken through the pack's intake,
3. gets an appointment proposal (or an emergency escalation),
4. which lands in the approval queue,
5. which a staff member approves in the dashboard,
6. which writes to the tenant's calendar and sends a confirmation,
7. with every step visible in the audit log and the metrics page.

Repeatable on a fresh clone with `make up && make seed && make demo`.
