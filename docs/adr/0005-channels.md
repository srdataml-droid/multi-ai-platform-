# ADR 0005: Channel adapters, providers, and visitor identity

- Status: accepted
- Date: 2026-09-26
- Chunk: 2

## Context
Phase 1 needs three text channels. Each provider has its own webhook shape and its own
verification scheme. The core must stay free of provider SDKs and web frameworks.

## Decisions
1. **One adapter protocol** (`verify_signature`, `parse_inbound`, `send`) over a plain
   `InboundRequest` value. The API builds that value from the HTTP request; adapters never
   see FastAPI. Contact matching, threading and job creation are in `novaxis_core.inbound`,
   shared by every channel.
2. **Twilio for SMS**, with the signature recomputed in twelve lines rather than pulling the
   SDK. The signed URL is rebuilt from `NOVAXIS_PUBLIC_BASE_URL`, because behind a proxy the
   app sees a different URL from the one Twilio signed.
3. **Postmark for email**, both directions. Its inbound webhook is JSON with stripped reply
   text, which saves writing an email parser. Postmark does not sign webhooks; a shared token
   in the URL or a header is compared in constant time. Alternatives: SendGrid Inbound Parse
   (multipart, messier), Mailgun (fine, but one more vendor), Resend (inbound support to be
   confirmed `[VERIFY]`). Local dev sends through Mailpit; inbound is exercised with fixtures.
4. **Web chat visitors** carry an HMAC-signed visitor id in localStorage. It holds no personal
   data, cannot be forged, and threads a returning visitor into their conversation. The widget
   reads replies by polling a messages endpoint scoped to that visitor. Origin allow-listing
   and rate limits are Chunk 12.
5. **Contact matching**: phone exact, email lowercased, visitor id exact. Never by name, so
   two "John Smith"s are two contacts and a merge is a deliberate human act.
6. **Opt-out** is handled in the API before any job exists. STOP words close the
   conversation, flip consent, and send one confirmation synchronously. Opted-out contacts
   who write again are recorded and never answered until they opt back in.
7. **messages stays append-only** except a column-level grant on `provider_ref` and
   `delivered_at`, which an outbound send fills in once. Replayed webhooks are no-ops via a
   unique index on (tenant, channel, provider_ref).

## Consequences
- Adding WhatsApp (Meta Cloud API) is one adapter file plus a routing key.
- Every tenant's channel identifiers (number, inbound address) live in `settings.channels`,
  indexed for routing. Two tenants cannot share a number.
- Twilio verification fails closed when `NOVAXIS_TWILIO_AUTH_TOKEN` is empty; the same for
  Postmark's token. A misconfigured deployment rejects traffic rather than accepting forgeries.
