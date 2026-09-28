"""The reference external agent for `agent_run.py`: it replays each golden conversation's
`script` through the agent API, exactly as a perfectly obedient model would.

It proves the runner and the API end to end without a model, and it shows what any
external agent does *not* get from the built-in assistant: evals that pass here only
because of the platform (emergencies) and evals that fail here because the built-in
assistant helps its model (the intake engine that proposes when the model forgets, the
check that stops a reply promising a booking). docs/agent-api.md lists them.
"""

from __future__ import annotations

import os
import sys

import httpx
import yaml


def main() -> int:
    spec = yaml.safe_load(open(os.environ["NOVAXIS_EVAL_FILE"]).read())
    turn = int(os.environ["NOVAXIS_EVAL_TURN"])
    script = spec.get("script") or []
    if turn >= len(script):
        return 0
    step = script[turn]
    api = httpx.Client(
        base_url=os.environ["NOVAXIS_API"],
        headers={"Authorization": f"Bearer {os.environ['NOVAXIS_AGENT_KEY']}"},
        timeout=30,
    )
    for item in api.get("/agent/v1/conversations").raise_for_status().json()["items"]:
        url = f"/agent/v1/conversations/{item['conversation_id']}/proposals"
        for call in step.get("calls") or []:
            api.post(url, json={"kind": call["tool"], "params": call.get("input", {})})
        if step.get("text"):
            api.post(url, json={"kind": "reply", "params": {"text": step["text"]}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
