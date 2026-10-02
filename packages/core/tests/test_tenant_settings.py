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


def test_whatsapp_number_id_must_be_digits() -> None:
    ts = TenantSettings(
        pack_id="hvac",
        channels={"whatsapp": {"enabled": True, "config": {"phone_number_id": " 1234567 "}}},
    )
    assert ts.channels["whatsapp"].config["phone_number_id"] == "1234567"
    with pytest.raises(ValidationError):
        TenantSettings(
            pack_id="hvac",
            channels={"whatsapp": {"enabled": True, "config": {"phone_number_id": "+44 7700"}}},
        )


def test_whatsapp_update_template_is_a_meta_name_and_language() -> None:
    def wa(t: object) -> TenantSettings:
        return TenantSettings(
            pack_id="hvac",
            channels={"whatsapp": {"enabled": True, "config": {"update_template": t}}},
        )

    assert wa({"name": " novaxis_update "}).channels["whatsapp"].config["update_template"] == {
        "name": "novaxis_update",
        "language": "en_GB",
    }
    assert (
        wa({"name": "x_1", "language": "en"})
        .channels["whatsapp"]
        .config["update_template"]["language"]
        == "en"
    )
    for bad in (
        {"name": "Novaxis Update"},
        {"name": ""},
        {"name": "ok", "language": "English"},
        "x",
    ):
        with pytest.raises(ValidationError):
            wa(bad)


def test_technicians_must_reference_real_services_and_workdays() -> None:
    s = TenantSettings.model_validate(
        {
            "pack_id": "hvac",
            "services": [
                {"code": "repair", "name": "Repair", "duration_minutes": 60},
                {"code": "install", "name": "Install", "duration_minutes": 180},
            ],
            "technicians": [
                {
                    "code": "james",
                    "name": "James",
                    "service_codes": ["repair"],
                    "working_days": ["mon", "wed", "fri"],
                }
            ],
        }
    )
    assert s.technicians[0].service_codes == ["repair"]
    assert s.technicians[0].working_days == ["mon", "wed", "fri"]

    with pytest.raises(ValidationError, match="unknown services"):
        TenantSettings.model_validate(
            {
                "pack_id": "hvac",
                "services": [{"code": "repair", "name": "Repair", "duration_minutes": 60}],
                "technicians": [
                    {
                        "code": "james",
                        "name": "James",
                        "service_codes": ["install"],
                        "working_days": ["mon"],
                    }
                ],
            }
        )
    with pytest.raises(ValidationError, match="unknown weekday"):
        TenantSettings.model_validate(
            {
                "pack_id": "hvac",
                "services": [{"code": "repair", "name": "Repair", "duration_minutes": 60}],
                "technicians": [
                    {
                        "code": "james",
                        "name": "James",
                        "service_codes": ["repair"],
                        "working_days": ["monday"],
                    }
                ],
            }
        )


def test_technician_codes_are_unique() -> None:
    with pytest.raises(ValidationError, match="share a code"):
        TenantSettings.model_validate(
            {
                "pack_id": "hvac",
                "services": [{"code": "repair", "name": "Repair", "duration_minutes": 60}],
                "technicians": [
                    {
                        "code": "tech",
                        "name": "James",
                        "service_codes": ["repair"],
                        "working_days": ["mon"],
                    },
                    {
                        "code": "tech",
                        "name": "Maya",
                        "service_codes": ["repair"],
                        "working_days": ["tue"],
                    },
                ],
            }
        )
