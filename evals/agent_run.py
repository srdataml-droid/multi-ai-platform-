"""Golden-conversation evals for an external agent (docs/agent-api.md).

The agent is a black box: any command that, run once, reads the agent API and proposes.
For each golden conversation the runner plays the customer: it sends a message, lets the
platform do its part (the emergency check), runs the agent command once, and repeats; then
it grades the conversation with the same checks as `run.py`.

    uv run python evals/agent_run.py --agent "python examples/hermes_agent.py --once"
    uv run python evals/agent_run.py --agent "python evals/scripted_agent.py"   # reference
    uv run python evals/agent_run.py --agent "..." --pack hvac --json

The command gets, as environment variables: NOVAXIS_API (a local API started for the run),
NOVAXIS_AGENT_KEY (a key for a dedicated eval business per trade, set to "our own agent"),
and NOVAXIS_EVAL_FILE / NOVAXIS_EVAL_TURN (only the scripted reference agent uses them).

Two grades, because they are not the same kind of failure:
- **safety** (an emergency not escalated, a forbidden phrase sent, something that should be
  refused and was not): must be 100%, always;
- **overall**: the pack's threshold (thresholds.yaml), as for the built-in assistant.
Needs the local database (`make up`).
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import uvicorn
import yaml
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parent))

from run import check  # noqa: E402

from novaxis_api.main import create_app  # noqa: E402
from novaxis_core.agent import new_key  # noqa: E402
from novaxis_core.channels import NormalisedInbound  # noqa: E402
from novaxis_core.inbound import ingest  # noqa: E402
from novaxis_core.models import Conversation, Job, Tenant  # noqa: E402
from novaxis_core.tenant_settings import ChannelConfig  # noqa: E402
from novaxis_core.turn import run_turn  # noqa: E402
from novaxis_db.seed import DEMO_TENANTS, _settings  # noqa: E402
from novaxis_db.session import service_session, tenant_session  # noqa: E402
from novaxis_packs import get_pack  # noqa: E402

EVALS_DIR = Path(__file__).resolve().parent


@dataclass
class Outcome:
    name: str
    failures: list[str] = field(default_factory=list)
    safety_failures: list[str] = field(default_factory=list)
    agent_seconds: list[float] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures and not self.safety_failures


class _NoModel:
    """The platform's own model must not run in an external-agent eval."""

    def complete(self, **_: Any) -> Any:
        raise AssertionError("the built-in model ran in external-agent mode")


def start_api() -> str:
    """The real API in this process, on a free local port, for the agent to call."""
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(
        uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            return f"http://127.0.0.1:{port}"
        time.sleep(0.05)
    raise SystemExit("the local API did not start")


def eval_business(pack_id: str) -> tuple[Tenant, str]:
    """A dedicated business per trade, answered by "our own agent", web chat only (so it
    never claims a real business's number), and a fresh key for this run."""
    slug = f"eval-agent-{pack_id}"
    name = next(n for s, n, p in DEMO_TENANTS if p == pack_id)
    settings = _settings(pack_id, slug)
    settings.channels = {"webchat": ChannelConfig(enabled=True)}
    settings.assistant = "external"
    with service_session() as s:
        t = s.scalar(select(Tenant).where(Tenant.slug == slug))
        if t is None:
            t = Tenant(slug=slug, name=name, pack_id=pack_id, status="active", plan="internal")
            s.add(t)
        t.settings = settings.model_dump()
        t.worker_enabled = False  # the runner plays the platform's part itself
        s.flush()
        tenant_id = t.id
        # Earlier runs' conversations must not appear on this run's to-do list.
        for conv in s.scalars(select(Conversation).where(Conversation.tenant_id == tenant_id)):
            conv.status = "closed"
    with tenant_session(tenant_id) as s:
        _, key = new_key(s, tenant_id, "eval-runner", None)
    with service_session() as s:
        t = s.get(Tenant, tenant_id)
        assert t is not None
        s.expunge(t)
    return t, key


def run_agent(cmd: list[str], env: dict[str, str], timeout: float) -> tuple[float, str | None]:
    started = time.monotonic()
    try:
        r = subprocess.run(
            cmd, env=env, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        return time.monotonic() - started, f"agent timed out after {timeout:.0f}s"
    took = time.monotonic() - started
    if r.returncode != 0:
        last = ((r.stderr or r.stdout).strip().splitlines() or [""])[-1]
        return took, f"agent exited {r.returncode}: {last[:200]}"
    return took, None


def run_one(
    path: Path, tenant: Tenant, cmd: list[str], env: dict[str, str], timeout: float
) -> Outcome:
    spec = yaml.safe_load(path.read_text())
    pack = get_pack(tenant.pack_id)
    out = Outcome(spec.get("name", path.stem))
    visitor = f"agent-eval-{uuid.uuid4().hex[:10]}"
    conv_id: uuid.UUID | None = None
    for i, turn in enumerate(spec["turns"]):
        with tenant_session(tenant.id) as s:
            r = ingest(
                s,
                tenant,
                NormalisedInbound(
                    channel="webchat",
                    provider_ref=f"webchat:{visitor}:{uuid.uuid4().hex[:6]}",
                    tenant_ref=tenant.slug,
                    sender_visitor_id=visitor,
                    body=turn,
                ),
            )
            conv_id = r.conversation_id
            if r.job_id is None:
                continue
            job = s.get(Job, r.job_id)
            if job is not None:
                job.state = "done"
            # The platform's part: the emergency check (and nothing else in this mode).
            run_turn(s, tenant, pack, _NoModel(), conv_id)  # type: ignore[arg-type]
        took, error = run_agent(
            cmd, {**env, "NOVAXIS_EVAL_FILE": str(path), "NOVAXIS_EVAL_TURN": str(i)}, timeout
        )
        out.agent_seconds.append(took)
        if error:
            out.failures.append(f"turn {i + 1}: {error}")
    assert conv_id is not None
    with tenant_session(tenant.id) as s:
        for failure, safety in check(s, pack, conv_id, spec.get("expect") or {}):
            (out.safety_failures if safety else out.failures).append(failure)
        conv = s.get(Conversation, conv_id)
        if conv is not None:
            conv.status = "closed"  # off the to-do list for the next conversation
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True, help="command that runs your agent once")
    ap.add_argument("--pack", default=None)
    ap.add_argument("--timeout", type=float, default=120.0, help="seconds per agent run")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--gate",
        choices=["full", "safety"],
        default="full",
        help="full: no safety failure and the pass rate meets the threshold (before real "
        "customers); safety: only no safety failure (CI, with the scripted reference agent)",
    )
    args = ap.parse_args()
    cmd = shlex.split(args.agent)
    thresholds = yaml.safe_load((EVALS_DIR / "thresholds.yaml").read_text())
    packs = (
        [args.pack]
        if args.pack
        else sorted(p.name for p in EVALS_DIR.iterdir() if p.is_dir() and list(p.glob("*.yaml")))
    )
    api = start_api()
    ok = True
    report: dict[str, Any] = {}
    for pack_id in packs:
        tenant, key = eval_business(pack_id)
        env = {**os.environ, "NOVAXIS_API": api, "NOVAXIS_AGENT_KEY": key}
        outcomes = [
            run_one(f, tenant, cmd, env, args.timeout)
            for f in sorted((EVALS_DIR / pack_id).glob("*.yaml"))
        ]
        passed = sum(o.passed for o in outcomes)
        unsafe = [o for o in outcomes if o.safety_failures]
        rate = passed / len(outcomes) if outcomes else 0.0
        need = float(thresholds.get(pack_id, thresholds.get("default", 0.9)))
        seconds = [t for o in outcomes for t in o.agent_seconds]
        pack_ok = not unsafe and (args.gate == "safety" or rate >= need)
        ok = ok and pack_ok
        report[pack_id] = {
            "passed": passed,
            "total": len(outcomes),
            "rate": rate,
            "threshold": need,
            "safety_failures": {o.name: o.safety_failures for o in unsafe},
            "failures": {o.name: o.failures for o in outcomes if o.failures},
            "agent_seconds_median": round(statistics.median(seconds), 2) if seconds else None,
            "agent_seconds_max": round(max(seconds), 2) if seconds else None,
        }
        print(
            f"{'OK ' if pack_ok else 'LOW'} {pack_id}: {passed}/{len(outcomes)} passed "
            f"({rate:.0%}, threshold {need:.0%}); safety failures: {len(unsafe)}; "
            f"agent time median {report[pack_id]['agent_seconds_median']}s"
        )
        for o in outcomes:
            mark = "pass" if o.passed else ("UNSAFE" if o.safety_failures else "FAIL")
            why = "; ".join(o.safety_failures + o.failures)
            print(f"     {mark:6} {o.name}" + (f"  -> {why}" if why else ""))
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
