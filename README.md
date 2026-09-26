# Novaxis AI Worker Platform

A multitenant AI worker for small service businesses (HVAC, dental, restoration). It answers
messages, does intake, proposes bookings, and a human approves anything risky. One core, one
dashboard, per-industry packs. See `CLAUDE.md` for the rules and `docs/ARCHITECTURE.md` for the design.

## Status

Chunks 0 to 5 done: skeleton and CI; core tables with row-level security; JWT auth; three channel adapters; the worker loop and LLM turn; the approval gate and executors; packs as validated folders with an intake engine, service-area check, idle-customer workflows and golden evals; three packs (HVAC, dental, restoration) on one core, each passing 5 of 5 evals with the scripted model; sensitive intake fields encrypted at rest; customer photos and attachments stored under the tenant's prefix; scheduling with held slots, a deterministic window parser, Google Calendar as the system of record (business hours as fallback), idempotent confirmation and reminder steps. Phase 1's definition of done is met through the API. Chunk 9 (the dashboard) is next.

## Where things are

| Path | What it is |
|---|---|
| `CLAUDE.md` | Standing rules Claude Code reads every session: stack, layout, working rules, definition of done |
| `docs/ARCHITECTURE.md` | Tenancy, data model, worker loop, approval gate, packs, integrations, deployment |
| `docs/BUILD-PLAN.md` | Fifteen build chunks (0 to 14), one Claude Code session each, with tests and a definition of done |
| `docs/research/RESEARCH-BRIEF.md` | Existing tools, workflows, compliance map, pricing shape, open source vs paid. Claims tagged `[VERIFY]` are unchecked |
| `docs/research/PROSPECTING-FRAMEWORK.md` | The 100-a-day outreach system, human-sent and rule-compliant |
| `docs/adr/` | Architecture Decision Records, written as chunks land |
| `docs/demo/` | Put the old demo here so Chunk 0 can mine it for reuse |

## How to build it

1. Open Claude Code (Opus 5.5) in this repo.
2. Paste **Chunk 0** from `docs/BUILD-PLAN.md`. One chunk per session, never several at once.
3. Review every diff. Run `make test` yourself before calling a chunk done.
4. Do not start the next chunk until the current one is committed green.

## Ground rules

- Smallest thing that works. Every chunk ships something you can run.
- A human approves anything risky. The worker proposes; a person confirms.
- Tenant isolation lives in the database, not in application code.
- Verify before citing. No `[VERIFY]` item goes into a pitch until checked against the primary source.
- No local model training. Every LLM call goes to an API.
