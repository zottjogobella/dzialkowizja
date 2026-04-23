from __future__ import annotations

import asyncio
import datetime
import json
import logging

import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response as FastAPIResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Request

from app.audit.recorder import record
from app.auth.dependencies import require_auth
from app.config import settings
from app.db.engine import get_db
from app.db.models import PlotSnapshot, User
from app.middleware.rate_limit_dep import rate_limit_detail
from app.permissions.fields import is_section_restricted
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
            result = dict(zip(PLOT_COLUMN_NAMES, row))

            # Look up POG status via teryt
            teryt7 = id_dzialki.split(".")[0].replace("_", "") if "." in id_dzialki else None
            if teryt7 and result.get("zoning_symbol"):
                cur.execute(
                    "SELECT DISTINCT r.status_pog FROM pog_status_registry r"
                    " INNER JOIN pog_strefy s ON s.plan_id = r.id"
                    " WHERE s.teryt = %s LIMIT 1",
                    (teryt7,),
                )
                pog_row = cur.fetchone()
                result["pog_status"] = pog_row[0] if pog_row else None
            else:
                result["pog_status"] = None

            return result
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


def _fetch_listings(lng: float, lat: float, limit: int = 10) -> dict:
    """Get active + inactive listings near a point from przetargi DB."""
    radius_m = settings.listings_radius_m
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
        "lng", "lat",
    ]
    spatial_filter = (
        " geom_2180 IS NOT NULL"
        " AND ST_DWithin(geom_2180,"
        "     ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 2180), %s)"
    )
    select_cols = (
        "id, name, property_type, deal_type, price, price_per_meter,"
        " area, city, url, site, publish_date,"
        " ST_X(ST_Transform(geom_2180, 4326)) AS lng,"
        " ST_Y(ST_Transform(geom_2180, 4326)) AS lat"
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


def _fetch_nearest_transactions(
    cx: float,
    cy: float,
    limit: int = 30,
    type_filter: str = "all",
    include_outliers: bool = False,
) -> list[dict]:
    """Nearest land transactions, joined across DBs in a single SQL round trip.

    The sqlite source ships centroids in per-województwo local CRSes, so
    transakcje_gruntowe.cx_2180/cy_2180 are garbage. We use ``dblink``
    instead of a plain postgres_fdw JOIN because postgres_fdw can't push
    PostGIS's KNN ``<->`` operator — without it the foreign scan has to
    fetch every lot in the ring and sort locally (~30 s). ``dblink``
    lets gruntomat run the full KNN + LIMIT against its GiST index
    (~1 s) and returns only the 500 closest candidates.

    ``type_filter``:
        - ``"all"``:      everything (default)
        - ``"gruntowe"``: only land plots (rodzaj_nieruchomosci IN 1,2)
        - ``"inne"``:     everything that isn't a plain land plot

    ``include_outliers`` — False (default) hides outlier=1 / do_wyceny=0
    rows. True lets them through so the UI can badge them.
    """
    if type_filter == "gruntowe":
        type_sql = " AND t.rodzaj_nieruchomosci IN (1, 2)"
    elif type_filter == "inne":
        type_sql = (
            " AND (t.rodzaj_nieruchomosci NOT IN (1, 2) "
            " OR t.rodzaj_nieruchomosci IS NULL)"
        )
    else:
        type_sql = ""
    outlier_sql = (
        ""
        if include_outliers
        else " AND COALESCE(t.outlier, 0) = 0"
             " AND COALESCE(t.do_wyceny, 1) = 1"
    )

    # dblink's query argument is a text string executed literally on the
    # foreign side, so we can't use psycopg2 parameters inside it. cx/cy
    # come from PostGIS on our own gruntomat centroid lookup — coerce to
    # plain floats and inline.
    cx_f = float(cx)
    cy_f = float(cy)
    remote_sql = (
        "SELECT id_dzialki,"
        f" ST_Distance(centroid, ST_SetSRID(ST_MakePoint({cx_f}, {cy_f}), 2180)),"
        " ST_X(ST_Transform(centroid, 4326)),"
        " ST_Y(ST_Transform(centroid, 4326))"
        " FROM lots_enriched"
        " WHERE centroid IS NOT NULL"
        f" AND ST_DWithin(centroid, ST_SetSRID(ST_MakePoint({cx_f}, {cy_f}), 2180), 10000)"
        f" ORDER BY centroid <-> ST_SetSRID(ST_MakePoint({cx_f}, {cy_f}), 2180)"
        " LIMIT 500"
    )

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
                f"""
                WITH nearest AS (
                    SELECT * FROM dblink('gruntomat_fdw', %s)
                    AS x(id_dzialki text, distance_m double precision,
                         lng double precision, lat double precision)
                )
                SELECT t.id, t.teryt, t.wojewodztwo, t.id_dzialki,
                    t.data_transakcji, t.rok, t.oznaczenie_dokumentu, t.tworca_dokumentu,
                    t.cena_transakcji, t.cena_nieruchomosci, t.cena_dzialki, t.cena_do_analizy,
                    t.kwota_vat, t.liczba_dzialek_w_transakcji,
                    t.powierzchnia_m2, t.powierzchnia_nieruchomosci_ha, t.cena_za_m2,
                    t.rodzaj_nieruchomosci, t.rodzaj_rynku, t.rodzaj_transakcji, t.rodzaj_prawa,
                    t.udzial_w_prawie, t.sposob_uzytkowania, t.przeznaczenie_mpzp,
                    t.strona_kupujaca, t.strona_sprzedajaca,
                    t.miejscowosc, t.ulica, t.numer_porzadkowy,
                    t.dodatkowe_informacje,
                    t.segment_rynku, t.outlier, t.do_wyceny, t.jakosc_ceny,
                    n.lng, n.lat, n.distance_m
                FROM transakcje_gruntowe t
                JOIN nearest n USING (id_dzialki)
                WHERE t.cena_transakcji > 0
                  {type_sql}
                  {outlier_sql}
                ORDER BY n.distance_m
                LIMIT %s
                """,
                (remote_sql, limit),
            )
            columns = [desc[0] for desc in cur.description]
            rows = cur.fetchall()

        results: list[dict] = []
        for row in rows:
            d = dict(zip(columns, row))
            if d.get("distance_m") is not None:
                d["distance_m"] = round(d["distance_m"], 1)
            for key in ("data_transakcji",):
                if d.get(key) is not None and not isinstance(d[key], str):
                    d[key] = str(d[key])
            results.append(d)
        return results
    finally:
        conn.close()


def _fetch_transaction_stats(cx: float, cy: float, limit: int = 300) -> list[dict]:
    """Lightweight chart data: distance + date + price/m². Same dblink
    pattern as _fetch_nearest_transactions — KNN runs on gruntomat.
    """
    cx_f = float(cx)
    cy_f = float(cy)
    remote_sql = (
        "SELECT id_dzialki,"
        f" ST_Distance(centroid, ST_SetSRID(ST_MakePoint({cx_f}, {cy_f}), 2180))"
        " FROM lots_enriched"
        " WHERE centroid IS NOT NULL"
        f" AND ST_DWithin(centroid, ST_SetSRID(ST_MakePoint({cx_f}, {cy_f}), 2180), 20000)"
        f" ORDER BY centroid <-> ST_SetSRID(ST_MakePoint({cx_f}, {cy_f}), 2180)"
        " LIMIT 2000"
    )

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
                WITH nearest AS (
                    SELECT * FROM dblink('gruntomat_fdw', %s)
                    AS x(id_dzialki text, distance_m double precision)
                )
                SELECT t.data_transakcji, t.cena_za_m2, n.distance_m
                FROM transakcje_gruntowe t
                JOIN nearest n USING (id_dzialki)
                WHERE t.cena_za_m2 IS NOT NULL
                  AND t.cena_za_m2 > 0
                ORDER BY n.distance_m
                LIMIT %s
                """,
                (remote_sql, limit),
            )
            results = []
            for date, price, d in cur.fetchall():
                if date is not None and not isinstance(date, str):
                    date = str(date)
                results.append({
                    "date": date,
                    "price_per_m2": float(price),
                    "distance_m": round(d, 1) if d is not None else None,
                })
            return results
    finally:
        conn.close()


def _fetch_listing_stats(lng: float, lat: float, limit: int = 300) -> list[dict]:
    """Lightweight query for charts: just publish_date and price/m² for all listings in area."""
    conn = psycopg2.connect(
        host=settings.przetargi_db_host,
        port=settings.przetargi_db_port,
        dbname=settings.przetargi_db_name,
        user=settings.przetargi_db_user,
        password=settings.przetargi_db_password,
        connect_timeout=10,
    )
    radius_m = settings.listings_radius_m
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT publish_date, price_per_meter, valid_until
                FROM nieruchomosci_ogloszenia.ogloszenia_formatted
                WHERE geom_2180 IS NOT NULL
                    AND price_per_meter IS NOT NULL
                    AND price_per_meter > 0
                    AND ST_DWithin(
                        geom_2180,
                        ST_Transform(ST_SetSRID(ST_MakePoint(%s, %s), 4326), 2180),
                        %s
                    )
                ORDER BY publish_date DESC NULLS LAST
                LIMIT %s
                """,
                (lng, lat, radius_m, limit),
            )
            results = []
            for row in cur.fetchall():
                pub = row[0]
                if pub is not None and not isinstance(pub, str):
                    pub = pub.isoformat() if hasattr(pub, "isoformat") else str(pub)
                valid = row[2]
                is_active = valid is None or (
                    hasattr(valid, "__gt__") and valid > datetime.datetime.now(datetime.timezone.utc)
                )
                results.append({
                    "date": pub,
                    "price_per_m2": float(row[1]),
                    "active": bool(is_active),
                })
            return results
    finally:
        conn.close()


def _fetch_buildings(id_dzialki: str, limit: int = 1000) -> dict:
    """Get building footprints near a plot from egib_budynki + buildings_bdot + osm_buildings."""
    buffer_m = settings.buildings_buffer_m
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

                    UNION ALL

                    SELECT ST_AsGeoJSON(ST_Transform(b.geom, 4326))::json AS geometry,
                           COALESCE(b.levels, 0) AS floors,
                           b.building_type AS src_type,
                           'osm' AS source
                    FROM osm_buildings b, buf
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


@router.get("/{id_dzialki:path}/transactions/stats")
async def get_plot_transaction_stats(id_dzialki: str, _user=Depends(require_auth)):
    """Lightweight stats for charts — 300 nearest transactions, minimal fields."""
    centroid = await asyncio.to_thread(_fetch_plot_centroid_2180, id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    cx, cy = centroid
    try:
        return await asyncio.to_thread(_fetch_transaction_stats, cx, cy, 300)
    except Exception:
        logger.exception("Failed to fetch transaction stats")
        return []


@router.get("/{id_dzialki:path}/listings/stats")
async def get_plot_listing_stats(id_dzialki: str, _user=Depends(require_auth)):
    """Lightweight stats for charts — all listings in configured radius."""
    if not settings.przetargi_db_user:
        return []

    centroid = await asyncio.to_thread(_fetch_plot_centroid, id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    lng, lat = centroid
    try:
        return await asyncio.to_thread(_fetch_listing_stats, lng, lat, 300)
    except Exception:
        logger.exception("Failed to fetch listing stats")
        return []


@router.get("/{id_dzialki:path}/transactions")
async def get_plot_transactions(
    id_dzialki: str,
    type: str = "all",
    include_outliers: bool = False,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Return the N nearest transactions to the plot centroid.

    Query params:
        type — all | gruntowe | inne, default ``all``. ``gruntowe`` keeps
               only rodzaj_nieruchomosci in {1,2} (plots of land);
               ``inne`` returns everything else (budynkowa/lokalowa).
        include_outliers — when true, include rows flagged outlier=1 or
               do_wyceny=0 by the RCN cleanup pipeline. Default false.
    """
    if await is_section_restricted(db, user, "section.transactions"):
        return []

    centroid = await asyncio.to_thread(_fetch_plot_centroid_2180, id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    cx, cy = centroid
    type_filter = type if type in ("all", "gruntowe", "inne") else "all"
    try:
        return await asyncio.to_thread(
            _fetch_nearest_transactions, cx, cy, 30, type_filter, include_outliers
        )
    except Exception:
        logger.exception("Failed to fetch transactions")
        return []


def _parse_teryt(id_dzialki: str) -> tuple[str | None, str | None]:
    """Extract (gmina_teryt, powiat_teryt) from an id_dzialki.

    id_dzialki format: ``TTTTTT_X.YYYY.A`` where the first 6 characters are
    the gmina TERYT code and the first 4 are the powiat TERYT code.
    """
    prefix = id_dzialki.split(".", 1)[0].replace("_", "")
    if len(prefix) < 6 or not prefix[:6].isdigit():
        return None, None
    return prefix[:6], prefix[:4]


@router.get("/{id_dzialki:path}/ceny-srednie")
async def get_plot_ceny_srednie(
    id_dzialki: str,
    _user=Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Average RCN prices for the plot's gmina and powiat.

    Returns three blocks matching the three reference tables:
      * ``gmina``:        per rodzaj_nieruchomosci (1..4) — no segment split
      * ``powiat_total``: per rodzaj_nieruchomosci (1..4) — no segment split
      * ``powiat``:       per rodzaj × segment_rynku (rows only where data exists)
    """
    gmina, powiat = _parse_teryt(id_dzialki)
    if not gmina or not powiat:
        raise HTTPException(status_code=400, detail="Nieprawidłowy identyfikator działki")

    gmina_rows = (await db.execute(
        text(
            """
            SELECT rodzaj_nieruchomosci, rodzaj_nazwa, liczba_transakcji,
                   cena_za_m2_srednia, cena_za_m2_mediana,
                   cena_za_m2_q1, cena_za_m2_q3,
                   pow_m2_srednia, cena_transakcji_srednia, rok_min, rok_max
            FROM srednie_ceny_gmina WHERE gmina = :g
            ORDER BY rodzaj_nieruchomosci
            """
        ),
        {"g": gmina},
    )).mappings().all()

    powiat_total_rows = (await db.execute(
        text(
            """
            SELECT rodzaj_nieruchomosci, rodzaj_nazwa, liczba_transakcji,
                   cena_za_m2_srednia, cena_za_m2_mediana,
                   cena_za_m2_q1, cena_za_m2_q3,
                   pow_m2_srednia, cena_transakcji_srednia, rok_min, rok_max
            FROM srednie_ceny_powiat_total WHERE teryt = :t
            ORDER BY rodzaj_nieruchomosci
            """
        ),
        {"t": powiat},
    )).mappings().all()

    powiat_seg_rows = (await db.execute(
        text(
            """
            SELECT rodzaj_nieruchomosci, rodzaj_nazwa, segment_rynku,
                   liczba_transakcji,
                   cena_za_m2_srednia, cena_za_m2_mediana,
                   cena_za_m2_q1, cena_za_m2_q3,
                   cena_za_m2_min, cena_za_m2_max,
                   pow_m2_srednia, cena_transakcji_srednia, rok_min, rok_max
            FROM srednie_ceny_powiat WHERE teryt = :t
            ORDER BY rodzaj_nieruchomosci, segment_rynku
            """
        ),
        {"t": powiat},
    )).mappings().all()

    def to_num(v):
        """psycopg2/asyncpg returns Decimal for NUMERIC — make it JSON-safe."""
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def clean_row(r: dict) -> dict:
        out = {}
        for k, v in r.items():
            out[k] = to_num(v) if k.startswith("cena") or k.startswith("pow") else v
        return out

    return {
        "gmina_teryt": gmina,
        "powiat_teryt": powiat,
        "gmina": [clean_row(dict(r)) for r in gmina_rows],
        "powiat_total": [clean_row(dict(r)) for r in powiat_total_rows],
        "powiat": [clean_row(dict(r)) for r in powiat_seg_rows],
    }


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
async def get_plot_listings(
    id_dzialki: str,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    if await is_section_restricted(db, user, "section.listings"):
        return {"active": [], "inactive": []}

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


@router.get("/{id_dzialki:path}/snapshot/{snapshot_type}")
async def get_plot_snapshot(
    id_dzialki: str,
    snapshot_type: str,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    """Get or generate a plot snapshot (ortho or map). Lazy-loaded and cached in DB."""
    if await is_section_restricted(db, user, "section.snapshots"):
        raise HTTPException(status_code=404, detail="Sekcja ukryta")

    if snapshot_type not in ("ortho", "map"):
        raise HTTPException(status_code=400, detail="Typ: ortho lub map")

    # Check DB cache
    stmt = select(PlotSnapshot).where(
        PlotSnapshot.id_dzialki == id_dzialki,
        PlotSnapshot.snapshot_type == snapshot_type,
    )
    result = await db.execute(stmt)
    snapshot = result.scalar_one_or_none()

    if snapshot is not None:
        age = (datetime.datetime.now(datetime.timezone.utc) - snapshot.created_at).days
        if age < settings.snapshot_max_age_days:
            return FastAPIResponse(
                content=snapshot.image_data,
                media_type="image/jpeg",
                headers={
                    "Cache-Control": "public, max-age=604800",
                    "Content-Disposition": f'inline; filename="{id_dzialki}_{snapshot_type}.jpg"',
                },
            )
        await db.delete(snapshot)
        await db.commit()

    # Generate
    geometry_feature = await asyncio.to_thread(_fetch_plot_geometry, id_dzialki)
    if geometry_feature is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    from app.plots.snapshots import OrthoUpstreamError, generate_snapshot

    cache_result = True
    try:
        image_data, width, height = await generate_snapshot(geometry_feature, snapshot_type)
    except OrthoUpstreamError:
        # Geoportal ortho WMS is down — serve the basemap snapshot instead,
        # but don't cache it so we retry ortho once upstream recovers.
        logger.warning(
            "Ortho WMS unavailable for %s — serving basemap fallback", id_dzialki
        )
        try:
            image_data, width, height = await generate_snapshot(geometry_feature, "map")
        except Exception:
            logger.exception("Basemap fallback also failed for %s", id_dzialki)
            raise HTTPException(status_code=502, detail="Nie udało się wygenerować zdjęcia")
        cache_result = False
    except Exception:
        logger.exception("Snapshot generation failed for %s/%s", id_dzialki, snapshot_type)
        raise HTTPException(status_code=502, detail="Nie udało się wygenerować zdjęcia")

    if cache_result:
        new_snapshot = PlotSnapshot(
            id_dzialki=id_dzialki,
            snapshot_type=snapshot_type,
            image_data=image_data,
            width=width,
            height=height,
        )
        db.add(new_snapshot)
        await db.commit()

    return FastAPIResponse(
        content=image_data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=604800" if cache_result else "no-store",
            "Content-Disposition": f'inline; filename="{id_dzialki}_{snapshot_type}.jpg"',
        },
    )


@router.get("/{id_dzialki:path}")
async def get_plot(
    id_dzialki: str,
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_detail),
):
    result = await asyncio.to_thread(_fetch_plot, id_dzialki)
    if result is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    await record(db, user, action_type="plot_view", request=request, target_id=id_dzialki)
    return result
