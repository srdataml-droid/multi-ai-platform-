# Novaxis: plan compared with the current Figma copy

Reviewed 11 October 2026. Primary role: senior UX and observability designer. Scope: the separate Product UX v2 file, page `02 · Refined experience`. No application code or deployment changed.

## Intended plan

Finish the existing design before implementing the coherent UK HVAC workflow in Novaxis. Review the customer's report without inventing a diagnosis; resolve address, authority, access, scope and duration. Check engineer suitability, fresh availability, incoming and onward travel, breaks, leave and protected finish time. Keep missing evidence with the office. Separate a proposal, staff approval, calendar confirmation and customer delivery. A failed customer message must not create another booking; an unknown calendar result must be reconciled before retrying.

Desktop and mobile companions, reusable components, accessible status treatments and verified prototype navigation are part of design completion. Static Figma states are not working provider integrations.

## Current file compared with that plan

| Area | Current evidence | Assessment |
| --- | --- | --- |
| Request review | `27:134`, visually reviewed in presentation mode | Distinguishes report from diagnosis and leaves missing facts explicit. |
| Incomplete visit feasibility | `27:272`, visually reviewed | Covers duration, qualified engineer, both journeys, freshness and protected time. |
| Calendar-disconnected recovery | Existing `24:130` retained | Earlier verified recovery loop remains part of the design; not a real reconnect. |
| Complete-evidence proposal | `44:154`, visually reviewed | Newer than the previous work record. Fictional travel calculations and protected time are shown; no booking or hold. |
| Unknown calendar result | `40:144` plus `69:176`, visually reviewed | Lookup/reconciliation screen now branches to matched event, verified absence or still unknown. It is a design simulation, not a live calendar check. |
| Booked, message failed | `43:151`, visually reviewed | Correctly preserves the booked visit and distinguishes notification failure. |
| Confirmed and delivered | `44:292`, visually reviewed | Separate approval, event and receipt records are shown. Visual success treatment and fixture consistency needed correction. |
| Mobile and broader workspace | Existing mobile workspace frames and mobile Studio visible in the layer inventory | HVAC mobile companions and parity with the original nine-screen mobile pass are not verified as complete. |
| Desktop approval journey | Proposal → `60:164` approval → `62:171` execution → `69:176` lookup → `70:183` booked details / existing recovery | Core branches are represented and wired in the prototype. The full click-through should be repeated after final mobile work; no provider writes are implemented. |

## 11 October follow-up

The separate copy now also contains `v7 · Mobile HVAC office approval` (390 px) and a new `v7 · Mobile HVAC execution and result` draft (390 px, approximately 1,884 px tall). The mobile execution draft hides the desktop side rail and stacks its sections vertically. Its primary status remains “booking in progress / calendar result pending”; it does not imply the appointment was confirmed.

**Mobile execution is not finished.** At the editor zoom, several copied text blocks still look clipped inside their cards. I have not confirmed the mobile approval button routes to the mobile execution frame, nor that the preview actions land on mobile-specific outcomes. Therefore mobile parity and its click-through remain open. The Figma board reports screen-reader support disabled; no keyboard or screen-reader audit is claimed.

## Corrections saved

1. Feasible proposal action `44:232`: changed the inherited dental Connections destination to HVAC request review `27:134`; changed the visible label from **Review proposal** to **Review request**.
2. Booked/message-failed button associated with label layer `43:229`: selected its parent instance and replaced the inherited Connections destination with delivered outcome `44:292`. This previews fictional successful message delivery only.
3. Unknown-result action `40:222`: removed the unrelated Connections navigation. Note `40:264` now explicitly says calendar-result lookup is not wired and the original attempt must be resolved before retrying.
4. Confirmed-outcome action `44:350`: removed the unrelated Connections navigation. Note `44:412` explicitly identifies booked-visit details as unwired and the shown evidence/receipt as fictional.
5. Confirmed booking badge `44:375`: swapped the existing Calendar failed component for the existing Confirmed component, preserving the custom label.
6. Delivered message badge (text `44:392`, parent status instance): swapped Pending approval for Confirmed, preserving the custom delivery label.
7. Success explanation `44:388`: changed the error-text variable to the existing `text/primary` variable.
8. Proposal badge (text `44:237`, parent instance): swapped Calendar failed for Pending approval, preserving the no-booking/no-hold label.
9. Audit copy `44:410`: retained event `HVAC-DEMO-EVT-1042` and its original 09:43 confirmation after the message retry; approval 09:43 and receipt 09:47 are distinct records. Multiline formatting was corrected and visually verified.
10. Added flow **UK HVAC · Request, feasibility and recovery**, starting at `27:134`, with a description recording prototype scope and open work.

## Verification

- Clicked the corrected proposal action: `44:154` → `27:134`.
- Clicked Check feasibility: `27:134` → `27:272`.
- Clicked Retry message only: `43:151` → `44:292`.
- Reopened the successful prototype and visually confirmed green status components, the corrected audit reference/times, multiline formatting and the prototype-only note.
- Saved screenshot: `novaxis-figma-corrected-outcome.jpg`.
- Figma's MCP connector returned its Starter-plan call limit. Existing browser editor access was used for the corrections above; no quota-dependent extraction or alternate account was used. This was a scoped visual/interaction review, not a full automated accessibility or bounds audit.

## Remaining, in order

1. Complete the HVAC exact-payload approval and execution journey, including fresh-check/conflict and cancellation behavior. Do not simulate approval by silently jumping from proposal to confirmed.
2. Design and wire the calendar-result lookup branches: existing event found, no event verified, and still unknown. Give booked-visit details its own destination. Those current buttons remain illustrative and unwired.
3. Finish mobile execution card widths and wrapping, then wire and click mobile approval → execution → result lookup → booked details / unresolved outcome.
4. Add and verify HVAC mobile request, feasibility, recovery and outcome companions.
5. Finish the broader workspace mobile parity, component adoption and full accessibility/overflow review. Older dental reference navigation and layer names remain outside this scoped correction pass.
6. Implement the approved flow against verified API behavior, retaining tenant isolation, approval enforcement and separate booking/delivery outcomes. Travel-aware scheduling and live Google Calendar access are not proven by this Figma pass.

[Open the HVAC entry](https://www.figma.com/proto/KlfBnaMKECl18mVmwXplnP/Novaxis-Product-UX-v2?node-id=27-134&page-id=1%3A3128&starting-point-node-id=27%3A134&scaling=scale-down)
