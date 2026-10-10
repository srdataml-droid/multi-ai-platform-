# Novaxis HVAC design continuation

Date: 11 October 2026

## What was studied

Read Figma AI's continuation report in the original file and inspected its mobile frame inventory. All nine workspace mobile frames are present. The newly added Assistant Studio, Connections, Settings and Onboarding frames are visible on the canvas. The inspected Studio layout uses sections for operating rules, permitted tools, approval boundaries and confirmation/retry handling.

Figma AI reports replacing 116 elements with component instances, improving secondary text contrast, fixing a setup date and reviewing bounds and contrast. Those counts and automated review results were not independently reproduced in this pass. Prototype wiring and live integrations are still explicitly unfinished in the original file. Its private agent implementation is not available; the method below is inferred from its visible work and report.

## Working method adopted

| Responsibility | Required output |
|---|---|
| Lead UX designer | A named customer task, readable hierarchy, explicit unknowns and next owner |
| Design-system designer | Existing component instances, consistent spacing and semantic status treatments |
| Interaction designer | Correct destinations; click through the whole journey after saving |
| Responsive designer | Desktop and mobile companions, including long content and failure states |
| UX writer | Distinguish requests, proposals, approval, provider confirmation and delivered messages |
| Quality reviewer | Read back edits, reopen saved frames, inspect layouts and document unfinished work |

For each journey: inventory gaps → refine content and states → reuse components → add responsive layouts → wire interactions → inspect and click through → record evidence. Do not describe a static design or a navigation prototype as a functioning integration.

## Changes completed in the separate working file

File: [Novaxis — Product UX v2](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/Novaxis-Product-UX-v2?node-id=27-272)

The original Figma AI file was not edited.

### Request review — 27:134

The existing draft separates the customer's reported heating problem from a diagnosis, and visibly leaves address, customer authority, access, scope, duration and engineer assignment unresolved. It identifies the office as owner and the customer response as an unsent draft.

### Visit feasibility — 27:272

Completed the draft's content and reopened the frame to confirm saved content:

- Approved visit length: the generic 60-minute fallback is not evidence for this job.
- Engineer qualification, crew size and equipment.
- Incoming travel from the preceding job.
- Onward travel to the next job or return, including protected finish time.
- Calendar freshness and provider confirmation.
- Business and engineer hours, breaks, leave, access, parts and approved buffers.
- Unknown travel is not zero travel; missing evidence keeps the request with the office.
- A customer preference does not reserve a slot.
- Approval, calendar confirmation and customer delivery remain separate outcomes.

The screen reuses the existing button and status instances and auto-layout card structure. It is not a complete migration of every repeated element in the file.

### Prototype corrections

| Control | Source | Destination |
|---|---|---|
| Check feasibility | 27:212 | 27:272 |
| Review recovery from request | 27:253 | 24:130 |
| Review recovery from feasibility | 27:350 | 24:130 |
| Back to request from feasibility | 27:391 | 27:134 |
| Back to request from recovery | 24:249 | 27:134 |

All five controls were clicked in presentation mode and their resulting frame URLs checked. The request → feasibility → recovery → request loop completed. The recovery return previously led to the generic approval screen; it now returns to the HVAC request.

## Evidence and limits

- Text edits were confirmed by selecting each changed text layer and reading its copied content.
- The completed feasibility frame was reopened and reviewed visually.
- Presentation review covered the top and bottom of request, feasibility and recovery layouts. No obvious overlap or cropped text was observed in those views; this is not an automated bounds or accessibility audit.
- PNG export was attempted through Figma's export control, but no download was returned before the timeout. No new exported image is claimed.
- These changes are saved Figma designs and navigation interactions. No app implementation, deployment, calendar event or customer message was performed.

## Remaining work, in order

1. Add mobile request-review, feasibility and recovery companions and audit their navigation separately.
2. Add UK HVAC confirmed, provider-result-unknown and booked-but-message-failed states on desktop and mobile. Keep each outcome's next action distinct.
3. Bring the separate copy's broader mobile coverage up to the original's newer nine-screen pass, preserving existing refinements.
4. Audit component adoption across the whole copy, then verify secondary-text contrast, overflow, content dates and timezone consistency with recorded evidence.
5. Extend prototype wiring to the remaining secondary and mobile controls; document illustrative controls explicitly.
6. Implement approved designs only against verified server behavior.

## 11 October continuation

Added `v7 · Mobile HVAC execution and result` (`86:194`) as a separate 390 px-wide draft, derived from the desktop execution state. It hides the desktop navigation rail, stacks the execution sections vertically, and constrains the heading, outcome column, and detail cards to mobile widths. The frame contains the approved visit awaiting calendar result, execution history, the paused customer message, and the two preview outcomes. It is a long mobile canvas (about 1,884 px tall), so treat it as a scrollable design, not a single-screen dashboard.

This is not yet a verified mobile flow: after resizing, the selected frame still showed truncated heading/body copy, so wrapping and overflow need another pass; no prototype link from mobile approval to this mobile execution frame has been confirmed, and the copied outcome controls may still lead to desktop states. The frame exists in Figma but should not be called complete until each card's text wraps cleanly and the mobile destinations are clicked through. Keyboard and screen-reader behavior cannot be proven in the Figma canvas (Figma reports board screen-reader support disabled). The Figma connector export was blocked by its Starter-plan call limit, so this continuation relies on the live editor view; no new screenshot export is claimed.

[Open the HVAC prototype](https://www.figma.com/proto/KlfBnaMKECl18mVmwXplnP/Novaxis-Product-UX-v2?page-id=1%3A3128&node-id=27-134&starting-point-node-id=27%3A134&scaling=scale-down-width)
