import pytest
from pydantic import ValidationError

from novaxis_core.tenant_settings import DayHours, TenantSettings


def test_minimal_settings_validate() -> None:
    s = TenantSettings(pack_id="hvac")
    assert s.timezone == "Europe/London"


def test_unknown_weekday_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown weekday"):
        TenantSettings(
            pack_id="hvac", business_hours={"funday": DayHours(open="09:00", close="17:00")}
        )


def test_bad_risk_override_rejected() -> None:
    with pytest.raises(ValidationError, match="risk must be"):
        TenantSettings(pack_id="hvac", risk_overrides={"reply": "yolo"})


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError):
        TenantSettings.model_validate({"pack_id": "hvac", "typo_field": 1})


def test_retention_and_privacy_link_are_validated() -> None:
    ts = TenantSettings(pack_id="hvac")
    assert ts.retention_days == 730 and ts.privacy_url is None
    assert TenantSettings(pack_id="hvac", privacy_url=" ").privacy_url is None
    with pytest.raises(ValidationError):
        TenantSettings(pack_id="hvac", retention_days=5)
    with pytest.raises(ValidationError):
        TenantSettings(pack_id="hvac", privacy_url="javascript:alert(1)")


def test_routing_addresses_are_stored_in_one_form() -> None:
    def channels(**c: dict[str, str]) -> dict[str, dict[str, object]]:
        return {k: {"enabled": True, "config": v} for k, v in c.items()}

    ts = TenantSettings(
        pack_id="hvac",
        channels=channels(
            twilio_sms={"number": "07700 900123"},
            email={"inbound_address": " Shop@Inbound.Novaxis.test "},
        ),
    )
    assert ts.channels["twilio_sms"].config["number"] == "+447700900123"
    assert ts.channels["email"].config["inbound_address"] == "shop@inbound.novaxis.test"
    assert (
        TenantSettings(pack_id="hvac", channels=channels(twilio_sms={"number": "+1 500 555 0006"}))
        .channels["twilio_sms"]
        .config["number"]
        == "+15005550006"
    )
    for bad in ({"number": "call us"}, {"number": "12345"}):
        with pytest.raises(ValidationError):
            TenantSettings(pack_id="hvac", channels=channels(twilio_sms=bad))
    with pytest.raises(ValidationError):
        TenantSettings(pack_id="hvac", channels=channels(email={"inbound_address": "nope"}))
