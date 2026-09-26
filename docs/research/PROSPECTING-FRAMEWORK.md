# Prospecting Framework: 100 candidates a day, human-sent, rule-compliant

> The goal from the brief: identify 100 businesses a day that could use the worker and reach
> out. This framework separates **finding** (can be automated) from **contacting** (human sends,
> always) and keeps both inside UK and US rules. Rules are tagged `[VERIFY]` in
> `docs/research/RESEARCH-BRIEF.md` section 4 and must be checked before the first send.

## 1. Sequence

Do not start outreach before Chunk 9 gives you a demo you can show. Outreach without a demo
burns the list. Weeks 1 to 8 are for building; run the **finding** side in the background so
week 9 opens with a warm list.

## 2. Who to target first

Score every candidate on four things. Reach out only to businesses that score 3 or 4.

| Signal | Why it predicts a yes | How to check in under a minute |
|---|---|---|
| Owner-operated, 2 to 15 staff | Big enough to lose money on missed contacts, small enough that the owner decides | Website "about" page, company registry, review count |
| Visible intake pain | Reviews mention "couldn't get through", "no reply", "left a message"; website has a form but no chat; phone goes to voicemail after hours | Read the last 10 reviews; call once after hours |
| Uses a system you can integrate with | Chunk 11 is cheaper | Job ads mention the software; website booking widget reveals the vendor; ask in discovery |
| High job value | The worker pays for itself on one recovered job | HVAC installs, dental private treatments, restoration claims |

Region order: UK first (founder's own choice, one regulatory regime, one time zone close to Lagos),
then US metro areas with high HVAC seasonality or high private-dental density, then anywhere
English-speaking with card payments.

## 3. Finding: the daily list

Automate the finding with a small script in `tools/prospecting/` in the new repo. It is not
part of the product and never touches tenant data.

Sources that permit business lookups `[VERIFY each source's terms of use before scripting]`:
- Business directories and maps listings for the category and area, with review counts and hours.
- Company registries (UK Companies House has a public API) for size and age.
- The business's own website: contact page, booking widget vendor, whether a chat exists.
- Trade-body member directories where public.
- Job boards: a business hiring a receptionist or dispatcher has the exact pain.

Output: a sheet with one row per business, the score, the public contact route (email, contact
form, business social page), the named owner if the business publishes it, and the evidence
line ("3 of last 10 reviews mention unanswered calls").

Daily target: 100 rows found, roughly 30 to 40 scoring 3 or above. Automate the finding, but
have a human eyeball every row before it enters the contact queue (30 minutes a day).

## 4. Contacting: human-sent, three channels

**Rules built into the process, not left to memory:**
- A human sends every message. No bulk tool, no automation on the send side, until a
  compliance review says otherwise.
- Business email to a company address, with a clear opt-out and your real name and address.
  Sole traders and partnerships in the UK count as individuals under PECR `[VERIFY]`; for them,
  use the contact form or a phone call instead of unsolicited email.
- Record every contact in the sheet: date, channel, message version, response. This is also
  your legitimate-interests evidence.
- One follow-up after 5 working days, then stop. A no is a no.
- Never contact a business's customers. Never use anything gathered from a person's post.

**Channel A: email to the business address.** Four lines:
1. Evidence line about their business (the review pattern, the after-hours voicemail).
2. One sentence on what the worker does in their words ("answers and books while you're on a job, you approve every booking").
3. One number from your own pilot once you have one; until then, no numbers.
4. One ask: a 15-minute call or a 3-minute video of the demo on their own website.

**Channel B: contact form or business social page message.** Same four lines, shorter.

**Channel C: phone call, for the top 5 a day.** Script: who you are, the evidence line, the ask.
If they say send details, use Channel A with their name.

## 5. Discovery call, 15 minutes

Ask, do not pitch:
1. How do calls and messages reach you today, and what happens after hours?
2. What software runs your diary or jobs?
3. What would a booked job or appointment need to look like for you to trust it?
4. What must never happen? (This becomes their risk-rule overrides.)
5. If this worked, what number would you look at in a month to know?

End with the pilot offer from `docs/research/RESEARCH-BRIEF.md` section 5: setup fee waived, 60 days, three
agreed numbers, cancel any time.

## 6. Weekly numbers to track

| Number | Target while learning |
|---|---|
| Found | 500 a week |
| Qualified (score 3+) | 150 |
| Contacted | 100 |
| Replies | measure, do not guess |
| Discovery calls | measure |
| Pilots started | 1 in the first month after the demo exists |

One pilot, run well, is worth more than the next 500 contacts. The first pilot's numbers become
the third line of every later message.

## 7. What the platform does for outreach later

None of the above uses the AI worker to contact prospects. Later, once tenants exist, the
worker can help each **tenant** with their own customers: review replies, recall campaigns to
consented patients, estimate follow-ups. That is inside the tenant's relationship with its own
customers and inside the gate. Novaxis finding its own customers stays a human job.
