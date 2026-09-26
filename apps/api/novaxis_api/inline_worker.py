"""Run queued jobs inside the API process, for serverless hosting.

On Vercel there is no always-on worker. With NOVAXIS_INLINE_WORKER=true, every
mutating request drains the queue for up to a time budget before its response is
sent, and a once-a-minute timer calls /internal/tick for scheduled jobs (follow-ups,
reminders, roll-ups). The job code is exactly the worker's: same leasing, same
backoff, same hand-off to a person after three failures.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

from novaxis_core.llm import build_llm
from novaxis_core.settings import get_settings
from novaxis_packs import get_pack
from novaxis_worker.loop import Handler, build_handlers, default_worker_id, tick

log = logging.getLogger("novaxis.inline_worker")


@lru_cache(maxsize=1)
def _handlers() -> dict[str, Handler]:
    return build_handlers(get_pack, build_llm())


@lru_cache(maxsize=1)
def _worker_id() -> str:
    return "inline:" + default_worker_id()


def drain_for(budget_seconds: float | None = None, max_jobs: int = 50) -> int:
    """Run jobs until the queue is empty, the budget is spent, or max_jobs ran."""
    budget = (
        get_settings().inline_worker_budget_seconds if budget_seconds is None else budget_seconds
    )
    deadline = time.monotonic() + budget
    ran = 0
    while ran < max_jobs and time.monotonic() < deadline:
        try:
            if not tick(_handlers(), _worker_id()):
                break
        except Exception:  # noqa: BLE001 - never fail the request because a job failed
            log.exception("inline tick failed")
            break
        ran += 1
    return ran
