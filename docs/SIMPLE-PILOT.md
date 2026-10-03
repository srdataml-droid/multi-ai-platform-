# Novaxis simple pilot

This branch does not delete the larger Novaxis platform. It narrows the visible product to
one workflow that can be tested with a real service business:

```
customer request
  -> Novaxis intake
  -> basic business / service-area / availability checks
  -> human approval
  -> confirmed booking
```

## Visible pilot product

The main navigation contains only:

- Inbox
- Approvals
- Schedule
- Settings

Settings shows only the controls needed to run that loop: business name and worker switch,
opening hours, services, service area, calendar connection and website-chat installation.

The deeper capabilities remain in the repository but are not part of the pilot interface:
contacts administration, analytics, work queue, billing, approval-learning UI, stock,
booking bridges, advanced risk configuration, team administration and other automation.

New owners can still pass through onboarding because the core loop needs business hours,
services and an initial service area before it can work.

## Pilot success condition

The first milestone is not autonomous dispatch.

A successful pilot is:

1. a real customer request arrives,
2. the required intake is captured,
3. Novaxis produces the correct approval request,
4. a human approves or changes it,
5. the booking appears correctly in Schedule,
6. the customer receives the correct confirmation.

Only after this is reliable should the parked operational-control features be brought back
into the visible product.
