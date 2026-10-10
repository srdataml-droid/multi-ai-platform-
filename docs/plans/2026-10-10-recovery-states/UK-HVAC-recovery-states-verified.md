# Novaxis — two recovery design states verified

10 October 2026. Primary role: senior UX/observability designer.

## Completed design chunk

- [v4 · UK HVAC booking result unknown](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/?node-id=40-144): resumed the existing unfinished copy, renamed it and updated editable text. The primary action checks the original calendar result. Office ownership, no blind second booking, no confirmation while uncertain, and found/verified-absent/still-unknown branches are visible. Original visit and approval details remain subject to checking; missing provider/action reference and last check are disclosed. The response draft does not promise an appointment.
- [v4 · UK HVAC booked · message failed](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/?node-id=43-151): duplicated the new uncertainty frame into another preserved copy and adapted it. Calendar confirmation and failed notification appear separately. The primary action retries only the message. The visit stays booked; no duplicate event or automatic cancellation. Recovery checks recipient and latest delivery result, keeps the message reference and retains office ownership if unresolved.

Both use the existing editable layout, styles and nested labels. No screenshots were flattened into the design. Source frames, existing pages and components were retained. Extra standalone text layers were preserved and moved below the screens (Y=2800, 2840 and 2880) so they no longer overlap the layouts. An attempted undo during correction did not remove the extra layer; it was subsequently preserved and repositioned.

## Verification

Each final composition was visually inspected. Figma was successfully reloaded; both exact frame names persisted. Each frame was then selected again and its complete final content visually checked after reload. Previews were saved from the browser after that check:

- `UK-HVAC-booking-result-unknown.png`
- `UK-HVAC-booked-message-failed.png`

Browser input occasionally stalled, so failed actions were checked before further edits. Final screenshots supersede intermediate screenshots and partial edit attempts.

## Evidence boundaries

These are design drafts, not runtime capabilities. Prototype destinations, keyboard navigation, accessibility and mobile parity were not validated. No app code changed, and no booking, message, outreach or server action occurred.

The confirmed visit is an explicitly fictional fixture: Alex Taylor, heating fault assessment, 90 minutes, Tuesday 13 October 2026 10:00–11:30 Europe/London, demo event `HVAC-DEMO-EVT-1042`. The fictional approval/route-check timeline is illustrative; it does not validate a real engineer, real route or tenant policy. It does not approve the catalogue's demo durations for business use.

The message-retry wording is a proposed design rule. Runtime retry limits, delivery reconciliation, idempotency and permissions still need implementation and policy review. Approval, booking and delivery must stay separate in the actual application too.

## Next concrete task

Role: senior UX designer. Build the feasible proposal and fully confirmed/delivered outcome using reviewed synthetic fixtures, then connect and verify the new-copy journey. Expose the qualified engineer, approved scope/duration evidence, confirmed location, incoming/onward routes, breaks/leave/hours, access/parts and source freshness before approval. Follow with mobile and accessibility work, then a scoped implementation with appropriate end-to-end checks.

The founder's instruction remains: **do not delete existing work; edit new copies**. Read this and `docs/LATEST-PLAN.md` when continuing from another chat.
