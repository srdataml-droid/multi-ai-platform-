# Signing in

One sign-in page for everyone. Pick who you are; your account decides what you can do.

| Who | Picks | Signs in with | Sees |
|---|---|---|---|
| Business owner | Business owner | Email + the login code shown once at sign-up | Everything, including Setup and Billing |
| Team member | Team member | Email + the code the owner gave them | Inbox, Approvals, Schedule, Customers, Work queue, Stock, Analytics, Settings (read only) |
| View only | Team member | Same as a team member | The same pages, read only; private answers show as `[redacted]` |
| Novaxis | "Novaxis staff" link | Operator email + operator passcode | The console of all businesses; enter one for an hour, recorded in its audit log |

Demo businesses (`owner@demo-hvac.test` and the others) sign in with the shared demo
passcode. Locally (`NOVAXIS_ENV=local`) any seeded email signs in without a code.

## Adding your team

Settings → Team: type their email, choose **Team** or **View only**, press Add. On the
hosted site a sign-in code appears once; send it to them. Lost code: **New code** next to
their name gives a fresh one and the old one stops working. Only owners add people or
issue codes (`POST /settings/staff`, `POST /settings/staff/{id}/code`).

## On a phone

The dashboard is built for phones first: tabs at the bottom (Inbox, Approvals, Schedule,
Customers) and everything else under **More**. Add it to the home screen to get alerts
(Settings → Alerts).
