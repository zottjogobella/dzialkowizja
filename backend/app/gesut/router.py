from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path

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

# On-disk tile cache. GESUT WMS is slow (seconds per 2048² tile) and MapLibre
# drops rasters from memory when a layer is hidden, so re-toggling a layer
# re-hits GUGiK every time. A simple filesystem cache keyed by (layer, bbox,
# size) lets the second toggle — and every later request from any user — hit
# local disk. Entries live for 24 h, matching the Cache-Control header we
# emit to the browser; the directory is ephemeral (container-local /tmp) and
# rebuilds itself on demand after a container recreate.
CACHE_DIR = Path("/tmp/gesut_cache")
CACHE_TTL_SEC = 86400  # 24 h


def _cache_path(layer: str, bbox_2180: str, width: int, height: int) -> Path:
    key = hashlib.sha1(
        f"{layer}|{bbox_2180}|{width}|{height}".encode()
    ).hexdigest()
    return CACHE_DIR / f"{key}.png"


def _read_cache(path: Path) -> bytes | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    if time.time() - st.st_mtime > CACHE_TTL_SEC:
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None


def _write_cache(path: Path, data: bytes) -> None:
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".png.tmp")
        tmp.write_bytes(data)
        tmp.replace(path)  # atomic swap — avoids half-written tiles on crash
    except OSError:
        # Cache write failure should never break a user request.
        logger.debug("Failed to write GESUT cache", exc_info=True)


async def _bbox_3857_to_2180(bbox: str) -> str | None:
    """Parse and reproject a comma-separated EPSG:3857 bbox to EPSG:2180."""
    try:
        parts = bbox.split(",")
        if len(parts) != 4:
            return None
        min_x, min_y, max_x, max_y = (float(v) for v in parts)
    except (ValueError, TypeError):
        return None

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
    return f"{row[0]},{row[1]},{row[2]},{row[3]}"


async def _fetch_tile(
    layer: str, bbox_2180: str, width: int, height: int
) -> bytes | None:
    """Return WMS tile bytes, using a disk cache on the way in and out.

    Returns `None` if the upstream fetch fails — callers map that to the
    transparent-PNG fallback so the map doesn't break when GUGiK is flaky.
    """
    path = _cache_path(layer, bbox_2180, width, height)
    cached = await asyncio.to_thread(_read_cache, path)
    if cached is not None:
        return cached

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
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
    except Exception:
        logger.exception("GESUT WMS fetch failed layer=%s", layer)
        return None

    if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
        return None

    await asyncio.to_thread(_write_cache, path, resp.content)
    return resp.content


async def _serve_tile(
    layer: str, bbox: str, width: int, height: int
) -> Response:
    bbox_2180 = await _bbox_3857_to_2180(bbox)
    if bbox_2180 is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    content = await _fetch_tile(layer, bbox_2180, width, height)
    if content is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@router.get("/tile")
async def gesut_tile(
    bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:3857"),
    width: int = Query(512, ge=1, le=2048),
    height: int = Query(512, ge=1, le=2048),
    _user=Depends(require_auth),
):
    """Proxy GESUT WMS tile (linie elektroenergetyczne) with disk cache."""
    return await _serve_tile("przewod_elektroenergetyczny", bbox, width, height)


@router.get("/tile-urzadzenia")
async def gesut_tile_urzadzenia(
    bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:3857"),
    width: int = Query(512, ge=1, le=2048),
    height: int = Query(512, ge=1, le=2048),
    _user=Depends(require_auth),
):
    """Proxy GESUT WMS tile (urządzenia uzbrojenia terenu) with disk cache."""
    return await _serve_tile("przewod_urzadzenia", bbox, width, height)
