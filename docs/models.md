# Choosing and switching the AI model

Every model call goes through one interface (`packages/core/novaxis_core/llm.py`). Three
providers exist; you pick one with environment variables, with no code change.

| `NOVAXIS_LLM_PROVIDER` | What it talks to | Cost |
|---|---|---|
| `fake` | Scripted replies (tests, demos; what the live site uses today) | Free |
| `openai_compatible` | Any OpenAI-style chat API: **Ollama** on your laptop, **vLLM** on a rented GPU, or a hosted open-model service | Free locally; pay per token or per hour hosted |
| `anthropic` | Claude | Pay per token |

## Settings for `openai_compatible`

| Variable | Example | Notes |
|---|---|---|
| `NOVAXIS_LLM_BASE_URL` | `http://localhost:11434/v1` | Ollama's default. A hosted service gives you its own URL ending in `/v1` |
| `NOVAXIS_LLM_API_KEY` | (empty for Ollama) | Hosted services give you a key. Put it in Vercel as a sensitive variable, never in the repo |
| `NOVAXIS_MODEL_WORKER` | the model's name on that server | Replies to customers; needs **tool calling** |
| `NOVAXIS_MODEL_CLASSIFY`, `NOVAXIS_MODEL_SUMMARISE` | a smaller, cheaper model | Summaries and sorting |
| `NOVAXIS_LLM_TIMEOUT_SECONDS`, `NOVAXIS_LLM_MAX_RETRIES` | `20`, `1` | Already set this way on Vercel |

The app refuses to start this provider while any model name still starts with `claude-`,
so a half-finished switch fails loudly instead of sending Claude names to another server.

## Try it on your laptop (free)

Your laptop has no graphics card and about 13GB of memory: small models run, slowly.
Good enough to see it work and to run the evals, not to serve customers.

1. Install Ollama from ollama.com.
2. Pick a small model that supports **tools**. Ollama's model library tags these. Pull it:
   `ollama pull <model>`.
3. In the repo, with Postgres running (`make up` or your local Postgres):

   ```bash
   export NOVAXIS_LLM_PROVIDER=openai_compatible
   export NOVAXIS_LLM_BASE_URL=http://localhost:11434/v1
   export NOVAXIS_MODEL_WORKER=<model> NOVAXIS_MODEL_CLASSIFY=<model> NOVAXIS_MODEL_SUMMARISE=<model>
   export NOVAXIS_LLM_TIMEOUT_SECONDS=120   # small models on a CPU are slow
   make evals-real
   ```

4. Read the pass rate per pack. **The evals choose the model, not the brand.** A model
   that does not call `escalate_emergency` or `propose_appointment` when it should will
   fail there. Try two or three models and keep the table below up to date.

## Going live with an open model

1. Choose a hosted service that serves your chosen model with tool calling, or rent a GPU
   and run vLLM. Check the service's data terms: customer messages (health data for
   dental) must not be used for training, and you need their data processing agreement
   (see `docs/compliance.md`).
2. Set a monthly spend limit with the provider.
3. On Vercel `novaxis-api`: set the variables above, then redeploy.
4. Watch the first days with every reply needing approval (shadow mode, see the plan in
   `docs/audit/2026-09-27-status-and-plan.md`).

## What differs from Claude, on purpose

- **No prompt caching:** the whole system prompt is sent every turn. Budget per token accordingly.
- **Tool schemas are sent without `strict`:** many open servers reject it. The approval
  gate checks every tool input against its schema, so a malformed call is refused, never
  run. A call whose arguments are not valid JSON is dropped.
- **Hidden reasoning is removed:** some open models write `<think>...</think>` before the
  answer; it is stripped so it never reaches a customer.

## Eval results

| Date | Provider / model | dental | hvac | restoration | Cost per conversation | Notes |
|---|---|---|---|---|---|---|
| 2026-09-27 | fake (scripted) | 5/5 | 6/6 | 5/5 | £0 | Plumbing only, not AI quality |
