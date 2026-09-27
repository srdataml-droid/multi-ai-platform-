"""Synthetic bookings with *known* causes of no-shows, to prove the pipeline end to end.

This is not a model of real customers. It exists so that, before any real outcomes are
recorded, we can check that export, training, the exported file and live scoring agree,
and that training recovers effects we planted. Planted effects (on the log-odds):

- each day booked in advance: +0.03 (clipped at 120 days)
- the customer confirmed: -1.2
- each earlier missed appointment: +0.7; each earlier attended one: -0.15
- Monday: +0.3; booked by web chat: +0.25; hour 8 (first slot): +0.2
"""

from __future__ import annotations

import math
import random
from datetime import UTC, datetime, timedelta

from novaxis_core.features import Booking, LabelledRow, features

SERVICES = {
    "hvac": ["repair_visit", "boiler_service", "install_quote"],
    "dental": ["checkup", "hygiene", "emergency"],
    "restoration": ["inspection", "drying_visit"],
}
CHANNELS = ["webchat", "twilio_sms", "email"]
BASE = -2.2


def true_logit(b: Booking) -> float:
    x = features(b)
    z = BASE + 0.03 * x["lead_days"] - 1.2 * x["confirmed"]
    z += 0.7 * x["prior_no_shows"] - 0.15 * x["prior_attended"]
    z += 0.3 * (x["weekday"] == "mon") + 0.25 * (x["channel"] == "webchat")
    z += 0.2 * (x["hour"] == 8.0)
    return float(z)


def generate(n: int = 4000, seed: int = 7) -> list[LabelledRow]:
    rng = random.Random(seed)
    start = datetime(2025, 1, 6, tzinfo=UTC)
    rows: list[LabelledRow] = []
    for _ in range(n):
        pack = rng.choice(list(SERVICES))
        day = start + timedelta(days=rng.randrange(0, 600))
        while day.weekday() == 6:
            day += timedelta(days=1)
        starts = day.replace(hour=rng.randrange(8, 17))
        lead = rng.choice([0, 1, 2, 3, 5, 7, 10, 14, 21, 30, 45, 60, 90])
        b = Booking(
            starts_at=starts,
            booked_at=starts - timedelta(days=lead, hours=rng.randrange(0, 12)),
            service_code=rng.choice(SERVICES[pack]),
            channel=rng.choice(CHANNELS),
            pack_id=pack,
            confirmed=rng.random() < 0.55,
            prior_attended=rng.choice([0, 0, 0, 1, 1, 2, 3, 5]),
            prior_no_shows=rng.choice([0, 0, 0, 0, 0, 1, 1, 2]),
            timezone="UTC",
        )
        p = 1 / (1 + math.exp(-true_logit(b)))
        rows.append(LabelledRow(starts, features(b), int(rng.random() < p)))
    rows.sort(key=lambda r: r.starts_at)
    return rows
