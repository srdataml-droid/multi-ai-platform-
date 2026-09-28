"""A write is committed before its response is sent. FastAPI's default runs a yield
dependency's exit (our commit) after the response, so a client could read before its own
write landed, or be told "saved" for a write whose commit then failed. Found through a
flaky browser test: save, reload, the new row missing. Needs a real server: the test
client waits for the commit either way."""

from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from sqlalchemy.orm import Session

from novaxis_api.devtoken import mint
from novaxis_api.main import create_app
from novaxis_db.seed import seed
from novaxis_db.session import service_session


def test_writes_are_committed_before_the_response(
    migrated: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    with service_session(migrated) as s:
        seed(s)
    commits: list[float] = []
    real_commit = Session.commit

    def slow_commit(self: Session) -> None:
        time.sleep(0.8)  # a slow database
        real_commit(self)
        commits.append(time.monotonic())

    monkeypatch.setattr(Session, "commit", slow_commit)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(create_app(), port=port, log_level="error"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.02)
    try:
        owner = {"Authorization": f"Bearer {mint('dev|owner@demo-hvac')}"}
        base = f"http://127.0.0.1:{port}"
        r = httpx.post(
            f"{base}/settings/agent-keys", json={"name": "order"}, headers=owner, timeout=30
        )
        answered = time.monotonic()
        assert r.status_code == 201
        time.sleep(2)  # a commit left for after the response would land in this window
        assert commits and all(c <= answered for c in commits), "responded before committing"
        listed = httpx.get(f"{base}/settings/agent-keys", headers=owner, timeout=30).json()["items"]
        assert r.json()["id"] in {k["id"] for k in listed}, "read-your-writes"
    finally:
        server.should_exit = True
