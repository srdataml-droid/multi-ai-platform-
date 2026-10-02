# ADR 0016: Technician eligibility lives in tenant settings first

**Status:** accepted  
**Date:** 2026-10-02

## Context

Novaxis already checks business hours, service area, calendar conflicts, notice time,
buffers, protected time and a daily booking cap. That is not enough for a service business
with several field workers: a slot can be free while nobody who is qualified for that job
is working.

The product needs to answer two operational questions before it offers a time:

1. Which people can handle this service?
2. Is at least one of them normally working that day?

This is still rules-aware booking, not autonomous dispatch. Travel routing, per-technician
job limits and automatic assignment are separate decisions.

## Decision

Add optional `technicians` to validated `TenantSettings`.

Each technician has:

- a stable code
- a display name
- the service codes they can handle
- their normal working days

The scheduler treats this as an additional availability rule. When technician profiles are
configured, a day is offerable only if at least one technician both supports the requested
service and normally works that day.

When no technician profiles are configured, scheduling behaves exactly as before using the
shared business calendar. This keeps existing tenants and vendor-calendar pilots compatible.

Technician profiles are configuration, not dashboard users. A technician does not need a
Novaxis login, and a dashboard user is not automatically a field technician.

## Why settings instead of a new table

For this first capability the data is small, tenant-owned and changed infrequently. Keeping
it in the existing validated settings model avoids a migration and lets us validate service
codes atomically with the rest of business configuration.

A separate resource/dispatch table becomes justified when we add assignment history,
technician-specific calendars, travel time or per-person capacity.

## Consequences

Positive:

- Novaxis stops offering a service on a day when no qualified person is scheduled.
- The rule is deterministic and testable; the LLM does not decide staff capability.
- Existing tenants are unchanged until they configure technicians.

Not included yet:

- choosing or assigning a technician to a booking
- technician-specific working hours inside a day
- per-technician maximum jobs
- travel distance or route optimisation
- on-call rotations

Those should be added only after the pilot proves which of them changes booking decisions.
