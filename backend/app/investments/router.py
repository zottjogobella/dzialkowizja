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
    "pozwolenie": "typ = 'pozwolenie_budowa'",
    "zgloszenie": "typ = 'zgloszenie'",
    "warunki": "typ = 'warunki_zabudowy'",  # reserved for future source
}

InvestmentType = Literal["all", "pozwolenie", "zgloszenie", "warunki"]


def _fetch_plot_centroid_2180(id_dzialki: str) -> tuple[float, float] | None:
    """Plot centroid in EPSG:2180 (matches gunb_investments.geom CRS)."""
    conn = psycopg2.connect(
        host=settings.geo_db_host,
        port=settings.geo_db_port,
        dbname=settings.geo_db_name,
        user=settings.geo_db_user,
        password=settings.geo_db_password,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ST_X(ST_Centroid(geom)), ST_Y(ST_Centroid(geom))"
                " FROM lots_enriched WHERE id_dzialki = %s",
                (id_dzialki,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return (row[0], row[1])
    finally:
        conn.close()


def _fetch_investments(
    cx: float,
    cy: float,
    months: int,
    type_filter: InvestmentType,
    radius_m: int,
    limit: int = 100,
) -> list[dict]:
    conn = psycopg2.connect(
        host=settings.geo_db_host,
        port=settings.geo_db_port,
        dbname=settings.geo_db_name,
        user=settings.geo_db_user,
        password=settings.geo_db_password,
        connect_timeout=10,
    )
    type_sql = TYPE_FILTER_SQL.get(type_filter, "TRUE")
    # Time window: treat data_decyzji OR data_wniosku as the "event date";
    # zgłoszenia never have data_decyzji, so data_wniosku is the fallback.
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT
                    id, typ, status, data_wniosku, data_decyzji,
                    inwestor, organ, miejscowosc, adres, opis,
                    kategoria, rodzaj_inwestycji, parcel_id,
                    ST_X(ST_Transform(geom, 4326)) AS lng,
                    ST_Y(ST_Transform(geom, 4326)) AS lat,
                    ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 2180)) AS distance_m
                FROM gunb_investments
                WHERE geom IS NOT NULL
                  AND {type_sql}
                  AND ST_DWithin(geom, ST_SetSRID(ST_MakePoint(%s, %s), 2180), %s)
                  AND COALESCE(data_decyzji, data_wniosku)
                      >= (NOW() - make_interval(months => %s))::date
                ORDER BY distance_m ASC, COALESCE(data_decyzji, data_wniosku) DESC NULLS LAST
                LIMIT %s
                """,
                (cx, cy, cx, cy, radius_m, months, limit),
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
    radius_m: int = Query(500, ge=50, le=2000),
    _user=Depends(require_auth),
):
    """Return GUNB RWDZ investments within `radius_m` of the plot centroid.

    Query params:
        months   — time window in months from data_decyzji (or data_wniosku), default 24, max 120
        type     — all | pozwolenie | zgloszenie | warunki, default all
        radius_m — search radius in metres, default 500, max 2000

    Results sorted by distance asc then decision date desc, capped at 100.
    """
    centroid = await asyncio.to_thread(_fetch_plot_centroid_2180, id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    cx, cy = centroid
    try:
        return await asyncio.to_thread(
            _fetch_investments, cx, cy, months, type, radius_m, 100,
        )
    except Exception:
        logger.exception("Failed to fetch investments")
        return []
