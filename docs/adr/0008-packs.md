# ADR 0008: Packs are folders of data plus one rules file; the intake engine decides, the model phrases

- Status: accepted
- Date: 2026-09-26
- Chunk: 5

## Context
Three verticals share one core. Each needs its own vocabulary, questions, emergencies,
follow-ups and dashboard columns, and none of them should be able to reach into core code.

## Decisions
1. **A pack is a folder** under `packages/packs/novaxis_packs/<id>/`: `manifest.yaml`,
   `intake.yaml`, `vocabulary.yaml`, `workflows.yaml`, `dashboard.yaml`, `prompts/system.md`
   and an optional `rules.py`. `novaxis_core.packs.load_pack` validates every file with
   Pydantic and reports `file: key: message`. An unknown pack id degrades to `generic`.
2. **Two hooks only.** `rules.py` may define `classify(kind, params, ctx)` for the gate and
   `is_emergency(text)` for the pre-check. Both are plain functions; neither gets a database
   session. The HVAC rule treats "no heating" plus a vulnerable occupant as an emergency and
   raises a vulnerable-household job to medium so a person sees it first.
3. **The engine decides, the model phrases.** `intake.py` reads the ordered questions and the
   conversation's extracted fields, validates answers (choice, phone, postcode, yes/no), and
   tells the model, in the volatile system block, exactly which key to ask for next and how
   to record it. The model's wording stays natural; what gets asked is deterministic. Invalid
   answers are asked again; skip logic is `skip_if: {key: value}` and nothing cleverer.
4. **The engine finishes what the model forgets.** When intake is complete and the model did
   not call `propose_appointment`, the turn creates the proposal from the extracted fields
   using the manifest's service-code map. The gate still decides its risk.
5. **Service area is a core feature keyed by the pack.** `service_area_field` names the intake
   key; outside the tenant's prefixes, the reply becomes the pack's decline text and a
   low-risk `hand_to_human` is proposed.
6. **Workflows are jobs.** Idle-customer steps are scheduled after every reply with
   `run_after`, superseded on the next reply, and re-checked when they fire. Their messages
   are `reply` proposals, so consent and safeguarding rules apply to a 24-hour chase exactly as
   to a live reply.
7. **Evals are the pack's acceptance test.** Five YAML conversations per pack run through the
   real ingest and turn code. With the scripted model they are deterministic and part of the
   test suite; with the real model (`make evals-real`) only the expectations are checked.
   A pack must hold the threshold in `evals/thresholds.yaml` before a paying tenant gets it.

## Consequences
- Adding a pack is a folder and a seed tenant. No core change.
- The intake question list is the product for that vertical. Changing it changes what the
  business receives; review changes to `intake.yaml` as product decisions.
- "Missed-call text back" from the plan needs voice (Phase 3); the HVAC workflows ship the
  estimate chases at 24h and 72h and a close at 7 days.
