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
