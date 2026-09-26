# ADR 0011: Scheduling through one system-of-record interface, with holds and a calendar-first write

- Status: accepted
- Date: 2026-09-26
- Chunk: 8

## Context
The worker must offer real times, never double-book, and put bookings where the business
already looks. Different tenants have different diaries; the first pilot may have none.

## Decisions
1. **One `SystemOfRecord` interface**: `busy`, `create_booking`, `update_booking`,
   `cancel_booking`, `health`. Google Calendar is the first implementation; a business-hours
   calendar is the fallback when nothing is connected, so a pilot can start on day one and
   connect a calendar later. Chunk 11 adds the vendor of the pilot's choice as another adapter.
2. **Availability = business hours minus busy minus ours.** Slots are cut at the service's
   duration inside the tenant's opening hours in the location's time zone, minus the system of
   record's busy times, minus our own held or confirmed appointments.
3. **Holds, expiring lazily.** Offering a slot writes an `appointments` row in `held` state
   that expires after ten minutes. Availability and confirmation ignore expired holds, so no
   sweeper job is needed. Two conversations cannot be offered the same slot; the second is
   offered the next one.
4. **The window parser is deterministic.** "Tomorrow morning", "Tuesday afternoon", "asap"
   become a search window in code, not in the model. Unknown words widen the window, never
   narrow it, so the worst case is more options rather than a wrong day.
5. **Calendar first, then the row, then the message as a job.** `confirm` writes the external
   booking (idempotent on the proposal id, also carried as an extended property on the Google
   event so a retry finds it), then flips the row, then enqueues the confirmation message and
   the pack's reminder steps. A failed send retries alone; the booking is never repeated.
6. **Two decisions per booking by default.** `propose_appointment` (offer slots) and
   `confirm_appointment` (book) are both medium risk. A tenant can lower proposing to low,
   since offering times is harmless, and mark services `auto_confirm` to skip the second
   decision. That maps to how much they trust the worker, per service.
7. **Reminders are workflow steps bound to the appointment.** `before_appointment` steps run
   at `starts_at - after`; cancelling or moving the appointment marks them done and, on a
   move, schedules them afresh.
8. **OAuth tokens** are sealed with the sensitive-fields key on the `integrations` row and
   refreshed in the worker; the web never sees them. Disconnecting wipes the credentials.

## Deferred
- Time-zone edge cases across DST changes on the day of an appointment.
- Waitlist fill (dental) and no-show recovery need attendance status, which arrives with the
  dashboard's "mark as attended / no-show" in Chunk 9.

## Consequences
- The model never computes a time. It sees numbered offered slots with ids and passes an id
  back. A hallucinated time cannot become a booking.
- Google API field names were written from the documented shape and are tagged `[VERIFY]`
  for the first real connection.
