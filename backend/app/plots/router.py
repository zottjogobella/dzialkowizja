from __future__ import annotations

import asyncio
import datetime
import json
import logging

import psycopg2
from fastapi import APIRouter, Depends, HTTPException

from app.auth.dependencies import require_auth
from app.config import settings
from app.plots.schemas import Listing

logger = logging.getLogger(__name__)

router = APIRouter()

PLOT_COLUMNS = (
    "id_dzialki, gmina, numer_dzialki, miejscowosc, ulica, area,"
    " lot_type, is_buildable, zoning_symbol, zoning_name,"
    " zoning_max_height, zoning_max_coverage, zoning_min_green,"
    " building_count_bdot, building_count_egib, building_count_osm,"
    " is_nature_protected, nature_protection,"
    " nearest_road_name, nearest_road_class, nearest_road_distance_m,"
    " nearest_education_m, nearest_healthcare_m, nearest_shopping_m, nearest_transport_m,"
    " has_water, has_sewage, has_gas, has_electric, has_heating, has_telecom,"
    " utility_count"
)

PLOT_COLUMN_NAMES = [c.strip() for c in PLOT_COLUMNS.replace("\n", "").split(",")]


def _fetch_plot(id_dzialki: str) -> dict | None:
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
                f"SELECT {PLOT_COLUMNS} FROM lots_enriched WHERE id_dzialki = %s",
                (id_dzialki,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return dict(zip(PLOT_COLUMN_NAMES, row))
    finally:
        conn.close()


def _fetch_plot_geometry(id_dzialki: str) -> dict | None:
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
                "SELECT ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geometry"
                " FROM lots_enriched WHERE id_dzialki = %s",
                (id_dzialki,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            geometry = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            return {
                "type": "Feature",
                "properties": {"id_dzialki": id_dzialki},
                "geometry": geometry,
            }
    finally:
        conn.close()


def _fetch_plot_centroid(id_dzialki: str) -> tuple[float, float] | None:
    """Get centroid as (lng, lat) in EPSG:4326 from gruntomat."""
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
                "SELECT ST_X(ST_Transform(ST_Centroid(geom), 4326)),"
                " ST_Y(ST_Transform(ST_Centroid(geom), 4326))"
                " FROM lots_enriched WHERE id_dzialki = %s",
                (id_dzialki,),
            )
            row = cur.fetchone()
            if row is None:
                return None
            return (row[0], row[1])
    finally:
        conn.close()


def _fetch_listings(lng: float, lat: float, radius_m: int = 500, limit: int = 10) -> dict:
    """Get active + inactive listings near a point from przetargi DB."""
    conn = psycopg2.connect(
        host=settings.przetargi_db_host,
        port=settings.przetargi_db_port,
        dbname=settings.przetargi_db_name,
        user=settings.przetargi_db_user,
        password=settings.przetargi_db_password,
        connect_timeout=10,
    )
    columns = [
        "id", "name", "property_type", "deal_type", "price",
        "price_per_meter", "area", "city", "url", "site", "publish_date",
    ]
    spatial_filter = (
        " geom_2180 IS NOT NULL"
        " AND ST_DWithin(geom_2180,"
        "     ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 2180), %s)"
    )
    select_cols = (
        "id, name, property_type, deal_type, price, price_per_meter,"
        " area, city, url, site, publish_date"
    )

    def _to_dicts(rows):
        results = []
        for row in rows:
            d = dict(zip(columns, row))
            if isinstance(d.get("publish_date"), datetime.datetime):
                d["publish_date"] = d["publish_date"].isoformat()
            elif d.get("publish_date") is not None:
                d["publish_date"] = str(d["publish_date"])
            results.append(d)
        return results

    try:
        with conn.cursor() as cur:
            # Active: valid_until IS NULL or valid_until > now()
            cur.execute(
                f"SELECT {select_cols}"
                f" FROM nieruchomosci_ogloszenia.ogloszenia_formatted"
                f" WHERE {spatial_filter}"
                f"   AND (valid_until IS NULL OR valid_until > now())"
                f" ORDER BY publish_date DESC NULLS LAST"
                f" LIMIT %s",
                (lng, lat, radius_m, limit),
            )
            active = _to_dicts(cur.fetchall())

            # Inactive: valid_until <= now()
            cur.execute(
                f"SELECT {select_cols}"
                f" FROM nieruchomosci_ogloszenia.ogloszenia_formatted"
                f" WHERE {spatial_filter}"
                f"   AND valid_until IS NOT NULL AND valid_until <= now()"
                f" ORDER BY valid_until DESC"
                f" LIMIT %s",
                (lng, lat, radius_m, limit),
            )
            inactive = _to_dicts(cur.fetchall())

        return {"active": active, "inactive": inactive}
    finally:
        conn.close()


def _fetch_plot_centroid_2180(id_dzialki: str) -> tuple[float, float] | None:
    """Get centroid as (x, y) in EPSG:2180 from gruntomat."""
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


def _fetch_nearest_transactions(cx: float, cy: float, limit: int = 10) -> list[dict]:
    """Find nearest land transactions by Euclidean distance in EPSG:2180.

    cx, cy are from gruntomat ST_X/ST_Y(ST_Centroid(geom)) in EPSG:2180.
    Transakcje table has pre-computed cx_2180, cy_2180 in the same CRS.
    """
    conn = psycopg2.connect(
        host=settings.transakcje_db_host,
        port=settings.transakcje_db_port,
        dbname=settings.transakcje_db_name,
        user=settings.transakcje_db_user,
        password=settings.transakcje_db_password,
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, teryt, wojewodztwo, id_dzialki,
                    data_transakcji, rok, oznaczenie_dokumentu, tworca_dokumentu,
                    cena_transakcji, cena_nieruchomosci, cena_dzialki, cena_do_analizy,
                    kwota_vat, liczba_dzialek_w_transakcji,
                    powierzchnia_m2, powierzchnia_nieruchomosci_ha, cena_za_m2,
                    rodzaj_nieruchomosci, rodzaj_rynku, rodzaj_transakcji, rodzaj_prawa,
                    udzial_w_prawie, sposob_uzytkowania, przeznaczenie_mpzp,
                    strona_kupujaca, strona_sprzedajaca,
                    miejscowosc, ulica, numer_porzadkowy,
                    dodatkowe_informacje,
                    ST_Distance(
                        ST_SetSRID(ST_MakePoint(cx_2180, cy_2180), 2180),
                        ST_SetSRID(ST_MakePoint(%s, %s), 2180)
                    ) AS distance_m
                FROM transakcje_gruntowe
                WHERE cx_2180 IS NOT NULL AND cena_transakcji > 0
                ORDER BY ST_SetSRID(ST_MakePoint(cx_2180, cy_2180), 2180)
                     <-> ST_SetSRID(ST_MakePoint(%s, %s), 2180)
                LIMIT %s
                """,
                (cx, cy, cx, cy, limit),
            )
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            results = []
            for row in rows:
                d = dict(zip(columns, row))
                # Convert date-like fields to strings
                for key in ("data_transakcji",):
                    if d.get(key) is not None and not isinstance(d[key], str):
                        d[key] = str(d[key])
                # Round distance
                if d.get("distance_m") is not None:
                    d["distance_m"] = round(d["distance_m"], 1)
                results.append(d)
            return results
    finally:
        conn.close()


def _fetch_buildings(id_dzialki: str, buffer_m: int = 300, limit: int = 1000) -> dict:
    """Get building footprints near a plot from egib_budynki + buildings_bdot."""
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
                """
                WITH buf AS (
                    SELECT ST_Buffer(geom, %s) AS geom
                    FROM lots_enriched WHERE id_dzialki = %s
                )
                SELECT geometry, floors, src_type, source FROM (
                    SELECT ST_AsGeoJSON(ST_Transform(b.geom, 4326))::json AS geometry,
                           COALESCE(b.kondygnacje_nadziemne, 0) AS floors,
                           b.rodzaj AS src_type,
                           'egib' AS source
                    FROM egib_budynki b, buf
                    WHERE b.geom IS NOT NULL AND ST_Intersects(b.geom, buf.geom)

                    UNION ALL

                    SELECT ST_AsGeoJSON(ST_Transform(b.geom, 4326))::json AS geometry,
                           COALESCE(b.liczba_kondygnacji, 0) AS floors,
                           b.funkcja_budynku_kod::text AS src_type,
                           'bdot' AS source
                    FROM buildings_bdot b, buf
                    WHERE b.geom IS NOT NULL AND ST_Intersects(b.geom, buf.geom)
                ) all_buildings
                LIMIT %s
                """,
                (buffer_m, id_dzialki, limit),
            )
            rows = cur.fetchall()

        features = []
        for geom, floors_val, src_type, source in rows:
            geometry = json.loads(geom) if isinstance(geom, str) else geom
            floors = floors_val if floors_val and floors_val > 0 else 2
            features.append({
                "type": "Feature",
                "properties": {
                    "height": floors * 3.2,
                    "floors": floors,
                    "type": src_type,
                    "source": source,
                },
                "geometry": geometry,
            })
        return {"type": "FeatureCollection", "features": features}
    finally:
        conn.close()


@router.get("/{id_dzialki:path}/transactions")
async def get_plot_transactions(id_dzialki: str, _user=Depends(require_auth)):
    centroid = await asyncio.to_thread(_fetch_plot_centroid_2180, id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    cx, cy = centroid
    try:
        return await asyncio.to_thread(_fetch_nearest_transactions, cx, cy)
    except Exception:
        logger.exception("Failed to fetch transactions")
        return []


@router.get("/{id_dzialki:path}/buildings")
async def get_plot_buildings(id_dzialki: str, _user=Depends(require_auth)):
    try:
        result = await asyncio.to_thread(_fetch_buildings, id_dzialki)
        return result
    except Exception:
        logger.exception("Failed to fetch buildings from gruntomat DB")
        return {"type": "FeatureCollection", "features": []}


@router.get("/{id_dzialki:path}/geometry")
async def get_plot_geometry(id_dzialki: str, _user=Depends(require_auth)):
    result = await asyncio.to_thread(_fetch_plot_geometry, id_dzialki)
    if result is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    return result


@router.get("/{id_dzialki:path}/listings")
async def get_plot_listings(id_dzialki: str, _user=Depends(require_auth)):
    if not settings.przetargi_db_user:
        return {"active": [], "inactive": []}

    centroid = await asyncio.to_thread(_fetch_plot_centroid, id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    lng, lat = centroid
    try:
        return await asyncio.to_thread(_fetch_listings, lng, lat)
    except Exception:
        logger.exception("Failed to fetch listings from przetargi DB")
        return {"active": [], "inactive": []}


@router.get("/{id_dzialki:path}")
async def get_plot(id_dzialki: str, _user=Depends(require_auth)):
    result = await asyncio.to_thread(_fetch_plot, id_dzialki)
    if result is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    return result
