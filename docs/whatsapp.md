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
| Voice note | Not transcribed yet. The assistant is told a voice note arrived and asks the customer to type |
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

## The 24-hour rule

WhatsApp allows free-form messages only within **24 hours of the customer's last message**.
After that, a business may only send a **template** that Meta has approved [VERIFY current
policy and pricing]. Before every WhatsApp send we check the window ourselves:

- **Inside 24 hours:** sent.
- **Outside:** not sent. The conversation goes to a person and staff are alerted, instead
  of Meta rejecting it silently. This mainly affects reminders and follow-ups timed days
  later.

**Not built yet: templates.** To send reminders on WhatsApp after 24 hours, create and get
approval for templates in Meta's WhatsApp Manager (e.g. "Reminder: your {service} is on
{date}. Reply C to confirm"), then add a template send to the adapter. Until then, reminders
for WhatsApp customers go to staff.

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
6. Send the number a WhatsApp message.

The demo businesses have test phone-number ids (`100000000000001` to `...003`), so the
webhook and the flow can be tested without Meta.
