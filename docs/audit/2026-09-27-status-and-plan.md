# Status, remaining faults, market research and plan (2026-09-27)

Written at the end of the fault-fixing round (batches 1–5 and N1), so that the founder,
future sessions and any engineer joining can pick up from here. Earlier record:
`2026-09-26-scorecard.md`. Controls and their tests: `docs/compliance.md`. Incidents:
`docs/RUNBOOK.md`.

## 1. Where the product stands

Live: https://novaxis-web.vercel.app (dashboard) and https://novaxis-api.vercel.app (API),
Supabase London. 341 Python tests (pass in any order), 16 golden conversations gating CI,
5 browser tests on the production build. Replies still come from the scripted model: no
real AI is connected yet.

| Area | 26 Sep | Now | Main reason it is not 10 |
|---|---|---|---|
| A. Safety & AI behaviour | 3 | 7 | Never run against the real model |
| B. Staff experience | 5 | 8 | Push alerts not yet tried on the founder's phone |
| C. Security | 5 | 7 | Repo is public |
| D. Channels & integrations | 3 | 3.5 | Web chat only; no voice |
| E. Reliability & operations | 4 | 6 | No error tracking; photos not durable; free database plan |
| F. Compliance | 2 | 5 | Legal items are the founder's |
| G. Business readiness | 3 | 3 | No pilot customer |
| Architecture | 7 | 7 | AI runs inside web requests; one region |
| Testing | 6 | 8 | Real-model evals never run |
| Docs & process | 6 | 8 | Founder review time (H2) |
| **Overall** | **4.4** | **≈6.3** | |

## 2. Remaining faults

Owner: **F** = founder decision, time or money; **C** = code (a session can do it).

| ID | Sev | Fault | Owner | Blocked on |
|---|---|---|---|---|
| A6 | Med | Replies never tested against the real model; the 16 golden conversations use a script | F then C | An API key with a spend cap |
| C5 | Med | GitHub repo is public | F | Two clicks |
| E3 | Med | Live site still deploys from `main` before tests finish | F | Vercel: Production branch → `production`, both projects |
| D1 | High | SMS, email, Google Calendar, Stripe have no live keys | F | Accounts and money |
| D2 | High | No voice, WhatsApp or Messenger. Section 3 shows voice is what competitors sell | F then C | Strategy decision, then a telephony provider |
| D3 | Med | No direct write to booking software (bridge is manual); no price quoting | C | A pilot's actual software |
| E1 | Med | Health check and monitor exist, but no error tracking (Sentry). The 15-minute GitHub monitor ran once in 6 hours (N2) | C | Nothing (free tiers) |
| E2 | High | Photos saved to `/tmp` are lost between function runs | F then C | Supabase service key |
| E5 | Med | Supabase free plan: limited backups, may pause when idle [VERIFY] | F | Money |
| F1 | Med | Processor-agreement records and regulated-data mode not built; audit log has no retention rule | C then F | Vendors chosen; adviser |
| F2 | High | No privacy notice/terms for Novaxis, no ICO fee, no DPIA for dental | F | Legal |
| G1 | High | No pilot business; prices are placeholders; research `[VERIFY]` items unchecked | F | Founder time |
| G2 | Med | Stripe never used live; sign-ups have no email verification; a business cannot change its pack | C | Stripe key for the first |
| H2 | Med | The founder has not reviewed the code (K2: must be able to defend it) | F | ~2 h a week |
| N1r | Low | A number is checked as unclaimed, not as owned | C | Twilio key |
| N2 | Low | GitHub scheduled runs are best-effort; the monitor is not a reliable alarm | C | Free external uptime check, or run it from Supabase `pg_cron` |
| N3 | Low | Each commit now builds four Vercel deployments (slower, free) | C | Vercel ignore rule for `main` once production tracks `production` |
| Arch | — | AI turn runs inside the web request; single region; no always-on worker | C | Only matters at real volume |

Also known and harmless: the "Novaxis Smoke Test" business predates login codes and cannot
sign in; local browser tests share the dev database with pytest leftovers (CI does not).

## 3. Market research: who else does this

Search done 2026-09-27. Names and claims below are from the vendors' own pages; prices and
customer counts are their claims, not verified.

**The market is crowded and voice-first.** Almost every competitor answers the *phone*; ours
answers *text* (web chat, SMS, email). Missed calls are the pain they sell against.

| Segment | Examples | Notes |
|---|---|---|
| Built into field-service software (the incumbents) | Jobber AI Receptionist, Housecall Pro CSR AI, ServiceTitan Voice Agents | Answer calls, check availability and book straight into their own diary. They own the system of record, which is our D3 weakness. ServiceTitan's July 2026 update added a dashboard of booking rate, escalation reasons and transcripts |
| UK trades AI receptionists | Voco (from £49/month, 75 calls), ObserveAutomation (from £499/month), VoiceFleet, Airayflow, Raynaters | Sets the UK price band: roughly £49–£499/month |
| US home-services AI receptionists | Newo.ai, LeadTruffle, Autocalls, RealVoice, PickupBell | About $99–$397/month (aggregated from search results) |
| UK dental | SmileDesk (claims 200+ UK practices), Hi Human, ViveoAI, DentaAI (WhatsApp/SMS booking links), Patientdesk, Antek | Crowded; several say they integrate with practice-management systems |
| Restoration (water damage) | Trillet, InstaNexus, CallJolt, Marlie, RevenuePack | Same pattern: capture carrier, claim number, loss type, rooms; book the assessment |
| A shift to watch | Google agentic calling (reported July 2026): Google's AI phones businesses for homeowners | Future customers may be other AIs, so a clean booking API may matter as much as a voice |

**What this means for Novaxis**

1. **Text-only will not win the UK trades or dental market alone.** Either add voice (D2), or
   pick a niche where text is the natural channel (WhatsApp-heavy customers, after-hours web
   enquiries, photo-first restoration intake).
2. **Where we are stronger than the pages suggest the others are:**
   - Every risky action waits for approval.
   - Emergency replies are honest when the alert fails.
   - Safeguarding stops the AI.
   - Opt-out works per channel.
   - Export and erasure are built in.
   - The booking bridge serves diaries with no API.

   These are reasons a *dental* practice or a cautious UK firm would choose us. Sell safety
   and compliance, not "an AI that answers".
3. **Integration is the moat the incumbents have.** A pilot on one named piece of booking
   software, integrated properly, beats broad claims.
4. **Price:** the UK band is about £49–£499 a month. Our cost is about 5p per text
   conversation on Claude Sonnet 5 (estimate), so £49–£99 has room [measure before pricing].

Sources: [Jobber](https://www.getjobber.com/features/ai-receptionist/),
[Housecall Pro CSR AI](https://www.housecallpro.com/features/ai-team/csr-ai/),
[ServiceTitan summary](https://aiflowreview.com/home-service-voice-agents/),
[Voco](https://vocohq.co.uk/industries/trades/plumbers),
[ObserveAutomation](https://www.observeautomation.com/products/tradesreceptionist/),
[UK trades guide](https://www.softomatesolutions.com/blog/best-ai-receptionist-trades-uk-2026/),
[Newo.ai](https://newo.ai/hvac-plumbing-ai-receptionist/),
[SmileDesk](https://www.smiledesk.ai/), [Hi Human](https://hihuman.co.uk/),
[ViveoAI](https://viveoai.com/), [DentaAI](https://dentaai.com/),
[The Probe: AI at the front desk](https://the-probe.co.uk/blog/2026/07/ai-at-the-front-desk/),
[Trillet restoration](https://trillet.ai/blogs/ai-answering-service-for-water-damage-restoration),
[CallJolt restoration](https://calljolt.com/blog/restoration/ai-answering-service-water-damage-restoration),
[Google agentic calling](https://www.marketingcode.com/mobile-ai-google-agentic-calling-home-repairs-ai-to-ai-booking-jul-2026/).

## 4. Plan

Principle (founder's call, 27 Sep): **one strong product before scaling.** Depth over breadth.

### Phase A: close the free items (no money)
1. Founder: repo private (C5); Vercel production branch (E3); read the Revluma IP clause.
2. Code: Sentry free tier for errors (E1); move the health check to a reliable timer (N2);
   Vercel ignore rule for `main` (N3); email verification on sign-up (G2).

### Founder decisions (27 Sep, after the first draft of this plan)
- **All channels, not one:** text (web chat, SMS, email, WhatsApp), **voice** and **photo**.
- **Open-source model first**, then switch to whatever is most affordable. Not Claude for now.
- **Camera for stock counting** (count products, keep stock levels) is part of the vision.

### Phase B: connect a real AI, open source first
The code talks to the model through one interface (`packages/core/novaxis_core/llm.py`);
today it has a scripted stand-in and an Anthropic adapter.
1. **Done 27 Sep:** `OpenAICompatLLM` in `llm.py`, how-to in `docs/models.md`. First real run is on the founder's laptop (this build environment cannot reach Ollama). Code: add **one "OpenAI-compatible" adapter**. Ollama (local), vLLM (self-hosted) and most
   hosted open-model services (Groq, Together, OpenRouter, ...) speak this format, so
   switching to "something affordable" is a change of three settings, with no code
   change: base URL, model name and key. [VERIFY each provider's tool-calling support
   before choosing it.]
2. Code: run the 16 golden conversations on two or three open models and record the pass
   rate and cost. **The evals choose the model, not the brand.** The model must call tools
   reliably: booking and emergency escalation depend on it.
3. Code: grow to about 25 golden conversations per pack: prompt injection, abuse,
   medical-advice bait, messages that are only "?" or "yes". Hold 90%+ before any real
   customer.
4. Founder: the laptop (no GPU, about 13GB RAM) can run only small models, slowly: fine
   for trying, not for customers. Production means a hosted open-model API (pay per token)
   or a rented GPU. Set a monthly spend cap either way.
5. Shadow mode for the first pilot: the AI drafts, staff approve before anything is sent.
   The per-business setting `risk_overrides: {"reply": "medium"}` should route every reply
   through approval; test that end to end before relying on it.

### Phase C: voice and photo on the same brain
Every channel feeds the same worker: approval step, packs, bookings. A new channel is an
adapter that turns its input into text (plus attachments) and the reply back into its format.
- **Photo (partly built):** photos are received and stored today but lost between function
  runs (E2) and not yet understood. Next: durable storage, then an open vision-language
  model to describe the photo ("water stain on ceiling, about 1m wide") into the
  conversation. [VERIFY model licence and quality]
- **Voice:** phone number and calls (a telephony provider, which costs money), speech-to-text
  (open source: Whisper), text-to-speech (open-source options exist [VERIFY which]), and
  a low-latency path. A caller will not wait 10 seconds, so voice cannot use today's
  request-bound worker unchanged (see "Arch" in section 2).
- **WhatsApp:** Meta's business API (a provider account, per-conversation fees [VERIFY]).
- Order proposed: **photo → WhatsApp → voice** (cheapest first, voice last because it
  needs the most new infrastructure). Founder may reorder.

Then one pilot business and a direct integration with its software (D3).

### Phase D: machine learning and neural networks
Where they fit, now that stock counting is in scope:

| Model | Kind | Predicts | Needs |
|---|---|---|---|
| **Stock counting from a photo** | Neural network (object detection) | How many of each product is on a shelf | A few hundred labelled photos per product type; training on a GPU (Colab works); licence check: some popular detectors are AGPL, which has conditions for commercial use [VERIFY before choosing] |
| No-show risk (dental) | Classical ML (XGBoost) | Which bookings will not turn up | A few thousand bookings labelled attended/missed; the C-confirm flow (A7) already records confirmations |
| Job duration (trades) | Classical ML | How long a job really takes | Booked vs actual times |
| Urgency / lead value | Classical ML | Which enquiries to answer first | Outcome labels per conversation |

**Start now at zero cost:** record outcomes (attended, cancelled, job value) on every
booking, and keep stock photos with the counts staff confirm, so training data exists later.

**Recorded dissent (the founder's call stands):**
- **The Simplifier (K1)** says stock counting serves a different customer: shops and
  warehouses, not service businesses taking bookings. Building it alongside voice risks
  two half-products. Proposal: finish text + photo + voice for service businesses first,
  then stock counting as its own pack on the same platform.
- **The ML Engineer** replies that stock counting is the one place a neural network is
  justified now (vision needs one), and the photo pipeline is shared.
- **Resolution:** one platform. Stock counting becomes a pack after the pilot proves the
  core loop.

## 5. Questions for the founder
1. First pilot business: which type (trades, dental, restoration, or a shop that counts
   stock)?
2. Is UK still first, or should an African market run alongside (Novaxis focus)? The
   research above is UK/US only.
3. Monthly spend cap for the hosted open model (Phase B)?
4. Two hours a week for code review (H2): which day?

## 6. When a session resumes
Read this file, then in order: Phase A code items → Phase B (open-source adapter and evals) →
whatever the founder chose in section 5. Keep the working rules:
- find → why → fix only when asked;
- every fix gets a test that fails on the old code;
- run the full suite in both orders, evals and browser tests before a push;
- check the live site after a deploy.
