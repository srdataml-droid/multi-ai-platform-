# Evals

Golden conversations per pack arrive with each pack chunk (5, 6, 7) and scale up in Chunk 13.
`make evals` runs them against the real worker code.

## External agents

`agent_run.py` plays the same conversations against a business's own agent through the
agent API (docs/agent-api.md): `make evals-agent AGENT="<command that runs it once>"`.
Failures are graded as safety (must be none) or behaviour (the pass rate). CI runs it with
the scripted reference agent, `scripted_agent.py`, and `--gate safety`.

