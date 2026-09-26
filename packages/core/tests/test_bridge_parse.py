"""The booking bridge's pure parts: reading vendor diary exports and writing hand-off emails."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from novaxis_core.bridge import BridgeConfig, parse_export, ref_for, render_email
from novaxis_core.models import BridgeTicket

FIX = Path(__file__).parent / "fixtures" / "bridge"
LONDON = ZoneInfo("Europe/London")


def _read(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_uk_export_reads_times_refs_and_skips_cancelled_and_broken_rows() -> None:
    blocks, report = parse_export(_read("uk_diary_export.csv"), LONDON, "dmy")
    assert (report.rows, report.imported, report.skipped) == (5, 3, 2)
    assert len(report.errors) == 1 and report.errors[0].startswith("row 6:")
    first, ours, pm = blocks
    assert first.starts_at == datetime(2026, 9, 30, 8, 0, tzinfo=UTC)  # 09:00 BST
    assert first.ends_at == datetime(2026, 9, 30, 9, 30, tzinfo=UTC)
    assert first.ref is None and "Mrs Patel" in first.label
    assert ours.ref == "NX-1A2B3C"
    assert pm.starts_at == datetime(2026, 10, 1, 13, 30, tzinfo=UTC)  # 2:30 pm BST


def test_separate_date_time_and_duration_columns() -> None:
    blocks, report = parse_export(_read("date_time_duration.csv"), LONDON, "dmy")
    assert report.imported == 2 and report.skipped == 1
    assert "no start time" in report.errors[0]
    assert blocks[0].starts_at == datetime(2026, 10, 2, 7, 40, tzinfo=UTC)
    assert (blocks[0].ends_at - blocks[0].starts_at).seconds == 20 * 60


def test_us_date_order_is_a_setting() -> None:
    ny = ZoneInfo("America/New_York")
    blocks, _ = parse_export(_read("us_style_export.csv"), ny, "mdy")
    assert blocks[0].starts_at == datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
    uk_read, _ = parse_export(_read("us_style_export.csv"), ny, "dmy")
    assert uk_read[0].starts_at.month == 3, "the same file read UK-style lands in March"


def test_byte_order_mark_and_iso_offsets() -> None:
    blocks, report = parse_export(_read("bom_iso.csv"), LONDON)
    assert report.imported == 1
    assert blocks[0].starts_at == datetime(2026, 9, 30, 14, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("", "no header row"),
        ("Title,Notes\nx,y\n", "no start or date column"),
        ("Start,Title\n2026-09-30 10:00,x\n", "no end time or duration"),
    ],
)
def test_unusable_files_say_why(text: str, error: str) -> None:
    blocks, report = parse_export(text, LONDON)
    assert blocks == [] and error in report.errors[0]


def test_references_are_short_stable_and_distinct() -> None:
    a = ref_for("confirm:1")
    assert a == ref_for("confirm:1") and a != ref_for("confirm:2")
    assert a.startswith("NX-") and len(a) == 9


def test_hand_off_email_has_everything_needed_to_key_it_in() -> None:
    ticket = BridgeTicket(
        id=uuid.uuid4(),
        ref="NX-ABC123",
        action="create",
        starts_at=datetime(2026, 9, 30, 9, 0, tzinfo=UTC),
        ends_at=datetime(2026, 9, 30, 10, 30, tzinfo=UTC),
        summary="Repair visit: Sam",
        details={
            "service_code": "repair_visit",
            "service_name": "Repair visit",
            "customer_name": "Sam",
            "customer_phone": "+447700900123",
        },
    )
    cfg = BridgeConfig(
        vendor_name="Acme Jobs", email_to="office@x.test", service_map={"repair_visit": "Callout"}
    )
    subject, body = render_email(ticket, cfg, LONDON)
    assert subject == "[Novaxis] NEW booking NX-ABC123: Callout Wed 30 Sep 10:00"
    assert "Please enter this booking in Acme Jobs." in body
    assert "When: Wed 30 Sep 2026, 10:00–11:30 (Europe/London)" in body
    assert "Job type in Acme Jobs: Callout" in body
    assert "Phone: +447700900123" in body
    ticket.action = "cancel"
    subject, body = render_email(ticket, cfg, LONDON)
    assert "CANCELLED booking NX-ABC123" in subject and "remove this booking" in body
