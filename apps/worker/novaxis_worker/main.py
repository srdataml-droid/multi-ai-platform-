"""Worker entry point.

Runs `tick()` until told to stop. SIGTERM and SIGINT stop it cleanly between
jobs, so a deploy never kills a job mid-flight: the lease simply completes.
`--once` drains the queue and exits, for demos and cron-style runs.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from types import FrameType

from novaxis_core.llm import build_llm
from novaxis_core.settings import get_settings
from novaxis_core.version import build_info
from novaxis_packs import get_pack
from novaxis_worker.loop import Handler, build_handlers, default_worker_id, tick

log = logging.getLogger("novaxis.worker")


class Worker:
    """Runs until `stop()` is called or a termination signal arrives."""

    def __init__(self, poll_seconds: float, handlers: dict[str, Handler] | None = None) -> None:
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._handlers = handlers
        self.worker_id = default_worker_id()
        self.ticks = 0
        self.jobs_run = 0

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> bool:
        """One unit of work: at most one job."""
        self.ticks += 1
        if self._handlers is None:
            return False
        ran = tick(self._handlers, self.worker_id)
        if ran:
            self.jobs_run += 1
        return ran

    def run(self) -> None:
        log.info("worker %s starting %s", self.worker_id, build_info())
        while not self._stop.is_set():
            try:
                busy = self.tick()
            except Exception:  # noqa: BLE001 - keep the loop alive, log the cause
                log.exception("tick crashed")
                busy = False
            if not busy:
                self._stop.wait(self._poll_seconds)
        log.info("worker stopped after %d ticks, %d jobs", self.ticks, self.jobs_run)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    handlers = build_handlers(get_pack, build_llm())
    worker = Worker(poll_seconds=settings.worker_poll_seconds, handlers=handlers)

    if "--once" in sys.argv:
        from novaxis_worker.loop import drain

        n = drain(handlers, worker.worker_id)
        print(f"ran {n} job(s)")
        return

    def _handle(signum: int, _frame: FrameType | None) -> None:
        log.info("signal %s received, stopping", signum)
        worker.stop()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    worker.run()


if __name__ == "__main__":
    main()
