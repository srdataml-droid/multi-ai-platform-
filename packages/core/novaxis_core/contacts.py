"""The same person reaching us on two channels (web chat, then SMS) starts as two contacts,
because each channel identifies people differently. When a chat visitor types a phone number
or email that another contact already has, staff see it as a possible duplicate and merge.

Never merged automatically: a chat visitor can type anyone's number, and merging would join
their conversation to a stranger's history."""

from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from novaxis_core.models import Appointment, AuditLog, Contact, Conversation
from novaxis_core.sensitive import is_encrypted

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_phone(raw: str) -> str | None:
    """E.164 for the numbers a UK business sees: 07700 900123, +44 7700 900123, 447700900123.
    Anything else with a leading + is kept as typed digits. Returns None if it is not a phone."""
    s = raw.strip().replace("(0)", "")  # "+44 (0)7700 ..." drops the trunk zero
    digits = re.sub(r"\D", "", s)
    if s.startswith("+"):
        out = "+" + digits
    elif digits.startswith("44"):
        out = "+" + digits
    elif digits.startswith("0") and len(digits) == 11:
        out = "+44" + digits[1:]
    else:
        return None
    return out if 10 <= len(out) - 1 <= 15 else None


def normalize_email(raw: str) -> str | None:
    s = raw.strip().lower()
    return s if EMAIL.match(s) else None


def typed_identifiers(extracted: dict[str, Any]) -> tuple[set[str], set[str]]:
    """Phones and emails a customer typed during intake (the pack's `phone`/`email` keys)."""
    phones: set[str] = set()
    emails: set[str] = set()
    for key, value in extracted.items():
        if not isinstance(value, str) or is_encrypted(value):
            continue
        k = key.lower()
        if "phone" in k or k in ("mobile", "tel"):
            if p := normalize_phone(value):
                phones.add(p)
        elif "email" in k:
            if e := normalize_email(value):
                emails.add(e)
    return phones, emails


def possible_duplicates(
    session: Session, contacts: list[Contact]
) -> dict[uuid.UUID, list[Contact]]:
    """For each contact, the other live contacts already holding a phone or email it typed."""
    if not contacts:
        return {}
    typed: dict[uuid.UUID, tuple[set[str], set[str]]] = {c.id: (set(), set()) for c in contacts}
    for conv in session.scalars(
        select(Conversation).where(Conversation.contact_id.in_(list(typed)))
    ):
        phones, emails = typed_identifiers(conv.extracted or {})
        typed[conv.contact_id][0].update(phones)
        typed[conv.contact_id][1].update(emails)
    all_phones = sorted({p for ph, _ in typed.values() for p in ph})
    all_emails = sorted({e for _, em in typed.values() for e in em})
    if not all_phones and not all_emails:
        return {}
    conds = []
    if all_phones:
        conds.append(Contact.phones.overlap(all_phones))
    if all_emails:
        conds.append(Contact.emails.overlap(all_emails))
    holders = list(
        session.scalars(select(Contact).where(Contact.merged_into.is_(None), or_(*conds)))
    )
    out: dict[uuid.UUID, list[Contact]] = {}
    for cid, (phones, emails) in typed.items():
        matches = [
            h for h in holders if h.id != cid and (phones & set(h.phones) or emails & set(h.emails))
        ]
        if matches:
            out[cid] = matches
    return out


def merge(
    session: Session, tenant_id: uuid.UUID, keep: Contact, drop: Contact, actor: str
) -> Contact:
    """Fold `drop` into `keep`: its conversations and appointments move over, identifiers
    are combined, and an opt-out on either side wins. `drop` stays as a pointer."""
    if keep.id == drop.id or drop.merged_into is not None or keep.merged_into is not None:
        raise ValueError("these contacts cannot be merged")
    session.execute(
        update(Conversation).where(Conversation.contact_id == drop.id).values(contact_id=keep.id)
    )
    session.execute(
        update(Appointment).where(Appointment.contact_id == drop.id).values(contact_id=keep.id)
    )
    keep.phones = list(dict.fromkeys([*keep.phones, *drop.phones]))
    keep.emails = list(dict.fromkeys([*keep.emails, *drop.emails]))
    keep.visitor_ids = list(dict.fromkeys([*keep.visitor_ids, *drop.visitor_ids]))
    keep.display_name = keep.display_name or drop.display_name
    keep.pack_fields = {**drop.pack_fields, **keep.pack_fields}
    if drop.consent.get("status") == "opted_out" and keep.consent.get("status") != "opted_out":
        keep.consent = drop.consent
    drop.merged_into = keep.id
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor=actor,
            event="contact.merged",
            subject_table="contacts",
            subject_id=keep.id,
            diff={"merged": str(drop.id)},
        )
    )
    session.flush()
    return keep
