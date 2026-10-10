# Novaxis booking UX handoff — UK HVAC

Version 0.1 · 9 October 2026 · Prepared for the senior UX/observability role

Build these requirements into the existing Novaxis Product UX v2 file. The earlier inventory verified workspace/mobile screens, customer widget, booking recovery storyboard, contextual states and reusable specimens; it did not establish that these requirements are already designed. This handoff does not claim Figma has been edited.

## One journey to finish first

Customer reports an issue → assistant clarifies the requested service → staff resolve missing scope/duration when needed → system checks the engineer and both travel legs → customer selects an offered slot → authorized action rechecks and books → customer receives a separately tracked confirmation.

The first implementation should prove this journey across the three existing service codes. Complete interruption and recovery states with the same care as the successful journey.

## Screen requirements

| Existing surface | Required content and action | Important state to design |
|---|---|---|
| Inbox/request detail | Customer's words; proposed visit type; equipment/fuel; urgency; location; access; who can authorise; current owner and missing facts | “Service needs clarification”; “Visit length needs staff estimate”; “Assigned to staff” |
| Approvals/booking review | Exact customer/property; approved visit scope; duration source; proposed engineer/crew; incoming/onward travel; protected time; price/scope acceptance if required | “Cannot confirm yet” with each missing/failed check and a useful next action |
| Schedule | Engineer-specific work, travel, holds, breaks, leave and closures; explain why a gap cannot be offered | Time changed since review; hold expired; engineer became unavailable |
| Settings/onboarding | Service catalogue with scope, systems/fuels, duration evidence, skills/crew, fees, region and activation review | Draft profile; unsupported system; expired competence record; no escalation owner |
| Connections | Source name, authoritative fields, permission and last successful read | Stale calendar, stale sheet, disconnected routing or conflicting source values |
| Action history/recovery | Proposal, approval, external booking and notification as separate events | Calendar booked/message failed; unresolved provider timeout; alert delivery failed |
| Customer widget | Brief context-aware questions, plain visit scope, available options and honest pending/confirmed messages | Unknown scope, callback needed, no feasible slots, expired offer, human takeover |
| Mobile staff view | Compact request facts, missing-check summary, ownership and safe review actions | Meaningful decisions without horizontal tables; detailed sources expandable |

The refined page was reopened on 9 October 2026. Its layer inventory includes the workspace/mobile surfaces above and seven additional frames: `v2 · Restore template confirmation`, `v2 · Mobile Assistant Studio`, `v2 · Booking recovery`, `v2 · Booking confirmed`, `v2 · Website installation`, `v2 · Assistant playground`, and `v2 · Model and behavior`. Use the booking recovery/confirmed frames for execution/delivery distinctions and the model/behavior frame for capability controls. These are verified layer names, not a content or prototype audit. Individual-frame selection is intermittently failing through browser controls.

The refined `Workspace · Approvals` frame was selected and its URL identified as node `1:5545`: [open the existing approval frame](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/?node-id=1-5545). Browser input intermittently times out or completes after a delay, so readable frame-content inspection remains open. This navigation changed no design content.

If the current file combines some surfaces, extend the relevant existing frame rather than duplicate product areas. Associate the remaining frame/component IDs with these requirements after inspecting them. The existing [Figma file](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/) is the intended design destination.

## Request details

Separate **Customer reported** from **Suggested visit**. The former preserves the customer's wording; the latter shows the assistant's proposed classification and its supporting facts. Staff can correct it. Reclassification invalidates a dependent duration, slot or approval and reruns the checks.

Use actionable missing-data labels: “Confirm boiler or heat pump”, “Confirm service address”, “Staff estimate needed”, “Authorisation callback needed”. Do not show an AI confidence percentage as proof that a visit can be booked. An optional support flag should avoid displaying unnecessary medical details.

Urgent concerns interrupt the entire booking journey. Show contact/escalation ownership and delivery status. “Alert queued” and “Alert delivered” are distinct. The customer must never be told that an engineer was alerted or will respond immediately solely because a tool proposal exists.

## Booking review layout

1. Customer/property and requested scope, with the approved commercial terms where relevant.
2. Visit length and evidence: profile version or staff-estimate author/time; range/uncertainty only when supported.
3. Assigned engineer/crew and relevant competence check, with status and verification time.
4. Day timeline showing previous commitment → travel → proposed visit → onward travel → next commitment. Include shift boundary locations, access allowance, breaks and leave.
5. Feasibility checklist with checked, missing, stale and failed states, each accompanied by a reason and next action.
6. Action summary identifying whether the proposal is automatic, requires review or is blocked under the actual policy.

The primary action describes the immediate operation. Use “Recheck and confirm” only when the workflow supports that operation. While it executes, show progress and prevent duplicate submission. A customer-facing time is an arrival/start window agreed by the business, not a guarantee of repair completion.

## Required state behavior

| State | Staff explanation | Customer wording pattern | Next action |
|---|---|---|---|
| Unclassified request | Need equipment/work context | “I need one more detail so the team can arrange the right visit.” | Clarify or assign staff |
| Duration unknown | No approved planning length | “The team needs to confirm the visit scope before I can offer a time.” | Request a documented estimate |
| Address uncertain | Cannot verify property route | “Please confirm the service address.” | Resolve address; reroute |
| Qualification unknown/expired | Resource not verified for this work | “The team is checking who can handle this visit.” | Verify/reassign; no override of a failed requirement |
| Travel infeasible | Gap cannot fit both route legs | “That time is unavailable. Here are the alternatives.” | Offer checked alternatives |
| Break/leave conflict | Work or travel overlaps protected time | Same unavailable-time message | Select another resource/time |
| Stale source | Availability cannot be trusted | “I’m checking availability with the team.” | Refresh or staff handoff |
| No feasible slots | No option meets current requirements | “I can pass your preferred time to the team for a callback.” | Record preference, not an appointment |
| Held | Temporary hold and visible expiry | “This time is held until [actual expiry]. Please confirm your choice.” | Confirm before expiry |
| Approval pending | Staff approval is still required | “Your request is with the team. The appointment is not confirmed yet.” | Staff review |
| Calendar write uncertain | Provider result unresolved | “We’re checking your booking. Please wait for confirmation.” | Reconcile by existing reference before retry |
| Booked, notification failed | Booking exists; delivery failed | Do not imply successful message delivery | Retry message only; expose alternative permitted contact |
| Confirmed | Booking record and required checks succeeded | “Your [visit scope] is booked for [actual agreed time/window].” | Track delivery/reminder separately |
| Taken over | Staff own communication | Staff-authored response | Stop automated replies; deliberate handback |

These are wording patterns for product design, not emergency scripts or claims that the underlying runtime already supports each state. Names/times/references must come from actual results.

## Recovery and observability

Keep business outcomes durable across refreshes and devices. A temporary banner alone is insufficient for an unresolved booking or failed customer notification. Show a responsible owner, last attempt, error explanation, existing external reference and safe next action. Restrict staff-only calendar event names, private leave reasons and internal client assessments from customer responses.

Record profile version, evidence references, source checks, resource assignment, route results, slot/hold revisions, policy outcome, author/approval and execution/delivery outcomes. Activity logs should explain the decision while avoiding full customer addresses or support details in routine telemetry. Measure missing-estimate handoffs, classification corrections, infeasible-route rejections, confirmation success, duplicate prevention, partial failures and recovery time.

## Acceptance checks for the completed Figma journey

- The three pilot visit scopes and an unclassified request have explicit paths.
- The 90/60/45-minute repository examples are never presented as approved timings.
- Routine servicing and landlord safety checks are distinguishable.
- Changing work scope invalidates the dependent appointment proposal.
- Unknown duration, location or competence prevents a confirmation claim.
- Both travel legs and protected times are visible in the review timeline.
- No-slot, source-stale, hold-expired and conflict paths return to a useful action.
- Approval, external booking and customer delivery have separate states.
- Failed delivery after booking retries the message without creating another booking.
- Safety escalation and takeover interrupt routine intake; delivery claims reflect tool results.
- Desktop and mobile show the same critical decisions and controls.
- Keyboard order, focus, labels, error messages, status announcements, non-colour status cues and responsive behavior are specified for implementation. These checks apply the [WCAG 2.2](https://www.w3.org/TR/WCAG22/) target; Figma alone cannot establish conformance.

Use the [service catalogue](UK-HVAC-service-catalogue.md) for business facts and the [scenario fixture](UK-HVAC-booking-scenarios.json) as the review script. Design completion is evidenced by inspected Figma frames and linked prototype paths, with unresolved backend dependencies identified. A written handoff or a screen inventory alone does not complete that task.

## First Figma draft completed — 10 October 2026

Created [v3 · UK HVAC booking recovery](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/?node-id=24-130) as an editable copy of the visible v2 recovery frame. The fictional heating-fault enquiry has no approved duration or assigned engineer, a disconnected calendar, no held slot and an unsent customer response. Its timeline distinguishes review, booking result and message delivery; recovery instructions include the estimate, qualified engineer, both travel legs, breaks and leave. The original source frame is retained.

Twenty-five text changes were read back and the full composition visually checked. See the [preview and handoff](UK-HVAC-Figma-recovery-handoff.md). This is one draft state, with remaining desktop/mobile flows and prototype behavior still open. The final browser reload timed out, so persistence after reload was not independently rechecked. No application or provider action was performed.
