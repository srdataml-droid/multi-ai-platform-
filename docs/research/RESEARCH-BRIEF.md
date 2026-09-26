# Research Brief: Existing tools, workflows, compliance, pricing, open source vs paid

> Written from the session's own knowledge because live web research was declined in this
> session. Every claim about a vendor, a price, or a law is tagged `[VERIFY]` and must be
> checked against the primary source before it appears in a pitch, a contract, or a design
> decision that is expensive to reverse. Struck claims are better than hedged ones.
>
> Verification order: (1) vendor pricing and API pages, (2) regulator text (ICO, GDC, FCC,
> HHS), (3) the prospect's own answer during discovery. A prospect telling you what they use
> beats any list below.

## 1. Does this already exist?

Yes, in pieces. No, as one product across these three industries with an approval gate and
a business-owned system of record. The honest map:

**Layer A: the systems of record the businesses already run.** These are entrenched, expensive
to replace, and you should never try. You integrate.

| Industry | Tools commonly in use | Notes |
|---|---|---|
| HVAC / field service | ServiceTitan, Housecall Pro, Jobber, FieldEdge, Service Fusion `[VERIFY current API access and partner programme terms]` | Housecall Pro and Jobber have public APIs with partner programmes; ServiceTitan's API is gated behind a developer programme `[VERIFY]` |
| Dental (US) | Dentrix, Eaglesoft, Open Dental, Curve Dental `[VERIFY]` | Open Dental has a documented API; the others mostly reached through middleware such as NexHealth or Sikka `[VERIFY]` |
| Dental (UK) | Dentally, SOE Exact (Software of Excellence), Carestream R4, iSmile, Aerona `[VERIFY]` | Dentally has a public API; SOE Exact integration is via partner agreement `[VERIFY]` |
| Restoration | Xcelerate, DASH (formerly Next Gear Solutions), Albi, JobNimbus, Encircle for documentation, Xactimate for estimates `[VERIFY]` | APIs are thin or partner-only; expect the CSV/email bridge from Chunk 11 to be the realistic first integration |

**Layer B: AI front-desk products that already sell the "answer, qualify, book" outcome.**
These are your direct competitors per vertical, and the source of the phrases customers already
understand.

| Segment | Products `[VERIFY each: still trading, pricing, features]` | What they sell in their own words (patterns you can reuse) |
|---|---|---|
| Home services AI receptionist | Avoca, Slang.ai, Goodcall, Dialzara, Smith.ai (human plus AI), Ruby (human) | "Never miss a call", "book jobs 24/7", "missed-call text back", "every call answered in under a second" |
| Dental AI receptionist | Arini, Annie (NexHealth), Weave's AI features, RevenueWell, Peerlogic | "Fill your schedule", "reduce no-shows", "answer every patient call", "HIPAA-compliant" |
| Horizontal AI phone agents | Retell, Vapi, Bland, Synthflow, Sierra, Decagon (enterprise) | "Build a voice agent in minutes", "human-like", "transfers to your team" |
| Restoration-specific AI intake | Thin. Some answering services market to restoration; no dominant AI-first product known to this session `[VERIFY by searching "restoration AI intake" and the DASH and Xcelerate partner marketplaces]` | This is the least crowded lane |

**Layer C: what nobody is selling well, which is your wedge.**
1. **One worker, many industries, one dashboard.** Competitors are single-vertical. A founder who can run HVAC and dental and restoration tenants on one core has a cost structure they do not.
2. **Approval gate as the product.** Most competitors pitch autonomy. Small business owners are scared of an AI booking the wrong job. "It proposes, you approve, it learns your rules" is a calmer sale and a safer product.
3. **Managed service, not software.** The pasted note from the earlier session had this right: sell one outcome (reliable intake), configure it per business, monitor it, charge setup plus monthly. The dashboard is for them; the tuning is your job.
4. **Restoration is under-served.** Emergency intake with photos and claim-document chasing is a real pain and few AI products target it.

## 2. Industry workflows and dashboards

What each business does today, from first contact to money. The worker takes the left side.

**HVAC**
1. Call or web form arrives, often during a job when nobody can answer. Missed calls go to voicemail; a large share never call back `[VERIFY with the prospect's own missed-call data during discovery, not with industry statistics]`.
2. Office asks: what's wrong, how old is the unit, where are you, is it urgent, when are you free.
3. Dispatcher assigns a technician and a window in the field-service tool.
4. Confirmation and "on the way" texts.
5. Technician quotes on site; estimates that are not chased die.
6. Invoice, review request, maintenance plan upsell.

Dashboard they already stare at: the dispatch board (technicians by time), the job list by status, the estimate pipeline.

**Dental (UK)**
1. Phone is the main channel; reception is busy at the desk with patients in front of them.
2. Reception asks: registered with us, NHS or private, what is wrong, how long, pain level, then finds a slot in the practice software.
3. Confirmation, reminders, form links.
4. No-shows are a direct revenue loss and a scheduling headache.
5. Recall (six-monthly check-up) and waitlist management fill the diary.

Dashboard they already stare at: the day-view appointment book by provider and room, the recall list, unconfirmed appointments.

**Restoration**
1. Emergency call, often at night, from a distressed homeowner or a property manager.
2. Intake: what happened, is it still happening, is there an insurance claim, photos.
3. Crew dispatched for mitigation; inspection and estimate follow.
4. Claim documentation is chased for weeks; adjuster back-and-forth.
5. Invoice to insurer or owner.

Dashboard they already stare at: the active jobs board, claims by status, documents outstanding.

## 3. Integration priority

Pick the integration after discovery with the pilot, not before. The order of preference for
Chunk 11 given what is likely to have a usable API `[VERIFY each]`:

1. HVAC: Housecall Pro or Jobber (public API, partner programme).
2. Dental UK: Dentally (public API). Dental US: Open Dental (API) or NexHealth as middleware.
3. Restoration: CSV/email bridge first; check the DASH and Xcelerate partner programmes.

Generic integrations that cover most tenants in Phase 1: Google Calendar, Microsoft 365 calendar (Phase 2), Twilio number porting or forwarding so the business keeps its number.

## 4. Compliance map

Not legal advice. Each row is the rule as understood in this session and the control that
implements it. Verify with the regulator's text, and for dental get an hour with a UK
data-protection adviser before the first tenant.

| Concern | UK | US | Control in the architecture |
|---|---|---|---|
| Personal data processing | UK GDPR and Data Protection Act 2018. Lawful basis needed; health data is special category `[VERIFY the exact conditions relied on]` | State laws vary; California CCPA/CPRA for some sizes `[VERIFY]` | Consent ledger, retention, export, purge, region pinning (section 11 of the architecture) |
| Health information | Special category data. Dental practices are controllers; Novaxis is a processor and needs a written processing agreement `[VERIFY]` | HIPAA. Any vendor handling protected health information for a covered entity needs a Business Associate Agreement. Whether your LLM provider, telephony provider and hosting provider will sign one is the gating question `[VERIFY with each vendor; do not assume]` | Regulated-data mode (Chunk 12) refuses to activate without agreement records for each processor |
| Marketing messages to individuals | PECR: electronic marketing to individuals needs consent, with a narrow existing-customer exception for similar services with an opt-out at collection `[VERIFY]` | TCPA: automated texts and calls to mobiles need prior express consent; written consent for marketing `[VERIFY]`. CAN-SPAM for email | Outbound to individuals only in reply to their contact or with recorded consent; `outbound_first_contact` is high risk |
| Marketing to businesses (your prospecting) | PECR treats corporate subscribers differently from sole traders and partnerships, who count as individuals `[VERIFY]`. UK GDPR still applies to named contacts; legitimate interests assessment needed | CAN-SPAM: opt-out, accurate headers, physical address `[VERIFY]` | Prospecting framework in `docs/research/PROSPECTING-FRAMEWORK.md` |
| AI voice disclosure | Emerging guidance; disclose that the caller is speaking to an AI `[VERIFY current ICO and Ofcom positions]` | FCC has treated AI-generated voices in robocalls as artificial voices under TCPA `[VERIFY]` | Disclosure on first message is a core requirement, not a pack option |
| Dental professional standards | General Dental Council standards on communication and on advertising `[VERIFY]` | State dental boards | Pack rules: no diagnosis, no treatment advice, emergency phrases route to a human or emergency services |
| Platform terms | Social platforms prohibit automated scraping and unsolicited contact from data gathered on them `[VERIFY each platform's developer terms]` | Same | The worker never scrapes. See section 6 below |

## 5. Pricing

No numbers here until verified. The shape that fits a managed service:

- **Setup fee**: covers configuration, channel setup, calendar connect, a two-week tuning period. Priced against the founder's real hours.
- **Monthly per location**: includes a message allowance and the dashboard.
- **Usage over allowance**: per message segment and per voice minute, passed through with margin.
- **Pilot**: setup fee waived, monthly at full price, 60 days, with the three success numbers agreed up front (response time, intake completion, bookings approved).

Set the numbers after the pilot from `usage_events`, not from competitor price pages. What competitors charge is a `[VERIFY]` item for positioning only.

## 6. The social-listening outbound idea: dissent recorded

The idea from the brief: the worker sees someone post "I have a toothache" or "my basement
flooded" and contacts them, or tells the business to.

**Objection (LENS, BENCH Ethicist, Counsel).** Contacting a person because of what they posted,
using health or distress signals, without any prior relationship, is the highest-risk thing in
this plan. It is likely to breach platform terms, PECR and TCPA consent rules, and special-category
data rules for the dental case, and it would harm the brand of the business doing it. `[VERIFY
the specific rules, but the direction is clear enough that BENCH would not ship it as designed]`

**What survives, and is genuinely useful:**
1. **Own-channel monitoring.** The business's own Google Business Profile questions, reviews,
   Facebook page messages and comments, Instagram DMs. People who wrote to the business. The
   worker drafts, a human sends. Low risk, high value.
2. **Public request boards where the person asked for offers.** Local quote-request services and
   community groups where someone explicitly asks "can anyone recommend a plumber". The worker
   flags it to staff with a suggested reply; a human posts under the business's own name. Medium
   risk, human at the wheel.
3. **Never** automated contact from a scraped post. The core gate makes this `high` and no pack
   can lower it.

Chair's ruling: build 1 in Phase 2 as a "mentions" inbox source, build 2 only after a tenant asks
for it and a platform's terms are read, and do not build the original idea. Dissent from the
founder's original brief recorded here; if the founder overrules, it is a Sovereign escalation
because it attaches Novaxis's name to the risk.

## 7. Open source vs paid

| Need | Open source option | Paid option | Recommendation |
|---|---|---|---|
| Database, auth, storage, realtime | Postgres plus your own auth | Supabase (managed, free tier to start) | Supabase. Free tier is enough for the pilot `[VERIFY tier limits]` |
| Queue | Postgres table (build) | Hosted Redis or a queue service | Postgres table. K1 |
| LLM | Self-hosted open models via Ollama | Anthropic API | Anthropic API. No GPU and quality matters; keep the interface so a cheaper classifier model can be swapped in later |
| LLM observability | Langfuse self-hosted | Langfuse cloud | Self-hosted on Railway if the free cloud tier is too small `[VERIFY]` |
| Shared inbox | Chatwoot (self-hosted, mature) | Front, Intercom | Do not adopt Chatwoot as the product; the approval gate and packs need to be first-class. Read its data model for the Inbox and Conversation pages |
| CRM | Twenty (self-hosted) | HubSpot | Not needed; `contacts` plus the vendor's system of record is the CRM |
| Scheduling | Cal.com (self-hosted) | Calendly | Not needed in Phase 1; Google Calendar plus our holds. Revisit if tenants without any calendar appear |
| Workflow automation | n8n, Temporal | Zapier, Make | Not in the core. n8n may be useful for one-off tenant integrations in Phase 2 |
| Telephony | none realistic | Twilio, Telnyx, Vonage | Twilio for SMS and voice. Telnyx as the fallback if number costs matter `[VERIFY pricing]` |
| Speech (Phase 3) | Whisper (needs GPU for real time), Coqui | Deepgram, ElevenLabs, or a managed voice-agent platform | Decide in Chunk 14 after call volume is known. Managed platform likely wins on founder time |
| Email sending | SMTP | Resend, Postmark, SendGrid | Resend or Postmark `[VERIFY inbound parsing support]` |
| Error tracking | GlitchTip | Sentry | Sentry free tier |
| Hosting | Docker anywhere | Railway, Render, Fly.io, Vercel | Railway or Render for API and worker, Vercel for web. Founder already uses them |
| Payments | none | Stripe | Stripe |

Paid items the founder must budget for from day one: Supabase (may stay free), Twilio numbers
and messages, Anthropic API usage, a domain, Vercel and Railway once past free tiers. Everything
else can start on a free tier or self-hosted.

## 8. Phrases people already use

Collected from the competitor positioning above and from how these businesses talk about their
own pain. Use in demos and outreach because prospects already understand them.

- "Never miss a call again"
- "Missed-call text back"
- "Book jobs while you're on the roof"
- "Fill the gaps in your diary"
- "Cut no-shows"
- "Answer every patient, even at lunch"
- "It works your phones, you approve the bookings"
- "Sits in front of the software you already use"
- "You see every conversation, you can jump in any time"
- "Set up in a week, tuned for two, then it runs"

Avoid: "AI agent", "autonomous", "replaces your receptionist". Small business owners hear risk
and staff hear a threat.
