# Booking types

Each business decides what it books, for whom, and what it asks before a time is offered.
A new patient's first visit, an existing customer's follow-up and a quote can each ask
their own questions and book their own service. Every business has its own; nothing is
shared between businesses.

## Who sets them up

- **The business itself:** Settings → Booking types. "Start from our standard questions"
  copies in the questions for its trade to edit; "Add a booking type" starts blank.
- **Novaxis, helping them:** Operator console → Tenants → enter the business (one hour,
  recorded in its audit log) → Settings → Booking types. Same editor, same checks.

## What each type holds

| Field | Meaning |
|---|---|
| Name customers see | Also the option the customer picks, e.g. "New patient check-up" |
| Who can book it | Anyone, new customers only (never had a confirmed booking) or existing customers only |
| Books this service | The service (and so the length) the booking request is for |
| What we ask first | The questions, in order: words, one option from a list, yes/no, phone, email, postcode (checked against the service area), or when they would like it |

When more than one type fits the customer, the assistant first asks the question set in
Settings (default "What can we help you with?") with the types' names as the options. A
customer who says everything in one message ("I'm new, I'd like a check-up, I'm Ann, Monday
morning") has the type and its answers read from that one message. With no types set, every
customer gets the trade's standard questions, as before.

Staff see the type on the booking request in Approvals ("New patient check-up: proposed by
intake engine"), and an agent on the agent API gets it in the conversation context
(`intake.booking_type`, with every question for that type).

Settings refuse, with a message, a type that books a service the business does not have,
two types with the same name, a choice question with fewer than two options, and two
questions in one type that would store their answers under the same key.

Code: `packages/core/novaxis_core/booking_types.py` (`intake_for`), settings model in
`tenant_settings.py`, editor in `apps/web/components/BookingTypesCard.tsx`.

## Private answers

Tick **private** on a question for health, money or other personal details. Those answers
are handled exactly like the trade's own sensitive questions (the dental symptoms, say):

- encrypted before they are stored (`enc:v1:`, Fernet, key in the environment only);
- shown to owners and staff, `[redacted]` to read-only viewers;
- held back from your own agent ("(held by the business)") and from reports;
- still read by the built-in assistant, so a booking completes as normal.

Ticking private on a question that already has answers encrypts those answers when the
settings are saved. Unticking it later leaves stored answers encrypted (and hidden from
viewers) but readable by staff. Standard questions copied with "Start from our standard
questions" keep their private tick. The customer's messages themselves are encrypted at
rest too (docs/encryption.md).
