"""MPZP — Krajowa Integracja Miejscowych Planów Zagospodarowania Przestrzennego.

Mirrors ``app.gesut`` patterns: a disk-cached WMS GetMap proxy for the raster
plan layer, plus a GetFeatureInfo endpoint that answers "what does the MPZP
say about this plot?" by querying GUGiK at the plot's centroid.

Upstream service (free, no auth): integracja.gugik.gov.pl. Both GetMap and
GetFeatureInfo accept EPSG:2180, so we reproject incoming EPSG:3857 bboxes
and centroids using PostGIS the same way GESUT does.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from pathlib import Path
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.recorder import record
from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.geo import get_geo_pool
from app.db.models import User
from app.middleware.rate_limit_dep import rate_limit_detail

logger = logging.getLogger(__name__)

router = APIRouter()

MPZP_WMS_URL = (
    "https://mapy.geoportal.gov.pl/wss/ext/"
    "KrajowaIntegracjaMiejscowychPlanowZagospodarowaniaPrzestrzennego"
)

# GetMap: use raster scans layer for tile rendering.
# The parent "plany" group layer does NOT composite sub-layers for GetMap.
MPZP_TILE_LAYERS = "raster"

# GetFeatureInfo: the "plany" group layer returns attribute data (plan name,
# przeznaczenie, etc.) even though it doesn't render visible tiles.
MPZP_QUERY_LAYER = "plany"

# Transparent 1x1 PNG fallback (matches GESUT — on upstream errors we return
# an empty tile rather than 500 so the basemap keeps rendering).
TRANSPARENT_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
    b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

CACHE_DIR = Path("/tmp/mpzp_cache")
CACHE_TTL_SEC = 86400  # 24 h — MPZP changes rarely and slowly


def _cache_path(layer: str, bbox_2180: str, width: int, height: int) -> Path:
    key = hashlib.sha1(
        f"{layer}|{bbox_2180}|{width}|{height}".encode()
    ).hexdigest()
    return CACHE_DIR / f"{key}.png"


def _read_cache(path: Path) -> bytes | None:
    try:
        st = path.stat()
    except (FileNotFoundError, OSError):
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
        tmp.replace(path)
    except OSError:
        logger.debug("Failed to write MPZP cache", exc_info=True)


async def _bbox_3857_to_2180(bbox: str) -> str | None:
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
            min_x, min_y, max_x, max_y,
        )
    return f"{row[0]},{row[1]},{row[2]},{row[3]}"


async def _fetch_tile(
    layer: str, bbox: str, width: int, height: int, srs: str = "EPSG:3857",
) -> bytes | None:
    path = _cache_path(layer, bbox, width, height)
    cached = await asyncio.to_thread(_read_cache, path)
    if cached is not None:
        return cached

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetMap",
        "LAYERS": layer,
        "SRS": srs,
        "BBOX": bbox,
        "WIDTH": str(width),
        "HEIGHT": str(height),
        "FORMAT": "image/png",
        "STYLES": ",".join("" for _ in layer.split(",")),
        "TRANSPARENT": "TRUE",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(MPZP_WMS_URL, params=params)
    except Exception:
        logger.exception("MPZP WMS fetch failed layer=%s", layer)
        return None

    if resp.status_code != 200 or "image" not in resp.headers.get("content-type", ""):
        return None

    await asyncio.to_thread(_write_cache, path, resp.content)
    return resp.content


@router.get("/tile")
async def mpzp_tile(
    bbox: str = Query(..., description="minx,miny,maxx,maxy in EPSG:3857"),
    width: int = Query(512, ge=1, le=2048),
    height: int = Query(512, ge=1, le=2048),
    _user=Depends(require_auth),
):
    """Proxy KI MPZP WMS tile (plan polygons) with a 24 h disk cache.

    Passes the EPSG:3857 bbox straight to the WMS (which supports it)
    to avoid reprojection-induced tile seams.
    """
    content = await _fetch_tile(MPZP_TILE_LAYERS, bbox, width, height)
    if content is None:
        return Response(content=TRANSPARENT_PNG, media_type="image/png")

    return Response(
        content=content,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )


async def _plot_centroid_2180(id_dzialki: str) -> tuple[float, float] | None:
    """Return the plot's centroid in EPSG:2180, or None if the plot is missing.

    Centroid is used instead of ST_PointOnSurface for speed; for convex plots
    the two are close enough, and GetFeatureInfo is tolerant to being off by
    a few metres inside a plan polygon of hectares.
    """
    pool = get_geo_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT ST_X(c) AS x, ST_Y(c) AS y
            FROM (
                SELECT ST_Centroid(geom) AS c
                FROM lots_enriched
                WHERE id_dzialki = $1
            ) t
            """,
            id_dzialki,
        )
    if row is None or row["x"] is None:
        return None
    return float(row["x"]), float(row["y"])


def _clean(val: str | None) -> str | None:
    """Treat GUGiK sentinels (``null``, ``0``, blanks) as missing."""
    if val is None:
        return None
    s = val.strip()
    if not s or s.lower() == "null" or s == "0":
        return None
    return s


def _parse_gugik_xml(body: str, final_url: str | None) -> list[dict]:
    """Parse the ``<GetFeatureInfo_Result>`` XML GUGiK actually returns.

    Upstream ignores ``INFO_FORMAT=application/json`` and always responds with
    XML shaped like ``<GetFeatureInfo_Result><ROWSET><ROW>...``. Fields are
    Polish plan attributes (``NAZWA_PLAN``, ``FUN_NAZWA``, ``FUN_SYMB``,
    ``INTEN_ZAB``, ``MAX_WYS``, ``DZIELNICA``, ``WWW``). We fold each ROW
    into the flat shape the frontend expects.
    """
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        logger.debug("MPZP GetFeatureInfo: unparseable XML: %s", body[:200])
        return []

    seen: set[tuple[str | None, ...]] = set()
    out: list[dict] = []
    for row in root.iter("ROW"):
        props = {child.tag: (child.text or "") for child in row}
        nazwa_plan = _clean(props.get("NAZWA_PLAN"))
        fun_nazwa = _clean(props.get("FUN_NAZWA"))
        fun_symb = _clean(props.get("FUN_SYMB"))
        inten_zab = _clean(props.get("INTEN_ZAB"))
        max_wys = _clean(props.get("MAX_WYS"))
        dzielnica = _clean(props.get("DZIELNICA"))

        przeznaczenie = fun_nazwa
        if fun_nazwa and fun_symb:
            przeznaczenie = f"{fun_nazwa} ({fun_symb})"
        elif fun_symb:
            przeznaczenie = fun_symb

        opis_parts: list[str] = []
        if max_wys:
            opis_parts.append(f"Maks. wysokość zabudowy: {max_wys} m")
        if inten_zab:
            opis_parts.append(f"Intensywność zabudowy: {inten_zab}")
        if dzielnica:
            opis_parts.append(f"Dzielnica: {dzielnica}")
        opis = "\n".join(opis_parts) or None

        # WWW values often come back as placeholders (``../dane/plany/ .html``
        # with literal spaces). Only resolve when it looks like a real path,
        # and turn relative refs into absolute URLs based on the redirected
        # upstream host.
        www = props.get("WWW", "").strip()
        link: str | None = None
        if www and " " not in www and www not in {"null", "0"}:
            link = urljoin(final_url or MPZP_WMS_URL, www) if final_url else www

        key = (nazwa_plan, przeznaczenie, opis, link)
        if key in seen:
            continue
        seen.add(key)
        if not any(key):
            continue

        out.append({
            "tytul_planu": nazwa_plan,
            "uchwala": None,
            "data_uchwalenia": None,
            "przeznaczenie": przeznaczenie,
            "opis": opis,
            "link_do_uchwaly": link,
            "raw": props,
        })
    return out


async def _get_feature_info(cx: float, cy: float) -> list[dict] | None:
    """Query MPZP GetFeatureInfo at a single point in EPSG:2180.

    We pin a 2 m × 2 m bbox around the centroid and request a 1×1 px image —
    the point of interest sits at pixel (0, 0). This keeps the HTTP payload
    tiny and avoids "click on the map" semantics creeping in.
    """
    half = 1.0
    bbox = f"{cx - half},{cy - half},{cx + half},{cy + half}"

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.1.1",
        "REQUEST": "GetFeatureInfo",
        "LAYERS": MPZP_QUERY_LAYER,
        "QUERY_LAYERS": MPZP_QUERY_LAYER,
        "SRS": "EPSG:2180",
        "BBOX": bbox,
        "WIDTH": "1",
        "HEIGHT": "1",
        "X": "0",
        "Y": "0",
        "INFO_FORMAT": "application/json",
        "FEATURE_COUNT": "10",
    }

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20) as client:
            resp = await client.get(MPZP_WMS_URL, params=params)
    except Exception:
        logger.exception("MPZP GetFeatureInfo failed")
        return None

    if resp.status_code != 200:
        logger.warning("MPZP GetFeatureInfo HTTP %s", resp.status_code)
        return None

    body = resp.text
    # GUGiK ignores INFO_FORMAT=application/json and returns XML with a
    # ``text/html`` content type. Try JSON first in case a future version
    # honours the hint, then fall back to XML parsing.
    try:
        data = resp.json()
        features = data.get("features") or []
        results: list[dict] = []
        for f in features:
            props = f.get("properties") or {}
            # obowiazujeod comes as "2013-05-15Z" — strip trailing Z
            obowiazuje_od = _clean(props.get("obowiazujeod"))
            if obowiazuje_od and obowiazuje_od.endswith("Z"):
                obowiazuje_od = obowiazuje_od[:-1]
            obowiazuje_do = _clean(props.get("obowiazujedo"))
            if obowiazuje_do and obowiazuje_do.endswith("Z"):
                obowiazuje_do = obowiazuje_do[:-1]

            results.append({
                "tytul_planu": props.get("tytul") or props.get("tytul_planu") or props.get("name"),
                "uchwala": props.get("dokumentuchwalajacy") or props.get("uchwala") or props.get("uchwala_nr"),
                "data_uchwalenia": obowiazuje_od or props.get("data_uchwalenia") or props.get("data"),
                "obowiazuje_do": obowiazuje_do,
                "status": _clean(props.get("status")) or _clean(props.get("state")),
                "typ_planu": _clean(props.get("typplanu")) or _clean(props.get("type")),
                "przeznaczenie": props.get("przeznaczenie"),
                "opis": props.get("opis") or props.get("tresc"),
                "link_do_uchwaly": props.get("xlinkhref") or props.get("link_do_uchwaly") or props.get("url"),
                "rysunek_url": _clean(props.get("rysunek_lacze")),
                "dokument_przystepujacy": _clean(props.get("dokumentprzystepujacy")),
                "mapa_podkladowa": _clean(props.get("mapapodkladowa")),
                "raw": props,
            })
        return results
    except ValueError:
        pass

    return _parse_gugik_xml(body, str(resp.url))


@router.get("/{id_dzialki:path}")
async def mpzp_for_plot(
    id_dzialki: str,
    request: Request,
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_detail),
):
    """GetFeatureInfo at a plot's centroid against KI MPZP.

    Returns `{ "features": [...] }`. Empty list when the plot falls outside
    any plan that GUGiK has ingested — absence of MPZP is itself useful info
    for the user and not an error.
    """
    centroid = await _plot_centroid_2180(id_dzialki)
    if centroid is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")

    features = await _get_feature_info(*centroid)
    await record(db, user, action_type="mpzp_fetch", request=request, target_id=id_dzialki)
    if features is None:
        # Upstream glitch — don't surface it as 5xx, the map tile layer will
        # still show the plan visually.
        return {"features": [], "upstream_error": True}
    return {"features": features}
