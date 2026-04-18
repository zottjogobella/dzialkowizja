"""Endpoints for the "Aktywność inwestycyjna" (investment activity) feature.

Returns nearby GUNB RWDZ records (building permits + zgłoszenia) for a plot.
Data is populated by `backend/scripts/ingest_gunb_rwdz.py` into
`gruntomat.gunb_investments`; this endpoint does a spatial lookup in EPSG:2180
around the plot centroid, mirroring the pattern used by the transactions and
listings endpoints in `app.plots.router`.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Literal

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import record
from app.auth.dependencies import require_auth
from app.config import settings
from app.db.engine import get_db
from app.db.models import User
from app.middleware.rate_limit_dep import rate_limit_detail
from app.permissions.fields import is_section_restricted

logger = logging.getLogger(__name__)

router = APIRouter()

TYPE_FILTER_SQL = {
    "all": "TRUE",
    "pozwolenie": "i.typ = 'pozwolenie_budowa'",
    "zgloszenie": "i.typ = 'zgloszenie'",
    "warunki": "i.typ = 'warunki_zabudowy'",  # reserved for future source
}

InvestmentType = Literal["all", "pozwolenie", "zgloszenie", "warunki"]


def _fetch_investments(
    id_dzialki: str,
    months: int,
    type_filter: InvestmentType,
    max_distance_m: int,
    limit: int = 30,
) -> list[dict] | None:
    """Return the *nearest* N investments to the plot, capped by max distance.

    Returns None when the plot does not exist.

    Distances are against the full plot polygon (not the centroid), and the
    nearest-neighbour ORDER BY uses the GiST index via the ``<->`` operator.
    The max-distance cap stops us from listing records hundreds of km away
    when the area has sparse coverage, while still returning SOMETHING if
    there's anything within a sensible reach.
    """
    conn = psycopg2.connect(
        host=settings.geo_db_host,
        port=settings.geo_db_port,
        dbname=settings.geo_db_name,
        user=settings.geo_db_user,
        password=settings.geo_db_password,
        connect_timeout=10,
    )
    type_sql = TYPE_FILTER_SQL.get(type_filter, "TRUE")
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT geom FROM lots_enriched WHERE id_dzialki = %s",
                (id_dzialki,),
            )
            if cur.fetchone() is None:
                return None

            # Time window uses COALESCE(data_decyzji, data_wniosku) so zgłoszenia
            # (no decision date) are still filtered in. Sort by the index-
            # friendly KNN operator so we get the nearest N even when the
            # table is sparse in this region.
            cur.execute(
                f"""
                SELECT * FROM (
                    SELECT
                        i.id, i.typ, i.status, i.data_wniosku, i.data_decyzji,
                        i.inwestor, i.organ, i.wojewodztwo, i.gmina,
                        i.miejscowosc, i.teryt_gmi, i.adres, i.opis,
                        i.kategoria, i.rodzaj_inwestycji, i.kubatura,
                        i.parcel_id, i.source_id, i.raw_data,
                        ST_X(ST_Transform(i.geom, 4326)) AS lng,
                        ST_Y(ST_Transform(i.geom, 4326)) AS lat,
                        ST_Distance(i.geom, lot.geom) AS distance_m
                    FROM gunb_investments i,
                         (SELECT geom FROM lots_enriched WHERE id_dzialki = %s) lot
                    WHERE i.geom IS NOT NULL
                      AND {type_sql}
                      AND COALESCE(i.data_decyzji, i.data_wniosku)
                          >= (NOW() - make_interval(months => %s))::date
                    ORDER BY i.geom <-> lot.geom
                    LIMIT %s
                ) nearest
                WHERE distance_m <= %s
                ORDER BY distance_m ASC, COALESCE(data_decyzji, data_wniosku) DESC NULLS LAST
                """,
                (id_dzialki, months, limit, max_distance_m),
            )
            columns = [d[0] for d in cur.description]
            results = []
            for row in cur.fetchall():
                d = dict(zip(columns, row))
                for k in ("data_wniosku", "data_decyzji"):
                    if d.get(k) is not None:
                        d[k] = d[k].isoformat() if hasattr(d[k], "isoformat") else str(d[k])
                if d.get("distance_m") is not None:
                    d["distance_m"] = round(float(d["distance_m"]), 1)
                if d.get("lng") is not None:
                    d["lng"] = float(d["lng"])
                if d.get("lat") is not None:
                    d["lat"] = float(d["lat"])
                if d.get("kubatura") is not None:
                    d["kubatura"] = float(d["kubatura"])
                # raw_data is JSONB — psycopg2 usually returns a dict but
                # older drivers leave it as a string. Normalise either way so
                # the API contract stays ``dict | null``.
                raw = d.get("raw_data")
                if isinstance(raw, str):
                    try:
                        import json as _json
                        d["raw_data"] = _json.loads(raw)
                    except ValueError:
                        d["raw_data"] = None
                results.append(d)
            return results
    finally:
        conn.close()


@router.get("/{id_dzialki:path}")
async def get_investments(
    id_dzialki: str,
    request: Request,
    months: int = Query(24, ge=1, le=120),
    type: InvestmentType = Query("all"),
    max_distance_m: int = Query(10000, ge=100, le=50000),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_detail),
):
    """Return the nearest GUNB RWDZ investments to the plot.

    Query params:
        months          — time window in months from data_decyzji (or
                          data_wniosku), default 24, max 120
        type            — all | pozwolenie | zgloszenie | warunki,
                          default all
        max_distance_m  — ignore investments farther than this from the
                          plot edge (default 10 km, max 50 km). Needed
                          because the table is currently sparse (only a
                          test slice of RWDZ is loaded); otherwise KNN
                          would return results from another voivodeship.

    Results are the 30 nearest items, then re-sorted by distance asc and
    decision date desc.
    """
    if await is_section_restricted(db, user, "section.investments"):
        return []

    try:
        result = await asyncio.to_thread(
            _fetch_investments, id_dzialki, months, type, max_distance_m, 30,
        )
    except Exception:
        logger.exception("Failed to fetch investments id=%s", id_dzialki)
        return []

    if result is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    await record(db, user, action_type="investment_fetch", request=request, target_id=id_dzialki)
    return result
