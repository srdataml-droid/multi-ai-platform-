"""The onboarding wizard's answers become a valid TenantSettings for every pack."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from novaxis_core.onboarding import Wizard, build_settings, defaults_for, wizard_from_settings
from novaxis_core.tenant_settings import TenantSettings
from novaxis_packs import available_packs, get_pack


def _answers(pack_id: str, **over: Any) -> dict[str, Any]:
    base = defaults_for(get_pack(pack_id), "Acme Services")
    base["on_call"] = {"name": "Sam", "phone": "+447700900123", "email": None}
    base.update(over)
    return base


@pytest.mark.parametrize("pack_id", available_packs())
def test_defaults_plus_on_call_build_valid_settings_for_each_pack(pack_id: str) -> None:
    pack = get_pack(pack_id)
    wizard = Wizard.model_validate(_answers(pack_id))
    built = build_settings(pack, wizard, slug="acme", inbound_email_domain="in.example.test")
    again = TenantSettings.model_validate(built.model_dump())
    assert again.pack_id == pack_id
    assert again.services, "every pack ships default services"
    assert again.channels["webchat"].enabled
    assert not again.channels["twilio_sms"].enabled
    assert again.escalation_contacts[0].phone == "+447700900123"
    codes = {s.code for s in again.services}
    ai = pack.after_intake
    assert set(ai.service_code_map.values()) <= codes
    assert not ai.default_service_code or ai.default_service_code in codes


def test_channels_follow_the_answers() -> None:
    pack = get_pack("hvac")
    wizard = Wizard.model_validate(
        _answers("hvac", sms_number="+447700900555", email_from="hello@acme.test")
    )
    built = build_settings(pack, wizard, slug="acme", inbound_email_domain="in.example.test")
    assert built.channels["twilio_sms"].enabled
    assert built.channels["twilio_sms"].config == {"number": "+447700900555"}
    assert built.channels["email"].config == {
        "inbound_address": "acme@in.example.test",
        "from_address": "hello@acme.test",
    }


def test_round_trip_reopens_the_same_answers() -> None:
    pack = get_pack("dental")
    answers = _answers("dental", service_area=["sw1a", " SE1 "], email_from="a@b.test")
    wizard = Wizard.model_validate(answers)
    built = build_settings(pack, wizard, slug="x", inbound_email_domain="d.test")
    back = wizard_from_settings("Acme Services", built.model_dump())
    assert Wizard.model_validate(back) == wizard
    assert back["service_area"] == ["SW1A", "SE1"]


@pytest.mark.parametrize(
    ("override", "fragment"),
    [
        ({"timezone": "Mars/Olympus"}, "unknown time zone"),
        ({"business_hours": {"mon": {"open": "18:00", "close": "08:00"}}}, "before closing"),
        ({"business_hours": {"funday": {"open": "08:00", "close": "18:00"}}}, "unknown weekday"),
        ({"on_call": {"name": "Sam", "phone": None, "email": None}}, "phone number or an email"),
        ({"service_area": ["SW1 !"]}, "not a postcode"),
        ({"services": []}, "at least 1"),
        ({"sms_number": "07700 900123"}, "pattern"),
    ],
)
def test_bad_answers_fail_with_a_readable_reason(override: dict[str, Any], fragment: str) -> None:
    with pytest.raises(ValidationError) as exc:
        Wizard.model_validate(_answers("hvac", **override))
    assert fragment in str(exc.value)


def test_duplicate_service_codes_are_refused() -> None:
    services = defaults_for(get_pack("hvac"))["services"]
    with pytest.raises(ValidationError, match="its own code"):
        Wizard.model_validate(_answers("hvac", services=[services[0], services[0]]))
