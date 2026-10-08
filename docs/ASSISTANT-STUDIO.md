# Assistant Studio

Added locally on 8 October 2026. Open `/assistant` from the owner menu after deploying
the web and API updates together. The page uses the existing authentication, business
settings, visitor chat channel, worker queue, approvals, and usage records.

## Chat

The chat pane sends visitor messages to `/inbound/webchat/{tenant_slug}` and polls the
visitor's messages using the signed visitor token returned by that route. It does not
send the owner's bearer token to visitor routes or invent replies in the browser.
The widget channel and assistant must both be enabled. Replies appear when the existing
worker processes the message or staff reply to the conversation.

These are real business-inbox messages, not an isolated sandbox. The page labels this
before sending and asks for fictional details. Existing booking and approval rules apply.
Starting a new conversation clears the pane and visitor token; it does not delete records.
No chat message was submitted to production while building this feature.

## Model visibility

`GET /settings/assistant` requires owner/operator access and returns only safe metadata:

- API-configured provider and response/classification/summary models.
- Scripted demo mode, where the effective model is `fake`.
- The latest `llm.worker_turn` model and timestamp recorded for this business.

The query uses the tenant-scoped database session and explicitly filters by tenant id.
API keys, provider base URLs, prompts, and conversation text are not returned.

API settings and observed worker usage are displayed separately. A separate worker can
have different environment settings. A usage record establishes that a model call ran;
it does not establish that the reply was approved or delivered, and it is not a per-message
model attribution. An absent record remains unknown. The studio does not infer the current
production model from potentially outdated repository documentation.

## Business-specific behavior

The existing worker prompt includes the industry's instructions plus the business's
name, tone, opening hours, services, service areas, and saved FAQ answers. Booking
questions and approval rules govern intake and actions. Studio shows those business facts,
links to their existing editors, and saves reply style through validated business settings.
The latest settings are read before saving style to preserve other fields; saves do not
have optimistic concurrency control, so simultaneous edits from multiple users can still
conflict. Scripted demo replies do not demonstrate business understanding.

## Website setup

Studio now also includes guided website installation. Owners can enter one website per
line, save the normalized origins, copy the tenant-specific embed code, and follow visitor
test instructions. A full page URL is reduced to its origin; a bare domain uses HTTPS.
The www and non-www variants are distinct. Empty saved origins are correctly described as
unrestricted access; the Novaxis dashboard remains allowed for previews. Saving origins
does not install the script or verify a live connection. Website saves read fresh settings
and preserve the other fields, subject to the same concurrency limitation as tone saves.

## Switching providers later

Provider changes remain administrator deployment settings. Configure the API and worker
consistently using `NOVAXIS_LLM_PROVIDER`, `NOVAXIS_MODEL_WORKER`,
`NOVAXIS_MODEL_CLASSIFY`, and `NOVAXIS_MODEL_SUMMARISE`. For OpenAI-compatible providers,
also configure the server-side endpoint and secret described in `docs/models.md`.
Supported adapters are `anthropic`, `openai_compatible`, and `fake`. The provider must
support the worker's tool calls. Run business-pack evaluations against the chosen model
before serving customers. Studio does not claim that arbitrary model names are supported
or change production settings from the browser.

## Verification

- Type checking, lint, and web unit suite: passed (14 unit tests, including website-origin parsing).
- Web production build: passed, including the new `/assistant` route.
- Backend metadata checks: 6 passed without a database, using dependency overrides.
  Checks cover authentication, owner permissions, tenant-query filtering, secret omission,
  configured-versus-observed models, scripted mode, and missing usage.
- Python lint for changed backend files: passed.
- Browser checks: 2 passed with mocked API responses, covering chat send/reply, inbox link,
  saved style preserving other fields, website saves normalizing origins and preserving
  tone, conversation reset, unavailable metadata, and a
  disabled chat channel. The first attempt had incomplete test-user metadata; fixing the
  fixture and using polling for the machine's exhausted file watchers resolved it.
- Screenshot: local browser fixture with sample business data, not a production account.

The Studio flow has not been tested against a live model or production business account.
No deployment, provider switch, outbound email, or live customer submission was performed.


## Industry profiles (8 October 2026)

Signup already stores the chosen pack. Studio now resolves a versioned, explicitly registered
industry template for HVAC, dental or property restoration through an owner/operator-only
endpoint. Unsupported packs receive no invented industry template. Existing accounts use
the same lookup without migration.

The profile stores optional assistant name, personality and additional handoff preferences,
plus owner-confirmed business details and pricing policy. Customisation enables only the
optional behaviour fields. Disabling it preserves edits; business facts remain in context.
An editing lock is a local UI convenience, not an authorization boundary. Reset restores
industry behaviour while keeping saved facts and unrelated settings. Existing tone settings
remain the baseline style. Industry prompts, emergency checks and action gates remain active.
Onboarding preserves the profile. Settings storage remains tenant-scoped and validated.

General industry background is marked as background, not company capabilities. Fields remain
blank until the owner confirms them. Calendar availability is never inferred from these text
fields. The profile is loaded on built-in worker turns; external agents manage their own
context. No website import, customer long-term memory, or automatic learning is introduced.

Research sources appear in the Studio template panel. US industry sources support general
workflows; existing UK dental intake and emergency rules remain unchanged. Future industries
require explicit reviewed registry entries, their own pack and intake configuration.

## Existing chat integration lab

`/company-lab.html` is a fictional Northline HVAC site with its own chat interface.
Disconnected mode now uses an owner-authenticated generic model endpoint with no tools or booking capability. It reuses the configured server-side model, enforces 10 calls/minute and 60/day per business, checks the trial and records token usage. No public model relay or client-side provider key is introduced.
The user must enter a business slug and connect before any messages go to Novaxis.
Connected mode calls the existing visitor webchat API through `/api`, retains the
visitor token only in memory, and polls replies. Connected visitor mode sends no staff credentials. Generic mode uses the existing Novaxis owner session with the first-party API.
It demonstrates replacing a chat backend while retaining the UI, not adding tools
inside an independently running third-party AI agent. An external AI using its own
reasoning must instead integrate the server-side agent API and approval tools.
This lab shares the Novaxis origin; it is not proof of a separate-domain integration.
New conversation clears local state, not persisted Novaxis inbox records.
