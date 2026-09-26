"""Executors: the only code that turns a proposal into a side effect.

`execute()` is the single entry point and refuses to run unless the proposal is
in `auto_approved` or `approved`. Executors are plain functions registered by
kind; none of them is reachable from anywhere else, and every one of them ends
with an audit row (ADR 0004).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from novaxis_core.actions import parse_params
from novaxis_core.models import ActionProposal, AuditLog, Tenant

log = logging.getLogger("novaxis.executors")

EXECUTABLE_STATES = frozenset({"auto_approved", "approved"})


class GateBypassError(RuntimeError):
    """Raised when something tries to execute a proposal the gate has not cleared."""


@dataclass(frozen=True)
class ExecResult:
    ok: bool
    result: dict[str, Any]
    error: str | None = None


Executor = Callable[[Session, Tenant, ActionProposal, Any], ExecResult]
_REGISTRY: dict[str, Executor] = {}


def executor(kind: str) -> Callable[[Executor], Executor]:
    def register(fn: Executor) -> Executor:
        _REGISTRY[kind] = fn
        return fn

    return register


def registered_kinds() -> frozenset[str]:
    return frozenset(_REGISTRY)


def _audit(session: Session, proposal: ActionProposal, event: str, diff: dict[str, Any]) -> None:
    session.add(
        AuditLog(
            tenant_id=proposal.tenant_id,
            actor="worker:executor",
            event=event,
            subject_table="action_proposals",
            subject_id=proposal.id,
            diff=diff,
        )
    )


def execute(session: Session, tenant: Tenant, proposal: ActionProposal) -> ExecResult:
    if proposal.state not in EXECUTABLE_STATES:
        _audit(
            session,
            proposal,
            "proposal.execute_refused",
            {"kind": proposal.kind, "state": proposal.state},
        )
        session.flush()
        raise GateBypassError(f"proposal {proposal.id} is {proposal.state}, not approved")
    fn = _REGISTRY.get(proposal.kind)
    if fn is None:
        proposal.state = "failed"
        proposal.error = f"no executor for {proposal.kind}"
        _audit(
            session, proposal, "proposal.failed", {"kind": proposal.kind, "error": proposal.error}
        )
        return ExecResult(False, {}, proposal.error)
    try:
        params = parse_params(proposal.kind, proposal.params)
        res = fn(session, tenant, proposal, params)
    except NotImplementedError as exc:
        res = ExecResult(False, {}, f"not implemented: {exc}")
    except Exception as exc:  # noqa: BLE001 - executor failures are recorded, not raised
        log.exception("executor %s failed for proposal %s", proposal.kind, proposal.id)
        res = ExecResult(False, {}, f"{type(exc).__name__}: {exc}")
    proposal.executed_at = datetime.now(UTC)
    proposal.result = res.result
    if res.ok:
        proposal.state = "executed"
        _audit(
            session, proposal, "proposal.executed", {"kind": proposal.kind, **_small(res.result)}
        )
    else:
        proposal.state = "failed"
        proposal.error = res.error
        _audit(session, proposal, "proposal.failed", {"kind": proposal.kind, "error": res.error})
    session.flush()
    return res


def _small(d: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v for k, v in d.items() if isinstance(v, (str, int, float, bool)) and len(str(v)) < 200
    }


def conversation_id_of(proposal: ActionProposal) -> uuid.UUID:
    if proposal.conversation_id is None:
        raise ValueError("proposal has no conversation")
    return proposal.conversation_id


# Import the executor modules so they register themselves.
from novaxis_core.executors import messaging as _messaging  # noqa: E402, F401
from novaxis_core.executors import pending as _pending  # noqa: E402, F401
from novaxis_core.executors import scheduling as _scheduling  # noqa: E402, F401
from novaxis_core.executors import staff as _staff  # noqa: E402, F401
