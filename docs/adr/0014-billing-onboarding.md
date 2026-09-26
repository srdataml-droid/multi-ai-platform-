# ADR 0014: Billing, trial, self-serve onboarding and the operator console

- Status: accepted
- Date: 2026-09-26

## Context
Chunk 10: a new business must be able to sign up, set up, and pay without Novaxis
touching the database, and Novaxis staff need one screen that shows every tenant's health.
The founder wants to see the product before connecting any paid service: no Anthropic key,
no Stripe account yet.

## Decisions
1. **One billing state machine, two providers.** `novaxis_core.billing.apply_event` is the
   only code that moves `tenants.status` for money reasons. With no Stripe keys the provider
   is `demo`: "Choose a plan" builds the event Stripe would send and runs it through the
   same handler, so no money moves and the demo still exercises the real path. With
   `NOVAXIS_STRIPE_SECRET_KEY` and `NOVAXIS_STRIPE_WEBHOOK_SECRET` set, checkout redirects
   to Stripe Checkout and `POST /billing/webhook` verifies the `Stripe-Signature` header
   (HMAC-SHA256 over `{t}.{body}`, 5-minute tolerance).
2. **Events handled.** `checkout.session.completed` activates the tenant and stores the
   customer and subscription ids. `invoice.payment_failed` pauses, `invoice.paid` resumes
   a paused tenant, and `customer.subscription.deleted` closes. Tenants are matched by
   `metadata.tenant_id`, then `client_reference_id`, then the stored customer id. Every
   event is logged once in `billing_events` by its id, so a replay does nothing. Every
   applied event writes an audit row in the tenant's log.
3. **Pausing is the job picker's filter.** The picker already takes jobs only for
   `active` and `trial` tenants, so `paused` and `closed` stop the worker with no new code
   path. `paused` is set only by billing; the owner's own switch is `worker_enabled`.
4. **Trial: 14 days or 100 AI replies, whichever comes first, with every feature on.** When
   either runs out, the worker stops calling the model. Each new conversation goes to
   `waiting_human`, so the business's team sees it in the inbox. The emergency keyword
   pre-check still replies and escalates, because it needs no model and a customer
   reporting a gas leak must never get silence. Follow-up workflow steps are skipped.
5. **The billed unit is the AI reply**: an outbound message the worker wrote. Staff replies
   and inbound messages are not billed. Tokens are shown to the owner for information.
   Under Stripe, a daily job reports yesterday's count to a Stripe meter with the
   identifier `{tenant_id}:{date}`, so a retried job is a no-op at Stripe. The included
   allowance and the overage rate are configured on the Stripe price (graduated tiers), not
   in our code.
6. **Prices are placeholders** (`NOVAXIS_PRICE_*` settings), shown with a notice in the
   dashboard. The research brief says to set them from `usage_events` after the pilot. The
   Pilot plan waives the setup fee.
7. **Sign-up follows the sign-in mode.** In Supabase mode, sign-up needs the new user's
   JWT. In demo mode it needs the demo passcode. Locally it is open. `NOVAXIS_SIGNUP_MAX_TENANTS`
   (default 50) caps customer tenants, so a leaked passcode cannot fill the database.
8. **The wizard is a separate shape from `TenantSettings`.** `onboarding.Wizard` asks plain
   questions. `build_settings` (a pure function, tested for every pack) produces the full
   configuration. Each pack's manifest now carries `default_services` and
   `default_service_area`. The pack loader refuses a pack whose `after_intake` service
   codes are not among its default services.
9. **Operators** are users with role `operator` in the internal tenant `novaxis-ops`
   (`plan = internal`, worker off, hidden from the console and the timers). The console
   reads across tenants with the service session. "Enter" writes `operator.entered` to the
   customer's own audit log and returns a one-hour token carrying `act_tenant`. Auth
   honours that claim only for operator users, and an entered operator cannot use the
   console until they exit.

## Consequences
- The live demo can show the full commercial path (trial, plan, payment failure, pause,
  resume, cancellation) with no Stripe account and no money at risk.
- Going live with Stripe needs these steps:
  - create the prices (monthly, setup, and metered on a meter named
    `novaxis_ai_replies`);
  - set the price ids in `NOVAXIS_STRIPE_PRICES`;
  - add the webhook endpoint for the four event types.

  `[VERIFY]` the Checkout Session and Billing Meter Events request fields against Stripe's
  current API reference before the first live key. The container that built this could
  not reach Stripe's documentation.
- If the owner removes a service that the pack's `after_intake` maps to, booking proposals
  for that service fail at the scheduling step. A later chunk should warn about this in the
  wizard.

## Dissent recorded
- **LENS:** showing any price before the pilot risks anchoring. *Overruled:* the demo
  needs to show the shape of the offer. The numbers are settings, and the page labels them
  as placeholders.
- **Undertaker:** in demo mode, anyone holding the passcode can sign up, activate a plan
  for free, and sign in as the operator. *Accepted for the demo:* it holds only demo data,
  and tenant count is capped. Before a real customer's data is on the deployment, switch
  to Supabase sign-in and Stripe, rotate the passcode, and remove the demo operator.
