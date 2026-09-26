# ADR 0006: The worker turn is one call with proposal tools, not an agent loop

- Status: accepted
- Date: 2026-09-26
- Chunk: 3

## Context
The model must be able to say things and want things (book, escalate, hand off). The usual
pattern is an agentic loop: the model calls a tool, the code runs it, the result goes back,
repeat. That puts side effects inside the model's turn and makes "a human approves anything
risky" a special case bolted on afterwards.

## Decisions
1. **One LLM call per turn.** The model gets proposal tools; each `tool_use` block becomes an
   `action_proposals` row and nothing runs inside the call. The text block is the reply. The
   gate (Chunk 4) decides what executes and when. `extract_fields` is the one exception: it
   only records what the customer said, so it applies immediately.
2. **Context from rows, every time.** History is rendered as plain alternating text turns from
   `messages`, never as raw content blocks. This sidesteps the API rule that every tool_use
   needs a tool_result, keeps the transcript human-readable, and means a turn is reproducible
   from the database.
3. **Stable prefix cached.** The pack's system prompt carries the cache breakpoint; tenant facts,
   the summary and the first-reply hint come after it. Nothing time-varying goes before the
   breakpoint.
4. **Emergency keywords before the model.** A hard-coded phrase list per pack short-circuits
   the LLM entirely. The dangerous branch has no model in it.
5. **Claims are verified.** A reply that says "booked" without a `propose_appointment` call
   creates a medium-risk `verify_claim` proposal in `awaiting`, so a person sees it.
6. **Queue on Postgres.** `SELECT ... FOR UPDATE SKIP LOCKED` over `jobs`, a lease with
   `locked_at`, stale-lease reclaim, and backoff 10s/60s/300s. Three failures mark the
   conversation `waiting_human` and stop. No Redis.
7. **Models by task, from settings.** `worker_turn` defaults to `claude-sonnet-5` on cost
   grounds for a front-desk reply; `classify` and `summarise` to `claude-haiku-4-5`. The
   Anthropic SDK reference defaults to `claude-opus-5`; switching is one environment variable
   (`NOVAXIS_MODEL_WORKER`) and evals (Chunk 13) decide per pack. Effort is `low` for the same
   reason; thinking stays at the model's adaptive default.
8. **Tracing** is a structured log line per call carrying tokens, latency, tool names and
   ids, never message text. A Langfuse exporter is deferred to Chunk 13 alongside evals, so the
   dependency arrives with the code that reads it.

## Deferred
- The 20-second "one moment" holding message and the 60-second hand-off. Today a call that
  exceeds the client timeout fails the job, which backs off and, after three attempts, hands
  to a human. Revisit when real latency numbers exist.

## Consequences
- Adding a proposal kind is a schema entry in the pack's tool list plus an executor (Chunk 4).
- The model cannot see tool results, so anything it must know (availability, prices) is put
  in the volatile system block by code, not fetched by the model.
