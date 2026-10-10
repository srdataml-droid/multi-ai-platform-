# Novaxis: market, distribution and profit strategy

Research date: 9 October 2026. Active role: product strategist and researcher. This is a desk-research recommendation based on the public repository, Figma inventory and current primary sources. No customer interviews, live production audit or actual tenant cost data were available. Recommendations and prices below are hypotheses to test, not established product-market fit.

## Recommendation

Start with a managed enquiry-to-booking service for small UK heating/HVAC contractors, provisionally those with 2–15 staff, existing incoming enquiries and no satisfactory intake automation. Sell timely qualification, reliable booking handoff and evidence of commercial outcomes. Keep the shared core, but concentrate acquisition, onboarding and initial integration on one segment.

UK is the repository's stated initial region, not a preference inferred from the founder's location. The exact city and segment should follow accessible prospects and interviews. Do not spend heavily on expansion before the first segment renews at a price that covers delivery.

Positioning hypothesis: “Novaxis turns incoming enquiries into qualified booking requests, keeps your office in control, and shows which requests became completed jobs.” This is a proposed offer. Job completion and revenue attribution still require reliable business-system data or staff confirmation.

The present text-channel product can sell enquiry handling, intake and booking assistance. It cannot honestly sell full phone answering until voice is built and verified. If discovery shows that telephone calls dominate the lost-demand problem, run a bounded voice-provider feasibility task before further text-only feature expansion. Missed-call text-back also needs a verified missed-call event integration; SMS capability alone does not provide it.

## What the evidence changes

| Evidence | Strategic implication |
|---|---|
| Jobber provides 24/7 call/text reception and booking. Its eligible-plan add-on is $29/month for 30 conversations, then $0.79 each; Plus includes unlimited usage. These are add-on prices, not the total Jobber subscription. | A generic receptionist offer has strong bundled competition. Qualify existing automation before selling. |
| Smith.ai publishes an AI Pro entry of $150/month for 75 calls, with setup support and scheduling. | Buyers can compare Novaxis with an established managed-support offer. Demonstrate workflow value rather than merely model capability. |
| Goodcall's pricing page starts at $79/month for 100 unique customers. Its FAQ and pricing page disagree on higher-tier allowances and prices. | Predictable customer-based billing is a useful pattern; higher-tier figures should be confirmed before use. |
| Housecall Pro documents CSR AI answering calls and using configured service information. | Service knowledge, scheduling and integration are expected product capabilities. |
| ServiceTitan offers configurable voice agents, direct booking and unified multi-account contact-center workflows; its documentation describes early-access/account requirements. | Human control, multi-account operation and existing-software compatibility are not automatically exclusive advantages. |

Sources: [Jobber](https://help.getjobber.com/en/articles/receptionistpowered-by-jobber-ai/), [Smith.ai](https://smith.ai/pricing/ai-receptionist), [Goodcall pricing](https://www.goodcall.com/pricing), [Goodcall FAQ](https://www.goodcall.com/faq), [Housecall Pro](https://help.housecallpro.com/en/articles/12001958-csr-ai-best-practices-and-faqs), [ServiceTitan](https://help.servicetitan.com/docs/configure-your-voice-agent-settings).

These vendors establish competing supply, not independent proof of demand, willingness to pay or the size of Novaxis's obtainable market. The repository's claim that competitors are single-vertical is too broad: Goodcall and Smith.ai serve varied businesses. Treat one core across industries as an internal development-efficiency hypothesis rather than a customer-facing moat.

## Segment choice

| Segment | Reason to consider | Main obstacle | Recommendation |
|---|---|---|---|
| Small UK heating/HVAC contractors | Matches existing intake pack; a specific qualification and booking workflow can be demonstrated | Native incumbents, telephone-heavy enquiries, dispatch complexity | Initial discovery and pilot candidate |
| Restoration contractors | Existing photos, inspection and claim-document flows could support a focused follow-up offer | Emergency escalation, operational accountability, difficult integrations | Second discovery track after first-segment evidence; underserved status remains unverified |
| Dental practices | Repeat appointments, reminders and structured intake align with the product | Sensitive data, specialist systems, established competition | Defer commercial expansion until privacy controls and a suitable integration are validated |

Do not interpret this table as a measured market ranking. A reachable restoration buyer with a funded problem can outweigh the provisional HVAC choice. Choose from evidence, not software already written.

## Product adjustments, in priority order

1. **Make the first use case explicit.** Start with one service category, one customer journey and one compatible booking system. Keep other packs available internally without equal marketing investment.
2. **Measure outcomes through the whole funnel.** Distinguish received enquiry, qualified request, proposed booking, approved request, calendar confirmation, job completion and payment. Attribute an outcome only when source evidence exists. Track response time, staff effort and lost/failed cases alongside conversions.
3. **Reduce review friction.** Retain mandatory protections, but reconcile the contradictory approval documents and define when routine actions may run automatically. Make booking approvals mobile-friendly. Show stale slots, deadlines and the exact proposed action. A review queue that nobody handles cannot be the product's promise.
4. **Make integrations match operational reality.** Google Calendar can support a pilot; it may not represent technician skills, geography, duration or dispatch capacity. Label a CSV/email ticket as a booking request until accepted into the real system. Pick the next native adapter from pilot usage.
5. **Replace complex setup with guided configuration.** Collect services, service area, hours, booking rules, contact/escalation routes and examples. Test before activation. Offer assisted onboarding first and standardize it as patterns repeat.
6. **Design observability in Figma now.** Every conversation should expose control ownership, action status, failed delivery, integration health and next recovery step. Provide an office view and an internal operator view. Monitor overhead and support minutes per tenant, not only AI accuracy.
7. **Move advanced Assistant Studio behind business settings.** Put task-focused controls such as services, knowledge and booking rules first. Offer prompt/tool internals only where an advanced operator benefits.
8. **Bound usage and support.** Include a defined allowance, cost alerts, support scope and paid custom integration terms. Avoid unlimited communications or unlimited manual tuning before real usage is known.
9. **Build a defensible learning asset.** Collect consented, de-identified workflow examples where appropriate; maintain pack evaluations, failure cases and reusable integration tests. Do not pool raw tenant conversations into a shared training database by default.

Figma inventory proves these areas have frames, not that the above requirements are met. The detailed frame audit remains outstanding.

## Distribution: learning first, repeatability second

### First customers: founder-led, targeted discovery

Build a small list of 30–50 suitable companies in one region. Qualify channel mix, existing receptionist tools, unmet intake pain, software compatibility, enquiry volume, decision maker and ability to pay. Interview 10–15 before making substantial design commitments. Ask for a recent real failed enquiry and how staff currently resolve it. Website observations alone do not establish pain.

Offer three paid, assisted pilots for 30–60 days with agreed baselines and a bounded workflow. Target numbers are proposed experiment criteria, not forecasts. A pilot should include activation, weekly outcome review, cost tracking, cancellation terms and a conversion/renewal decision. A discount or waived setup fee must be recorded as acquisition cost.

Use a short workflow demo: customer enquiry → intake → office decision → booking handoff → recovery from conflict → outcome evidence. Do not advertise a voice demo for a text-only implementation.

### Repeatable channel: specialist service partners

After direct pilots, test two or three agencies already building websites or generating leads for heating contractors. Their incentive is turning existing leads into paid work. Provide one documented setup procedure, a joint demonstration, explicit support ownership and a limited referral agreement. Start with referral introductions; defer white-label, reseller permissions and multi-agency management until support and unit economics are proven.

A proposed 15% recurring referral commission must be deducted from contribution margin. Pay against collected revenue and define reversals for refunds. Do not agree perpetual bespoke support at an ordinary subscription price.

### Later: integrations, marketplace and search content

Jobber's marketplace requires an app review; draft apps are limited to five paying Jobber accounts. A marketplace listing is neither guaranteed distribution nor an easy escape from native competition. Pursue it only if customers need a distinctive supported workflow. Build case-study and integration content from actual pilot results. Delay paid advertising until activation, retention and acquisition cost are measurable.

Sources: [Jobber app publishing](https://developer.getjobber.com/docs/publishing_your_app/app_listing_details/), [draft integration limits](https://developer.getjobber.com/docs/custom_integrations/).

### Correct the current prospecting plan

The existing plan emphasizes 100 candidates daily. Start smaller while learning and judge channel quality by paying retained customers, not list size. Begin discovery while finishing the product; begin live delivery after the required flow passes its checks. A contact form or social DM is not a safe workaround for marketing consent requirements. Human sending also does not remove those obligations.

For UK acquisition, ICO distinguishes corporate subscribers from sole traders and some partnerships. Personal-data processing still needs appropriate handling; identify the sender, provide opt-out and maintain suppression records. Screen relevant preference registers before marketing calls. The ICO page says its guidance is under review, so verify the applicable route before a campaign. No outreach has been sent in this research task.

Sources: [ICO B2B marketing](https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/business-to-business-marketing), [electronic-mail guidance](https://ico.org.uk/media/for-organisations/guide-to-pecr/guidance-on-direct-marketing-using-electronic-mail-1-0.pdf).

## Pricing and contribution economics

Test a managed text-intake offer at **£199–£299 per location/month**, with **£250–£500 standard setup** and a clearly defined allowance. These are proposed experiments, not market-validated prices. Start with one offer rather than an elaborate tier system. Confirm billing eligibility, taxes and payment-processing terms for the founder's actual legal entity; selling to UK businesses does not establish a UK merchant account.

At this price, Novaxis needs measurable workflow value and assisted implementation. A buyer satisfied by a cheap native add-on is a poor prospect. Separate voice, high-volume messages and custom integrations until their costs are measured.

Illustrative monthly model, all figures in GBP and assumed rather than actual vendor quotes:

| Item | Standard tenant | High-touch tenant |
|---|---:|---:|
| Collected subscription revenue | 249 | 249 |
| Model, communications and provider usage | 25 | 60 |
| Hosting/monitoring delivery allocation | 20 | 20 |
| Support: £35/hour assumed | 35 (1 hour) | 140 (4 hours) |
| Payment fees/refunds allowance | 8 | 8 |
| Total delivery cost | 88 | 228 |
| Contribution before acquisition and fixed overhead | **161** | **21** |
| Contribution percentage | **64.7%** | **8.4%** |

A 15% partner fee on £249 is £37.35, reducing standard contribution to £123.65 (49.7%) and high-touch contribution to -£16.35. Support effort can make a seemingly profitable subscription lose money.

At £4,000 assumed monthly fixed overhead, excluding the delivery costs already included above, recurring break-even is 25 standard direct tenants or 33 comparable partner tenants. This excludes taxes and assumes revenue is collected and customer mix stays constant. If fixed overhead includes founder salary, do not count the same delivery hours twice. Setup revenue should cover onboarding costs rather than disguise weak recurring economics.

Acquisition payback = acquisition cost / monthly contribution. At £500 assumed acquisition cost, direct payback is 3.1 months and partner payback is 4.0 months. These are simple illustrative calculations; refunds, churn and delayed payment extend payback. Do not forecast lifetime value from unmeasured retention.

Communications matter: Twilio currently publishes UK mobile SMS at $0.056 outbound and $0.0075 inbound **per segment**, with possible additional fees. At six outbound and three inbound single segments per conversation, 250 conversations cost $89.625 for SMS alone. That scenario already exceeds the standard model's assumed £25 usage budget unless the channel mix or allowance is different; convert currencies using actual invoices and rates when modeling. Longer messages multiply costs. Web chat and email versus SMS mix must be measured.

Source: [Twilio UK SMS pricing](https://www.twilio.com/en-us/sms/pricing/gb).

Proposed commercial gates: target at least 60% direct contribution after delivery labor; onboarding within four repeatable hours; recurring support at or below one hour per location/month; acquisition payback within four months. These are operating targets, not sector benchmarks. Change packaging, channel allowance or service scope if customers fail these economics.

Customer value: incremental contribution from completed jobs plus genuinely saved staff cost, less Novaxis fees. Job revenue is not job profit. Record baseline, attribution evidence and seasonality; a request or proposal is not a recovered paid job. Test whether customers can demonstrate value comfortably exceeding their fee without fabricated conversion claims.

## Core builders and their responsibilities

These are the required disciplines, not eight immediate full-time hires. Initially combine compatible responsibilities and buy specialist reviews when needed.

| Core responsibility | Deliverable | Lean ownership |
|---|---|---|
| Product/research/distribution | Discovery, segment choice, offer, success metrics, pilot sales and renewals | Founder accountable; assistant prepares research and artifacts |
| UX/UI and observability | Complete Figma tasks/states, mobile controls, reusable components and outcome views | One senior product designer or equivalent focused role |
| Software/integration engineering | Dashboard/API, tenant isolation, booking-system adapters, billing and reliable action execution | One strong full-stack/backend owner; specialist provider support as needed |
| AI engineering | Context, structured proposals, pack rules, model selection, evaluations and response cost/latency | Separate accountable workstream; may initially share engineer |
| QA/reliability/security | Journey tests, retries, permission boundaries, monitoring, incidents and release evidence | Explicit owner; independent review of critical boundaries |
| Customer implementation | Standard setup, training, escalation, weekly pilot feedback and support cost | Founder initially; hire when volume supports it |
| Privacy/legal review | Processing agreements, retention, outreach rules and regulated-data launch review | Scoped external specialist |

The assistant can work through these roles with defined outputs; it cannot replace accountable production operations or manufacture customer validation.

Technical core to protect: tenant-scoped database access, action proposals and gate, reliable job processing, idempotent executors, channel adapters, booking-system boundary, pack configuration, audit/events and evaluation fixtures. Build the shared core; adapt intake and vocabulary through packs. Reconcile gate rules before relaxing controls. Validate queue handling under idle periods, failures and concurrent requests; an attractive Figma is not evidence of production reliability.

Use existing model APIs initially. Compare models against task evaluations and actual cost. Build domain workflows and recovery; buy commodity telephony, speech, hosting and authentication where appropriate. Avoid custom training, a replacement CRM, a general automation platform and a proprietary voice stack before evidence justifies them.

For US dental, HHS describes BAA and risk-management obligations for covered entities/business associates using cloud services that handle ePHI. Vendor agreements and actual controls must precede a regulated launch; a dashboard toggle alone does not establish compliance. This is one reason to defer dental expansion, not a claim that all dental activity everywhere is governed by HIPAA.

Source: [HHS cloud guidance](https://www.hhs.gov/hipaa/for-professionals/special-topics/health-information-technology/cloud-computing/index.html).

## Next 30 days: research-driven tasks

1. Week 1: 10–15 interviews; document channels, software, lost-demand examples, owner decision process and price objections. Resolve approval policy. Reject segments where native automation already solves the problem.
2. Week 2: complete the selected workflow in Figma, including onboarding, mobile review and recovery. Define an event/cost dictionary. Verify the corresponding implementation before delivery; do not label mock frames as working functionality.
3. Weeks 3–4: aim for three paid pilot agreements, activate only within verified capability, measure cost and outcomes weekly, and test the first agency introduction route. These are targets; recruiting or live changes are separate authorized execution tasks.
4. Continue for at least a full operating cycle: require renewal at ordinary pricing, inspect customer value and support burden, and decide whether to scale, change the offer, change the segment or stop the experiment.

If most qualified prospects need voice and will not buy text intake, move voice feasibility earlier. If multiple prospects share one native system and refuse CSV handoff, prioritize that adapter. If support exceeds the limit, standardize configuration or raise/reshape pricing before adding customers. If interest does not become paid use, revisit the problem and offer before expanding the dashboard.

## Unresolved evidence

Customer interviews and willingness to pay; existing lead/channel volumes; production feature completeness; actual token/communication/support costs; vendor permissions and account eligibility; geographic acquisition reach; partner conversion; job outcome attribution; retention and refunds; restoration competitive coverage. No defensible revenue forecast or product-market-fit claim can be made until these are measured.

## Existing project sources reviewed

[Repository](https://github.com/srdataml-droid/multi-ai-platform-), [architecture](https://github.com/srdataml-droid/multi-ai-platform-/blob/main/docs/ARCHITECTURE.md), [standing rules](https://github.com/srdataml-droid/multi-ai-platform-/blob/main/CLAUDE.md), [research brief](https://github.com/srdataml-droid/multi-ai-platform-/blob/main/docs/research/RESEARCH-BRIEF.md), [prospecting framework](https://github.com/srdataml-droid/multi-ai-platform-/blob/main/docs/research/PROSPECTING-FRAMEWORK.md). The earlier research brief explicitly marked vendor/legal claims for verification. This report verifies selected decision-relevant claims and does not treat the remaining brief as verified fact.
