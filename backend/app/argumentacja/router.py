"""Argumentacja endpoint — valuation arguments for a plot."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import Argumentacja, User
from app.permissions.fields import is_section_restricted

router = APIRouter()


def _opt_float(v) -> float | None:
    return float(v) if v is not None else None


@router.get("/{id_dzialki:path}")
async def get_argumentacja(
    id_dzialki: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
):
    if await is_section_restricted(db, user, "section.argumentacja"):
        raise HTTPException(status_code=404, detail="brak argumentacji")

    stmt = select(Argumentacja).where(Argumentacja.id_dzialki == id_dzialki)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="brak argumentacji")

    # Collapse argument_1..15 + waga into a sorted list
    argumenty = []
    for i in range(1, 16):
        text = getattr(row, f"argument_{i}", None)
        waga = getattr(row, f"argument_{i}_waga", None)
        if text:
            argumenty.append({"text": text, "waga": int(waga) if waga is not None else 0})
    argumenty.sort(key=lambda a: a["waga"], reverse=True)

    return {
        "id_dzialki": row.id_dzialki,
        "segment": row.segment,
        "pow_m2": _opt_float(row.pow_m2),
        "pow_buforu": _opt_float(row.pow_buforu),
        "procent_pow": _opt_float(row.procent_pow),
        "cena_ensemble": _opt_float(row.cena_ensemble),
        "wartosc_total": _opt_float(row.wartosc_total),
        "cena_m2_roszczenie_orig": _opt_float(row.cena_m2_roszczenie_orig),
        "wartosc_roszczenia_orig": _opt_float(row.wartosc_roszczenia_orig),
        "pewnosc_0_100": row.pewnosc_0_100,
        "pewnosc_kategoria": row.pewnosc_kategoria,
        "argumenty": argumenty,
    }
