# Agent API: plug your own agent (e.g. Hermes) into Novaxis

A business can have its customers answered by **its own agent** instead of the built-in
assistant: one built with a Hermes model, the Hermes agent framework, or anything else
that can make HTTP calls. The agent reads conversations and **proposes** actions. The
platform's approval gate decides what actually happens, exactly as for the built-in
assistant.

```
customer ──> Novaxis (channels, emergency check) ──> your agent reads  GET  /agent/v1/...
                                                  <── your agent proposes POST /agent/v1/.../proposals
             Novaxis gate: low risk runs · medium waits for staff · high refused
```

Code: rules `packages/core/novaxis_core/agent.py`, routes `apps/api/novaxis_api/routes_agent.py`,
a working example agent `examples/hermes_agent.py`, tests `apps/api/tests/test_agent_api.py`.

## What stays with the platform, whoever the agent is

| Guarantee | How |
|---|---|
| Emergencies ("I can smell gas") get the honest emergency reply and the on-call alert | The keyword check runs on every customer message before any agent sees it; needs no model |
| The first reply says it is an AI assistant | Added to the agent's first reply automatically |
| Opt-outs, safeguarding, prices, payments | The same gate as the built-in assistant; the agent cannot lower a risk |
| Staff approve anything risky | Medium-risk proposals wait in Approvals; an agent key cannot approve |
| The agent only does what the trade allows | Only the pack's tools plus `reply`; anything else is refused (422) |
| No double replies | Proposals are refused (409) unless the owner switched "Who answers customers" to "Our own agent"; the built-in assistant is then quiet |
| A retried request does not message the customer twice | The same proposal from the agent within 10 minutes returns the first one (`"duplicate": true`) |
| One business only | A key belongs to one business; other businesses' conversations are 404 |
| Least data | The agent gets names, messages and intake answers, not phone numbers or email addresses; sensitive intake answers are withheld |

## Turning it on (owner)

1. **Settings → Your own agent → Create key.** Copy the key (`nvx_agent_...`) now; only
   its hash is kept. Revoke it there at any time; "used ..." shows when it last called.
2. Point your agent at the API with that key (below). While "Who answers customers" is
   still "The built-in assistant", the agent can read but not propose: a safe way to
   watch it.
3. When ready: **Who answers customers → Our own agent**, then **Save all**. Switch back
   the same way; nothing else changes.

## The calls

All calls: `Authorization: Bearer nvx_agent_...`, base `https://novaxis-api.vercel.app`.
Limit: 600 calls a minute per key.

| Call | What for |
|---|---|
| `GET /agent/v1/tools` | `instructions` (the built-in assistant's own prompt, to start from) and `tools` in OpenAI function-calling format: `reply` plus the trade's tools |
| `GET /agent/v1/conversations` | Conversations where the customer spoke last and nobody has answered: your to-do list |
| `GET /agent/v1/conversations/{id}` | Everything to decide: messages, contact name and consent, intake answers and the next question, bookings, what already waits for staff, the business's facts, `agent_may_act` |
| `POST /agent/v1/conversations/{id}/proposals` | `{"kind": "reply", "params": {"text": "..."}}` or any tool. Answer: `state` = `executed` (done), `awaiting` (staff decide), or `rejected` (with `reason`) |
| `GET /agent/v1/proposals/{id}` | Has staff decided yet? (`awaiting` → `executed` / `rejected`) |

Errors: `401` bad or revoked key · `404` not this business's · `409` built-in assistant is
on, or `422` not an allowed tool, or the conversation is with a person or closed · `402`
the free trial has ended · `429` too many calls.

Example:

```bash
curl -s -H "Authorization: Bearer $KEY" https://novaxis-api.vercel.app/agent/v1/conversations
curl -s -X POST -H "Authorization: Bearer $KEY" -H 'content-type: application/json' \
  -d '{"kind":"reply","params":{"text":"Thanks, what is your postcode?"}}' \
  https://novaxis-api.vercel.app/agent/v1/conversations/$CONV/proposals
```

## The example agent (Hermes over Ollama)

`examples/hermes_agent.py` is about 100 lines: poll, read, ask the model with the tools,
propose. Run it on your laptop against a Hermes model in Ollama:

```bash
ollama pull hermes3            # [VERIFY] the current Hermes tag and size for 13 GB RAM
export NOVAXIS_AGENT_KEY=nvx_agent_... NOVAXIS_API=https://novaxis-api.vercel.app
export HERMES_BASE_URL=http://localhost:11434/v1 HERMES_MODEL=hermes3
python examples/hermes_agent.py --once
```

It is tested against the real API with the model's answer scripted
(`test_the_example_hermes_agent_works_against_the_real_api`). It drops malformed tool
calls rather than guessing at them, and treats the model's plain text as the reply.

For the **Hermes agent framework** (Nous Research) or any other framework: give it the
five calls above as tools, or wrap them as an MCP server if your framework prefers MCP
[VERIFY what your Hermes framework version supports]. The rules do not change.

## Limits (honest)

- **Polling, not push.** The agent asks every few seconds; there are no webhooks yet.
  Fine for text channels; the customer waits for your polling interval plus the model.
- **Phone calls** need a reply within seconds. With your own agent the caller hears "one
  moment" and, if the agent is slower than about 40 seconds, the call goes to a person
  (docs/voice.md). Voice with an external agent needs push, not yet built.
- **Your agent's uptime is yours.** If it is down, customers wait (the emergency check
  still answers emergencies). Staff see waiting conversations in the inbox as usual.
- **Evals:** run the golden conversations against your agent before real customers.
  `make evals-real` covers the built-in assistant with any model; an eval runner for an
  external agent is the next piece to build.
