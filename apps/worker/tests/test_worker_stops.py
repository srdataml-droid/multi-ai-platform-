import threading

from novaxis_worker.main import Worker


def test_worker_runs_then_stops_cleanly() -> None:
    w = Worker(poll_seconds=0.01)
    t = threading.Thread(target=w.run)
    t.start()
    threading.Event().wait(0.05)
    w.stop()
    t.join(timeout=1)
    assert not t.is_alive()
    assert w.ticks >= 1
