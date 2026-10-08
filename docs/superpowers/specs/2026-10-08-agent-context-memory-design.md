# Novaxis agent context, response quality and skills

Status: design for review; implementation and production deployment pending.

## Intended outcome
Every HVAC, dental and property-restoration assistant has explicit operating rules,
personality, business knowledge, customer context and controlled memory. Owners can
understand and customise its behaviour without bypassing booking validation or approvals.
The company lab keeps a general-chat baseline and a separately connected business workflow.

## Current evidence
- Signup already assigns a pack; packs declare allowed tools and intake questions.
- Pack prompts supply operating instructions; Studio saves optional personality and facts.
- Worker turns include business facts, recent messages, conversation summary, intake and appointments.
- Contacts are tenant-scoped. Cross-channel identifiers do not automatically merge people.
- The lab generic model endpoint has no tools; connected mode uses the visitor worker flow.
- Persistent, reviewed customer preferences and a unified context preview are missing.

## Context sections and precedence
1. Protected platform policy, actual permission checks and action gates.
2. Versioned industry AGENTS.md: role, workflow, supported skills and operating limits.
3. SOUL.md: industry communication defaults with owner-approved style overrides.
4. BUSINESS.md: verified services, location, policies, hours and fees from structured settings.
5. USER.md: current contact identity and relevant approved preferences, not owner account credentials.
6. MEMORY.md: bounded current-thread context and approved persistent facts, with sources.
7. Current customer messages and imported material, treated as data rather than policy.

The files are meaningful because the application explicitly loads them. File names alone
create no capabilities. Pack files contain reusable defaults; per-business and per-customer
values stay in the tenant-scoped database. Preview/export renders their readable equivalents.
Customer text and memory cannot become system policy or change permissions.

## Response refinement
- Answer a direct service, hours or price question using known facts before collecting intake.
- Do not demand a name simply to answer an FAQ.
- Use one or two short sentences normally and one necessary question at a time.
- Avoid Markdown decorations in plain-text widget replies.
- Do not repeat an introduction or information already supplied.
- Describe uncertainty plainly; unknown fees, policies and times remain unknown.
- Describe action status accurately: requested, awaiting staff, offered, confirmed, failed.
- Never describe an alert as delivered unless its execution succeeded.
- Follow the owner's style within the platform and industry rules.
- Generic company-lab mode remains general chat without booking tools; switching modes clears local context.

## Industry-specific skills
Skills are reviewed workflow instructions paired with existing allowed tools, not arbitrary
plugins or executable code uploaded by business owners.

Common skills:
- FAQ answering: verified business facts only; hand off unknowns.
- Intake: extract supplied answers and ask the next relevant missing question.
- Booking: propose a visit, present verified offered slots and confirm a selected valid slot.
- Changes: request rescheduling or cancellation through existing gated actions.
- Human handoff: transfer context without claiming immediate human availability.
- Emergency routing: existing deterministic pre-check and escalation, never weakened by style.

HVAC: equipment/service enquiry intake, service-area checks, maintenance or estimate requests.
Dental: new/existing patient intake, appointment requests, clinician preference and clinical handoff;
no diagnosis or treatment recommendations.
Property restoration: damage intake, ongoing-hazard escalation, inspection request and relevant
claim administration; no insurance coverage or safe-occupancy promises.

Only manifest-allowed tools are exposed. Text edits cannot enable a tool, add an integration,
change a risk floor or expand access. Each skill shows its inputs, allowed tools and outcome
states in Studio. New industries require reviewed pack instructions and skill definitions.

## Short-term memory
Reuse the current conversation messages, summary, extracted intake and appointment state.
Summaries remain lower-trust data. Structured appointment records override stale summaries.
Bound the context size, prioritise recent relevant information and do not persist model reasoning.

## Long-term memory
Initial version: owner/operator-approved, non-clinical customer preferences only. No automatic
write from model output. No clinical notes, diagnoses, credentials, payment data or inferred traits.

An additive customer-memory table stores tenant, contact, category, value, source conversation,
creator, timestamps, expiry and active/deleted state. Categories initially: preferred language,
contact preference, preferred visit window and owner-approved service context. Each value has
strict length limits. Contact preference is not marketing consent and cannot trigger outreach.
A preferred window is not live availability. Service context excludes access codes and secrets.

All reads/writes use the tenant-scoped session and contact ownership checks. RLS applies.
Encrypt values at rest using the existing sensitive-data machinery. Audit records contain action
and record identifiers, not raw memory values. Do not log customer content.

Owner/operator controls: add, review, edit, disable retrieval, expire and remove entries.
No customer-facing memory write tool in this first release. Retrieval uses only the exact
current contact within the current tenant, capped at a small number of relevant active entries.
Do not use a typed phone number as proof of identity. Honour existing explicit contact merges.
A deleted/expired memory is never retrieved. Integrate with contact export, erasure and retention;
a business must not retain customer memory after the associated contact is erased.

External-agent context respects current sensitive-data restrictions. Do not expand the agent
API's customer-data disclosure merely because built-in memory exists.

## Studio experience
A context panel shows Operating rules, Personality, Business facts, Skills and Memory.
The normal editor uses plain labels; Markdown preview/export is optional.
Protected rules are read-only. Customisation and reset preserve business facts and customer records.
Editing lock remains a UI convenience; owner/operator authorization remains server-side.
Customer memory is managed within a selected customer, never in a shared company profile.
Preview shows sources, enabled skills, effective style and missing business facts without secrets.
Use dedicated updates for profile/memory rather than overwriting unrelated settings.

## Delivery sequence
1. Versioned context sections and reviewed skills, shared by built-in reply generation and
   owner previews; refine response style and document the generic/connected lab distinction.
2. Add controlled customer memory with schema/RLS, privacy lifecycle and owner UI.
3. Verify approved cases and deploy web/API together; do not label memory live before step 2.
Each step remains small enough to review independently. No new provider or model training required.

## Acceptance evidence required before claiming completion
Context assembly selects the correct industry and tenant; profile reset preserves facts.
Replies answer FAQs without unnecessary intake, avoid repeated questions and state booking status honestly.
Only allowlisted tools are exposed and every existing approval/permission check remains active.
Memory cannot cross tenants or contacts, expire/delete entries are excluded, and erasure/export include it.
Dental clinical details and secrets are excluded from persistent preference memory.
Live Studio displays the effective sections; the lab general/connected modes remain distinct.
Tests are not run or added until the user requests verification, per session instructions;
build, syntax and deployment checks are recorded separately and never described as behavioural tests.

## Scope boundaries
No autonomous outreach, website scraping, self-modifying instructions, new third-party integrations,
provider changes, clinical decision-making or automatic cross-customer learning.
