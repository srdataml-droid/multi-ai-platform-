# Novaxis work plan and first product review

Updated 10 October 2026. Scope: complete the unfinished Figma product experience, then implement and verify it through software engineering, AI engineering and integrations. Each task has one primary role; work stays in that role until the task's deliverable is checked.

## Verified starting point

- GitHub: https://github.com/srdataml-droid/multi-ai-platform-
- Figma: https://www.figma.com/design/KlfBnaMKECl18mVmwXplnP/
- Figma has reference and refined-experience pages. The refined page contains nine workspace screens, five mobile screens, a customer chat widget, booking recovery storyboard, backend approval/retry workflow, a contextual state matrix and seven reusable UI specimens.
- The inventory is verified through the Figma interface. Individual screens, prototype behavior, accessibility and implementation parity remain unverified. Browser actions intermittently time out.

## Task order

| Order | Role | Work | Completion evidence | Status |
|---|---|---|---|---|
| 1 | Senior product strategist and researcher | Reconcile product rules; define users, tasks, outcomes and screen requirements; establish the manifesto and scope | Product brief, decision register and acceptance criteria | Desk research, pilot preparation and draft catalogue complete; customer validation and policy resolution open |
| 2 | Senior UX designer | Complete desktop and mobile journeys across inbox, approvals, schedule, customers, studio, connections, settings, onboarding, automation and analytics | Complete Figma flows, including empty, loading, error, permission and recovery states | Active role; one editable HVAC recovery draft visually checked; remaining flows pending |
| 3 | Senior UI and design-system designer | Complete typography, spacing, semantic statuses, components, responsive layouts and accessible interaction specifications | Reusable components and consistent Figma screens | Existing styles reused for HVAC draft; full review pending |
| 4 | Senior observability designer | Design action history, explanations, ownership, failures, integration health, recovery and outcome reporting alongside the UX/UI work | Figma views showing what happened, why, who controls it and the next action; event specification | Recovery timeline and unconfirmed/unsent states drafted in Figma; remaining views pending |
| 5 | Senior software engineer | Translate completed design into the dashboard, API and data flows in coherent changes | Working product flows, preserved tenant boundaries and approval enforcement | Pending |
| 6 | Senior AI engineer | Build and evaluate context, intake, tool proposals, risk classification, handoff, response quality and latency | Evaluations proving expected and forbidden behavior | Pending |
| 7 | Senior integration engineer | Verify channel delivery, calendar operations, booking handoffs, credentials, reconnects and safe retries | Verified provider flows and recovery from partial failures | Pending |
| 8 | Senior QA engineer | Verify complete journeys, accessibility, permissions, conflicts, failures, retries and takeover | End-to-end evidence and remaining-issue register | Pending |

These titles identify the professional discipline and review standard used for each task. The same assistant performs the roles sequentially. UX, UI and observability belong to the Figma completion phase; engineering follows, with QA criteria defined early and verified throughout. The existing Figma is unfinished work to extend. A visible frame does not prove a feature is complete. The [progress report](Novaxis-progress-report.md) records all saved deliverables and distinguishes completed preparation from remaining implementation.

## Role discipline for each task

Before starting, name the active role, the task, its inputs, the concrete output and the completion check. Remain focused on that task until the output is checked or a specific dependency is recorded. Record findings and decisions so the next role receives a usable handoff. Finish with what changed, evidence, open issues and the next task. Avoid switching disciplines merely to report progress.

## Active task

Role: senior UX/observability designer. Current task: extend the HVAC request and feasibility journey following the first recovery draft. See the completed draft and remaining acceptance checks in [UK-HVAC-Figma-recovery-handoff.md](UK-HVAC-Figma-recovery-handoff.md).

Desk research on market, distribution, builders and contribution economics is completed in [Novaxis-market-and-profit-strategy.md](Novaxis-market-and-profit-strategy.md). It recommends testing one UK heating/HVAC segment, assisted pilots, measured outcome attribution and bounded delivery costs. Customer validation, detailed Figma audit and approval-policy resolution remain open; product-market fit is not established.

The preceding product task established initial booking requirements using repository rules, architecture, the Figma inventory and researched human-AI/accessibility guidance. The saved catalogue and UX handoff now support concrete design work. Approval-policy reconciliation remains an open product decision; full per-workflow acceptance criteria and customer validation remain incomplete.

## First review: approval rules need reconciliation

CLAUDE.md says medium and high risk actions require an approved approval row, and broadly puts booking changes and health-related actions behind approval. ARCHITECTURE.md describes low-risk automatic actions, medium-risk review, and high-risk refusal; appointment confirmation may become low risk when enabled for a service. These documents need one explicit policy table before UI or executors are changed. This is a documented inconsistency, not yet a verified code defect.

Proposed acceptance criteria for that policy:

1. Each action shows whether it is automatic, needs review, or is blocked, with a reason understandable to staff.
2. Approval shows the exact recipient, action and proposed details. Edits invalidate stale approval when the approved payload changes.
3. Approval, execution and customer notification are distinct states. A booking is never presented as confirmed before the calendar write succeeds.
4. Calendar conflicts return to selecting another slot. Expired holds cannot silently become confirmed bookings.
5. Retries cannot create duplicate appointments or duplicate notifications. Partial success remains visible and recoverable.
6. Taking over stops automated replies; handing back makes the current context and control state clear.
7. The final policy reconciles opt-outs, emergencies, safeguarding, booking changes and tenant overrides without weakening mandatory protections.

These are proposed review requirements; implementation behavior still needs inspection.

## Draft working manifesto

Design around the business task and its outcome. Make human and assistant control visible. Show proposals, approvals and completed actions separately. Give every failure a clear next step. Reuse the core experience across industries while adapting vocabulary and intake. Judge progress by working flows and evidence, rather than screen count. Inspect existing work before extending it.

## Research applied to the review

- Microsoft Human-AI Interaction Guidelines: clarify capabilities and limitations; support correction and dismissal; explain behavior; convey consequences; provide global controls. Applied here to approval details, takeover, assistant settings and recovery. https://www.microsoft.com/en-us/research/?p=564561
- WCAG 2.2: use AA as the review target. Check keyboard operation, visible and unobscured focus, contrast, labels, error identification, status announcements, reflow and target size. Figma inspection alone cannot establish conformance. https://www.w3.org/TR/WCAG22/
- Repository standing rules: small coherent changes, tenant isolation, approval enforcement, protected credentials and verified completion. https://github.com/srdataml-droid/multi-ai-platform-/blob/main/CLAUDE.md
- Product architecture: shared industry packs, scheduling, takeover, action states and recovery. https://github.com/srdataml-droid/multi-ai-platform-/blob/main/docs/ARCHITECTURE.md

## Next concrete task

The founder expanded the assistant requirements to include service-specific duration evidence, property/route understanding, engineer skills, travel before and after visits, rest, leave, events, connected sheets, lead qualification and controlled outbound assistance. UK HVAC remains the initial market. See [Novaxis-operational-assistant-plan.md](Novaxis-operational-assistant-plan.md) for the architecture/model decision and execution order, and [skills/novaxis-hvac-operations/SKILL.md](skills/novaxis-hvac-operations/SKILL.md) for the created operating skill.

Source review found configurable service durations, protected times and generic buffers already implemented. The HVAC pack's demo values are 90 minutes for a repair visit, 60 for a boiler service and 45 for an estimate. They are sample configuration, not business-approved duration evidence. Silent 60-minute fallback, automatic classification of “other” as a repair visit, resource assignment and routing remain important gaps. Resolve prompt/gate policy wording before live demonstrations. Skill syntax was validated; application behavior has not been changed by the planning work.

## Service catalogue preparation completed — 9 October 2026

Primary role: senior product strategist and researcher. Prepared [UK-HVAC-service-catalogue.md](UK-HVAC-service-catalogue.md), a [structured review catalogue](UK-HVAC-service-catalogue.json), [booking UX handoff](UK-HVAC-booking-UX-handoff.md) and [19 synthetic acceptance scenarios](UK-HVAC-booking-scenarios.json).

The catalogue preserves the three existing HVAC pack codes while clarifying fault assessment, boiler service and replacement survey scope. It defines intake, uncertainty, duration evidence, resource checks, commercial fit and separately reviewed service extensions. Approved durations, prices, crew/skills and tenant rules remain explicitly empty until supplied by a business. The structured format is not currently a supported runtime import. Preparation is complete; business/practitioner approval and application integration remain open.

Figma's refined-experience page was reopened and its layer inventory checked. It also contains seven additional v2 frames: restore-template confirmation, mobile Assistant Studio, booking recovery, booking confirmed, website installation, assistant playground, and model/behavior. These are inventory observations; their content and behavior are not yet audited. Selecting individual frames is intermittently failing through browser controls. No Figma content was edited during catalogue preparation.

Validation passed for both JSON artifacts: no duplicate keys/codes, all referenced intake fields/evidence and local handoff links resolve, the original demo values are preserved, unapproved durations remain empty, and the synthetic travel/break examples are internally consistent. These checks validate the artifacts only; no application/provider behavior was tested.

Next primary role: senior UX/observability designer. Extend and verify the existing refined request, approval, schedule, setup, widget and recovery frames against the supplied handoff/scenarios. The existing refined approval frame was selected and identified as node `1:5545`; its content remains unaudited. Browser controls intermittently time out or complete after a delay. Associate remaining actual frame IDs and prototype paths with the acceptance checks. Travel-aware booking remains an implementation requirement, not a verified live feature.
