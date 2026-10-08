# Novaxis walkthrough and verification

**Checked:** 8 October 2026  
**Repository:** `srdataml-droid/multi-ai-platform-`  
**Production web commit checked:** `224fdb7` (`main`)

This report separates what was checked on the deployed app from tests run against an isolated local copy. No real customer enquiry or booking was submitted, and no email was sent.

## What Novaxis presents

Novaxis is a business-aware inbox and workflow assistant for small service businesses. The documented business packs cover HVAC, dental, and property restoration. Its core promise is to collect useful enquiry details, help staff respond consistently, propose next steps, and keep a person involved in decisions.

The main workflow is:

1. **Inbox:** review incoming enquiries and identify items that need staff attention.
2. **Approvals:** review, edit, approve, or reject proposed actions.
3. **Schedule:** inspect proposed, held, and confirmed bookings and attendance.
4. **Contacts:** review customer history and manage data export or erasure.
5. **Settings:** configure hours, services, FAQs, booking types, channels, team, website chat, and assistant controls.

Owner setup and billing are also documented. Some broader features are parked behind an extras flag, including phone-call handling and other advanced workflows. The live deployment was not confirmed to have the extras flag enabled, and no live phone call was made. Treat voice calling as unverified, not as an available production feature.

The HVAC demo form is a separate public intake page. It collects a service request and says the business will call to schedule; this check did not submit that form.

## Live deployment checks

- The production web app loaded and redirected to the inbox successfully.
- The web app exposes a valid installable web-app manifest. This confirms a progressive web app setup; it does not establish that a native iOS or Android app has been published.
- The production API health endpoint returned healthy.
- The deeper health check reported the database available, schema current, zero stuck jobs, zero failed jobs in the previous hour, and zero emergency alerts awaiting delivery over 24 hours.
- Live pages and health endpoints were read only. No sign-in, production write, customer submission, or booking was attempted.

### Public production pages

- The dashboard URL resolves to the sign-in page. Its inbox API request returns 401 while unauthenticated; no production credentials were provided, so authenticated dashboard screens and the production feature flags could not be checked.
- The public sign-up page advertises a 14-day or 100-AI-reply trial with no card. It lists UK dental, trades, property restoration, and other appointment businesses, but requires a demo passcode to create an account. I did not submit the form.
- The demo passcode is a shared API environment setting; sign-up does not create it. A read-only public API check confirms demo mode is active. The connected Vercel access could list the Novaxis projects but denied access to environment-variable metadata (403), including after the user granted access. I could not verify the passcode, so no account was created. A separate login code is generated only after successful sign-up.
- The user reports trying a passcode and receiving “wrong.” Fresh read-only checks still show demo auth mode and a 14-day/100-reply trial. This confirms the gate is active, but not which passcode the running API expects. No signup was created.
- After the user reported changing the setting and redeploying, read-only checks of the live API returned healthy production status, demo auth mode, and the expected 14-day/100-reply trial options. These checks confirm the API is responding in demo mode; they do not validate the new passcode. No account was created by this walkthrough.
- A public API key is not needed for the current signup flow. The API reports `demo` auth mode; in this mode, signup requires the shared demo passcode. A public Supabase anon key is only used by the separate Supabase-auth path. No API key was requested or used.
- The separate HVAC page is branded “Brightside Heating & Air” and asks for contact details, service needed, problem description, urgency, and preferred time. It tells visitors the office will call to confirm a time. It is labeled a demo with placeholder business details; its displayed phone number is a 555 placeholder. I did not submit a request or call the number.
- The HVAC page’s form flow is customer self-service intake; it does not demonstrate an AI answering a phone call. Current live voice-receptionist capability therefore remains unverified.

## Local verification

Tests ran against the local checkout and an isolated local database with a fake model provider. They did not send paid model requests or change production data.

- Web unit tests: **12 passed**.
- Web type check, lint, and production build: **passed**.
- Python suite: **454 passed, 1 skipped**.
- Scripted business-pack evaluations: **16 of 16 passed** (HVAC 6/6, dental 5/5, restoration 5/5).
- Browser walkthrough: after correcting the local test harness, all **9 scenarios** passed across the complete run and rerun of the four affected flows. In a later repeat of the full suite, **8 of 9** passed under the default 60-second limit; the remaining approval-to-schedule scenario passed when rerun with a 120-second limit. Its fake worker took about 38 seconds in that run, so the overall flow exceeded the default test limit. This points to a slow local test path; production latency was not measured.

The nine browser scenarios cover sign-up and onboarding, demo billing and operator access, booking-type setup, the end-to-end enquiry/approval/schedule flow, viewer permissions, the external booking bridge, the agent API, stock counting, and website chat including a spoken reply. The optional bridge, agent, and stock pages were deliberately enabled for local browser coverage; their presence in those tests does not mean they are enabled in the production menu.

The browser suite needed a local test harness adjustment to pass the fake response script into its worker. The initial harness failures were corrected. The later timeout and extended-limit pass are both recorded above. A temporary `.dockerignore` was used during local image builds and removed afterward.

### Follow-up: phone country selector and website chat setup

At the user's request, a country selector was added to the on-call phone field in onboarding. The selected country is used to format the saved phone number in international form. Website Chat settings now explain how to allowlist a website origin, install the Novaxis embed snippet, and verify a message in the Novaxis Inbox.

- Onboarding browser check: **1 passed**. The check selected a country, entered a national-format number, and verified the international-format number in the review step.
- Cross-origin website chat browser check: **1 passed**. The widget was embedded on a separate local website origin, sent a visitor message to the isolated demo tenant, and received a scripted reply.
- Web type check and lint: **passed**.

These follow-up checks used the local demo tenant, isolated database, and fake AI response. They did not use the user's production account, a real external website, live customer data, or a paid model request. The code changes have not been committed, pushed, or deployed. Production domain allowlisting and live-widget behavior remain unverified.

## Limits and next checks

### Assistant Studio follow-up

The owner approved a new Assistant Studio area. It adds visitor chat through the existing
webchat channel, safe model configuration metadata, the latest recorded worker model for
the business, and an editor for saved reply style. Implementation details and the exact
verification scope are recorded in `docs/ASSISTANT-STUDIO.md`. Browser verification used
mocked API responses; no production chat was sent. Changes remain local.

- These checks establish that the tested flows pass in the local test configuration, with one browser scenario needing a longer timeout in the expanded run. They do not prove production reliability, customer outcomes, or deployment of optional voice features.
- The app was not signed into on production, so owner-only setup and billing screens were not exercised there.
- Cross-origin widget behavior was verified locally only; to test the user's real website, its exact origin must be allowlisted in the account's Website Chat settings and the generated embed snippet installed on that site.
- Before inviting pilot businesses, confirm the exact production feature set, test a complete workflow with synthetic data in a staging environment, and verify human handoff and failure handling. Keep real calls and customer records out of testing until the owner explicitly chooses a safe pilot setup.

## Remaining before a real pilot

1. **Finish demo access.** The live API reports demo auth mode, but no account has been created and the passcode the user tried was rejected. The owner must check or set `NOVAXIS_DEMO_PASSCODE` on the `novaxis-api` Production environment, ensure the value has no extra spaces, save, and redeploy the API. Credential changes require the owner to enter/save them; my Vercel project-settings requests currently return 403. Afterward, retry signup and save the one-time login code.
2. **Confirm API deployment wiring.** The owner reports Vercel shows `novaxis-api` without a connected Git repository. This could prevent automatic deploys from the repo. The hosting ADR expects both API and web projects to deploy from the shared repo. Verify the Git link, production branch, and deployed commit in Vercel before relying on future code changes. I could not inspect these settings through the current Vercel connection.
3. **Verify the production model provider.** Project documentation says the demo can use scripted replies until a real model provider is configured. Environment settings are inaccessible, so the live provider and reply quality remain unverified.
4. **Confirm integrations by channel.** The website form/chat are publicly reachable. SMS, WhatsApp, email, phone calls, and external calendar behavior need their provider credentials, webhooks, or deployment switches checked; no live integrations were exercised. Phone-call answering remains unverified.
5. **Run a controlled pilot check.** Use synthetic requests in staging first, verify approvals, handoff, emergency handling, schedule behavior, and failure recovery, then invite pilot businesses only after the production configuration is confirmed.

## References checked

- Production web app: https://novaxis-web.vercel.app
- HVAC demo intake: https://novaxis-hvac-demo.vercel.app
- Production API health: https://novaxis-api.vercel.app/health
- Production API deep health: https://novaxis-api.vercel.app/health/deep
- Local project documentation: `docs/prototype.md`, `docs/ARCHITECTURE.md`, and `docs/BUILD-PLAN.md`
