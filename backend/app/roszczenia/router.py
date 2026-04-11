"""Claim lookup endpoint — reads the ``roszczenia`` table in the app DB.

This is the "spreadsheet" pre-computed claim value for plots owned by legal
entities. It does not talk to gruntomat at all; the data is local to this
project and loaded by ``backend/scripts/ingest_roszczenia_csv.py``.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import Roszczenie

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{id_dzialki:path}")
async def get_roszczenie(
    id_dzialki: str,
    db: AsyncSession = Depends(get_db),
    _user=Depends(require_auth),
):
    """Return the plot valuation from the sheet, or 404 if not present.

    Response::

        {"id_dzialki": "...", "wartosc_dzialki": 831744695.3}

    The claim itself is computed client-side as
    ``wartosc_dzialki × 0.5 × (intersection_area / plot_area)``.
    """
    stmt = select(Roszczenie).where(Roszczenie.id_dzialki == id_dzialki)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="brak w arkuszu")
    return {
        "id_dzialki": row.id_dzialki,
        "wartosc_dzialki": float(row.wartosc_dzialki),
    }
