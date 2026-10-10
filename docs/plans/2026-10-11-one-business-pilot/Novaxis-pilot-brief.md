# Novaxis: one-business pilot brief

11 October 2026. Planning draft grounded in current GitHub source and the founder’s latest direction. This document does not claim that the proposed changes are implemented or tested.

## Agreed direction

- One small or medium-sized UK HVAC business tests first and gives feedback. Expansion to other businesses follows that feedback; the earlier five-business intake target is superseded.
- One business can still have several staff members and simultaneous visitor conversations. Preserve the shared, multitenant product from the start.
- Visitors use the website assistant. Owners use a private assistant to understand and manage their own business workload.
- Keep Assistant Studio simple: business information, assistant behaviour, preview and connections. Technical profile files and memory mechanics stay out of the business-facing interface.
- Preserve the existing Figma work. The current planning pass does not change Figma, deploy code, resume the paused calendar setup or send outreach.

## First useful product

**Visitor journey:** ask about a supported service → collect necessary visit details → consider a preferred engineer → present an evidence-supported proposal or send it to the office → office decision → verified booking result → separate customer-message result.

**Owner journey:** ask “What needs attention today?” → receive a summary from current jobs, conversations and approvals → inspect the supporting records → decide what to assign or approve.

For the first pilot, activate a small owner-approved service list and website chat. Begin owner assistance with read-only daily summaries. Add controlled assignment proposals after staff competencies and availability are represented. Live booking is conditional on a working calendar and complete feasibility checks. Intake and office handoff can be tested first.

## Two assistant experiences, one controlled backend

| Surface | Who uses it | Information and actions |
|---|---|---|
| Website assistant | A visitor/customer | Public business facts, their own request, agreed service information, eligible public staff choices and permitted appointment proposals |
| Owner assistant | Signed-in owner or authorised staff | Their business’s workload, customer records, unresolved enquiries, approvals and schedules; actions restricted by role |
| Assistant Studio | Business administrator | Edit approved facts, tone and response preferences; preview the visitor assistant; open Connections |
| Connections | Business administrator | Connect website, calendar and supported data sources; show connection health, freshness and reconnect steps |

Owner questions can include “How many visits are confirmed today?”, “Which requests are waiting for our reply?” and “Who is available for this service?” Counts come from queries, with a timestamp and links to their records. Inventory questions are supported only when an inventory source is connected. A generic conversation model cannot establish those counts.

## Existing stack to preserve

| Layer | Source-confirmed choice | Pilot approach |
|---|---|---|
| Website/dashboard | Next.js, React, TypeScript, Tailwind | Continue the existing app and widget; implement the essential customer and office flows |
| API/domain logic | Python 3.12, FastAPI, Pydantic, SQLAlchemy | Keep calculations, permissions and booking rules in the backend |
| Data | Supabase Postgres, tenant-scoped sessions and row-level security | Keep business, contact and conversation boundaries; check a second synthetic tenant during verification |
| Jobs | Durable Postgres jobs with leases and retries | Fix conversation ordering and repeat-safe execution; measure queue age and visitor wait |
| Hosting | Repository decision: Vercel web/API and Supabase timer | Retain provisionally; verify deployed configuration and execution limits before the pilot. A different worker host would require an explicit architecture decision |
| Owner access | Supabase Auth is the intended real-tenant path; demo passcode also exists | Establish real staff sign-in and role permissions before real customer data |
| Model | Existing OpenAI-compatible or Anthropic adapter | Use a pinned hosted model behind the existing interface; retain a separate scripted provider for deterministic checks |

This source audit did not inspect private deployment credentials or verify current production model use. The saved 8 October deployment record observed **OpenAI-compatible**, **gpt-oss:120b** for responses/classification and **gpt-oss:20b** for summaries. That is a candidate baseline, not a newly verified production setting or a selected best model. The repository’s model guide contains older statements about scripted live replies, so it must not be treated as current deployment evidence.

Before selection, read safe configuration metadata and actual worker-call evidence, then compare response accuracy, tool use, latency and cost on the same HVAC tasks. Store the model and provider used for each run. Switching model must preserve business data and action permissions. No additional model subscription or trained model is selected by this brief.

## How the assistant knows the business

Use approved records for services, service duration, hours, coverage, fees, cancellation terms and escalation contacts. Use the current conversation for temporary context. Store reviewed returning-customer preferences separately from the general business profile, scoped to the correct customer and with a source. Match the customer appropriately before recalling a preference.

Multiple businesses can share one model service while receiving separate context. Do not combine customer histories or train automatically from those conversations.

The model’s job is to interpret the request, ask a useful missing question, explain tool results and propose allowed actions. The backend queries records, computes feasibility, enforces roles and carries out approved actions.

## Staff selection, travel and fees

1. Record each engineer’s business-approved service competencies, relevant qualifications, shift, leave and commitments. Current staff accounts are not evidence of a complete dispatch resource model.
2. Filter for eligible engineers and required crew/equipment. A returning customer’s preferred engineer is a preference, not a guaranteed assignment.
3. Check the property, access, service duration, business hours and protected time.
4. Check previous job/base → proposed job → next job/base. Obtain estimates from a routing provider using the relevant departure time. Show estimate freshness and uncertainty.
5. Recheck before committing. Missing evidence leaves the request with the office.
6. Show only approved fees, stating whether they are a call-out/assessment fee, estimate or fixed quote. Explain inclusions and owner-approved terms. Unknown repair cost requires a quote rather than an invented price.

Google Routes already documents estimates using historical and live traffic. A routing integration is the proposed starting approach; selecting a provider, validating coverage, terms, cost and credentials remains necessary. A new traffic model is not required for this pilot. Route estimates cannot guarantee arrival or visit duration.

The business’s service fee is separate from Novaxis pricing. Preserve the earlier free-test offer for this first pilot, with an agreed usage boundary and internal spend cap; no new customer price is selected here.

## Gaps established by source inspection

| Priority | Finding | Required pilot behaviour |
|---|---|---|
| 1 | Jobs are leased separately, but a worker turn does not use the inbound message ID or enforce conversation ordering | Rapid messages must not create repeated or out-of-order replies/proposals; different visitors can progress independently |
| 1 | Approval checks and external-calendar lookup/insert are not one atomic execution claim | Double clicks, concurrent decisions and ambiguous provider results must not create duplicate bookings |
| 1 | Disconnected calendar falls back to business hours and can produce a local “confirmed” record | Label an office/local record accurately; do not present it as a verified external calendar booking |
| 1 | The new engineer/travel contract is not implemented in confirmation | Recheck actual resources, calendar and both travel legs before confirming; otherwise use office review |
| 2 | API writes currently drain the shared queue before returning; the drain budget is checked between jobs | Acknowledge accepted messages promptly and expose pending/failed states; measure actual wait under concurrent use |
| 2 | Missing service duration can fall back to 60 minutes | Unknown work/duration requires an approved assessment profile or office estimate |
| 2 | Provider send acceptance can be recorded as delivery | Keep accepted, delivered, failed and unknown notification results separate |

These are source findings and risk mechanisms. No reproduction tests, production calls or implementation changes were performed in this planning pass.

## Ordered work and accountable disciplines

| Order | Primary role | Concrete output | Completion evidence |
|---|---|---|---|
| 1 | Product + HVAC domain reviewer | One business, owner decision maker, agreed services, staffing, fees and pilot boundaries | Owner-reviewed business configuration; unknown facts stay inactive |
| 2 | Backend engineer | Conversation ordering, repeat-safe approval/execution, accurate disconnected-calendar state | Rapid-message, retry, timeout and concurrent-approval checks pass |
| 3 | AI engineer | Pinned model baseline, allowed tools, response style and cost/latency record | Real-model cases demonstrate approved facts, useful intake and truthful action outcomes |
| 4 | Integration engineer | Working website connection; calendar and route tools when ready | Real provider outcomes distinguished from local records and uncertain results |
| 5 | UX/frontend designer | Clear visitor chat, owner daily summary, simple Studio/Connections and essential mobile flow | Request, review, pending, confirmed and recovery journeys are usable and consistent |
| 6 | QA reviewer | Pilot readiness evidence | Isolation, concurrency, takeover, permissions and partial-failure criteria verified |
| 7 | Founder + pilot owner | One-business feedback record | Review initial genuine conversations, corrections, time saved, unresolved issues and usage costs before adding a second business |

The first engineering slice should address conversation ordering and repeat-safe execution. Owner read-only summaries follow those foundations; advanced automatic dispatch is not a prerequisite for testing useful intake and handoff.

## Proposed acceptance checks

- Five simulated simultaneous visitors, including rapid messages, refresh and retry: no mixed history, lost intake or duplicate actions. Five is a test target, not proven capacity.
- A second synthetic business cannot access the first business’s messages, records or tools.
- Booking approval, calendar result and customer notification have distinct observable states.
- Calendar disconnected, changed availability or incomplete engineer/travel evidence never becomes a guaranteed appointment.
- Human takeover stops automatic replies and displays who controls the conversation.
- Owner summaries use current authorised records; visitors cannot query internal customer lists or staff workloads.
- Record acknowledgement time, response latency, queue age, model calls, tokens, errors and cost per resolved conversation. Any response-time target remains a target until measured.
- Review the first 20–30 genuine conversations with the business owner before expanding. Record feedback rather than infer success from screen quality.

## Evidence

Current GitHub checkpoint inspected: `5917d32`, 10 October plan. Newer changes since local runtime checkout `e6a7cc0` are documentation only.

- [Latest repository plan](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/docs/LATEST-PLAN.md), operating requirements and recorded implementation gaps.
- [Standing stack and working rules](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/CLAUDE.md).
- [Hosting decision](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/docs/adr/0013-vercel-hosting.md).
- [Model adapter](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/packages/core/novaxis_core/llm.py) and [safe model metadata](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/apps/api/novaxis_api/routes_settings.py).
- [Worker message dispatch](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/apps/worker/novaxis_worker/loop.py#L100) and [conversation turn](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/packages/core/novaxis_core/turn.py#L475).
- [Booking confirmation](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/packages/core/novaxis_core/scheduling.py#L453), [calendar creation](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/packages/core/novaxis_core/sor/google_calendar.py#L144) and [local fallback](https://github.com/srdataml-droid/multi-ai-platform-/blob/5917d32/packages/core/novaxis_core/sor/business_hours.py).
- [Vercel function limits](https://vercel.com/docs/functions/limitations), [Supabase row-level security](https://supabase.com/docs/guides/database/postgres/row-level-security), [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility), and [Google traffic estimates](https://developers.google.com/maps/documentation/routes/traffic-opt), checked 11 October 2026. Account-specific settings and billing were not checked.

Next concrete task: confirm the first business’s enabled services and action policy, then prepare the narrowly scoped conversation-ordering and repeat-safe execution design against this acceptance contract.
