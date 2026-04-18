"""Registry of restrictable response fields and per-org restriction lookup.

The registry is the single source of truth for which fields admins can hide
from role=user. Each key follows ``<endpoint>.<field>`` so the admin UI can
group them and so backend redaction sites can filter the relevant subset
by prefix.

Adding a new restrictable field is two steps: register it here, then call
``redact()`` (or check ``is_restricted()``) in the endpoint that returns it.
"""

from __future__ import annotations

import uuid
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RestrictedField


class FieldSpec(TypedDict):
    label: str
    description: str


# Ordered for stable rendering in the admin panel.
RESTRICTABLE_FIELDS: dict[str, FieldSpec] = {
    "roszczenia.kw": {
        "label": "Roszczenia: numer KW",
        "description": "Numer księgi wieczystej z arkusza roszczeń.",
    },
    "roszczenia.entities": {
        "label": "Roszczenia: właściciele",
        "description": "Lista podmiotów (nazwa + typ) z arkusza roszczeń.",
    },
}


async def get_restricted_keys(db: AsyncSession, organization_id: uuid.UUID | None) -> set[str]:
    """Return the set of field keys hidden for role=user inside this org.

    super_admin lives outside any org (organization_id is None) — they should
    never be redacted, so callers shouldn't reach this function for them.
    For safety we still return an empty set when organization_id is None.
    """
    if organization_id is None:
        return set()
    rows = await db.execute(
        select(RestrictedField.field_key).where(
            RestrictedField.organization_id == organization_id
        )
    )
    return {r[0] for r in rows}


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
