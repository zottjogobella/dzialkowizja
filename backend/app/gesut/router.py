from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, Depends, Query, Response

from app.auth.dependencies import require_auth
from app.db.geo import get_geo_pool

logger = logging.getLogger(__name__)

router = APIRouter()

GESUT_WMS_URL = (
    "https://integracja.gugik.gov.pl/cgi-bin/KrajowaIntegracjaUzbrojeniaTerenu"
)

# Minimal 1x1 transparent PNG returned on upstream errors.
TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@router.get("/tile")
async def gesut_tile(
    bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:3857"),
    width: int = Query(512, ge=1, le=2048),
    height: int = Query(512, ge=1, le=2048),
    _user=Depends(require_auth),
):
    """Proxy GESUT WMS tile: convert EPSG:3857 bbox → 2180, fetch, return PNG."""
    try:
        parts = bbox.split(",")
        if len(parts) != 4:
            return Response(content=TRANSPARENT_PNG, media_type="image/png")
        min_x, min_y, max_x, max_y = (float(v) for v in parts)
    except (ValueError, TypeError):
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    # Convert 3857 → 2180 via PostGIS
    pool = get_geo_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(env), ST_YMin(env), ST_XMax(env), ST_YMax(env)
            FROM (
                SELECT ST_Transform(
                    ST_MakeEnvelope($1, $2, $3, $4, 3857), 2180
                ) AS env
            ) t
            """,
            min_x,
            min_y,
            max_x,
            max_y,
        )

    bbox_2180 = f"{row[0]},{row[1]},{row[2]},{row[3]}"

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": "przewod_elektroenergetyczny",
        "SRS": "EPSG:2180",
        "BBOX": bbox_2180,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "STYLES": "",
        "TRANSPARENT": "TRUE",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(GESUT_WMS_URL, params=params)

        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            return Response(
                content=resp.content,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        logger.exception("GESUT WMS fetch failed")

    return Response(content=TRANSPARENT_PNG, media_type="image/png")


@router.get("/tile-urzadzenia")
async def gesut_tile_urzadzenia(
    bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:3857"),
    width: int = Query(512, ge=1, le=2048),
    height: int = Query(512, ge=1, le=2048),
    _user=Depends(require_auth),
):
    """Proxy GESUT WMS tile (urzadzenia): convert EPSG:3857 bbox → 2180, fetch, return PNG."""
    try:
        parts = bbox.split(",")
        if len(parts) != 4:
            return Response(content=TRANSPARENT_PNG, media_type="image/png")
        min_x, min_y, max_x, max_y = (float(v) for v in parts)
    except (ValueError, TypeError):
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    # Convert 3857 → 2180 via PostGIS
    pool = get_geo_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_XMin(env), ST_YMin(env), ST_XMax(env), ST_YMax(env)
            FROM (
                SELECT ST_Transform(
                    ST_MakeEnvelope($1, $2, $3, $4, 3857), 2180
                ) AS env
            ) t
            """,
            min_x,
            min_y,
            max_x,
            max_y,
        )

    bbox_2180 = f"{row[0]},{row[1]},{row[2]},{row[3]}"

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": "przewod_urzadzenia",
        "SRS": "EPSG:2180",
        "BBOX": bbox_2180,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "STYLES": "",
        "TRANSPARENT": "TRUE",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(GESUT_WMS_URL, params=params)

        if resp.status_code == 200 and "image" in resp.headers.get("content-type", ""):
            return Response(
                content=resp.content,
                media_type="image/png",
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception:
        logger.exception("GESUT WMS fetch failed")

    return Response(content=TRANSPARENT_PNG, media_type="image/png")
