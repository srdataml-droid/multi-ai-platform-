# Architecture: Novaxis AI Worker Platform

> Status: v0.2, live demo on Vercel. Every section names the chunk in `docs/BUILD-PLAN.md` that implements it.

## 1. Goals and non-goals

**Goals**
- One core, many tenants, three vertical packs. Adding a fourth pack must not touch `packages/core`.
- Every customer-facing outcome is measurable: response time, intake completion, bookings, recovered missed contacts, staff minutes saved.
- A human can take over any conversation at any moment and see exactly what the worker did and why.
- Runs for one tenant on a free-tier Supabase project and two Vercel projects (web and API). Scales by adding worker processes, not by rewriting.

**Non-goals for Phase 1**
- Voice calls (Phase 3). Text channels prove the loop first.
- Payments collection from end customers (only the tenant's subscription to us).
- Deep write integrations with practice-management or field-service software. Phase 1 writes to a calendar and sends messages. Phase 2 adds vendor APIs one at a time.
- Any local model training.

## 2. System overview

```
                 +-------------------+      +-------------------+
  Web chat  ---> |                   |      |                   |
  SMS       ---> |   apps/api        | ---> |   Postgres        | <--- apps/web (dashboard)
  Email     ---> |   (FastAPI)       |      |   (Supabase, RLS) |
  WhatsApp  ---> |   webhooks in     |      |                   |
  Voice(P3) ---> |   normalised      |      |  conversations    |
                 |   events out      |      |  messages         |
                 +-------------------+      |  jobs             |
                                            |  action_proposals |
                                            |  approvals        |
                                            |  audit_log        |
                                            +---------+---------+
                                                      |
                                                      v
                                            +-------------------+       +-----------------+
                                            |   apps/worker     | ----> | Anthropic API   |
                                            |   job loop        |       | Twilio / email  |
                                            |   worker turn     |       | Google Calendar |
                                            |   risk gate       |       | vendor APIs (P2)|
                                            |   executors       |       +-----------------+
                                            +-------------------+
```

Three processes. The API only validates, normalises and enqueues. The worker does all
thinking and all side effects. The dashboard reads Postgres directly through Supabase with
RLS and calls the API for mutations. This split means a stuck LLM call never blocks a webhook,
and a worker crash never loses an inbound message (it is already in `messages` and `jobs`).

## 3. Tenancy model (Chunk 1)

- A **tenant** is one business location group (one dental practice, one HVAC company). Multi-location businesses are one tenant with many `locations`.
- Every domain table has `tenant_id uuid NOT NULL REFERENCES tenants(id)`.
- Postgres RLS: `USING (tenant_id = current_setting('app.tenant_id')::uuid)`. The API sets this per request from the JWT. The worker sets it per job. Service-role access (migrations, cross-tenant metrics) uses a separate role and is never exposed to the web.
- **Tenant settings** is one JSONB column validated by a Pydantic model per pack. It holds: pack id, timezone, business hours, services offered, service area, escalation contacts, risk-rule overrides, channel config, tone settings.
- **Users** belong to exactly one tenant with a role: `owner`, `staff`, `viewer`. Novaxis staff use a separate `operator` role that can enter a tenant with an audit entry ("support session by X at Y").

## 4. Data model (Chunk 1, extended in later chunks)

Core tables. Columns shown are the ones that carry design intent; timestamps and ids are implied.

| Table | Purpose | Key columns |
|---|---|---|
| `tenants` | The business | `name, pack_id, settings jsonb, plan, status` |
| `locations` | Physical sites | `tenant_id, name, address, timezone, calendar_ref` |
| `users` | Dashboard logins | `tenant_id, role, email` |
| `contacts` | People the business talks to | `tenant_id, display_name, phones[], emails[], consent jsonb, pack_fields jsonb, merged_into` |
| `conversations` | One thread per contact per channel episode | `tenant_id, contact_id, channel, status (open, waiting_human, waiting_customer, closed), summary, extracted jsonb, owner_user_id, takeover_at` |
| `messages` | Every inbound/outbound message | `tenant_id, conversation_id, direction, channel, body, provider_ref, author (customer, worker, human), delivered_at` |
| `jobs` | Queue | `tenant_id, kind, payload jsonb, state (queued, running, done, failed), attempts, run_after, locked_by` |
| `action_proposals` | What the worker wants to do | `tenant_id, conversation_id, kind, params jsonb, risk (low, medium, high), reason, state (proposed, auto_approved, awaiting, approved, rejected, executed, failed)` |
| `approvals` | The human decision | `tenant_id, proposal_id, decided_by, decision, note` |
| `appointments` | Bookings the worker made or proposed | `tenant_id, location_id, contact_id, starts_at, ends_at, service_code, status, external_ref` |
| `audit_log` | Append-only trail | `tenant_id, actor (worker, user id, system), event, subject_table, subject_id, diff jsonb` |
| `integrations` | Per-tenant connected systems | `tenant_id, provider, encrypted_credentials, config jsonb, health` |
| `metrics_daily` | Rolled-up numbers for the dashboard | `tenant_id, day, channel, inbound, answered_under_10s, intake_completed, bookings_proposed, bookings_approved, escalations, human_takeovers` |

Rules:
- `messages` and `audit_log` are append-only. No UPDATE or DELETE grants for the app role.
- Health details (dental symptoms) live only in `conversations.extracted` and `contacts.pack_fields`, both of which are marked sensitive and excluded from logs and from metrics export.
- Contact merge is a soft pointer (`merged_into`), never a delete.

## 5. The worker loop (Chunk 3)

```
pick job (SELECT ... FOR UPDATE SKIP LOCKED, run_after <= now)
  -> set app.tenant_id
  -> load tenant, pack, conversation, last N messages, contact
  -> build context: pack system prompt + tenant facts + conversation state + tools
  -> LLM call with tool definitions (the pack's allowed actions)
  -> parse: reply text + zero or more action proposals
  -> for each proposal: classify risk (pack rules + core rules), store proposal
  -> low  : execute now, log
     medium: state=awaiting, notify staff, log
     high  : state=rejected with reason, reply asks a human to follow up, log
  -> send reply through the channel adapter, store message
  -> schedule follow-up job if the pack says so (reminder, chase, close)
  -> mark job done; on exception mark failed with backoff (max 3 attempts, then waiting_human)
```

Design points:
- **Deterministic context.** The prompt is built from database rows, never from prior LLM output alone. A conversation summary is regenerated every 10 messages and stored.
- **Tools are the contract.** The LLM can only propose actions that exist in the pack's tool list. Free-text "I'll book that for you" without a proposal is caught by a post-check that inserts a "verify claim" proposal at medium risk.
- **Idempotency.** Every executor takes the `proposal_id` as its idempotency key. Re-running a job cannot double-book or double-send.
- **Time budget.** A turn that exceeds 20 seconds sends "one moment" and continues; over 60 seconds it hands to a human.
- **Your own agent instead.** A business can set `assistant: external`: the built-in model stays quiet and the business's own agent (e.g. Hermes) reads conversations and proposes through `/agent/v1`, into the same `propose()` and gate. The emergency pre-check still runs here first. See docs/agent-api.md.

## 6. Action model and the approval gate (Chunk 4)

Actions are the only way the worker touches the world.

| Action kind | Default risk | Notes |
|---|---|---|
| `reply` | low | The text answer itself. Pack may raise to medium for health advice patterns |
| `ask_intake_question` | low | Structured question from the pack's intake form |
| `extract_fields` | low | Writes to `conversations.extracted` |
| `propose_appointment` | medium | Creates `appointments` in `proposed` state |
| `confirm_appointment` | medium, low once tenant enables auto-confirm for a service | Writes to calendar, sends confirmation |
| `reschedule_appointment`, `cancel_appointment` | medium | |
| `send_reminder` | low | Only for existing appointments, template text |
| `escalate_emergency` | low | Notifies the on-call contact immediately. Low risk because not escalating is the dangerous branch |
| `hand_to_human` | low | Sets conversation to `waiting_human` |
| `outbound_first_contact` | high | Never auto. Human composes or approves per message |
| `write_to_vendor_system` | medium | Phase 2 |
| `collect_payment`, `quote_price` | high | Price quoting is pack-configurable to medium with a price list |

Core rules that no pack can lower:
- A safeguarding concern is `high` and triggers `hand_to_human`: the writer appears to be a child, a child is left alone, or there is self-harm, a threat against a person, abuse or a weapon. A parent mentioning their child is ordinary and is not flagged (amended 2026-09-27, see ADR 0007).
- Anything that contacts a person who has not messaged the tenant first is `high`.
- Any message that would go to a number or address with `consent.status = 'opted_out'` is refused, not proposed.

The gate is a single function, `packages/core/gate.py:decide(proposal, tenant, pack) -> Decision`, with a table-driven test of at least 40 cases. The dashboard's approval queue is a view over `action_proposals WHERE state='awaiting'`.

## 7. Packs (Chunk 5, 6, 7)

A pack is a folder. It contains no core code.

```
packages/packs/dental/
  manifest.yaml        id, name, version, default risk overrides, allowed actions, channels
  intake.yaml          ordered questions with types, validation, skip logic, sensitivity flags
  vocabulary.yaml      terms: "patient" not "customer", "appointment" not "job", service codes
  prompts/
    system.md          the worker's role, tone, boundaries, escalation phrases
    summarise.md
  rules.py             pack-specific risk hooks: def classify(proposal, context) -> Risk | None
  workflows.yaml       reminder timings, no-show recovery, recall cadence, waitlist logic
  dashboard.yaml       which columns and widgets the dashboard shows for this pack
  evals/               golden conversations with expected proposals
  tests/
```

Loading: `packages/core/packs.py` reads the manifest, validates it against a schema, and exposes `Pack` objects. The core never imports a pack directly; it looks up `tenant.pack_id`.

Pack summaries:

**HVAC**: intake asks for problem type, symptom, equipment age if known, urgency (no heat in winter and gas smell are emergencies), address and service area check, preferred window. Workflows: missed-call text back, estimate follow-up at 24h and 72h, seasonal maintenance reminder. Dashboard: unassigned requests, emergencies, estimate pipeline.

**Dental**: intake asks new or existing patient, reason for visit, pain scale and duration, insurance or NHS/private (UK), preferred provider and time. Emergencies: uncontrolled bleeding, facial swelling affecting breathing or swallowing, trauma. Workflows: confirmation at booking, reminder at 48h and 2h, no-show recovery, recall at 6 months, waitlist fill. Dashboard: unconfirmed appointments, incomplete forms, waitlist. All symptom text is sensitive.

**Restoration**: intake asks damage type (water, fire, mould, storm), when it happened, is it still active (water still flowing is an emergency), property type, insurance claim yes/no and insurer, photos requested. Workflows: emergency dispatch acknowledgement, inspection scheduling, claim document chase, adjuster follow-up. Dashboard: active emergencies, inspections due, claims awaiting documents.

## 8. Channels and integrations (Chunk 2, 8, 11)

One adapter interface for channels:

```python
class ChannelAdapter(Protocol):
    provider: str
    async def parse_inbound(self, request) -> NormalisedInbound   # webhook -> event
    async def send(self, tenant, to, body, reply_to=None) -> ProviderRef
    async def verify_signature(self, request) -> bool
```

One adapter interface for systems of record:

```python
class SystemOfRecord(Protocol):
    provider: str
    async def find_contact(self, tenant, phone=None, email=None) -> ExternalContact | None
    async def availability(self, tenant, location, service_code, window) -> list[Slot]
    async def create_booking(self, tenant, appointment) -> ExternalRef
    async def update_booking(self, tenant, external_ref, changes) -> None
    async def health(self, tenant) -> Health
```

Phase 1 implementations: `webchat` (our own widget), `twilio_sms`, `email` (inbound via a provider webhook, outbound via SMTP or Resend), `google_calendar` as the system of record.
Phase 2 candidates, one per pack, chosen by which prospects actually use them: an HVAC field-service API, a dental practice-management API, a restoration job-management API or a CSV/email bridge where no API exists. See `docs/research/RESEARCH-BRIEF.md` section 3.

Credential storage: `integrations.encrypted_credentials` is encrypted with a Fernet key from the environment. OAuth refresh happens in the worker. The web never sees credentials.

## 9. Scheduling model (Chunk 8)

- `availability(...)` returns slots from the system of record. If none is connected, from the tenant's `business_hours` minus existing `appointments`.
- The worker offers at most three slots at a time. A slot is held for 10 minutes on proposal (row in `appointments` with `status='held'`, expiry job), so two conversations cannot offer the same slot.
- Confirmation writes the external booking, then the local row, then the confirmation message, in that order, each idempotent.

## 10. Dashboard (Chunk 9, 10)

Shared core areas with pack-specific columns loaded from `dashboard.yaml`:

| Area | Every pack | HVAC | Dental | Restoration |
|---|---|---|---|---|
| Inbox | all channels, unread, waiting on human | service and estimate requests | patient messages, appointment requests | damage reports, claim messages |
| Work queue | new, urgent, waiting, human review, done | unassigned jobs, emergencies | unconfirmed appointments, incomplete forms, insurance issues | active emergencies, inspections due, documents owed |
| Approvals | proposals awaiting a decision, one-click approve or edit or reject | | | |
| Contact | identity, history, consent, notes | address, equipment, service history | patient, guardian, forms, appointment history | property, claim, insurer, adjuster |
| Schedule | availability, requests, confirmations | technician, service area, arrival window | provider, room, appointment type | crew, inspection, equipment |
| Conversation | transcript, summary, extracted fields, take over, hand back | symptom and safety flags | reason for visit, privacy controls | damage details, photos |
| Automation | rules, reminders, follow-ups, templates | missed-call, estimate chase | confirm, remind, recall, waitlist | dispatch ack, claim chase |
| Analytics | response time, intake completion, escalations, failures | qualified calls, booked jobs, recovered missed contacts | confirmations, form completion, no-shows | emergency response time, inspections booked |
| Settings | staff, permissions, integrations, knowledge, risk rules | field-service software, phone | practice software, phone | job-management software, phone |

Takeover: a staff member clicks "take over", the conversation switches to `waiting_human`, the worker stops replying but keeps extracting fields and suggesting replies in a side panel. "Hand back" returns control with the human's messages in context.

## 11. Safety and compliance controls (Chunk 4, 12)

Built into code, not policy documents:

- **Consent ledger** on `contacts.consent`: source, timestamp, channel, text shown. Outbound checks it before every send.
- **Opt-out** keywords (STOP, UNSUBSCRIBE and pack-specific phrases) handled in the API before any job is created.
- **Disclosure**: the first worker message on every channel says it is an AI assistant for the business and how to reach a person. Template is per tenant, the requirement is core.
- **Sensitive-field handling**: fields flagged `sensitive: true` in `intake.yaml` are stored encrypted, excluded from logs, excluded from analytics, and shown in the dashboard only to `owner` and `staff`.
- **Data retention** per tenant setting, default 24 months for conversations, with a nightly purge job and an audit entry.
- **Region pinning**: tenant setting `data_region` selects the Supabase project (UK/EU vs US). One deployment per region in Phase 2, tenants never move.
- **Regulated-data mode** (US dental): tenant flag that requires a signed agreement on file with every processor that sees health data before the pack activates, disables non-compliant channels, and enforces the stricter retention setting. Which vendors will sign such an agreement is a `[VERIFY]` item in the research brief.
- **Emergency phrases** are hard-coded per pack and tested. They never rely on the LLM alone; a keyword pre-check runs before the LLM call.
- **Kill switch**: tenant-level `worker_enabled=false` stops all automated sends within one job cycle. Platform-level switch stops everything.

## 12. Observability and evals (Chunk 3, 13)

- Every worker turn is a Langfuse trace with tenant id, conversation id, pack, model, tokens, latency and the proposals produced.
- `evals/<pack>/*.yaml`: a starting conversation, the customer's scripted turns, and the expected proposals and forbidden proposals. `make evals` runs each through the real worker code with the LLM and prints pass rate. A pack must hold 90 percent before it is enabled for a paying tenant. Thresholds live in `evals/thresholds.yaml` and CI fails below them.
- Metrics roll-up job runs hourly into `metrics_daily`. The dashboard reads only the roll-up.

## 13. Deployment (Chunk 2, 14; hosting per ADR 0013)

- **Local**: `docker compose up` with Postgres 16, api, worker, web. Mailpit for email, Twilio dev webhooks via ngrok when needed. The `apps/worker` process runs here.
- **Production**: Vercel project `novaxis-web` (Next.js) and `novaxis-api` (FastAPI as one Python function, London `lhr1`); Supabase project `novaxis-worker` (London). There is no worker process: with `NOVAXIS_INLINE_WORKER=true` the API drains the job queue after each POST or PUT, and Supabase `pg_cron` calls `POST /internal/tick` every minute for scheduled work, reading the shared secret from Supabase Vault. Migrations run when a new deployment first starts (`NOVAXIS_AUTO_MIGRATE`, advisory lock), so they must stay additive. Secrets live in Vercel project variables.
- **Previews**: Vercel previews behind Vercel Authentication, against the same database. There is no separate staging database yet.
- **Release**: CI promotes a commit to the `production` branch only after lint, types, unit, RLS and browser tests pass. Vercel's production branch must be set to `production` for that to gate the live site (a dashboard setting; see `docs/RUNBOOK.md`).
- **Monitoring**: `GET /health/deep` (database, stuck and failed jobs, undelivered emergency alerts, schema at head), checked every 15 minutes by `.github/workflows/monitor.yml`. Incident steps are in `docs/RUNBOOK.md`.
- **CI**: GitHub Actions. Lint, type check, unit tests, RLS test, scripted-model evals and browser tests on every push. Real-model evals run by hand (`make evals-real`).

## 14. Cost shape

No prices in this document (they change and must be verified). The shape:
- Fixed per month: Supabase, Vercel (web and API), Langfuse, Sentry free tiers to start.
- Variable per tenant: LLM tokens (dominated by worker turns, so keep contexts short), SMS segments, phone numbers, email volume.
- The metering table `usage_events` (Chunk 14) records tokens, messages and minutes per tenant so pricing can be set from real numbers after the pilot.

## 15. ADR seed list

Write these as the chunks land:
1. Postgres-table queue instead of Redis or a hosted queue.
2. RLS as the tenancy boundary.
3. Packs as data plus a single `rules.py` hook, not plugins with core access.
4. Approval gate as one pure function with a table-driven test.
5. Text channels before voice.
6. Google Calendar as the first system of record.
7. Sensitive field encryption approach.
8. Region-per-deployment rather than region-per-row.

## 16. Open questions for the founder

1. UK dental first, or HVAC first? The plan builds the core pack-agnostic, but the first paying pilot decides which pack gets the Phase 2 integration. Recommendation: HVAC for the first pilot because it has no health-data burden, then dental once the regulated-data mode exists.
2. Which region's Supabase project is production first? Recommendation: UK/EU.
3. Voice vendor in Phase 3: build on Twilio plus a speech stack, or buy a managed voice-agent platform. Decide after Phase 1 metrics show call volume matters.
