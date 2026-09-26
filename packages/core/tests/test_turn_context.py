"""Pure context-building helpers, no database."""

from __future__ import annotations

from types import SimpleNamespace

from novaxis_core.turn import BOOKING_CLAIMS, build_messages


def _m(direction: str, body: str, author: str = "customer") -> SimpleNamespace:
    return SimpleNamespace(direction=direction, body=body, author=author)


def test_build_messages_alternates_and_merges() -> None:
    out = build_messages(
        [
            _m("inbound", "hi"),
            _m("inbound", "boiler broken"),
            _m("outbound", "sorry to hear", "worker"),
            _m("outbound", "I'll take over", "human"),
            _m("inbound", "thanks"),
        ]
    )
    assert [m["role"] for m in out] == ["user", "assistant", "user"]
    assert out[0]["content"] == "hi\n\nboiler broken"
    assert "[staff member]: I'll take over" in out[1]["content"]


def test_build_messages_always_ends_with_user_and_starts_with_user() -> None:
    out = build_messages([_m("outbound", "hello?", "worker")])
    assert out[0]["role"] == "user" and out[-1]["role"] == "user"


def test_booking_claim_regex() -> None:
    assert BOOKING_CLAIMS.search("Great, I've booked you for Tuesday.")
    assert BOOKING_CLAIMS.search("You're now scheduled for 9am")
    assert not BOOKING_CLAIMS.search("I've passed this to the team to confirm.")
