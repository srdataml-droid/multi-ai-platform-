# Booking proposal contract

This is a proposed implementation contract, not an existing API or approved business service catalogue.

## Required inputs

- Job: tenant, contact, reported symptom, service category, verified service profile/version, uncertainty, required skills/qualifications, crew/equipment, access window and prerequisites.
- Location: customer-confirmed address, coordinates, resolution quality, source and service-area decision. Use approximate location only for rough planning; do not claim exact travel.
- Resources: engineer IDs, valid qualifications, working shifts, diary busy intervals, leave, protected breaks, company closures and start/end base locations. A staff account does not necessarily represent a schedulable engineer.
- Duration: approved planning minutes, minimum/typical/range where known, evidence source, comparable-job count and cleanup/admin allowance. Unknown becomes staff review.
- Travel: predecessor/successor locations, mode, departure, travel minutes, estimate type (static/traffic-aware), routing provider timestamp and uncertainty buffer. Share only the minimum authorized location data with the provider.
- Sources: calendar/sheet freshness and version, authority for conflicting fields, tenant timezone and expiry of cached evidence.

## Feasibility

For proposed service start S and service finish F:

1. previous_finish + inbound_travel + arrival_allowance <= S.
2. F = S + approved_planning_duration + cleanup_admin_allowance.
3. F + outbound_travel + onward_allowance <= next_start; when last in day, apply the business's end-of-shift/return-base rule.
4. Travel and service occupancy respect shifts, leave, protected breaks, crew/equipment limits and customer windows. A break cannot be counted as travel time.
5. Every assigned engineer meets the service qualifications. Multi-person work consumes each person's capacity.
6. Recheck constraints and external-calendar version when creating a hold and confirming. Reserve assigned resources atomically in the local system and use provider reconciliation/idempotency for cross-system races.

When a critical input is absent, emit `needs_staff_estimate`, `needs_location_confirmation`, `needs_schedule_refresh` or `needs_dispatch_review`. Do not create a confirmed appointment from incomplete evidence.

## Proposal output

- State: requested / proposed / held / awaiting_review / confirmed / failed / cancelled.
- Service category and uncertainty; duration and evidence.
- Assigned resources, start/finish, arrival window and tenant timezone.
- Inbound/onward travel, allowances, relevant constraint checks and source versions.
- Plain reason for the offer; alternatives; missing inputs if provisional.
- Gate decision, hold expiry, idempotency key, external reference and delivery state.

## Tabletop checks

| Scenario | Required behavior |
|---|---|
| Prior visit ends 10:00; 35-minute journey and 10-minute arrival allowance | Do not offer 10:30; earliest candidate service start is 10:45 if all other constraints pass |
| Service ends 12:00; next visit starts 12:20, journey 30 minutes | Reject insertion even if the customer-facing calendar shows a gap |
| Protected break 12:00-12:30 | Travel or service cannot occupy the break; find another valid slot |
| Fault description has no approved duration profile | Request a staff estimate or use an approved diagnostic service, never invent a repair length |
| One engineer is on leave, another lacks the required qualification | Neither is a feasible assignment, regardless of customer value |
| Calendar write succeeds, customer notification fails | Keep external booking reference and retry notification only |

Times and durations above are synthetic feasibility examples, not recommended HVAC service lengths.
