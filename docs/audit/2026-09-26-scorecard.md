# Audit and scorecard, 2026-09-26 (after Chunk 11)

A full pass over everything built through Chunk 11:
- every check was run: 293 Python tests in both orders, 4 web unit tests, 5 browser
  specs run twice, and the web build;
- the live site was checked through Supabase `pg_net`;
- Supabase's security and performance advisors were read;
- Vercel's production error log was read;
- every area was reviewed by reading the code.

Confirmed defects were fixed in commit `0567cfe`. Each fix has a test that fails without
it.

## Defects found and fixed

| # | Severity | What was wrong | Proof |
|---|---|---|---|
| 1 | Critical | The chat widget could not run on a business's own website. The API sent no CORS headers, so browsers blocked every call. The demo page only worked because it sits on our own domain. | New e2e spec embeds the widget on another origin. It fails on the old code and passes now. Live: widget routes return `Access-Control-Allow-Origin: *`; staff routes do not. |
| 2 | High (security) | `/media` checked only that the key started with the caller's tenant id, so `<mine>/%2E%2E/<theirs>/photo` served another tenant's customer photo. | Test: HVAC owner fetched a restoration photo (200) on old code; 404 now. |
| 3 | High (ops) | Each deploy served about a minute of 500s. New code went live before the manual migrate call. | Vercel log: `column tenants.trial_ends_at does not exist`, twice. Now the API migrates on start; live DB reached 0010 with no manual call. |
| 4 | Medium (ops) | `/internal/tick` answered 200 "0 jobs" while the job loop was failing, so the timer's history hid outages. | Test: a broken loop now returns 500. |
| 5 | Medium | The setup wizard's time zone never reached the location, and slots are computed in the location's zone. A US business would be offered London times. | Test: wizard with America/New_York updates the location. |
| 6 | Low | An owner's own `{braces}` in the disclosure text crashed every first reply. | Test. |
| 7 | Medium (scale) | The tenancy predicate called `current_setting()` for every row. | `EXPLAIN` now shows one InitPlan and an index lookup. The advisor still flags it: its text match does not recognise `(SELECT NULLIF(current_setting(...)))`, so that warning is a false positive. |
| 8 | High (UX) | Dashboard unusable on a phone: the side menu took 60% of the width, and pages scrolled sideways. | Every page now fits 390 px. |
| 9 | Medium (UX) | Approval cards showed raw JSON. | Plain labelled details; JSON editor behind "Edit details". |
| 10 | Low (cost) | The widget polled the API every 3 s on every page view, even when closed. | Now it polls only while the chat is open. |
| 11 | Test | The e2e specs shared one job queue and ran in parallel, so one spec could take another's job. | They now run in series: 5/5, twice. |

## Scores (0–10)

| Area | Score | Before audit |
|---|---|---|
| Architecture and design | 8 | 8 |
| Security and tenant isolation | 7 | 5 |
| AI worker quality | 4 | 4 |
| Channels | 4 | 3 |
| Scheduling and integrations | 5 | 5 |
| Dashboard and UX | 6 | 4 |
| Onboarding and billing | 6 | 6 |
| Reliability and operations | 5 | 4 |
| Testing and CI | 8 | 7 |
| Compliance (UK GDPR, dental) | 3 | 3 |
| Documentation | 8 | 8 |
| Business readiness | 3 | 3 |
| **Overall (unweighted mean)** | **5.6** | 5.0 |

### Why each is not 10

**Architecture (8).**
- Serverless inline worker, capped by the function time limit. There is no true
  background worker, so with a real model the widget's send call waits for the AI turn.
- One region.
- Migrations must stay additive, because old code briefly runs against the new schema.

**Security (7).**
- No rate limits: the demo passcode can be brute-forced, and a spammer could run up AI
  costs once a key is set (Chunk 12).
- Demo mode shares one passcode, and it includes the operator login.
- The widget accepts any origin; there is no per-tenant allow-list yet.
- The repo is public.
- `pg_net` sits in the `public` schema (advisor warning).
- No external penetration test; defect 2 shows why one is needed.

**AI quality (4).**
- Never run against the real model in production.
- Evals are 5 scripted conversations per pack, run with the fake model.
- Reply quality, tone and cost per conversation are unmeasured.
- The safety architecture is strong: approval gate, emergency pre-check, claim check and
  AI disclosure.

**Channels (4).**
- Only web chat is live.
- SMS (Twilio) and email (Postmark) are coded and tested with fixtures, but no accounts
  are connected.
- No voice, and no WhatsApp or Facebook Messenger, which UK trades use heavily.

**Scheduling and integrations (5).**
- Google Calendar is coded, but no OAuth app is configured in production.
- The booking bridge works with any vendor but is manual.
- No vendor API adapter yet, and no Microsoft 365 calendar.

**Dashboard and UX (6).**
- Staff are not notified when something needs approval: email is not configured, and
  there is no SMS or push.
- Pages poll rather than update live.
- Service codes show raw (`repair_visit`) in places.
- Accessibility is unchecked.
- Only 4 web unit tests.

**Onboarding and billing (6).**
- Stripe has never been called for real; the request fields are marked `[VERIFY]`.
- Prices are placeholders.
- No email verification or password reset while in demo mode.
- The pack cannot be changed after sign-up.

**Reliability and operations (5).**
- No alerting: failures show only in Vercel logs that nobody watches.
- No error tracker and no uptime monitor.
- Photos are stored in `/tmp` and are lost.
- Backups are whatever the Supabase plan gives, not verified `[VERIFY]`.
- No incident runbook.

**Testing and CI (8).**
- Fake model only.
- No sandbox tests against Twilio, Postmark or Stripe.
- No load test.
- Live checks are manual.

**Compliance (3).**
- Chunk 12 is not built: retention purge, data export, consent screen, processor
  agreements, regulated mode.
- No privacy notice, ICO registration or dental DPIA.
- Sensitive fields are encrypted and AI disclosure is on.

**Documentation (8).**
- No incident runbook.
- No customer-facing help.

**Business readiness (3).**
- No pilot customer.
- No vendor named.
- Prices unset.
- Research `[VERIFY]` items unchecked.
- Only the demo can be shown.

## Dissent recorded
- **Simplifier:** do not chase 10 everywhere. A paid pilot needs about 7 in AI quality,
  channels, staff notification and security; compliance must reach 7 before any dental
  tenant. Everything else can wait.
- **LENS:** these scores are the reviewer's judgement, not measurements. AI quality in
  particular is a guess until real-model evals run.
- **Undertaker:** the reviewer also wrote the code. Defects 1 and 2 survived eleven chunks
  of tests; an outside review before real customer data is worth the money.
