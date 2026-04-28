"""Claim lookup endpoint — reads the ``roszczenia`` table in the app DB.

This is the "spreadsheet" pre-computed claim value for plots owned by legal
entities. It does not talk to gruntomat at all; the data is local to this
project and loaded by ``backend/scripts/ingest_roszczenia_csv.py``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import record
from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import Roszczenie, User, WycenaSupplemental
from app.middleware.rate_limit_dep import rate_limit_detail
from app.permissions.fields import get_restricted_keys, redact

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{id_dzialki:path}")
async def get_roszczenie(
    id_dzialki: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
    _rl: None = Depends(rate_limit_detail),
):
    """Return the plot valuation from the sheet, or 404 if not present.

    Response::

        {
          "id_dzialki": "...",
          "wartosc_dzialki": 831744695.3,
          "wartosc_dzialki_old": 720000000.0,
          "kw": "BB1B/00053878/8",
          "entities": "NAME;;os prawna"
        }

    ``wartosc_dzialki_old`` is the prior valuation from the CSV — null when
    that column wasn't present in the source. For role=user, ``kw`` and
    ``entities`` may be redacted to ``null`` based on per-organization
    restrictions toggled by the admin.
    """
    stmt = select(Roszczenie).where(Roszczenie.id_dzialki == id_dzialki)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is not None:
        # `no_kw_in_sheet` is computed before redaction and stays outside the
        # restrictable-fields registry: it's a complication flag, not KW data, so
        # users with `roszczenia.kw` hidden still get the "brak KW" warning.
        payload = {
            "id_dzialki": row.id_dzialki,
            "wartosc_dzialki": float(row.wartosc_dzialki),
            "wartosc_dzialki_old": float(row.wartosc_dzialki_old) if row.wartosc_dzialki_old is not None else None,
            # cena_m2 only ships from the supplemental fallback; for sheet rows
            # the per-m² price is surfaced via /api/argumentacja's
            # cena_m2_roszczenie_orig instead.
            "cena_m2": None,
            "kw": row.kw,
            "entities": row.entities,
            "has_sluzebnosci": row.has_sluzebnosci,
            "has_10_or_more_owners": row.has_10_or_more_owners,
            "has_state_owner": row.has_state_owner,
            "no_kw_in_sheet": not (row.kw and row.kw.strip()),
            "source": "sheet",
        }

        restricted = await get_restricted_keys(db, user.organization_id, user.role)
        if restricted:
            redact(payload, restricted, prefix="roszczenia")
    else:
        # Fallback to the supplemental sheet (wider plot coverage but no KW /
        # owner data). Returned in the same shape with the missing fields as
        # null/false so the frontend can still autofill the valuation.
        supp = (
            await db.execute(
                select(WycenaSupplemental).where(
                    WycenaSupplemental.id_dzialki == id_dzialki
                )
            )
        ).scalar_one_or_none()
        if supp is None:
            raise HTTPException(status_code=404, detail="brak w arkuszu")

        payload = {
            "id_dzialki": supp.id_dzialki,
            "wartosc_dzialki": float(supp.wartosc_dzialki),
            "wartosc_dzialki_old": None,
            "cena_m2": float(supp.cena_m2) if supp.cena_m2 is not None else None,
            "kw": None,
            "entities": None,
            "has_sluzebnosci": None,
            "has_10_or_more_owners": None,
            "has_state_owner": None,
            "no_kw_in_sheet": False,
            "source": "supplemental",
        }

    await record(db, user, action_type="roszczenie_fetch", request=request, target_id=id_dzialki)
    return payload
