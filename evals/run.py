"""Golden-conversation evals.

Each eval is a YAML file: the customer's scripted turns, and what must be true at
the end. With `--fake` (default) the model's replies come from the file's
`script`, so the run is deterministic and tests the plumbing. With `--real` the
real model answers and only the expectations are checked.

    uv run python evals/run.py            # all packs, fake model
    uv run python evals/run.py --real     # real model, needs ANTHROPIC_API_KEY
    uv run python evals/run.py --pack hvac
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from novaxis_core.channels import NormalisedInbound
from novaxis_core.inbound import ingest
from novaxis_core.llm import FakeLLM, LLMClient, ToolCall, build_llm
from novaxis_core.models import ActionProposal, Conversation, Message, Tenant
from novaxis_db.seed import seed
from novaxis_db.session import service_session, tenant_session
from novaxis_packs import get_pack

EVALS_DIR = Path(__file__).resolve().parent


@dataclass
class Outcome:
    name: str
    passed: bool
    failures: list[str]
    llm_calls: int


def _script(spec: dict[str, Any]) -> list[tuple[str, list[ToolCall]]]:
    out: list[tuple[str, list[ToolCall]]] = []
    for i, turn in enumerate(spec.get("script") or []):
        calls = [
            ToolCall(c["tool"], c.get("input", {}), f"s{i}-{j}")
            for j, c in enumerate(turn.get("calls") or [])
        ]
        out.append((turn.get("text", ""), calls))
    return out


def run_one(path: Path, tenant: Tenant, llm: LLMClient | None) -> Outcome:
    spec = yaml.safe_load(path.read_text())
    pack = get_pack(tenant.pack_id)
    fake = llm is None
    model: LLMClient = FakeLLM(script=_script(spec)) if fake else llm  # type: ignore[assignment]
    visitor = f"eval-{uuid.uuid4().hex[:10]}"
    conv_id: uuid.UUID | None = None
    llm_calls = 0
    for turn in spec["turns"]:
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
        from novaxis_core.turn import run_turn

        with tenant_session(tenant.id) as s:
            before = len(model.calls) if isinstance(model, FakeLLM) else 0
            run_turn(s, tenant, pack, model, conv_id)
            if isinstance(model, FakeLLM):
                llm_calls += len(model.calls) - before
    assert conv_id is not None
    failures: list[str] = []
    expect = spec.get("expect") or {}
    with tenant_session(tenant.id) as s:
        conv = s.get(Conversation, conv_id)
        assert conv is not None
        proposals = list(
            s.scalars(select(ActionProposal).where(ActionProposal.conversation_id == conv_id))
        )
        kinds = {p.kind for p in proposals if p.state not in ("rejected", "failed")} | {
            p.kind for p in proposals if p.kind == "escalate_emergency"
        }
        rejected = {p.kind for p in proposals if p.state == "rejected"}
        outbound = [
            m.body
            for m in s.scalars(
                select(Message)
                .where(Message.conversation_id == conv_id, Message.direction == "outbound")
                .order_by(Message.created_at)
            )
        ]
        for k in expect.get("proposals") or []:
            if k not in kinds:
                failures.append(f"expected proposal {k}, got {sorted(kinds)}")
        for k in expect.get("no_proposals") or []:
            if k in kinds:
                failures.append(f"unexpected proposal {k}")
        for k in expect.get("rejected") or []:
            if k not in rejected:
                failures.append(f"expected {k} to be rejected")
        for key, value in (expect.get("extracted") or {}).items():
            got = str(conv.extracted.get(key, "")).lower()
            if value is True:
                if not got:
                    failures.append(f"expected extracted.{key} to be set")
            elif got != str(value).lower():
                failures.append(f"expected extracted.{key}={value!r}, got {got!r}")
        if "status" in expect and conv.status != expect["status"]:
            failures.append(f"expected status {expect['status']}, got {conv.status}")
        for phrase in expect.get("reply_contains") or []:
            if not any(phrase.lower() in b.lower() for b in outbound):
                failures.append(f"no reply contains {phrase!r}")
        for phrase in expect.get("reply_never_contains") or []:
            if any(phrase.lower() in b.lower() for b in outbound):
                failures.append(f"a reply contains forbidden {phrase!r}")
        if fake and "max_llm_calls" in expect and llm_calls > expect["max_llm_calls"]:
            failures.append(f"{llm_calls} LLM calls, max {expect['max_llm_calls']}")
    return Outcome(spec.get("name", path.stem), not failures, failures, llm_calls)


def run_pack(pack_id: str, real: bool) -> list[Outcome]:
    folder = EVALS_DIR / pack_id
    files = sorted(folder.glob("*.yaml"))
    with service_session() as s:
        seed(s)
        tenant = s.scalar(select(Tenant).where(Tenant.pack_id == pack_id))
        if tenant is None:
            raise SystemExit(f"no seeded tenant for pack {pack_id}")
        s.expunge(tenant)
    llm = build_llm() if real else None
    return [run_one(f, tenant, llm) for f in files]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--real", action="store_true", help="use the real model")
    ap.add_argument("--pack", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    thresholds = yaml.safe_load((EVALS_DIR / "thresholds.yaml").read_text())
    packs = (
        [args.pack]
        if args.pack
        else [p.name for p in EVALS_DIR.iterdir() if p.is_dir() and list(p.glob("*.yaml"))]
    )
    ok = True
    report: dict[str, Any] = {}
    for pack_id in sorted(packs):
        outcomes = run_pack(pack_id, args.real)
        passed = sum(o.passed for o in outcomes)
        rate = passed / len(outcomes) if outcomes else 0.0
        need = float(thresholds.get(pack_id, thresholds.get("default", 0.9)))
        report[pack_id] = {
            "passed": passed,
            "total": len(outcomes),
            "rate": rate,
            "threshold": need,
            "failures": {o.name: o.failures for o in outcomes if not o.passed},
        }
        status = "OK " if rate >= need else "LOW"
        print(
            f"{status} {pack_id}: {passed}/{len(outcomes)} passed "
            f"({rate:.0%}, threshold {need:.0%})"
        )
        for o in outcomes:
            mark = "pass" if o.passed else "FAIL"
            print(f"     {mark}  {o.name}" + ("" if o.passed else "  -> " + "; ".join(o.failures)))
        ok = ok and rate >= need
    if args.json:
        print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
