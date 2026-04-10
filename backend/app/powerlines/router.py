"""Powerlines endpoint: returns BDOT10k or OSM electric lines / devices near a plot.

Three sources exposed through `?source=`:
  - `bdot`:          rows from bdot_suln_l (BDOT10k SULN_L, ~390k rows
                     covering all 16 województw — uploaded by a sibling
                     project to gruntomat_geo)
  - `osm`:           rows from osm_power_lines (OSM power=line/minor_line/cable,
                     extracted by backend/scripts/extract_osm_powerlines.py)
  - `bdot_devices`:  rows from bdot_power_devices (BDOT10k point/polygon
                     devices: słupy, transformatory, podstacje, elektrownie,
                     ingested by backend/scripts/ingest_bdot_power_devices.py)

All source tables live in gruntomat_geo and store geometries as EPSG:2180.
The endpoint uses ST_DWithin against the plot geometry (not the centroid)
for correctness on large / elongated parcels, and returns geometries
transformed to EPSG:4326 wrapped in a GeoJSON FeatureCollection.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import require_auth
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

Source = Literal["bdot", "osm", "bdot_devices"]


def _db_connect():
    return psycopg2.connect(
        host=settings.geo_db_host,
        port=settings.geo_db_port,
        dbname=settings.geo_db_name,
        user=settings.geo_db_user,
        password=settings.geo_db_password,
        connect_timeout=10,
    )


def _fetch_powerlines(
    id_dzialki: str,
    source: Source,
    buffer_m: int,
    limit: int = 2000,
) -> dict | None:
    """Return a FeatureCollection of power lines within `buffer_m` of the plot.

    Returns None if the plot does not exist (caller maps to 404).
    """
    conn = _db_connect()
    try:
        with conn.cursor() as cur:
            # Resolve the plot geometry first. Missing plot → None.
            cur.execute(
                "SELECT geom FROM lots_enriched WHERE id_dzialki = %s",
                (id_dzialki,),
            )
            row = cur.fetchone()
            if row is None:
                return None

            if source == "bdot":
                # Now backed by `bdot_suln_l` — the full BDOT10k SULN_L
                # dataset covering all 16 województw (~390k rows) that was
                # uploaded by a sibling project. The old `bdot_power_lines`
                # table was a POC with only opolskie and has been dropped.
                sql = """
                    SELECT ST_AsGeoJSON(ST_Transform(p.geom, 4326))::json AS geometry,
                           p.lokalnyid,
                           p.rodzaj,
                           p.woj_teryt
                    FROM bdot_suln_l p,
                         (SELECT geom FROM lots_enriched WHERE id_dzialki = %s) lot
                    WHERE ST_DWithin(p.geom, lot.geom, %s)
                    LIMIT %s
                """
                cur.execute(sql, (id_dzialki, buffer_m, limit))
                rows = cur.fetchall()
                features = []
                for geom, lokalny_id, rodzaj, woj in rows:
                    geometry = json.loads(geom) if isinstance(geom, str) else geom
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "source": "bdot",
                            "lokalny_id": lokalny_id,
                            "rodzaj": rodzaj,
                            "source_woj": woj,
                        },
                        "geometry": geometry,
                    })
                return {"type": "FeatureCollection", "features": features}

            if source == "bdot_devices":
                sql = """
                    SELECT ST_AsGeoJSON(ST_Transform(d.geom, 4326))::json AS geometry,
                           d.gml_id,
                           d.rodzaj,
                           d.kategoria,
                           d.source_class,
                           d.source_powiat
                    FROM bdot_power_devices d,
                         (SELECT geom FROM lots_enriched WHERE id_dzialki = %s) lot
                    WHERE ST_DWithin(d.geom, lot.geom, %s)
                    LIMIT %s
                """
                cur.execute(sql, (id_dzialki, buffer_m, limit))
                rows = cur.fetchall()
                features = []
                for geom, gml_id, rodzaj, kategoria, source_class, powiat in rows:
                    geometry = json.loads(geom) if isinstance(geom, str) else geom
                    features.append({
                        "type": "Feature",
                        "properties": {
                            "source": "bdot_devices",
                            "gml_id": gml_id,
                            "rodzaj": rodzaj,
                            "kategoria": kategoria,
                            "source_class": source_class,
                            "source_powiat": powiat,
                        },
                        "geometry": geometry,
                    })
                return {"type": "FeatureCollection", "features": features}

            # source == "osm"
            sql = """
                SELECT ST_AsGeoJSON(ST_Transform(p.geom, 4326))::json AS geometry,
                       p.osm_id,
                       p.power_type,
                       p.voltage,
                       p.voltage_raw,
                       p.operator,
                       p.name
                FROM osm_power_lines p,
                     (SELECT geom FROM lots_enriched WHERE id_dzialki = %s) lot
                WHERE ST_DWithin(p.geom, lot.geom, %s)
                LIMIT %s
            """
            cur.execute(sql, (id_dzialki, buffer_m, limit))
            rows = cur.fetchall()
            features = []
            for geom, osm_id, power_type, voltage, voltage_raw, op, name in rows:
                geometry = json.loads(geom) if isinstance(geom, str) else geom
                features.append({
                    "type": "Feature",
                    "properties": {
                        "source": "osm",
                        "osm_id": osm_id,
                        "power_type": power_type,
                        "voltage": float(voltage) if voltage is not None else None,
                        "voltage_raw": voltage_raw,
                        "operator": op,
                        "name": name,
                    },
                    "geometry": geometry,
                })
            return {"type": "FeatureCollection", "features": features}
    finally:
        conn.close()


@router.get("/{id_dzialki:path}")
async def get_plot_powerlines(
    id_dzialki: str,
    source: Source = Query(..., description="bdot | osm | bdot_devices"),
    buffer_m: int = Query(50, ge=0, le=500, description="Search radius in metres"),
    _user=Depends(require_auth),
):
    """GeoJSON FeatureCollection of power lines within `buffer_m` of the plot.

    Example:
        GET /api/powerlines/261101_1.0004.123?source=bdot&buffer_m=100
    """
    try:
        result = await asyncio.to_thread(
            _fetch_powerlines, id_dzialki, source, buffer_m
        )
    except Exception:
        logger.exception(
            "Failed to fetch powerlines id=%s source=%s", id_dzialki, source
        )
        return {"type": "FeatureCollection", "features": []}

    if result is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    return result
