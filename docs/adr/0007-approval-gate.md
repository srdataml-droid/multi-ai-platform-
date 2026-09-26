# ADR 0007: The gate is one pure function; executors are the only side effects

- Status: accepted
- Date: 2026-09-26
- Chunk: 4

## Context
"A human approves anything risky" has to be a property of the code, not a habit. It
must survive new packs, new tenants with their own preferences, and a model that phrases
things persuasively.

## Decisions
1. **`gate.decide(kind, params, ctx)` is pure.** It reads plain values, touches no database,
   and is tested as a table of 50+ rows. Policy changes are diffs to that table.
2. **Three layers, fixed order of authority.** Core rules first (opt-out, first contact,
   payments, safeguarding terms); they can only refuse or raise. The pack's rule hook next;
   it can raise freely or lower to the kind's floor. Tenant overrides last; they can lower
   within the floor and raise freely. Nothing lowers below a floor.
3. **Three outcomes, three states.** low means `auto_approved` and executes now. medium means
   `awaiting`, staff are notified by a job, the dashboard shows it. high means `rejected`
   with a reason, and the reply gains one line saying a person will follow up.
4. **The reply is an action.** It goes through the gate like everything else. That is how an
   opted-out contact or a safeguarding hit stops the reply without a special case: the gate
   refuses it and the conversation goes to a human.
5. **`executors.execute()` is the only door.** It refuses any state other than
   `auto_approved` or `approved`, writes an audit row when refused, and every executor ends
   with an audit row. Every action kind has a registered executor (asserted by a test), even
   the scheduling ones that fail loudly until Chunk 8, so nothing routes into a void.
6. **Edits make new proposals.** A staff edit rejects the old row, links it via
   `superseded_by`, and creates a new row that runs through the gate again. The human's edit
   counts as approval unless the gate says high. History is never rewritten.
7. **Emergencies stay low risk.** `escalate_emergency` auto-approves because the dangerous
   branch is not escalating. It alerts every escalation contact on every channel they have
   and records partial failures instead of raising.

## Alternatives considered
- Risk as a column on the pack tool definition: too static, cannot see consent or the
  customer's words.
- Executing medium actions optimistically and undoing on rejection: undo is not possible for
  a sent message or a calendar invite. Rejected.

## Consequences
- The safeguarding term list is blunt on purpose. It will over-trigger on "years old" in
  benign contexts; a false hand-off costs a staff minute, a miss could cost far more. Tune
  with evals in Chunk 13, never by removing the rule.
- `quote_price` needs a tenant `price_list` in settings before it can ever be medium. That
  setting arrives with the dashboard (Chunk 9).
