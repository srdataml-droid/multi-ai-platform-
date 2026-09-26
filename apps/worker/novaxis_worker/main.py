"""Worker entry point.

Chunk 0 scope: a loop that wakes on an interval, does nothing, and stops cleanly
on SIGTERM or SIGINT. Chunk 3 replaces the body with the real job pick.

Why the clean shutdown matters now: on Railway or Render a deploy sends SIGTERM;
a worker that ignores it gets killed mid-job and leaves a leased row behind.
"""

from __future__ import annotations

import logging
import signal
import threading
from types import FrameType

from novaxis_core.settings import get_settings
from novaxis_core.version import build_info

log = logging.getLogger("novaxis.worker")


class Worker:
    """Runs until `stop()` is called or a termination signal arrives."""

    def __init__(self, poll_seconds: float) -> None:
        self._poll_seconds = poll_seconds
        self._stop = threading.Event()
        self.ticks = 0

    def stop(self) -> None:
        self._stop.set()

    def tick(self) -> None:
        """One unit of work. Chunk 3 fills this in."""
        self.ticks += 1

    def run(self) -> None:
        log.info("worker starting %s", build_info())
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self._poll_seconds)
        log.info("worker stopped after %d ticks", self.ticks)


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    worker = Worker(poll_seconds=settings.worker_poll_seconds)

    def _handle(signum: int, _frame: FrameType | None) -> None:
        log.info("signal %s received, stopping", signum)
        worker.stop()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)
    worker.run()


if __name__ == "__main__":
    main()
