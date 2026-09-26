# Build Plan: PART B, one chunk per Claude Code session

> Paste one chunk at a time into Claude Code running Opus 5.5. Each chunk is written so the
> model can decide the details itself, record them, and prove the result with tests.
> Do not paste the next chunk until the current one is committed green.

## How each chunk is shaped

Every chunk gives the model: **Goal**, **Read first**, **Build**, **Decide yourself**
(choices it must make and record in an ADR), **Tests** (what must pass), **Demo** (what the
founder runs to see it), **Done when**, and **Do not**. The "Decide yourself" block is what makes
the model think rather than transcribe. Estimated founder time is review time, not build time.

Phases:
- **Phase 1, Chunks 0 to 9**: the loop end to end on text channels, one calendar, three packs, a dashboard. This is the pilot product.
- **Phase 2, Chunks 10 to 12**: vendor integrations, billing, compliance hardening.
- **Phase 3, Chunks 13 to 14**: evals at scale, voice, multi-region.

---

## Chunk 0: Repo skeleton, tooling, and architecture reconciliation

**Goal.** A repo that boots, lints, tests and has the architecture in it, with nothing else.

**Read first.** `CLAUDE.md`, `docs/ARCHITECTURE.md`, everything in `docs/research/` and `docs/demo/` if present.

**Build.**
- Monorepo layout from `CLAUDE.md`. Python managed with `uv`, one `pyproject.toml` per Python package, a root workspace.
- `apps/api` FastAPI app with `/health` and `/version`. `apps/worker` with a `main()` that polls nothing yet and exits cleanly on SIGTERM. `apps/web` Next.js with one page reading `/health`.
- `docker-compose.yml` with postgres, api, worker, web. `Makefile` with the targets in `CLAUDE.md`.
- Linting: ruff, mypy strict on `packages/core`, eslint and tsc on web. Pre-commit config.
- GitHub Actions workflow: lint, type check, tests, on every push.
- `docs/adr/0000-template.md` and `docs/adr/0001-stack.md` recording the stack as given.

**Decide yourself.** Package naming. Whether web talks to API through a proxy in dev. If `docs/demo/` exists, write `docs/adr/0002-demo-reuse.md` listing what from the demo is reused (files named), what is discarded and why. If the research files exist, list in the ADR any place they contradict `docs/ARCHITECTURE.md`, and pick the architecture unless the research has a verified source.

**Tests.** `make test` runs at least one test per package and passes. CI is green on the first push.

**Demo.** `make up` then open the web page and see the API version.

**Done when.** Fresh clone, `make up`, `make test` both work. ADRs written.

**Do not.** Add any domain tables, LLM calls, or UI beyond one page. Founder review: 30 minutes.

---

## Chunk 1: Tenancy, users, and the data model with RLS

**Goal.** Every core table exists with tenant isolation enforced by Postgres and proven by a test.

**Read first.** `docs/ARCHITECTURE.md` sections 3 and 4.

**Build.**
- Alembic in `packages/db`. Migration 0001 creates all tables in section 4 with `tenant_id`, RLS enabled, policies for the `app` role, and append-only grants on `messages` and `audit_log`.
- SQLAlchemy models in `packages/core/models.py`. A `tenant_session(tenant_id)` context manager that opens a session and sets `app.tenant_id`.
- Pydantic `TenantSettings` base model with the fields in section 3. Pack-specific settings models come later; leave an extension hook.
- Supabase Auth wiring in the API: a dependency that reads the JWT, resolves the user and tenant, and opens the tenant session. Local dev uses a signed dev JWT so no network is needed.
- `make seed` creates two tenants (`demo-hvac`, `demo-dental`) with one owner user each.

**Decide yourself.** Whether `audit_log` is written by triggers or by application code (record the trade-off). Index strategy for `messages` and `jobs`. How the dev JWT is produced.

**Tests.**
- `test_rls.py`: with tenant A's session, insert a contact; with tenant B's session, select contacts, expect zero rows; attempt update of A's row from B, expect zero rows affected.
- `test_append_only.py`: UPDATE on `messages` as the app role raises a permission error.
- Migration up and down round-trips on an empty database.

**Demo.** `make seed`, then `psql` as the app role with `SET app.tenant_id` and show that each tenant sees only its own rows.

**Done when.** Tests pass, migration is the only way tables are created, ADR 0003 (RLS as tenancy boundary) written.

**Do not.** Write any endpoint beyond `/me`. Founder review: 45 minutes.

---

## Chunk 2: Channel adapters and the inbound path

**Goal.** A message from web chat, SMS or email becomes a `messages` row and a `jobs` row within one request, with signatures verified and opt-outs handled.

**Read first.** Section 8 and section 11 (opt-out, disclosure).

**Build.**
- `packages/core/channels/base.py` with the `ChannelAdapter` protocol. Implementations: `webchat` (JSON endpoint plus a minimal embeddable widget in `apps/web/public/widget.js`), `twilio_sms` (webhook with signature check), `email` (inbound webhook from the chosen provider, with a Mailpit-based local path).
- `apps/api/routes/inbound/*` that: verify, parse to `NormalisedInbound`, find or create the contact, find or open the conversation, insert the message, insert a `worker_turn` job, return 200 fast.
- Opt-out handling before job creation: STOP and friends set `contacts.consent.status='opted_out'`, send the confirmation text, create no job.
- Outbound `send()` for each adapter, used by a `send_message` job kind. Not yet called by anything but tests.
- Channel config per tenant in settings: which channels are enabled, which Twilio number, which inbound address.

**Decide yourself.** Email provider for inbound parsing (pick one, record why). How the widget identifies a returning visitor (recommend a signed cookie, no PII). Contact matching rules across channels (phone exact, email lowercased; never merge on name).

**Tests.**
- Each adapter: a fixture webhook payload produces the expected `NormalisedInbound`.
- Bad signature returns 403 and writes nothing.
- STOP creates no job and flips consent.
- One inbound creates exactly one message and one job (idempotent on provider message id: replaying the webhook creates nothing new).

**Demo.** Send an SMS to the dev number via the Twilio console or `curl` the webchat endpoint; show the rows.

**Done when.** All three adapters pass their tests, and a replayed webhook is a no-op.

**Do not.** Call the LLM. Send anything outbound except the STOP confirmation. Founder review: 45 minutes.

---

## Chunk 3: The worker loop and the first LLM turn

**Goal.** The worker picks a job, runs one LLM turn with tool definitions, stores the reply and any proposals, and sends the reply. No pack yet: a built-in "generic" pack with one intake question proves the plumbing.

**Read first.** Sections 5 and 12. The `claude-api` reference for tool use and prompt caching if available in the session.

**Build.**
- `apps/worker/loop.py`: `SELECT ... FOR UPDATE SKIP LOCKED`, lease, run, complete or fail with backoff (attempts 1, 2, 3 at 10s, 60s, 300s; then conversation to `waiting_human`).
- `packages/core/llm.py`: thin Anthropic client wrapper with model selection by task (`worker_turn`, `classify`, `summarise`), timeouts, retries, token accounting into `usage_events`, and a Langfuse trace per call. Cache the stable prefix (system prompt plus pack context).
- `packages/core/turn.py`: `run_turn(job)`; builds context from rows, calls the LLM with the tool list, parses reply and proposals, stores proposals with `risk` set by the gate stub (everything `low` for now), sends the reply through the channel.
- Disclosure message on the first worker reply of a conversation.
- Summary regeneration every 10 messages.
- A `FakeLLM` for tests that returns scripted tool calls, selected by an environment variable.

**Decide yourself.** Context window budget per turn and what gets truncated first. The exact tool schema format. Where the "verify claim" post-check lives (section 5) and its regex or LLM approach.

**Tests.**
- With `FakeLLM`: an inbound message leads to one outbound message and the scripted proposal rows.
- Two worker processes on the same queue never run the same job (test with a shared Postgres and two loops).
- Failure path: a job that raises three times ends with the conversation in `waiting_human` and an audit entry.
- Disclosure appears on message one and not on message two.

**Demo.** `make demo` sends "hi" to the webchat endpoint and prints the worker's reply within 10 seconds using the real API.

**Done when.** The demo works against the real model and the tests pass with the fake.

**Do not.** Implement any real action executors except `reply`. Founder review: 1 hour.

---

## Chunk 4: The action model and the approval gate

**Goal.** Proposals carry risk, the gate decides, the dashboard has nothing yet but the API exposes the queue and the decision endpoint. Nothing medium or high executes without an approval row.

**Read first.** Section 6 and section 11.

**Build.**
- `packages/core/actions.py`: the action kinds in section 6 as Pydantic models with parameter schemas.
- `packages/core/gate.py`: `decide(proposal, tenant, pack) -> Decision`. Core rules first, pack hook second, tenant overrides third, and overrides can only lower risk within the pack's allowed range.
- `packages/core/executors/`: one executor per action kind. Phase 1 executors: `reply`, `ask_intake_question`, `extract_fields`, `hand_to_human`, `escalate_emergency` (email plus SMS to the on-call contact), `send_reminder`. Appointment executors are stubs that raise `NotImplemented` until Chunk 8.
- `execute(proposal)` refuses to run unless `state in (auto_approved, approved)`; the check is in one place and the executors are not reachable any other way.
- API: `GET /approvals` (awaiting for this tenant), `POST /approvals/{id}` with `decision in (approve, reject, edit)` where edit takes replacement params and re-runs the gate.
- Emergency keyword pre-check before the LLM call, per pack, with the generic pack having a minimal list.
- Kill switch: tenant `worker_enabled` and platform `WORKER_ENABLED` env var, checked at job pick time.

**Decide yourself.** Whether an edited proposal becomes a new proposal (recommended) or mutates the old one. Notification channel for staff when something awaits approval (recommend email plus the dashboard badge; SMS optional per tenant).

**Tests.**
- `test_gate.py`: table-driven, at least 40 rows covering each action kind, each core rule, tenant overrides that may and may not lower risk, and the safeguarding rule.
- `test_execute_refuses.py`: calling `execute` on a proposal in `awaiting` raises and writes an audit entry.
- Opted-out contact: proposal to send is refused, not created.
- Kill switch: with `worker_enabled=false`, a queued job is skipped and re-queued, nothing sends.

**Demo.** Message "I smell gas" to the HVAC demo tenant: the worker escalates immediately, the reply tells the customer to leave and call the emergency line, and the on-call contact receives the alert.

**Done when.** Gate tests pass, execution is provably gated, ADR 0004 (gate as a pure function) written.

**Do not.** Build UI. Founder review: 1 hour, and read `gate.py` line by line.

---

## Chunk 5: Pack framework and the HVAC pack

**Goal.** Packs load from folders, validate, and drive the worker. HVAC is the first real pack and completes an intake end to end.

**Read first.** Section 7.

**Build.**
- `packages/core/packs.py`: manifest schema, loader, validation error messages that name the file and key.
- `packages/packs/hvac/` with every file in section 7: manifest, intake (problem type, symptom, equipment age, urgency, address, service area check, preferred window), vocabulary, system prompt, rules (gas smell, carbon monoxide alarm, no heat with vulnerable occupant in cold weather are emergencies), workflows (missed-contact text back, estimate chase at 24h and 72h), dashboard.yaml, five golden evals.
- Service-area check as a pack rule: postcode or ZIP prefix list in tenant settings; outside area leads to a polite decline and a `hand_to_human` at low risk.
- Intake engine in core: asks the next unanswered question, validates, stores in `conversations.extracted`, marks intake complete, and then the worker moves to the pack's "after intake" step (for HVAC: propose a window, which is a stub until Chunk 8, so for now it creates a `propose_appointment` proposal that lands in the queue).
- Follow-up jobs from `workflows.yaml` scheduled with `run_after`.

**Decide yourself.** How skip logic is expressed in `intake.yaml`. How the intake engine and the LLM share control (recommend: LLM phrases, engine decides what to ask next).

**Tests.**
- Manifest validation rejects a pack with an unknown action kind.
- The five HVAC evals pass with the `FakeLLM` (deterministic), and are also runnable with the real model via `make evals`.
- Emergency pre-check fires on "gas smell" before any LLM call (assert the LLM mock was not called).
- Outside service area path produces the decline and the hand-off.

**Demo.** A full HVAC intake on webchat ending in a proposal in the approval queue, viewed through the API.

**Done when.** Evals hold 5 of 5 with the fake and at least 4 of 5 with the real model.

**Do not.** Touch dental or restoration yet. Founder review: 1 hour.

---

## Chunk 6: Dental pack (UK first) and sensitive-field handling

**Goal.** Second pack proves the framework needs no core changes, and adds the sensitive-data path.

**Read first.** Section 7 dental, section 11.

**Build.**
- `packages/packs/dental/` complete. Intake: new or existing patient, reason for visit, pain scale and duration, NHS or private, preferred provider and time. Emergencies: uncontrolled bleeding, swelling affecting breathing or swallowing, trauma, all routed to emergency advice plus `escalate_emergency`.
- Sensitive fields flagged in `intake.yaml`. Core support: encryption at rest for flagged fields (Fernet, key from env), exclusion from logs, exclusion from `metrics_daily`, role check on read.
- Vocabulary switches every dashboard label and every worker phrase.
- Workflows: confirmation at booking, reminders at 48h and 2h, no-show recovery message, six-month recall (scheduled only if the tenant enables it), waitlist fill (stub).
- Five golden evals including one where a parent messages about a child (safeguarding rule leads to a human).

**Decide yourself.** Whether encryption is column-level in Postgres (pgcrypto) or application-level (record trade-off; recommend application-level so the key never reaches the database).

**Tests.**
- No core file changed in this chunk except the sensitive-field support, and that is asserted in the PR description with the diff.
- Sensitive field is unreadable in the raw table and readable through the model as `staff`; a `viewer` gets a redacted value.
- Log capture test: a turn with a symptom never writes the symptom text to logs.
- Five dental evals pass with the fake.

**Demo.** A UK patient with toothache books through the flow; the log shows no symptom text; the dashboard API returns the symptom only for staff.

**Done when.** Above passes and ADR 0007 (sensitive field encryption) written.

**Do not.** Enable any US-specific health-data mode yet. Founder review: 1 hour.

---

## Chunk 7: Restoration pack and photo intake

**Goal.** Third pack, plus the first non-text input (photos), plus insurance-claim fields.

**Read first.** Section 7 restoration.

**Build.**
- `packages/packs/restoration/` complete. Intake: damage type, when, still active, property type, claim status and insurer, photo request. Emergencies: active water flow, active fire or smoke, structural danger, sewage. Workflows: dispatch acknowledgement within one minute, inspection scheduling, claim document chase at 48h and 7d.
- MMS and email attachments: adapters accept media, store in Supabase Storage under the tenant's prefix, link from the message. No image analysis in Phase 1; the dashboard shows thumbnails.
- Five golden evals.

**Decide yourself.** Media size limits and virus scanning approach (record; a scan can be deferred with a documented risk).

**Tests.** Pack loads with no core change except media support. A fixture MMS with one image produces a stored object and a linked message. Evals pass with the fake.

**Demo.** A burst-pipe report with a photo lands as an emergency with the photo visible via the API.

**Done when.** Three packs run on one core. Founder review: 45 minutes.

---

## Chunk 8: Scheduling and Google Calendar as system of record

**Goal.** The appointment executors work for real against a calendar, with holds and idempotency.

**Read first.** Sections 8 and 9.

**Build.**
- `SystemOfRecord` protocol and `google_calendar` implementation with OAuth connect flow (API endpoint plus callback), token storage in `integrations`, refresh in the worker.
- `availability()` from the calendar plus business hours plus service durations from pack vocabulary. Fallback to business hours when no calendar is connected.
- Slot holds with expiry jobs. Executors: `propose_appointment`, `confirm_appointment`, `reschedule_appointment`, `cancel_appointment`, all idempotent on `proposal_id`.
- Confirmation and reminder messages from pack templates, with the tenant's name and address filled in.

**Decide yourself.** Time zone handling rules (store UTC, render in `locations.timezone`). What happens when the calendar write succeeds and the message send fails (recommend: retry the send only).

**Tests.**
- Fake calendar backend for tests. Two conversations offered the same slot: only one can confirm; the other is re-offered.
- Re-running `confirm_appointment` for the same proposal makes exactly one calendar event.
- Reminder jobs are created at the pack's offsets and cancelled when the appointment is cancelled.

**Demo.** Full HVAC flow: intake, three slots offered, customer picks, proposal awaits approval, approval via API, event appears in a real Google Calendar, confirmation SMS arrives.

**Done when.** The Phase 1 definition of done in `CLAUDE.md` is met through the API. ADR 0006 written. Founder review: 1 hour.

---

## Chunk 9: Dashboard, Phase 1 complete

**Goal.** Staff can do everything in the browser: see the inbox, approve, take over, see metrics.

**Read first.** Section 10.

**Build.**
- Next.js app with Supabase Auth login, tenant context, and pages: Inbox, Work queue, Approvals, Conversation (transcript, extracted fields, take over and hand back, suggested reply panel), Contacts, Schedule (read-only calendar view), Analytics (from `metrics_daily`), Settings (business hours, services, service area, channels, risk-rule overrides within allowed range, staff and roles, integrations connect buttons).
- Pack-driven labels and columns from `dashboard.yaml` served by the API.
- Realtime updates for Inbox and Approvals via Supabase Realtime.
- Hourly roll-up job into `metrics_daily`.
- The embeddable web-chat widget finished with a one-line install snippet shown in Settings.

**Decide yourself.** Component structure. How much of the UI is generic table-plus-config versus bespoke per page (recommend generic for Inbox, Work queue, Contacts; bespoke for Conversation and Approvals).

**Tests.** Playwright: login, see an awaiting proposal appear when a message arrives, approve it, see the appointment in Schedule. Role test: `viewer` cannot approve. Roll-up job test with fixture rows.

**Demo.** `make up && make seed && make demo` then the founder plays customer on the widget and staff in the dashboard. Record a screen capture; this is the pilot demo.

**Done when.** Phase 1 definition of done met in the browser. Founder review: 2 hours, including running the demo twice.

---

## Chunk 10: Billing and tenant onboarding

**Goal.** A new business can sign up, pick a pack, connect channels and a calendar, and pay, without Novaxis touching the database.

**Build.**
- Stripe: subscription per tenant with a setup fee and a monthly plan, plus metered usage from `usage_events` (messages, tokens rolled up). Webhooks for payment failed and cancelled set `tenant.status` and pause the worker.
- Onboarding wizard in the web app: business details, pack, hours, services, service area, channels, calendar connect, on-call contact, review and confirm. Writes `TenantSettings` through the validated model.
- Operator console (Novaxis role): list tenants, health, usage, enter tenant with audit.

**Decide yourself.** Trial length and what the worker may do during trial (recommend: full features, hard cap on messages).

**Tests.** Stripe webhook fixtures move tenant status correctly. Wizard produces a valid `TenantSettings` for each pack. Operator entry writes an audit row.

**Done when.** A second real tenant can be created without a `psql` session. Founder review: 1 hour.

---

## Chunk 11: First vendor integration (chosen by the pilot)

**Goal.** Write bookings and contacts into the system the pilot business already uses.

**Build.** One `SystemOfRecord` implementation for the pilot's vendor (see `docs/research/RESEARCH-BRIEF.md` section 3 for candidates; the founder names the vendor in the chunk prompt). If the vendor has no public API, implement the CSV or email bridge: a daily export the worker parses, and a structured email the worker sends for each booking, with the human confirming in the vendor tool.

**Decide yourself.** Mapping of service codes. Conflict handling when the vendor calendar and ours disagree (vendor wins, we re-offer).

**Tests.** Recorded HTTP fixtures (VCR-style) for the vendor API. Health check reports token expiry and permission loss.

**Done when.** A booking approved in our dashboard appears in the vendor tool within one job cycle. Founder review: 1 hour.

---

## Chunk 12: Compliance hardening and regulated-data mode

**Goal.** The controls in section 11 are all implemented and tested, and the US dental mode exists behind a flag.

**Build.** Data retention purge job with audit. Data export per tenant (JSON) and per contact (for access requests). Consent ledger UI. Disclosure text per tenant. Regulated-data mode flag that: requires agreement records for each processor in `integrations`, disables channels not marked compliant, enforces retention. Security headers, rate limits on inbound, webhook replay protection window.

**Tests.** Purge deletes only past retention and only for the tenant. Export contains everything for one contact and nothing for another. Regulated mode refuses to activate a pack while a processor has no agreement record.

**Done when.** A checklist in `docs/compliance.md` maps each control to a test name. Founder review: 1 hour, then a conversation with a UK data-protection adviser before the first dental tenant.

---

## Chunk 13: Evals at scale and quality gates

**Goal.** Quality is a number that gates releases.

**Build.** Expand each pack to 25 golden conversations covering happy paths, edge cases, adversarial inputs (prompt injection in a customer message, requests for medical advice, abusive language), and multilingual inputs if the tenant enables them. `make evals` scores: correct proposals, forbidden proposals absent, tone rubric scored by `claude-opus-5-5` as judge with a fixed rubric. Nightly CI job with a token budget. Thresholds in `evals/thresholds.yaml`; release workflow fails below them. Regression report per pack committed as an artifact.

**Tests.** The eval runner itself has unit tests. An intentionally broken prompt drops the score and fails the gate.

**Done when.** All three packs hold 90 percent on the nightly run for one week. Founder review: 1 hour a week reading the reports.

---

## Chunk 14: Voice channel and multi-region

**Goal.** Phone calls enter the same loop. A second region exists.

**Build.** Voice adapter on Twilio: inbound call, streaming transcription, the same `run_turn` with a `voice` channel flag that shortens replies, text-to-speech out, recording and transcript stored as messages, warm transfer to a human on `hand_to_human`. Decide build vs buy for the speech stack in an ADR after reading the research brief. Second Supabase project and deployment for a second region, tenant `data_region` routing at login.

**Tests.** Recorded call fixture flows through to a proposal. Transfer path is exercised. Region routing test.

**Done when.** A real call to the demo number books an appointment through the approval gate. Founder review: 2 hours.

---

## Chunk cadence for a founder with a full-time job

| Week | Chunks | Founder hours (review and demo) |
|---|---|---|
| 1 | 0, 1 | 2 |
| 2 | 2, 3 | 2 |
| 3 | 4 | 1.5 |
| 4 | 5 | 1.5 |
| 5 | 6, 7 | 2 |
| 6 | 8 | 1.5 |
| 7 to 8 | 9 | 3 |
| 9 | pilot demo to first prospect, fixes | 4 |
| 10 to 12 | 10, 11 | 3 |
| 13 to 14 | 12, 13 | 3 |
| later | 14 | 3 |

Eight weeks to a demo you can put in front of a paying pilot, at 2 to 3 founder hours a week
of review. The model's build time is separate and not the bottleneck; your review is. Do not
compress this by skipping review. That is the one place K2 (you must be able to defend it) is
enforced.
