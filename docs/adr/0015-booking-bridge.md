# ADR 0015: The booking bridge, a vendor-neutral system of record

- Status: accepted
- Date: 2026-09-26

## Context
Chunk 11 writes bookings into the software the pilot business already uses. The founder
has not chosen the pilot or named its vendor yet. The research brief lists candidates with
public APIs, but their API terms are `[VERIFY]` items. For restoration it already
recommends a CSV and email bridge first. The build plan allows that bridge whenever the
vendor has no public API we can use.

## Decisions
1. **Build the bridge first, for any vendor.** `novaxis_core.bridge.BookingBridge`
   implements `SystemOfRecord`. While the bridge is connected, it is the tenant's system of
   record and takes precedence over Google Calendar, because the vendor's diary is the
   business's real diary. A vendor with a usable API gets its own adapter later behind the
   same interface; the scheduler does not change.
2. **Writes go through a person.** Each create, move or cancel becomes a `bridge_tickets`
   row with a short, stable reference (`NX-` plus 6 hex characters, derived from the
   confirmation's idempotency key). A `bridge_email` job emails the office a plain,
   structured message: action, reference, time with its time zone, the vendor's job type,
   and the customer's name, phone and email. The same ticket appears on the Schedule page
   with an "Entered" button, which writes an audit row. With no office email or email
   provider configured, the ticket still appears in the dashboard, marked "not emailed".
   An approved booking therefore reaches the office within one job cycle.
3. **Reads come from the vendor's daily diary export (CSV).** The parser accepts:
   - common column names;
   - ISO dates, or numeric dates in day-first or month-first order (a per-tenant setting);
   - 12- or 24-hour times;
   - a separate date column plus time and duration columns.

   It skips cancelled rows and reports bad rows by line number. A file with no usable
   rows never replaces the stored diary. The upcoming 120 days are kept, up to 5,000
   blocks, on the integration row. Availability subtracts those blocks.
4. **Conflicts: the vendor wins, and we re-offer.** On import, a vendor block counts as
   ours if it carries our `NX-` reference or matches our booking's exact start and end.
   Any other overlap means:
   - held offers under it are withdrawn;
   - a confirmed booking is cancelled;
   - the office gets a cancel ticket;
   - the customer is told in the same conversation and offered new held times through
     the normal flow.
5. **Service codes map to vendor job types** in the bridge settings (for example
   `repair_visit` to "Callout"). Unmapped services use their display name.
6. **Health.** The bridge is unhealthy until the first export arrives, and again when the
   last export is more than 36 hours old. The operator console lists that as a problem.
   Token expiry and permission loss, the plan's health checks for API vendors, apply to
   the first API adapter.

## Consequences
- A pilot can start on any booking software this week. The cost is one short manual step
  per booking for the office, plus one upload a day.
- Between exports, a slot filled directly in the vendor tool can still be offered. The
  next import catches it and re-offers, so the customer sees one apology rather than a
  double booking on the day. More frequent uploads shrink that window.
- Exports can also arrive by inbound email. That path is a small follow-up on top of the
  Postmark inbound route; for now the upload is manual.
- The ticket email carries customer contact details to the office's own mailbox. It never
  carries sensitive intake fields.

## Dissent recorded
- **Simplifier:** a manual "Entered" step and a daily upload look like busywork next to a
  real API. *Overruled for now:* no vendor is named, and the bridge works on day one with
  any of them. When the pilot names its vendor, the API adapter replaces the manual steps.
- **Undertaker:** people forget to upload the export, and the diary goes stale. *Mitigated:*
  the health check and the operator console flag it after 36 hours.
