# Novaxis UK HVAC service catalogue

Version 0.1 · 9 October 2026 · Product and research handoff

This is a prepared catalogue for business review. The accompanying JSON is a structured review artifact, not an import supported by the current application. No tenant has approved these profiles, prices, staffing or durations, and no live configuration has been changed.

## First offer

Start with enquiries for domestic heating faults, routine boiler servicing and replacement surveys in one business's declared service area. These correspond to the three existing application service codes. Recommend this bounded scope for the first pilot; heat pumps, landlord safety checks, commercial work and installation projects need their own enabled profiles and resource rules before taking bookings.

The assistant's job is to establish the requested visit, gather useful context and propose a feasible appointment. A fault assessment visit does not promise that the fault will be fixed during that visit. Installation work is not booked under a survey's duration. Urgent safety concerns leave the routine booking flow immediately.

## What the existing app actually contains

| Existing code | Current sample label | Sample minutes | Proposed customer label | Change needed |
|---|---|---:|---|---|
| `repair_visit` | Repair visit | 90 | Heating fault assessment | Identify the system and requested work; describe an assessment without guaranteeing a repair |
| `boiler_service` | Annual boiler service | 60 | Boiler service | Distinguish routine servicing from an active fault and a landlord safety check |
| `estimate` | Estimate visit | 45 | Heating replacement survey | Distinguish survey/quotation from installation |

These numbers come from the repository's HVAC manifest and demo seed. They are sample configuration values, not researched industry averages or approved timings for the first customer's business. The scheduler also supplies 60 minutes when a service is unknown or a duration is absent. That fallback must not qualify a booking as feasible.

The current intake maps no heating, no hot water, leak, noise and “other” to `repair_visit`. The first four are useful descriptions of a customer's problem, but they do not identify the system, work scope or engineer qualification. “Other” must open clarification or staff review rather than silently becoming a repair booking. [Current pack](https://github.com/srdataml-droid/multi-ai-platform-/blob/main/packages/packs/novaxis_packs/hvac/manifest.yaml), [scheduler](https://github.com/srdataml-droid/multi-ai-platform-/blob/main/packages/core/novaxis_core/scheduling.py).

## Minimum conversation

Reuse information already provided. Ask one useful question at a time; show staff the customer's own wording separately from the assistant's classification.

| Stage | Ask or establish | Why it matters |
|---|---|---|
| Requested help | “What would you like us to help with?” | Separate a fault, routine service, survey, safety check and existing job |
| System | “Is this a boiler, heat pump or another heating system? Do you know what it runs on?” | Determine which profile and competence checks apply; “not sure” is valid |
| Fault context, when relevant | “What is happening, and when did it start?” Then clarify whether heating, hot water or both are affected | Record symptoms without diagnosing the cause |
| Immediate concern | Apply the business's approved safety and urgent-support policy whenever the message warrants it | Safety and urgency can change mid-conversation; never wait for a form to finish |
| Area | Property postcode and domestic/commercial context | Check the declared service area and work scope before requesting detailed location |
| Booking details | Name, permitted contact method, confirmed service address, access constraints and preferred window | Support communication, reliable routing and access |
| Commercial scope | Show the business's approved call-out/service fee and inclusions; record acceptance where required | Prevent an unknown quote or customer expectation from becoming a booking promise |

Brand/model, age, a visible error code and previous work reference are optional unless the business's specific service profile needs them. Never ask the customer to dismantle equipment, reset a potentially unsafe system or perform diagnostic work to complete intake. For cold-related support, record the minimum necessary support/urgency flag and callback preference, rather than collecting a medical history.

An enquiry is not automatically rejected because a tenant cannot authorise paid work. Capture who can authorise the work and route a callback when necessary. Safety escalation proceeds independently of payment or purchasing authority.

## Pilot profiles

### Heating fault assessment — `repair_visit`

Use for a reported heating/hot-water fault only after identifying enough system context to select an enabled business scope. Ask about the symptom, when it started, what equipment is involved, fuel if known and any access restrictions. Record a visible error code only if already safely available. If the system or fuel remains unknown, staff review determines the work and resource requirements before a slot is promised.

Book an assessment scope approved by the business. The engineer decides the diagnosis, remedial work, parts and any return visit. Duration, crew size and competence requirements come from that assessment profile or a documented job-specific staff estimate. Gas work must match the engineer's current registration and qualifications for the actual work; a generic “engineer available” label is insufficient. [HSE engineer verification](https://www.hse.gov.uk/gas/gas-safe-register-check.htm), [HSE qualification/card guidance](https://www.hse.gov.uk/pubns/indg285.pdf).

Do not imply that the 90-minute demo value guarantees a repair. If the customer describes something outside the enabled heating scope, use clarification or a staff callback.

### Boiler service — `boiler_service`

Establish that the customer wants routine servicing, which boiler/fuel is involved, the number of appliances covered by the request and whether there is an active fault. Brand/model and previous service information are useful when known. A reported fault needs an explicit scope decision; do not hide it inside a routine service duration.

The business approves servicing scope, manufacturer-related requirements, resource requirements, pricing and duration. A landlord gas safety check is a separate service unless an explicitly defined combined visit covers both scopes. HSE distinguishes maintenance/service work from the annual safety check; one must not be assumed to fulfil the other. [HSE landlord guidance](https://www.hse.gov.uk/pubns/indg285.pdf).

### Heating replacement survey — `estimate`

Establish what the customer wants replaced or assessed, the existing system, property type, access and whether the request is only for a survey/quotation. Avoid gathering an extensive technical design brief before a human survey is needed.

Book the approved survey scope. Do not offer an installation appointment or promise a completed quotation, fixed price, savings or grant eligibility. Resource requirements depend on what the survey actually includes: observation and sales discussion do not automatically mean gas work, while physical gas work still needs the appropriate qualified resource.

## Separately enabled services

| Profile | Added intake and requirements | Activation rule |
|---|---|---|
| Landlord gas safety check | Property, requester/authoriser, applicable appliances/count, access arrangements and requested record delivery; qualified engineer for the actual appliance/fuel scope | Disabled until the business defines the service, duration and record workflow; servicing is not substituted |
| Heat pump service | System type, brand/model if known, requested maintenance vs active fault, access and business competence requirements | Disabled until a separate profile is reviewed; do not inherit the gas boiler profile |
| Return/remedial visit | Linked job, engineer-approved work scope, required parts readiness, crew and job-specific estimate | Disabled until the previous job's approved work plan exists; no default duration |

MCS installer selection is relevant to heat-pump installation and schemes described by GOV.UK. It is not a universal qualification rule for every heat-pump maintenance task. Requirements must match the work. [GOV.UK installer guidance](https://www.gov.uk/guidance/find-a-heat-pump-installer).

HSE sources here cover Great Britain. The tenant's nation and service area must be recorded, and Northern Ireland requirements and emergency instructions separately checked before enabling that jurisdiction. A UK target market does not establish one identical operational policy across all nations and fuel types.

## Duration evidence and approval

No approved duration is invented in this catalogue. All three demo values are retained in a clearly labelled reference field, with approved planning minutes left empty.

| Evidence state | Permitted behavior |
|---|---|
| Missing or demo value only | Gather the enquiry and request a staff estimate; no feasible-slot claim or confirmation |
| Job-specific staff estimate | Record the scope, minutes, author, time and validity; proceed only when all resource/travel/availability checks also pass |
| Business-approved profile | Use its version, applicability and planning minutes; reject a mismatch or expired profile |
| Comparable completed-job evidence | Record sample definition/count, source period, duration distribution and business-selected planning rule; business approves use before activation |

Measure on-site assessment/work separately from travel, access/setup allowance, breaks and follow-up administration. Record arrival/work start/work end/departure consistently. Preserve overruns, failed access and return visits as labelled outcomes; do not quietly remove difficult jobs to make timings look reliable. Learning changes a proposed profile version, never a live approved duration silently.

For a job, store requested visit scope; profile/version or staff-estimate reference; planning minutes; uncertainty/range when available; author/source time; applicability constraints; approved crew/skills; and the business's review conditions. Unknowns remain unknown. A duration range must not be manufactured from a single demo number.

## When a proposed appointment is feasible

Require a confirmed service address, enough equipment/work context, an approved applicable duration, a qualified available resource/crew, current calendar data, route estimates for both adjacent legs, working-time rules and any required parts/access readiness. Travel is additional to the visit duration. A postcode centroid is insufficient for a final property route.

Before the visit: previous job finish plus travel and business-approved allowance must fit before its start. After the visit: its finish plus onward travel and allowance must fit before the next commitment. For first/last jobs, apply the business's approved start/end location and shift policy. Check breaks, leave and closures across travel as well as on-site time. Display the sources and when they were checked; recheck before holding/confirming.

A free gap alone is not a feasible appointment. A regional bank holiday is information for the business's closure policy, not an automatic closure rule. Manual staff approval cannot waive an unknown qualification or a failed availability check.

## Customer quality and profitability

Evaluate operational fit using supported service, service area, scheduling/access feasibility, authority to commission work and acceptance of the actual approved commercial terms. Missing information means clarification, not “bad client.” Keep urgent support separate from commercial prioritisation.

Once enabled, measure booked visits per qualified enquiry, staff minutes per enquiry, repeat contact, missed appointments, completed-job duration/overrun, return visits, delivery cost and contribution after support. Pricing in the earlier sales kit is a hypothesis for validation, not a price written into this catalogue. No invented lead score or arbitrary lifetime-value estimate selects who receives urgent help.

## Business review checklist

Before activating even one profile, the founder and the HVAC business fill in:

1. Nation, declared area, supported systems/fuels and excluded work.
2. Exact visit scope and customer-facing inclusions/exclusions.
3. Planning minutes, evidence source, author and review conditions.
4. Engineer competence verification, crew requirements and expiry handling.
5. Approved price or quotation/callback policy.
6. Shifts, rest, leave, closures, start/end locations and routing allowances.
7. Approved urgency/safety instructions, escalation contact and fallback ownership.
8. Availability freshness rules, confirmation policy and reliable delivery checks.

The draft preparation and source distinctions are complete. Practitioner/business approval and runtime integration remain open. The concrete next handoff is [booking UX](UK-HVAC-booking-UX-handoff.md), with [structured catalogue](UK-HVAC-service-catalogue.json) and [review scenarios](UK-HVAC-booking-scenarios.json).
