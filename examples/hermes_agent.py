"""A minimal agent for the Novaxis agent API, driven by a Hermes model (or any model served
behind an OpenAI-compatible chat endpoint: Ollama, vLLM, llama.cpp, OpenRouter...).

It is a starting point to read and replace, not a product: poll for conversations where a
customer is waiting, ask the model what to do with the business's own tools, and send what
it decides back as *proposals*. The platform's gate decides what actually happens.

    export NOVAXIS_AGENT_KEY=nvx_agent_...                    # Settings > Your own agent
    export NOVAXIS_API=https://novaxis-api.vercel.app
    export HERMES_BASE_URL=http://localhost:11434/v1          # Ollama's OpenAI endpoint
    export HERMES_MODEL=hermes3                                # [VERIFY] the tag you pulled
    python examples/hermes_agent.py            # keeps polling every 10 seconds
    python examples/hermes_agent.py --once     # one pass, then exit

    # On a server, as a service that restarts itself: deploy/aws/setup-agent.sh
    # (docs/agent-on-aws.md). Ollama Cloud works too: HERMES_BASE_URL=https://ollama.com/v1,
    # HERMES_API_KEY=<your key>, HERMES_MODEL=gpt-oss:120b.

    # Or be told instead of polling (Settings > Your own agent > Webhook):
    export NOVAXIS_WEBHOOK_SECRET=whsec_...                   # shown when you set the webhook
    python examples/hermes_agent.py --serve 8787               # expose it over https, e.g. a tunnel

Needs only `httpx`. docs/agent-api.md explains every call.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import httpx


def ask_model(
    llm: httpx.Client, model: str, system: str, ctx: dict[str, Any], tools: list[dict[str, Any]]
) -> dict[str, Any]:
    """One chat completion with the business's tools. Returns the assistant message."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    for m in ctx["messages"]:
        role = "user" if m["from"] == "customer" else "assistant"
        text = m["text"] if m["from"] != "staff" else f"[staff member]: {m['text']}"
        messages.append({"role": role, "content": text})
    r = llm.post(
        "/chat/completions",
        json={"model": model, "messages": messages, "tools": tools, "tool_choice": "auto"},
    )
    r.raise_for_status()
    return dict(r.json()["choices"][0]["message"])


EXTRACT = (
    "You read what a customer just said and pull out the facts it states. Reply with a "
    "single JSON object and nothing else. Use only the keys listed. Leave a key out if the "
    "customer did not state it; never guess. For a key with options, use exactly one of them."
)


def extract_answers(llm: httpx.Client, model: str, ctx: dict[str, Any]) -> dict[str, str]:
    """The intake answers in the customer's last message, from one JSON call. Open models
    rarely call tools, so without this the answers (and the booking) never get recorded.
    The platform checks every value again; anything odd here is simply dropped."""
    intake = ctx["intake"]
    questions = {q["key"]: q for q in intake.get("questions", [])}
    said = [m["text"] for m in ctx["messages"] if m["from"] == "customer"]
    if intake["complete"] or not questions or not said:
        return {}
    keys = "\n".join(
        f"- {k}: {q['ask']}" + (f" (one of: {', '.join(q['choices'])})" if q["choices"] else "")
        for k, q in questions.items()
    )
    r = llm.post(
        "/chat/completions",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": f"{EXTRACT}\n\nKeys:\n{keys}"},
                {"role": "user", "content": said[-1]},
            ],
            "max_tokens": 400,
        },
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"].get("content") or ""
    start, end = text.find("{"), text.rfind("}")
    try:
        data = json.loads(text[start : end + 1]) if start >= 0 else {}
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        k: str(v).strip()
        for k, v in data.items()
        if k in questions
        and isinstance(v, (str, int, float))
        and not isinstance(v, bool)
        and str(v).strip()
    }


def system_prompt(instructions: str, ctx: dict[str, Any]) -> str:
    parts = [instructions, ctx["business"]]
    intake = ctx["intake"]
    if intake["answers"]:
        parts.append("What the customer has told us: " + json.dumps(intake["answers"]))
    if intake.get("complete"):
        parts.append(
            "Every answer is in. Do not ask any of the questions again. Thank the customer, "
            "say you have what you need and that the team will be in touch to confirm."
        )
    elif intake.get("next_question"):
        parts.append(f"Next thing to ask: {intake['next_question']['ask']}")
    if ctx["appointments"]:
        parts.append("Their bookings: " + json.dumps(ctx["appointments"]))
    if ctx["awaiting_staff"]:
        parts.append(
            "Already waiting for staff: " + ", ".join(p["kind"] for p in ctx["awaiting_staff"])
        )
    parts.append(
        "Use the reply tool (or plain text) to answer the customer. Everything you do is "
        "a proposal the business's rules decide on."
    )
    return "\n\n".join(parts)


def handle(
    api: httpx.Client,
    llm: httpx.Client,
    model: str,
    instructions: str,
    tools: list[dict[str, Any]],
    conversation_id: str,
) -> list[dict[str, Any]]:
    """Decide and propose for one conversation. Returns what the platform said to each."""
    path = f"/agent/v1/conversations/{conversation_id}"
    ctx = api.get(path).raise_for_status().json()
    if not ctx["conversation"]["agent_may_act"]:
        return []
    results = []
    answers = extract_answers(llm, model, ctx)
    if answers:
        r = api.post(
            f"{path}/proposals", json={"kind": "extract_fields", "params": {"fields": answers}}
        )
        results.append(
            {"kind": "extract_fields", "status": r.status_code, **(r.json() if r.content else {})}
        )
        # The platform may have acted on them: booked the job, or handed an address
        # outside the area to a person. Read again before replying.
        ctx = api.get(path).raise_for_status().json()
        if not ctx["conversation"]["agent_may_act"]:
            return results
    msg = ask_model(llm, model, system_prompt(instructions, ctx), ctx, tools)
    proposals: list[tuple[str, dict[str, Any]]] = []
    for call in msg.get("tool_calls") or []:
        fn = call["function"]
        try:
            args = (
                json.loads(fn["arguments"]) if isinstance(fn["arguments"], str) else fn["arguments"]
            )
        except json.JSONDecodeError:
            continue  # a malformed call is dropped, never guessed at
        proposals.append((fn["name"], args))
    text = (msg.get("content") or "").strip()
    if text and not any(kind == "reply" for kind, _ in proposals):
        proposals.append(("reply", {"text": text}))
    for kind, params in proposals:
        r = api.post(
            f"/agent/v1/conversations/{conversation_id}/proposals",
            json={"kind": kind, "params": params},
        )
        results.append({"kind": kind, "status": r.status_code, **(r.json() if r.content else {})})
    return results


def run_once(api: httpx.Client, llm: httpx.Client, model: str) -> list[dict[str, Any]]:
    setup = api.get("/agent/v1/tools").raise_for_status().json()
    done = []
    for item in api.get("/agent/v1/conversations").raise_for_status().json()["items"]:
        cid = item["conversation_id"]
        try:
            results = handle(api, llm, model, setup["instructions"], setup["tools"], cid)
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            # One conversation failing (the model timed out, a bad reply) must not stop
            # the others; it is tried again on the next pass while the customer waits.
            print(f"{cid} failed: {exc!r}", flush=True)
            continue
        for res in results:
            print(f"{cid} {res['kind']}: {res.get('state', res.get('detail'))}", flush=True)
            done.append(res)
    return done


def verify(secret: str, header: str, body: bytes, max_age: int = 300) -> bool:
    """Novaxis signs each push: `t=<unix time>,v1=<HMAC-SHA256 of "<t>.<body>">`."""
    try:
        fields = dict(part.split("=", 1) for part in header.split(","))
        t = int(fields["t"])
    except (ValueError, KeyError):
        return False
    if abs(time.time() - t) > max_age:
        return False
    mac = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, fields.get("v1", ""))


def serve(port: int, secret: str, api: httpx.Client, llm: httpx.Client, model: str) -> None:
    """Answer pushes. Acknowledge at once (Novaxis waits 5 seconds at most), then think."""
    setup = api.get("/agent/v1/tools").raise_for_status().json()

    def work(event: dict[str, Any]) -> None:
        if event["event"] == "message.received":
            cid = event["data"]["conversation_id"]
            try:
                results = handle(api, llm, model, setup["instructions"], setup["tools"], cid)
            except (httpx.HTTPError, KeyError, ValueError) as exc:
                print(f"{cid} failed: {exc!r}", flush=True)
                return
            for res in results:
                print(f"{cid} {res['kind']}: {res.get('state', res.get('detail'))}", flush=True)
        elif event["event"] == "proposal.decided":
            print(f"staff decided {event['data']['proposal_id']}: {event['data']['state']}")

    class Hook(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - the http.server name
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            if not verify(secret, self.headers.get("X-Novaxis-Signature", ""), body):
                self.send_response(401)
                self.end_headers()
                return
            self.send_response(204)
            self.end_headers()
            threading.Thread(target=work, args=(json.loads(body),), daemon=True).start()

    run_once(api, llm, model)  # anything that arrived while this agent was down
    print(f"listening for Novaxis pushes on port {port}")
    ThreadingHTTPServer(("0.0.0.0", port), Hook).serve_forever()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--serve", type=int, metavar="PORT", help="receive pushes instead of polling")
    args = ap.parse_args()
    key = os.environ.get("NOVAXIS_AGENT_KEY")
    if not key:
        print("set NOVAXIS_AGENT_KEY (Settings > Your own agent > Create key)", file=sys.stderr)
        return 2
    api = httpx.Client(
        base_url=os.environ.get("NOVAXIS_API", "http://localhost:8000"),
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    llm = httpx.Client(
        base_url=os.environ.get("HERMES_BASE_URL", "http://localhost:11434/v1"),
        headers={"Authorization": f"Bearer {os.environ.get('HERMES_API_KEY', 'none')}"},
        timeout=120,
    )
    model = os.environ.get("HERMES_MODEL", "hermes3")
    if args.serve:
        secret = os.environ.get("NOVAXIS_WEBHOOK_SECRET")
        if not secret:
            print("set NOVAXIS_WEBHOOK_SECRET (shown when you set the webhook)", file=sys.stderr)
            return 2
        serve(args.serve, secret, api, llm, model)
        return 0
    every = int(os.environ.get("POLL_SECONDS", "10"))
    print(f"Novaxis agent up: {api.base_url}, model {model}, checking every {every} s", flush=True)
    while True:
        try:
            run_once(api, llm, model)
        except httpx.HTTPError as exc:  # Novaxis or the network down: wait, then go on
            print(f"pass failed: {exc!r}", flush=True)
            if args.once:
                return 1
        if args.once:
            return 0
        time.sleep(every)


if __name__ == "__main__":
    sys.exit(main())
