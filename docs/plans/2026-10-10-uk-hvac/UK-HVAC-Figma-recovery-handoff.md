# UK HVAC recovery screen — design handoff

10 October 2026 · Primary role: senior UX/observability designer

## Created in your existing Figma

[v3 · UK HVAC booking recovery](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/?node-id=24-130), node `24:130`, on `02 · Refined experience`.

The existing visible `v2 · Booking recovery` frame (`8:1299`) was copied as an editable frame. The source is retained. The new frame is 1440 × 1000 at X 8744, Y 1600, with inherited auto-layout, components, typography and semantic colours. No flattened screenshot was imported as design content.

## Scenario and decision

A fictional customer reports no heating from a gas boiler. Tuesday morning is a preference, not an appointment. The calendar is disconnected; the visit estimate and engineer assignment are incomplete. The interface keeps the enquiry unconfirmed and the customer reply unsent.

The recovery instructions require staff to reconnect and reconcile any booking result before checking duration, qualified engineer, both travel legs, breaks and leave. This avoids implying that reconnecting alone makes the visit feasible or that staff approval already happened. No business-approved duration, fee, real customer address or availability was invented.

## Evidence

- [Preview of the full frame](UK-HVAC-Figma-recovery-preview.jpg).
- [25 text changes with selected-layer references](UK-HVAC-Figma-edits.json). Every change was read back from the selected Figma text layer after editing.
- Full layout visually checked: text wraps inside the inherited cards; status labels distinguish unconfirmed booking and unsent response.
- The hidden old workspace approvals frame (`1:5545`) was identified; work used the visible v2 recovery example instead.

The browser timed out during the final reload check. Edits and layout were verified in the active document beforehand; persistence after that reload was not independently rechecked.

## Remaining design work

1. Add request intake and a detailed feasibility view with actual evidence slots for duration, engineer/crew, source freshness, incoming/onward routes and protected time.
2. Complete the separate confirmed, booking-result-unknown and booked/message-failed cases. A notification retry must not recreate the booking.
3. Specify desktop/mobile parity, ownership and takeover, urgent escalation delivery, keyboard order, focus and status announcements.
4. Inspect and wire prototype destinations. The inherited Reconnect calendar and Return to approval controls have not been validated as working prototype interactions.
5. Reconcile product approval policy and obtain practitioner/business review of service scope, qualifications, timings and customer wording before activation.

Use the [UX handoff](UK-HVAC-booking-UX-handoff.md), [catalogue](UK-HVAC-service-catalogue.md) and [19 synthetic scenarios](UK-HVAC-booking-scenarios.json) for the next design pass. This is one draft screen; no Novaxis app code, real booking, calendar connection or customer message was changed.
