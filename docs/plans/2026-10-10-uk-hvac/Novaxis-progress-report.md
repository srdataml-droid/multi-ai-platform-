# Everything worked on in this chat

Updated 10 October 2026 · Novaxis / Multi AI Platform · UK HVAC first

## Current position

The product direction, market research, source review, pilot sales preparation, operational assistant requirements and draft service catalogue are prepared. A reusable HVAC operating skill is created, installed and validated. Figma access and its screen inventory have been checked. One new editable UK HVAC booking-recovery draft has now been created in your existing Figma file and visually checked. The complete Figma journey and live application implementation remain unfinished.
 github
“Prepared” means there is a saved deliverable to use. “Reviewed” means existing source or design inventory was inspected. “Validated” refers to the specific file/skill checks described below, rather than proof that the deployed product works.

## 1. Located the existing product

- Identified the [Multi AI Platform GitHub repository](https://github.com/srdataml-droid/multi-ai-platform-) using earlier chat context, and copied its public source locally for review.
- Opened your [Novaxis Product UX v2 Figma file](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/).
- Identified the reference and refined-experience pages. Inventoried nine workspace screens, five mobile screens, a customer widget, booking storyboard, backend recovery workflow, state matrix and seven reusable specimens.
- Also found seven additional v2 frames covering model/behavior, assistant playground, website installation, booking confirmation/recovery, mobile Assistant Studio and restore-template confirmation.
- Identified the refined workspace approval frame as node `1:5545`; this turn established that it is hidden. The visible v2 booking recovery frame `8:1299` was inspected and used as the source for the new HVAC draft. Remaining screens, interactions and implementation parity require further review.

The browser has intermittently timed out. A file opening successfully does not prove that its designs have been finished or that the live app has been tested. The source checkout remains unchanged.

## 2. Arranged roles and tasks

Established your requested sequence: product strategy/research → UX → UI/design system and observability → software engineering → AI engineering → integrations → QA. Each task has an accountable discipline, concrete output and completion evidence.

The working manifesto is to design around business outcomes, show human/assistant control, separate proposed actions from completed actions, explain failures and give staff a useful recovery path. UK HVAC is the first market; other industries use the shared product with their own operational rules later.

Deliverable: [work plan and manifesto](Novaxis-work-plan.md).

## 3. Researched the market, distribution and profit

Reviewed competing reception/booking products and their documented offerings, including Jobber, Smith.ai, Goodcall, Housecall Pro and ServiceTitan. The resulting positioning focuses on a bounded operational problem for small UK heating/HVAC businesses, rather than assuming that a general multi-industry assistant is unique.

Prepared founder-led discovery, bounded pilots, partner distribution and later integration/content routes. Identified the need to verify actual unmet demand, existing customer software and willingness to pay before expanding acquisition.

Prepared pricing experiments and an illustrative contribution model. A £249/month example leaves £161 contribution under the assumed standard delivery costs, but only £21 under the assumed high-support case. Those are hypothetical calculations, not measured profit. Communications usage, recurring support and partner fees need to be reflected in real pricing.

Researched UK outreach requirements and channel constraints; no prospect campaign or customer outreach was sent. The research is dated and sourced in the document; vendor prices and campaign rules need checking before an actual purchase or campaign.

Deliverable: [market, distribution and profit strategy](Novaxis-market-and-profit-strategy.md).

## 4. Reviewed the app and prepared sales material

Inspected source for intake, inbox, approvals, scheduling, setup, billing, navigation and the action gate. Defined the needs of the owner, office dispatcher, engineer, customer and Novaxis operator.

Prepared a bounded managed text-enquiry offer, qualification criteria, buyer discovery questions, a five-minute demo script, talking points, objections and prioritised app/Figma work. Voice answering is outside that proposed first offer until separately built and verified.

Found approval-policy wording that needs reconciliation: some documentation/prompts imply every job waits for office approval, while the reviewed gate allows configured low-risk actions and rejects high-risk actions. The implementation policy and customer wording need one consistent definition.

Deliverable: [app requirements and pilot sales kit](UK-HVAC-app-and-sales-kit.md).

## 5. Planned the assistant you described

Specified problem-dependent intake, business-approved visit lengths, precise service addresses, routing before and after visits, engineer skills/crew, breaks, leave, events, closures and clear customer communication.

Defined client quality as operational fit: supported work, service area, feasible timing, access, authority and understood commercial terms. Urgent support remains separate from commercial ranking.

Planned permissioned read-only sheet/knowledge imports with field authority, provenance, freshness and conflicts. Prepared controlled service follow-up and outbound requirements; the existing first-contact gate remains a boundary to resolve before any autonomous acquisition workflow.

Recommended starting with a hosted model API plus owned business rules, knowledge, tools and evaluations. An existing small model can be benchmarked later; fine-tuning requires evidence that it improves a narrow task. No model was trained, benchmarked or deployed here. No new server or paid hosting account was created.

Reviewed low-cost resources and production limitations for models, routing, holidays and hosting. Ownership, privacy and accuracy depend on the whole system, not just where model weights run.

Deliverable: [operational assistant and model/infrastructure plan](Novaxis-operational-assistant-plan.md).

## 6. Created and installed the HVAC operating skill

Created `novaxis-hvac-operations`, with guidance for classification, uncertainty, duration evidence, route/resource feasibility, protected time, connected data, commercial fit, escalation and truthful outcomes.

Created a companion booking contract covering inputs, constraints, source freshness, holds, confirmation and recovery. Installed the skill in Codex's discoverable skill folder. Skill validation passed, and its installed main file matches the saved deliverable by checksum.

This is usable guidance for Codex. It is not automatically an installed feature in the Novaxis application runtime.

Deliverables: [skill](skills/novaxis-hvac-operations/SKILL.md) and [booking contract](skills/novaxis-hvac-operations/references/booking-contract.md).

## 7. Prepared the UK HVAC service catalogue

Preserved the three existing HVAC pack codes while defining clearer scopes:

| Code | Prepared scope |
|---|---|
| `repair_visit` | Heating fault assessment; no guarantee of same-visit repair |
| `boiler_service` | Routine boiler servicing; active faults and safety checks need explicit scope decisions |
| `estimate` | Heating replacement survey; installation is planned separately |

Prepared three separately enabled extensions: landlord gas safety check, heat pump service and return/remedial visit. Defined intake questions, competence/resource requirements, duration evidence and activation conditions for all six draft profiles.

Corrected the earlier impression that everything already uses one hour: the existing pack has 90/60/45-minute sample values. The issues are that unknown services/durations fall back to 60 minutes, and “other” becomes a repair visit automatically. These findings come from source inspection; they have not been patched in the application.

The catalogue keeps approved durations, actual fees, crew/qualification rules and tenant policy empty until a business provides the evidence. Every prepared profile remains a disabled draft. The JSON is a review/handoff format, not a supported live import.

Deliverables: [readable catalogue](UK-HVAC-service-catalogue.md) and [structured catalogue](UK-HVAC-service-catalogue.json).

## 8. Prepared booking UX and review scenarios

Specified what request details, approvals, schedule, settings/onboarding, connections, customer widget, mobile review and action history must show. Defined missing-estimate, uncertain-address, unverified-engineer, travel-conflict, stale-source, expired-hold, takeover and partial-failure states.

Prepared 19 synthetic review scenarios covering those states, including incoming/onward travel, travel overlapping breaks, leave, servicing vs safety checks, survey vs installation, provider uncertainty and a booked visit whose message failed.

Checks passed for JSON syntax/duplicate keys, unique codes and scenario IDs, referenced intake/evidence fields, local document links, preserved sample values, empty unapproved timings and consistent travel/break arithmetic. These are artifact checks; the scenarios have not been executed against the application or real providers.

Deliverables: [booking UX handoff](UK-HVAC-booking-UX-handoff.md) and [19 review scenarios](UK-HVAC-booking-scenarios.json).

## 9. Created a new editable HVAC Figma draft — 10 October

Primary role: senior UX/observability designer. Created [v3 · UK HVAC booking recovery](https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/?node-id=24-130) on the refined-experience page, by duplicating the existing visible booking-recovery frame. The original dental example is retained. The new 1440 × 1000 frame uses the existing editable layers, auto-layout, component instances and Novaxis text/colour styles.

Updated 25 text fields/overrides and read each change back from its selected Figma layer. The full frame was visually inspected for wrapping and layout. It now shows:

- A fictional UK HVAC workspace and heating-fault enquiry.
- Visit length needing an estimate and engineer assignment still outstanding.
- A customer preference rather than a booked slot or a fabricated visit length.
- An unconfirmed status, disconnected calendar and no recorded booking result.
- A customer response marked as an unsent draft.
- A recovery timeline and instructions to reconcile any booking result, then check the estimate, qualified engineer, incoming/onward travel, breaks and leave.
- An explicit design-only label, with no claim of a live booking or sent customer message.

Deliverables: [screen preview](UK-HVAC-Figma-recovery-preview.jpg), [verified text change record](UK-HVAC-Figma-edits.json) and [design handoff note](UK-HVAC-Figma-recovery-handoff.md).

This completes one draft recovery screen, not the full HVAC product design. Route/resource details, request intake, remaining desktop/mobile states and prototype navigation remain open. Keyboard/accessibility and responsive behavior are not verified. The browser timed out during the final reload check, so persistence after reloading could not be independently rechecked; the edits were read back and visually verified in the active Figma document before that attempt.

## Work continuing next

Primary role: senior UX/observability designer. Extend request review and the engineer/travel feasibility view, then connect the confirmed, partial-failure and recovery states across desktop and mobile. Verify each change in the file and record exact frame links. Business-specific timings are not needed to design an honest “estimate required” state.

After that: implement the agreed screens and booking constraints, verify the calendar/message boundaries, compare model performance and run a measured pilot. A working end-to-end booking, Figma completion, live channel integrations, customer validation, revenue, outbound campaigns and model training remain open deliverables.
