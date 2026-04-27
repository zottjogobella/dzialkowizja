"""Registry of restrictable response fields and per-role restriction lookup.

The registry is the single source of truth for which fields admins can hide
from non-admin tiers. Each key follows ``<endpoint>.<field>`` so the admin
UI can group them and so backend redaction sites can filter the relevant
subset by prefix.

Restrictions are scoped per ``(organization_id, role)`` — admins configure
``handlowiec`` and ``prawnik`` independently. ``admin`` and ``super_admin``
are never redacted.

Adding a new restrictable field is two steps: register it here, then call
``redact()`` (or check ``is_section_restricted()``) in the endpoint that
returns it.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RESTRICTABLE_ROLES, RestrictedField


class FieldSpec(TypedDict):
    label: str
    description: str


# Ordered for stable rendering in the admin panel.
RESTRICTABLE_FIELDS: dict[str, FieldSpec] = {
    # ── Roszczenia (field-level) ──
    "roszczenia.kw": {
        "label": "Roszczenia: numer KW",
        "description": "Numer księgi wieczystej z arkusza roszczeń.",
    },
    "roszczenia.entities": {
        "label": "Roszczenia: właściciele",
        "description": "Lista podmiotów (nazwa + typ) z arkusza roszczeń.",
    },
    # ── Whole sections ──
    "section.argumentacja": {
        "label": "Argumentacja wyceny",
        "description": "Sekcja z argumentami i pewnością wyceny działki.",
    },
    "section.mpzp": {
        "label": "Plan zagospodarowania (MPZP)",
        "description": "Informacje o planie zagospodarowania przestrzennego z GUGiK.",
    },
    "section.snapshots": {
        "label": "Zrzuty mapy",
        "description": "Ortofotomapa i mapa bazowa działki.",
    },
    "section.transactions": {
        "label": "Transakcje w okolicy",
        "description": "Tabela transakcji gruntowych w okolicy działki.",
    },
    "section.listings": {
        "label": "Ogłoszenia w okolicy",
        "description": "Ogłoszenia nieruchomości z portali w okolicy działki.",
    },
    "section.investments": {
        "label": "Aktywność inwestycyjna",
        "description": "Pozwolenia na budowę i zgłoszenia z GUNB RWDZ.",
    },
}


async def get_restricted_keys(
    db: AsyncSession, organization_id: uuid.UUID | None, role: str
) -> set[str]:
    """Return the set of field keys hidden for ``role`` inside this org.

    Returns an empty set for admin/super_admin (or any role outside
    ``RESTRICTABLE_ROLES``) and for users without an organization.
    """
    if organization_id is None or role not in RESTRICTABLE_ROLES:
        return set()
    rows = await db.execute(
        select(RestrictedField.field_key).where(
            RestrictedField.organization_id == organization_id,
            RestrictedField.role == role,
        )
    )
    return {r[0] for r in rows}


async def is_section_restricted(
    db: AsyncSession, user, section_key: str,
) -> bool:
    """Check if a whole section is hidden for this user's role+org.

    Returns False for admin/super_admin — they always see everything.
    """
    if user.role not in RESTRICTABLE_ROLES:
        return False
    restricted = await get_restricted_keys(db, user.organization_id, user.role)
    return section_key in restricted


def redact(payload: dict, restricted: set[str], prefix: str) -> dict:
    """Remove fields from ``payload`` that are restricted under ``prefix``.

    A key like ``roszczenia.kw`` matches ``prefix='roszczenia'`` and removes
    ``payload['kw']``. Mutates and returns the same dict for convenience.
    """
    pref = f"{prefix}."
    for key in restricted:
        if not key.startswith(pref):
            continue
        field = key[len(pref):]
        if field in payload:
            payload[field] = None
    return payload
