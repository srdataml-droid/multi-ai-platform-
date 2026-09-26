"""Seed demo tenants. Idempotent: re-running updates, never duplicates.

Auth subjects use the `dev|` prefix so a dev token (apps/api devtoken.py) can
log in as them without a real identity provider.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from novaxis_core.models import Location, Tenant, User
from novaxis_core.tenant_settings import DayHours, EscalationContact, Service, TenantSettings
from novaxis_db.session import service_session

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri")


def _settings(pack_id: str) -> TenantSettings:
    hours = {d: DayHours(open="08:00", close="18:00") for d in WEEKDAYS}
    if pack_id == "hvac":
        services = [
            Service(code="repair_visit", name="Repair visit", duration_minutes=90),
            Service(code="boiler_service", name="Annual boiler service", duration_minutes=60),
            Service(code="estimate", name="Estimate visit", duration_minutes=45),
        ]
        area = ["SW1", "SW2", "SW3", "SE1"]
    else:
        services = [
            Service(code="checkup", name="Check-up", duration_minutes=20),
            Service(code="hygiene", name="Hygienist", duration_minutes=30),
            Service(code="emergency", name="Emergency appointment", duration_minutes=30),
        ]
        area = []
    return TenantSettings(
        pack_id=pack_id,
        business_hours=hours,
        services=services,
        service_area=area,
        escalation_contacts=[
            EscalationContact(name="On-call", phone="+447700900000", email="oncall@example.test")
        ],
    )


DEMO_TENANTS = (
    ("demo-hvac", "Demo Heating & Cooling", "hvac"),
    ("demo-dental", "Demo Dental Practice", "dental"),
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
        tenant.settings = _settings(pack_id).model_dump()
        session.flush()

        if session.scalar(select(Location).where(Location.tenant_id == tenant.id)) is None:
            session.add(Location(tenant_id=tenant.id, name="Main", timezone="Europe/London"))

        subject = f"dev|owner@{slug}"
        if session.scalar(select(User).where(User.auth_subject == subject)) is None:
            session.add(
                User(
                    tenant_id=tenant.id,
                    auth_subject=subject,
                    email=f"owner@{slug}.test",
                    role="owner",
                    display_name="Demo Owner",
                )
            )
        out.append(tenant)
    session.flush()
    return out


def main() -> None:
    with service_session() as s:
        tenants = seed(s)
        for t in tenants:
            print(f"seeded {t.slug} ({t.pack_id}) id={t.id}")


if __name__ == "__main__":
    main()
