from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, Query, Response

from app.auth.dependencies import require_auth

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


def _cache_path(layer: str, bbox_3857: str, width: int, height: int) -> Path:
    key = hashlib.sha1(
        f"3857|{layer}|{bbox_3857}|{width}|{height}".encode()
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


def _is_valid_bbox_3857(bbox: str) -> bool:
    try:
        parts = bbox.split(",")
        if len(parts) != 4:
            return False
        for v in parts:
            float(v)
    except (ValueError, TypeError):
        return False
    return True


async def _fetch_tile(
    layer: str, bbox_3857: str, width: int, height: int
) -> bytes | None:
    """Return WMS tile bytes, using a disk cache on the way in and out.

    Pass-through to KIUT WMS in EPSG:3857 — the same SRS MapLibre uses
    for the rest of the map. Earlier we reprojected the tile bbox to
    EPSG:2180 server-side, but that produced a slightly skewed
    axis-aligned envelope per tile, so adjacent tiles each rendered a
    marginally different geographic area and lines visibly broke at tile
    seams. KIUT advertises EPSG:3857 in its GetCapabilities, so we drop
    the reprojection and let GUGiK render exactly the area MapLibre
    requested.

    Returns `None` if the upstream fetch fails — callers map that to the
    transparent-PNG fallback so the map doesn't break when GUGiK is flaky.
    """
    path = _cache_path(layer, bbox_3857, width, height)
    cached = await asyncio.to_thread(_read_cache, path)
    if cached is not None:
        return cached

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "SRS": "EPSG:3857",
        "BBOX": bbox_3857,
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
    if not _is_valid_bbox_3857(bbox):
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    content = await _fetch_tile(layer, bbox, width, height)
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
