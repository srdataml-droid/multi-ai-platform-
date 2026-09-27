"""Seed demo tenants. Idempotent: re-running updates, never duplicates.

Auth subjects use the `dev|` prefix so a dev token (apps/api devtoken.py) can
log in as them without a real identity provider.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import Location, Tenant, User
from novaxis_core.tenant_settings import (
    ChannelConfig,
    DayHours,
    EscalationContact,
    Service,
    TenantSettings,
)
from novaxis_db.session import service_session

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")


def _channels(slug: str) -> dict[str, ChannelConfig]:
    """Demo channel config. The Twilio number is a documented test number, never live."""
    return {
        "webchat": ChannelConfig(enabled=True),
        "twilio_sms": ChannelConfig(
            enabled=True,
            config={
                "number": {"demo-hvac": "+15005550006", "demo-dental": "+15005550007"}.get(
                    slug, "+15005550008"
                )
            },
        ),
        # Calls to the same Twilio number (docs/voice.md).
        "twilio_voice": ChannelConfig(enabled=True),
        "email": ChannelConfig(
            enabled=True,
            config={
                "inbound_address": f"{slug}@inbound.novaxis.test",
                "from_address": f"hello@{slug}.test",
            },
        ),
    }


def _settings(pack_id: str, slug: str) -> TenantSettings:
    hours = {d: DayHours(open="08:00", close="18:00") for d in WEEKDAYS}
    if pack_id == "hvac":
        services = [
            Service(code="repair_visit", name="Repair visit", duration_minutes=90),
            Service(code="boiler_service", name="Annual boiler service", duration_minutes=60),
            Service(code="estimate", name="Estimate visit", duration_minutes=45),
        ]
        area = ["SW1", "SW2", "SW3", "SE1"]
    elif pack_id == "dental":
        services = [
            Service(code="checkup", name="Check-up", duration_minutes=20),
            Service(code="hygiene", name="Hygienist", duration_minutes=30),
            Service(code="emergency", name="Emergency appointment", duration_minutes=30),
        ]
        area = []
    else:
        services = [
            Service(code="inspection", name="Damage inspection", duration_minutes=60),
            Service(code="emergency_mitigation", name="Emergency mitigation", duration_minutes=120),
        ]
        area = ["SW", "SE", "W", "E", "N", "NW", "EC", "WC"]
    return TenantSettings(
        pack_id=pack_id,
        business_hours=hours,
        services=services,
        service_area=area,
        escalation_contacts=[
            EscalationContact(name="On-call", phone="+447700900000", email="oncall@example.test")
        ],
        channels=_channels(slug),
    )


DEMO_TENANTS = (
    ("demo-hvac", "Demo Heating & Cooling", "hvac"),
    ("demo-dental", "Demo Dental Practice", "dental"),
    ("demo-restoration", "Demo Restoration Services", "restoration"),
)


def seed(session: Session) -> list[Tenant]:
    out: list[Tenant] = []
    for slug, name, pack_id in DEMO_TENANTS:
        tenant = session.scalar(select(Tenant).where(Tenant.slug == slug))
        if tenant is None:
            tenant = Tenant(slug=slug, name=name, pack_id=pack_id, status="active")
            session.add(tenant)
        tenant.name = name
        tenant.pack_id = pack_id
        tenant.settings = _settings(pack_id, slug).model_dump()
        tenant.onboarded_at = tenant.onboarded_at or datetime.now(UTC)
        if tenant.plan == "trial" and tenant.status == "active":
            tenant.plan = "pilot"  # demo tenants run as pilots, not trials
        session.flush()

        if session.scalar(select(Location).where(Location.tenant_id == tenant.id)) is None:
            session.add(Location(tenant_id=tenant.id, name="Main", timezone="Europe/London"))

        for role in ("owner", "viewer"):
            subject = f"dev|{role}@{slug}"
            if session.scalar(select(User).where(User.auth_subject == subject)) is None:
                session.add(
                    User(
                        tenant_id=tenant.id,
                        auth_subject=subject,
                        email=f"{role}@{slug}.test",
                        role=role,
                        display_name=f"Demo {role.title()}",
                    )
                )
        out.append(tenant)
    _seed_operator(session)
    session.flush()
    return out


OPS_SLUG = "novaxis-ops"


def _seed_operator(session: Session) -> None:
    """Novaxis staff sign in to an internal tenant with the operator role. `plan = internal`
    keeps it out of the operator console, billing and the worker's timers."""
    ops = session.scalar(select(Tenant).where(Tenant.slug == OPS_SLUG))
    if ops is None:
        ops = Tenant(
            slug=OPS_SLUG,
            name="Novaxis Operations",
            pack_id="generic",
            plan="internal",
            status="active",
            worker_enabled=False,
            settings=TenantSettings(pack_id="generic").model_dump(),
            onboarded_at=datetime.now(UTC),
        )
        session.add(ops)
        session.flush()
    subject = f"dev|operator@{OPS_SLUG}"
    if session.scalar(select(User).where(User.auth_subject == subject)) is None:
        session.add(
            User(
                tenant_id=ops.id,
                auth_subject=subject,
                email="operator@novaxis.test",
                role="operator",
                display_name="Novaxis Operator",
            )
        )


def main() -> None:
    with service_session() as s:
        tenants = seed(s)
        for t in tenants:
            print(f"seeded {t.slug} ({t.pack_id}) id={t.id}")


if __name__ == "__main__":
    main()
