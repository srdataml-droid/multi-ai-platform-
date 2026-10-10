# Novaxis HVAC UX continuation — 10 October 2026

Role: senior UX/observability designer. Task: recover the purpose of the existing designs, compare the reference, and extend missing outcome states.

## Preservation instruction

The founder explicitly said: do not delete anything. Preserve all existing pages, screens and components; make changes in new clearly named copies. This instruction applies to future continuation too.

## What was verified in the live file

File: https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/

| Frame | Node | Purpose and evidence |
|---|---|---|
| Reference Workspace · Approvals | 1:2492 | Visually inspected on page 01. Staff approval, calendar write and notification have separate steps. Failed calendar writes are unconfirmed; failed notification retries only the message. |
| v3 · UK HVAC request review | 27:134 | Visually inspected on page 02. Customer wording, suggested assessment, missing address/authority/access/estimate and office ownership remain visible. A preferred time is not a hold. |
| v3 · UK HVAC visit feasibility | 27:272 | Visually inspected on page 02. Approved job duration, qualified engineer/crew, incoming and onward travel, fresh calendar, breaks/leave/hours, access and parts are explicit checks. Missing evidence prevents a time offer. |
| v3 · UK HVAC booking recovery | 24:130 | Reopened and visually inspected, establishing that the earlier draft persisted. Calendar disconnected; no confirmed visit or sent message. Existing editable frame properties inspected. |
| New unfinished recovery copy | 40:144 | Duplication was verified by the selected node URL and X=13184, Y=1600. Content remains the recovery template; uncertain-result edits were not completed. |

The request and feasibility frames existed at inspection. Their creation provenance was not established; do not attribute them to this continuation.

## Why these parts were added

The reference supplies the workspace structure, visual hierarchy and staff control model. Its illustrated dental consultation has a known duration and clinician. UK HVAC needs more evidence before an appointment can be promised: symptoms do not establish a diagnosis, every visit is not one hour, engineer competence matters, and travel consumes time on both sides. Request review collects these facts; feasibility evaluates the day; recovery exposes unresolved actions instead of implying success.

Keep the reference's calm sidebar, card hierarchy, explicit status labels and action timeline. Carry its separate approval/booking/message outcomes through every HVAC state.

## Work left, in execution order

1. **UX/observability — uncertain booking result.** Finish copy 40:144. Heading: “Check the calendar result before retrying.” State: “Booking result unknown · office review.” Show the original action reference, attempt time, provider, last checked time and reconciliation result when available. Do not fabricate these values. Primary action: “Check booking result”; secondary: “Back to request”. No new booking or confirmation message until the original result is known. Found event → confirmed state; verified absence → fresh feasibility/policy checks before retry; still unknown → retain office ownership. A disconnected calendar and an unknown write result are different states.
2. **UX/observability — booked, message failed.** Create another preserved copy. Show the provider-confirmed event and separate delivery status. Retry only customer notification. A delivery failure must not create another appointment or cancel the confirmed event.
3. **UX — feasible proposal and confirmed outcome.** Use clearly labelled synthetic fixtures for demonstrations. Show duration evidence, engineer, confirmed location, both journeys and protected time. Distinguish proposal, approval, provider confirmation and message delivery.
4. **UI/QA — navigation, mobile and accessibility.** Link and verify the new-copy journey. Complete mobile parity, focus/keyboard behaviour, status announcements, contrast, and loading/empty/error states. None of these were verified in this continuation.
5. **Software/AI/integrations — runtime.** Replace unsupported one-hour/unknown-service fallbacks, implement resource and route constraints, reconcile uncertain provider actions, and test tenant isolation, action gates and message-only retries. No application code changed here.

## Browser interruption and exact resume point

Figma input intermittently timed out even when a selection succeeded. After duplication, the attempted F2/rename sequence did not rename the frame: the visible tree showed a new standalone text layer named “@”, and two recovery frames. Preserve this layer as instructed; inspect and repurpose it only after verifying its location. Do not delete it or blindly repeat the duplication.

Navigation to the observed new node 40:144 timed out. Subsequent screenshot and browser inventory calls also timed out and reset the browser session. Therefore the copy's persistence after reload, rename, new text, prototype and final composition are unverified. No completed new outcome screen is claimed.

Resume by reconnecting to the existing user Figma tab, inspecting node 40:144, and renaming that existing copy through a verified UI control. Do not create another copy until its presence is checked. Originals were not deleted or intentionally edited.

No live booking, customer message, outreach, model training or server provisioning occurred.
