# The MVP: what works today and how to show it

Status as of 2026-09-28, checked on the live site (`novaxis-web.vercel.app`,
`novaxis-api.vercel.app`) with the demo heating business (`demo-hvac`).

## The journey

A customer describes a problem, the assistant collects the details, staff approve, the
customer picks a time, the booking is confirmed.

| Step | Live check |
|---|---|
| Customer writes in the website chat; the assistant says it is an AI and asks questions | ✅ |
| Customer answers (in one message or several); every answer is recorded | ✅ 8 of 8 fields |
| Booking request appears in **Approvals**, with the model's approve/reject guess | ✅ |
| Staff approve; the customer is offered times from the diary | ⏳ needs a staff click |
| Customer picks a time; the booking is confirmed and shows in **Schedule** | ⏳ after the step above |

How answers are recorded: before each reply, a small JSON call to the model pulls the
customer's answers into the intake fields (`NOVAXIS_INTAKE_EXTRACTION=true`, turn.py). Open
models on Ollama Cloud rarely call tools themselves; with this, bookings work anyway. It
costs one extra model call per customer message.

## Channels

| Channel | State | What it needs |
|---|---|---|
| Website chat | Live | Nothing |
| WhatsApp through Twilio | Built, not switched on | Twilio sandbox number and its webhook (docs/whatsapp.md) |
| SMS | Built | A Twilio phone number with its webhook set |
| Phone calls | Built | The same Twilio number, voice webhook set (docs/voice.md) |
| Email | Built | A Postmark account |
| WhatsApp through Meta | Paused | Meta business verification; use Twilio instead |

Photos and voice notes are kept in Postgres (`NOVAXIS_STORAGE_BACKEND=db`, migration 0021)
and voice notes are transcribed with Whisper through Together (docs/voice-notes.md).
Bookings go into the built-in business-hours diary until the owner connects Google
Calendar.

## Five-minute demo

1. Open `https://novaxis-web.vercel.app/widget-demo.html` (a sample page with the demo
   heating business's chat widget) and write: *"My boiler keeps banging when the
   heating comes on."*
2. Answer the questions, or paste everything at once: *"I'm Sam. Started yesterday, it's
   about 10 years old, nobody vulnerable, postcode SW1A 1AA, 07700 900123, tomorrow
   morning."*
3. In the dashboard (demo sign-in), open **Approvals**: the booking request is there with
   the details and the approval model's guess. Approve it.
4. Back in the chat, the customer is offered times. Reply with one of them.
5. **Schedule** shows the booking. **Conversations** shows the whole exchange, with the AI's
   actions in the audit trail.

Things worth saying in a demo: nothing is booked without a person approving it; an
emergency ("I can smell gas") goes straight to the on-call number before the AI answers;
the customer can ask for a person at any time.

## Known limits

- Each customer message takes about 3–5 s to answer (two model calls). Fine for chat and
  WhatsApp; phone calls feel slow.
- Media in Postgres suits a pilot. Move to Supabase Storage before the database nears its
  plan limit (check the Supabase dashboard).
- WhatsApp replies more than 24 hours after the customer's last message go to a person
  (no Twilio templates yet).
- Billing runs in demo mode until the Stripe webhook secret and price ids are set.
