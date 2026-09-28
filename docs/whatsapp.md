# WhatsApp

Customers message the business on WhatsApp and the assistant answers there. It's the same
assistant as every other channel: packs, approval step, emergency pre-check, bookings,
hand-offs.

Built on **Meta's WhatsApp Cloud API** directly (no middleman). Code:
`packages/core/novaxis_core/channels/whatsapp.py`, routes `GET/POST /inbound/whatsapp`.

## What it handles

| Customer sends | What happens |
|---|---|
| Text | A normal message |
| Photo, document, video, sticker (with or without caption) | Stored like any photo: downloaded with the WhatsApp token, shown to staff |
| Voice note | Transcribed with Whisper before the assistant answers (docs/voice-notes.md); without speech to text set up, the assistant asks the customer to type |
| Button or list reply | The chosen option's text |
| Location | "Location: name, address, lat,long" |
| "STOP" / "unsubscribe" | Opted out, as for SMS and email ("cancel" with a booking cancels the booking instead) |

- **Security:** every POST must carry Meta's `X-Hub-Signature-256` over the exact body,
  checked with the app secret. The one-off setup handshake needs the verify token.
- **Replays:** Meta retries; each message is stored once (by its WhatsApp id).
- **Several messages in one webhook** are all taken; delivery and read receipts are ignored.
  A message for a business that has not set up WhatsApp is dropped with a log line (a 200,
  so Meta does not retry it for days).
- **One customer:** the WhatsApp id is the phone number, so someone who texts, calls and
  uses WhatsApp is one contact.
- **Routing:** each business has its own WhatsApp phone-number id from Meta, unique per
  business (migration 0016). Owners cannot change it themselves; it is set by the
  operator, like the SMS number.

## The 24-hour rule and the update template

WhatsApp allows free-form messages only within **24 hours of the customer's last message**.
After that, a business may only send a **template** that Meta has approved [VERIFY current
policy]. This matters most for reminders, follow-up chasers (they fire 24 hours or more
after the last message, so always outside the window), and booking news that arrives
later (a staff approval, a cancellation, new times after a diary clash).

Before every WhatsApp send we check the window ourselves:

- **Inside 24 hours:** sent as a normal message.
- **Outside, and the business has an approved update template:** the message goes out
  **whole** inside the template. When the customer replies, the window opens again and
  the conversation carries on normally.
- **Outside, no template (or the message is too long for one):** not sent. The
  conversation goes to a person and staff are alerted. Never retried, never cut short.

One template covers every case, because the message itself is a parameter:

| Field | Value (submit exactly this in Meta's WhatsApp Manager) |
|---|---|
| Name | `novaxis_update` |
| Category | **Utility** |
| Language | English (UK), `en_GB` |
| Body | `Hello {{1}}, this is {{2}} about your enquiry: {{3}} Reply to this message to continue the conversation.` |
| Sample for {{1}} | `Sam` |
| Sample for {{2}} | `Bright Smile Dental` |
| Sample for {{3}} | `Reminder: your check-up is on Tue 3 Oct at 09:00.` |

`{{1}}` is the customer's name (or "there"), `{{2}}` the business name, `{{3}}` the
message, with new lines flattened (Meta does not allow them in parameters [VERIFY]).
Messages longer than 700 characters go to a person instead.

What the customer sees, for example:

> Hello Sam, this is Bright Smile Dental about your enquiry: Reminder: your appointment is
> in two days. Reply C to confirm or CHANGE to rearrange. Reply to this message to continue
> the conversation.

- **Transcript:** staff see the message as written; the audit log records
  `whatsapp.template_sent` against it (which template, which language).
- **Cost:** Meta charges for template messages; utility templates are priced per message
  and by the customer's country [VERIFY current pricing]. Every chaser and reminder sent
  outside the window is one charge **to the WhatsApp Business Account owner**.
- **Meta review risk:** Meta can reject a template whose main content is a parameter, or
  re-categorise it as Marketing (higher price) [VERIFY]. If `novaxis_update` is rejected,
  nothing breaks: messages outside the window keep going to a person. Tell the developer,
  and fixed-text templates (a reminder with date and time only) can be added.

Switching it on for a business, once Meta shows the template as **Approved**: the operator
adds to the business's settings

```json
"channels": {"whatsapp": {"config": {"phone_number_id": "<digits>",
  "update_template": {"name": "novaxis_update", "language": "en_GB"}}}}
```

Templates belong to a WhatsApp Business Account, so each account the businesses use needs
its own approved copy.

## Turning it on (founder)

1. **Meta:** create a Meta developer app with the WhatsApp product, and a WhatsApp Business
   Account with a phone number [VERIFY current steps and costs]. Note the **phone-number
   id** (digits, not the phone number).
2. **Access token:** create a system-user permanent token with WhatsApp messaging permission.
3. **Vercel `novaxis-api`** (sensitive variables):
   - `NOVAXIS_WHATSAPP_APP_SECRET`: the app's secret (App settings → Basic);
   - `NOVAXIS_WHATSAPP_VERIFY_TOKEN`: any long random string you choose;
   - `NOVAXIS_WHATSAPP_ACCESS_TOKEN`: the system-user token.
4. **Webhook in Meta:** URL `https://novaxis-api.vercel.app/inbound/whatsapp`, verify token
   = the same string. Subscribe to the **messages** field.
5. **The business:** the operator sets `channels.whatsapp` to enabled with
   `{"phone_number_id": "<digits>"}` in the business's settings.
6. Submit the update template (above); when Meta approves it, add `update_template`.
7. Send the number a WhatsApp message.

The demo businesses have test phone-number ids (`100000000000001` to `...003`), so the
webhook and the flow can be tested without Meta.
