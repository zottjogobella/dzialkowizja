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
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import require_auth
from app.config import settings

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
    radius_m: int,
    limit: int = 100,
) -> list[dict] | None:
    """Return investments within `radius_m` of the plot *geometry* (not centroid).

    Returns None when the plot does not exist.

    Distances and the ST_DWithin filter are computed against the full plot
    polygon, matching the powerlines endpoint — a 500 m buffer around a
    large plot can add hundreds of metres of reach compared to measuring
    from the centroid.
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
            # (which have no decision date) are still filtered in.
            cur.execute(
                f"""
                SELECT
                    i.id, i.typ, i.status, i.data_wniosku, i.data_decyzji,
                    i.inwestor, i.organ, i.miejscowosc, i.adres, i.opis,
                    i.kategoria, i.rodzaj_inwestycji, i.parcel_id,
                    ST_X(ST_Transform(i.geom, 4326)) AS lng,
                    ST_Y(ST_Transform(i.geom, 4326)) AS lat,
                    ST_Distance(i.geom, lot.geom) AS distance_m
                FROM gunb_investments i,
                     (SELECT geom FROM lots_enriched WHERE id_dzialki = %s) lot
                WHERE i.geom IS NOT NULL
                  AND {type_sql}
                  AND ST_DWithin(i.geom, lot.geom, %s)
                  AND COALESCE(i.data_decyzji, i.data_wniosku)
                      >= (NOW() - make_interval(months => %s))::date
                ORDER BY distance_m ASC, COALESCE(i.data_decyzji, i.data_wniosku) DESC NULLS LAST
                LIMIT %s
                """,
                (id_dzialki, radius_m, months, limit),
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
                results.append(d)
            return results
    finally:
        conn.close()


@router.get("/{id_dzialki:path}")
async def get_investments(
    id_dzialki: str,
    months: int = Query(24, ge=1, le=120),
    type: InvestmentType = Query("all"),
    radius_m: int = Query(1000, ge=50, le=5000),
    _user=Depends(require_auth),
):
    """Return GUNB RWDZ investments within `radius_m` of the plot geometry.

    Query params:
        months   — time window in months from data_decyzji (or data_wniosku), default 24, max 120
        type     — all | pozwolenie | zgloszenie | warunki, default all
        radius_m — search radius in metres from the plot edge, default 1000, max 5000

    Results sorted by distance asc then decision date desc, capped at 100.
    """
    try:
        result = await asyncio.to_thread(
            _fetch_investments, id_dzialki, months, type, radius_m, 100,
        )
    except Exception:
        logger.exception("Failed to fetch investments id=%s", id_dzialki)
        return []

    if result is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    return result
