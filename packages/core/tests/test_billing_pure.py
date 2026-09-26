"""Billing pieces that need no database: Stripe signatures, the HTTP calls, plans."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from urllib.parse import parse_qs

import httpx
import pytest

from novaxis_core.billing import StripeClient, plans, provider, verify_stripe_signature
from novaxis_core.models import Tenant
from novaxis_core.settings import get_settings

SECRET = "whsec_test_secret"


def _header(payload: bytes, t: int, secret: str = SECRET) -> str:
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def test_signature_accepts_a_fresh_correct_signature() -> None:
    body = b'{"id":"evt_1"}'
    assert verify_stripe_signature(body, _header(body, 1000), SECRET, now=1010)


@pytest.mark.parametrize(
    ("header_for", "now"),
    [
        (lambda b: _header(b + b" ", 1000), 1010),  # body changed after signing
        (lambda b: _header(b, 1000, "whsec_other"), 1010),  # someone else's secret
        (lambda b: _header(b, 1000), 1000 + 301),  # replayed after the tolerance window
        (lambda b: "t=1000", 1010),  # no signature
        (lambda b: "v1=abc", 1010),  # no timestamp
        (lambda b: "t=soon,v1=abc", 1010),  # junk timestamp
    ],
)
def test_signature_rejects(header_for, now: int) -> None:  # type: ignore[no-untyped-def]
    body = b'{"id":"evt_1"}'
    assert not verify_stripe_signature(body, header_for(body), SECRET, now=now)


def test_provider_is_demo_until_both_stripe_keys_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_STRIPE_SECRET_KEY", "sk_test_x")
    get_settings.cache_clear()
    try:
        assert provider() == "demo"
        monkeypatch.setenv("NOVAXIS_STRIPE_WEBHOOK_SECRET", "whsec_x")
        get_settings.cache_clear()
        assert provider() == "stripe"
    finally:
        get_settings.cache_clear()


def test_pilot_waives_the_setup_fee() -> None:
    p = plans()
    assert p["pilot"].setup_pence == 0
    assert p["standard"].setup_pence > 0
    assert p["pilot"].monthly_pence == p["standard"].monthly_pence


def test_checkout_sends_the_prices_and_the_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOVAXIS_STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv(
        "NOVAXIS_STRIPE_PRICES",
        '{"standard": {"monthly": "price_m", "setup": "price_s", "metered": "price_u"},'
        ' "pilot": {"monthly": "price_m", "setup": "price_s", "metered": "price_u"}}',
    )
    get_settings.cache_clear()
    seen: list[httpx.Request] = []

    def handle(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json={"url": "https://checkout.stripe.test/c/abc"})

    tenant = Tenant(id=uuid.uuid4(), name="A", slug="a", pack_id="hvac")
    try:
        client = StripeClient(transport=httpx.MockTransport(handle))
        assert client.checkout_url(tenant, "standard", "https://w/ok", "https://w/no") == (
            "https://checkout.stripe.test/c/abc"
        )
        client.checkout_url(tenant, "pilot", "https://w/ok", "https://w/no")
    finally:
        get_settings.cache_clear()
    std = {k: v[0] for k, v in parse_qs(seen[0].content.decode()).items()}
    assert seen[0].url.path == "/v1/checkout/sessions"
    assert seen[0].headers["authorization"].startswith("Basic ")
    assert std["mode"] == "subscription"
    assert std["client_reference_id"] == str(tenant.id)
    assert std["metadata[tenant_id]"] == str(tenant.id)
    assert std["metadata[plan]"] == "standard"
    assert std["line_items[0][price]"] == "price_m"
    assert std["line_items[1][price]"] == "price_s"
    assert std["line_items[2][price]"] == "price_u"
    assert "line_items[2][quantity]" not in std, "metered prices take no quantity"
    pilot = {k: v[0] for k, v in parse_qs(seen[1].content.decode()).items()}
    assert "price_s" not in pilot.values(), "pilot has no setup line"
    assert pilot["line_items[1][price]"] == "price_u"
