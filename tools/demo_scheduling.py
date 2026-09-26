"""Chunk 8 demo: intake -> staff approves the proposal -> slots offered and held.

Runs against the API at NOVAXIS_API_URL (default http://localhost:8000) with the
dev database. Needs the API running; the worker is driven inline with --once.
"""

from __future__ import annotations

import os
import subprocess
import sys

import httpx
from sqlalchemy import select

from novaxis_api.devtoken import mint
from novaxis_core.models import ActionProposal, Conversation, Tenant
from novaxis_db.session import service_session, tenant_session

API = os.environ.get("NOVAXIS_API_URL", "http://localhost:8000")


def worker_once() -> None:
    subprocess.run(
        [sys.executable, "-m", "novaxis_worker.main", "--once"], check=True, capture_output=True
    )


def main() -> int:
    token = mint("dev|owner@demo-hvac")
    auth = {"Authorization": f"Bearer {token}"}
    with httpx.Client(base_url=API, timeout=30) as c:
        r = c.post("/inbound/webchat/demo-hvac", json={"body": "hi, boiler service please"})
        r.raise_for_status()
        visitor = r.json()["visitor_token"]
        conv_id = r.json()["conversation_id"]
        worker_once()
        with service_session() as s:
            t = s.scalar(select(Tenant).where(Tenant.slug == "demo-hvac"))
            assert t is not None
            tid = t.id
        with tenant_session(tid) as s:
            conv = s.get(Conversation, conv_id)
            assert conv is not None
            p = ActionProposal(
                tenant_id=tid,
                conversation_id=conv.id,
                kind="propose_appointment",
                params={
                    "service_code": "boiler_service",
                    "preferred_window": "tomorrow",
                    "notes": "demo",
                },
                risk="medium",
                state="awaiting",
                reason="demo",
            )
            s.add(p)
            s.flush()
            pid = p.id
        print("--- staff approves the proposal to offer slots ---")
        r = c.post(f"/approvals/{pid}", headers=auth, json={"decision": "approve"})
        r.raise_for_status()
        print("proposal:", r.json()["state"], r.json()["result"])
        worker_once()
        msgs = c.get(
            "/inbound/webchat/demo-hvac/messages", params={"visitor_token": visitor}
        ).json()["messages"]
        for m in msgs:
            print(f"{m['author']}: {m['body']}")
        print("--- appointments held ---")
        for a in c.get("/appointments", headers=auth, params={"status": "held"}).json()["items"]:
            print(a["starts_at"], a["service_code"], a["status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
