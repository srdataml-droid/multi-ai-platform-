# The prototype

One promise: every customer answered in seconds, and nothing said the business did not give
or approve. The dashboard shows only what serves that loop.

## What an owner sees

| Screen | What it is for |
|---|---|
| Inbox | Every conversation; "Needs you" filters to the ones waiting on a person |
| Approvals | Bookings and replies waiting for Approve, change or Reject |
| Schedule | Bookings by day; mark who came |
| Customers | Everyone who has been in touch; export or erase one |
| Settings | Hours, services, what customers ask (FAQs), booking types, channels, team, website chat |
| Setup, Billing | Owners only |

## Kinds of business

| At sign-up | Demo business to try | Asks first |
|---|---|---|
| Trades (heating, plumbing, electrical) | `owner@demo-hvac.test` | Name, problem, how old the system is, anyone vulnerable at home, postcode, phone, when |
| Dental practice (UK) | `owner@demo-dental.test` | Name, new or existing patient, reason; symptoms, pain and funding kept private; phone, when |
| Property damage restoration | `owner@demo-restoration.test` | Name, what was damaged, is it still happening, insurer, address (private), phone, when |
| Any other appointment business (salon, cleaner, tailor, clinic) | sign up to try | Name, what they need, when |

Each business can rewrite these questions in Settings → Booking types.

## Parked, not deleted

Work queue, Analytics, Stock counting, the no-show and approval-model guesses, answering
phone calls, your own agent (agent API) and the booking bridge keep their code, pages and
tests. They show again on a web deployment with `NEXT_PUBLIC_NOVAXIS_EXTRAS=1`
(Vercel → novaxis-web → Environment Variables, then redeploy). The browser tests run with it
on so the parked parts stay working; the menu without them is checked in `app/menu.test.ts`.
