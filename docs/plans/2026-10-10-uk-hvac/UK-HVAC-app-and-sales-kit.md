# Novaxis UK HVAC: app requirements and pilot sales kit

9 October 2026. First users: UK HVAC businesses, confirmed by the founder. Work from the existing app; complete and adapt its experience before expanding scope.

## Roles and handoffs

1. Product strategist: define buyer, offer, scope and truthful feature claims. Deliverable: this brief and the capability review. Initial pass complete; customer validation remains open.
2. Sales strategist: turn that offer into discovery, demo and pilot materials. Deliverable: scripts and qualification criteria below. Prepared; no outreach sent.
3. UX designer: complete the selected HVAC flow in the existing Figma, matching the app and recording required adjustments. Deliverable: customer, office and owner journeys with recovery states. Next design task.
4. UI/observability designer: make status, ownership, failed execution and next actions consistent on desktop and mobile. Deliverable: complete components and readable operational views.
5. Software engineer: implement accepted changes in the existing app in small coherent tasks.
6. AI/integration engineer: evaluate intake, proposals and provider operations, including escalation, duplicate prevention and failed delivery.
7. QA: prove the demo and pilot flow on a controlled environment before customer activation.

These are focused disciplines performed sequentially, not a claim that a staffed team or live pilot already exists.

## Buyer and user roles

| Role | Their job | What Novaxis must make easy |
|---|---|---|
| Owner / commercial buyer | Decide whether the service pays for itself; control costs and business rules | Setup, clear service scope, usage, staff access, pause controls and evidence of outcomes |
| Office staff / dispatcher | Qualify requests, arrange visits, resolve conflicts and answer customers | Needs-you inbox, postcode and problem details, approval/edit/reject, takeover and reliable scheduling handoff |
| Engineer / field user | Understand the visit and urgent context | Concise job summary, customer contact, property location and clear visit status; do not assume a technician-dispatch product already exists |
| Customer / homeowner | Obtain help and know whether a visit is confirmed | Short intake, plain language, clear confirmation status and access to a person |
| Novaxis implementation/operator | Configure the business and recover service failures | Tenant-specific setup, connection health, action history and bounded support effort |

Use existing owner/staff/viewer/operator permissions where appropriate. These personas do not automatically require new application permission roles.

## Existing app: source-based capability review

Inspected a local copy of the public main branch. Source presence does not establish that the deployed feature works. Browser access to the deployed app timed out, so production behavior remains unverified.

| Area | Evidence in current source | Commercial implication / next action |
|---|---|---|
| HVAC intake | Pack asks name, problem category, symptom, optional system age, vulnerability to cold, postcode, phone and preferred visit window | Build the demo around boiler service or ordinary heating enquiries; use real configured services |
| Inbox | All / Needs you filter, channel, conversation status and pack facts | Show how the office finds work needing attention |
| Approvals | Approve, reject, editable details, conversation link and failed-execution message | Demonstrate office control; prove failure handling survives refresh and is visible to other staff |
| Scheduling | Held/confirmed statuses and attended/no-show outcomes appear in page source | Show a request becoming a confirmed visit; attendance is not proof of paid job revenue |
| Setup | Europe/London option, postcode service area, service configuration and Google Calendar connection | UK-specific setup is already partly present; confirm daylight-saving and actual diary behavior |
| Billing | GBP formatting, demo/Stripe distinction and placeholder-price fields | Do not treat app demo prices as the approved commercial offer |
| Navigation | Core pages are emphasized; work queue, analytics and stock are gated behind extras | Keep the initial demo focused; don't sell gated screens as default production features |
| Action policy | Gate maps low to automatic approval, medium to review, high to rejection; configured services can auto-confirm | Explain business control accurately; avoid promising every booking always waits for a person |
| Prompt policy | HVAC prompt says every job is approved by office and uses “passed to team” language | Reconcile prompt with actual configured gate before a live sales demo |

Source areas: HVAC pack intake/workflows/prompt/rules; core gate; web inbox, approvals, schedule, onboarding, billing and menu. Repository: https://github.com/srdataml-droid/multi-ai-platform-

## Initial offer

**Novaxis Enquiry Desk for UK Heating Businesses**

Proposed buyer-facing description:

“Give incoming heating enquiries a clear next step. Novaxis gathers the problem, postcode and preferred visit time, then helps your office review and arrange the visit. Your team can step into the conversation and see what still needs attention.”

Initial scope: one business location/team, one configured heating service workflow, web chat first, staff review and a verified calendar or documented office handoff. SMS/email can be added after provider configuration and delivery tests. Keep the customer's real diary as the operational source of truth.

Do not include full telephone answering, technician dispatch optimisation, guaranteed extra revenue, unlimited manual support or unrestricted custom integrations in this offer. Those require separate proof and scope.

Proposed commercial test: £249/month and £299 standard setup. Both are hypotheses pending customer and cost validation. Quote the specific allowance after measuring the channel mix; do not sell an unspecified unlimited allowance. A 30-day assisted pilot should have a written scope, baseline, support boundary and renewal/cancellation decision. Payment, tax and billing terms must match the actual legal entity and configured account.

## Qualification before a demo

- UK heating/HVAC business with incoming enquiries and an identifiable decision maker.
- A repeatable intake problem the office can show using a recent example.
- An office or owner available to handle human-review cases.
- A booking system compatible with the scoped workflow; establish the actual system during discovery.
- Enough enquiry activity to observe use during the pilot. Request real counts instead of inventing a threshold.
- Willingness to pay for a bounded outcome and provide feedback.

Poor initial fit: already satisfied by native reception automation; requires immediate autonomous phone dispatch; no staff coverage for escalations; demands a bespoke integration within the standard fee; cannot establish who confirms visits.

## Discovery script

1. What happens to website, email and text enquiries while your engineers and office are busy?
2. Walk me through the last enquiry that was delayed or lost. Where did it stop?
3. Which diary/job system do you use, and who decides whether a visit is confirmed?
4. What details must your office collect before arranging a visit?
5. Which enquiries must immediately go to a person? Who is available at those times?
6. What does your current software already automate well?
7. If we improve this workflow for a month, which result would make it worth paying for?
8. How would the proposed fee compare with your present cost and the value of the problem?

Record facts, objections and current alternatives. Do not treat positive interest as willingness to pay.

## Five-minute demo built around existing functionality

Use a controlled demo tenant and synthetic customer details. Do not submit fake enquiries into a live business's inbox or trigger real customer communications.

1. **Customer:** ask for a boiler service in the demo business's configured area. Collect the existing pack's details. Say “request” until confirmation succeeds.
2. **Office:** open Inbox → Needs you → conversation. Show the gathered facts and actual control ownership.
3. **Decision:** inspect the proposed appointment, edit if appropriate and approve in the configured workflow. Explain why the action needs review.
4. **Visit:** inspect Schedule and the connected diary/handoff. Distinguish approved request, pending external acceptance and confirmed visit according to the actual integration.
5. **Recovery:** use an approved test fixture for a calendar conflict or failed write. Show what staff must do next and verify retry behavior.
6. **Owner:** explain setup, permissions, usage and outcome review. Show only features present in that deployment.

Exit check: the customer-facing wording, stored action state, office screen and external booking all agree. If the external system or delivery cannot be demonstrated, label it explicitly and narrow the pilot offer.

## Sales conversation

Opening:

“We’re building Novaxis for UK heating businesses whose incoming enquiries need a quicker, clearer route to a visit. It gathers the details your office needs and keeps the team involved in booking decisions. I'd like to show the enquiry-to-visit workflow using the service and diary setup you actually use.”

Pilot invitation:

“For the pilot, we’ll scope one enquiry workflow, configure it with your team and review the results each week. We’ll measure completed intake, confirmed visits, staff effort and failures against your current process. After the pilot, we decide together whether it earns its monthly cost.”

Objections:

| Buyer says | Response |
|---|---|
| “We already have Jobber/another tool.” | “Let's check what it already handles. Novaxis is only useful if there's a remaining workflow problem we can solve.” |
| “Will it book the wrong visit?” | “We'll configure which actions need review, test the rules and show the exact details before confirmation. Let's identify the cases you would never automate.” |
| “Does it answer the phone?” | “The current scoped offer handles text enquiries. Full phone answering is outside this pilot unless separately implemented and verified.” |
| “Will it diagnose boiler faults?” | “No. It collects the request and routes it; qualified staff handle diagnosis and repairs.” |
| “How much money will it make us?” | “We haven't established that for your business. The pilot measures actual outcomes and staff effort before making a return claim.” |

These are prepared talking points, not messages sent to prospects.

## UK HVAC Figma/app tasks

| Priority | Primary role | Task | Completion check |
|---|---|---|---|
| P0 | Product + AI policy | Reconcile HVAC prompt, gate and service auto-confirm settings | One explicit action-policy table and customer wording matching every allowed state |
| P0 | UX | Complete customer boiler-service request → office review → diary confirmation | Intake, incomplete details, outside-area, handoff, hold expiry and confirmed states are designed |
| P0 | UX/observability | Define office needs-you view and persistent failed-action recovery | Staff can find the problem after refresh, understand ownership and take a valid next action |
| P0 | Integration/QA | Verify one real booking boundary in a controlled environment | Successful write, conflict, partial success and duplicate prevention have evidence |
| P0 | Product/implementation | Configure a repeatable UK pilot setup | Service area, Europe/London, services, hours, review rules, escalation contact and channel tests are recorded |
| P1 | UI | Finish mobile review and reusable action/status components | Readable summary, deliberate decision actions, consistent status labels and accessibility checks |
| P1 | Sales | Run qualified buyer discovery and record offer objections | Actual buyer answers and paid-pilot decisions, not assumed demand |
| P1 | Product/observability | Define weekly pilot evidence | Intake, confirmed visits, staff time, failures, cost and baseline are traceable |

No code, live configuration or Figma design has been changed by this source review. Next implementation/design work should use these concrete tasks rather than re-open broad product scope.
