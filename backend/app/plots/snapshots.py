"""Plot snapshot generation service — ortho and base map screenshots."""
from __future__ import annotations

import asyncio
import io
import logging
import math
from typing import Literal

import httpx
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer

from app.config import settings

logger = logging.getLogger(__name__)

SnapshotType = Literal["ortho", "map"]

_to_3857 = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)


def _bbox_from_geometry(geom: dict) -> tuple[float, float, float, float]:
    """Extract (min_lng, min_lat, max_lng, max_lat) from GeoJSON geometry."""
    coords = _flatten_coords(geom)
    lngs = [c[0] for c in coords]
    lats = [c[1] for c in coords]
    return min(lngs), min(lats), max(lngs), max(lats)


def _flatten_coords(geom: dict) -> list[list[float]]:
    t = geom.get("type", "")
    c = geom.get("coordinates", [])
    if t == "Point":
        return [c]
    if t in ("MultiPoint", "LineString"):
        return c
    if t in ("MultiLineString", "Polygon"):
        return [pt for ring in c for pt in ring]
    if t == "MultiPolygon":
        return [pt for poly in c for ring in poly for pt in ring]
    return []


def _pad_bbox(
    bbox: tuple[float, float, float, float],
    factor: float | None = None,
) -> tuple[float, float, float, float]:
    if factor is None:
        factor = settings.snapshot_bbox_padding
    min_lng, min_lat, max_lng, max_lat = bbox
    dlng = (max_lng - min_lng) * factor
    dlat = (max_lat - min_lat) * factor
    return (min_lng - dlng, min_lat - dlat, max_lng + dlng, max_lat + dlat)


def _project_ring_to_pixels(
    ring: list[list[float]],
    bbox_3857: tuple[float, float, float, float],
    w: int,
    h: int,
) -> list[tuple[int, int]]:
    min_x, min_y, max_x, max_y = bbox_3857
    sx = w / (max_x - min_x) if max_x != min_x else 1
    sy = h / (max_y - min_y) if max_y != min_y else 1
    pixels = []
    for lng, lat in ring:
        x, y = _to_3857.transform(lng, lat)
        px = int((x - min_x) * sx)
        py = int((max_y - y) * sy)  # Y flipped
        pixels.append((px, py))
    return pixels


def _draw_plot_outline(
    img: Image.Image,
    geometry: dict,
    bbox_3857: tuple[float, float, float, float],
) -> Image.Image:
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    rings: list[list[list[float]]] = []
    if geometry["type"] == "Polygon":
        rings.append(geometry["coordinates"][0])
    elif geometry["type"] == "MultiPolygon":
        for poly in geometry["coordinates"]:
            rings.append(poly[0])

    for ring in rings:
        pixels = _project_ring_to_pixels(ring, bbox_3857, w, h)
        if len(pixels) >= 3:
            # Fill with semi-transparent blue
            draw.polygon(pixels, fill=(37, 99, 235, 40))
            # Blue outline
            draw.line(pixels + [pixels[0]], fill=(29, 78, 216, 200), width=3)

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _draw_scale_bar(
    img: Image.Image,
    bbox_3857: tuple[float, float, float, float],
) -> Image.Image:
    """Draw a scale bar in the bottom-right corner."""
    w, h = img.size
    min_x, min_y, max_x, max_y = bbox_3857
    meters_per_pixel = (max_x - min_x) / w

    # Pick a nice round scale length
    target_px = w * 0.2  # aim for ~20% of image width
    target_m = target_px * meters_per_pixel
    nice_values = [5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 5000]
    scale_m = nice_values[0]
    for v in nice_values:
        if v <= target_m:
            scale_m = v
        else:
            break

    bar_px = int(scale_m / meters_per_pixel)
    bar_h = 6
    margin = 15
    text_margin = 4

    # Label
    label = f"{scale_m} m" if scale_m < 1000 else f"{scale_m / 1000:.0f} km"

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13)
    except (OSError, IOError):
        font = ImageFont.load_default()

    text_bbox = draw.textbbox((0, 0), label, font=font)
    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]

    # Position: bottom-right
    bar_x2 = w - margin
    bar_x1 = bar_x2 - bar_px
    bar_y2 = h - margin
    bar_y1 = bar_y2 - bar_h

    # Background
    bg_x1 = bar_x1 - 6
    bg_y1 = bar_y1 - text_h - text_margin - 6
    bg_x2 = bar_x2 + 6
    bg_y2 = bar_y2 + 6
    draw.rounded_rectangle([bg_x1, bg_y1, bg_x2, bg_y2], radius=4, fill=(255, 255, 255, 200))

    # Bar
    draw.rectangle([bar_x1, bar_y1, bar_x2, bar_y2], fill=(50, 50, 50))
    # Ticks at ends
    draw.rectangle([bar_x1, bar_y1 - 3, bar_x1 + 1, bar_y2], fill=(50, 50, 50))
    draw.rectangle([bar_x2 - 1, bar_y1 - 3, bar_x2, bar_y2], fill=(50, 50, 50))

    # Text centered above bar
    text_x = bar_x1 + (bar_px - text_w) // 2
    text_y = bar_y1 - text_h - text_margin
    draw.text((text_x, text_y), label, fill=(50, 50, 50), font=font)

    return img


# --- Ortho snapshot (single WMS request) ---

async def _generate_ortho(
    geometry: dict,
    bbox_4326: tuple[float, float, float, float],
) -> bytes:
    w, h = settings.snapshot_width, settings.snapshot_height
    min_lng, min_lat, max_lng, max_lat = bbox_4326
    min_x, min_y = _to_3857.transform(min_lng, min_lat)
    max_x, max_y = _to_3857.transform(max_lng, max_lat)
    bbox_3857 = (min_x, min_y, max_x, max_y)

    wms_url = (
        "https://mapy.geoportal.gov.pl/wss/service/PZGIK/ORTO/WMS/StandardResolution"
        f"?SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=Raster&STYLES="
        f"&SRS=EPSG:3857&BBOX={min_x},{min_y},{max_x},{max_y}"
        f"&WIDTH={w}&HEIGHT={h}&FORMAT=image/jpeg"
    )

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(wms_url)
        resp.raise_for_status()

    img = Image.open(io.BytesIO(resp.content)).convert("RGB")
    img = _draw_plot_outline(img, geometry, bbox_3857)
    img = _draw_scale_bar(img, bbox_3857)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# --- Map snapshot (CARTO tile stitching) ---

def _lng_to_tile_x(lng: float, zoom: int) -> int:
    return int((lng + 180.0) / 360.0 * (1 << zoom))


def _lat_to_tile_y(lat: float, zoom: int) -> int:
    lat_rad = math.radians(lat)
    n = 1 << zoom
    return int((1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n)


def _tile_lng(tx: int, zoom: int) -> float:
    return tx / (1 << zoom) * 360.0 - 180.0


def _tile_lat(ty: int, zoom: int) -> float:
    n = math.pi - 2.0 * math.pi * ty / (1 << zoom)
    return math.degrees(math.atan(math.sinh(n)))


def _compute_zoom(bbox_4326: tuple[float, float, float, float], target_w: int) -> int:
    min_lng, _, max_lng, _ = bbox_4326
    span = max_lng - min_lng
    if span <= 0:
        return 18
    for z in range(18, 0, -1):
        tiles_across = span / 360.0 * (1 << z)
        if tiles_across * 256 <= target_w * 2:
            return z
    return 15


async def _generate_map(
    geometry: dict,
    bbox_4326: tuple[float, float, float, float],
) -> bytes:
    w, h = settings.snapshot_width, settings.snapshot_height
    min_lng, min_lat, max_lng, max_lat = bbox_4326

    zoom = _compute_zoom(bbox_4326, w)
    tx_min = _lng_to_tile_x(min_lng, zoom)
    tx_max = _lng_to_tile_x(max_lng, zoom)
    ty_min = _lat_to_tile_y(max_lat, zoom)  # Note: y is flipped
    ty_max = _lat_to_tile_y(min_lat, zoom)

    tile_size = 512  # @2x tiles

    # Fetch tiles
    tiles: dict[tuple[int, int], Image.Image] = {}
    async with httpx.AsyncClient(timeout=30) as client:
        tasks = {}
        for tx in range(tx_min, tx_max + 1):
            for ty in range(ty_min, ty_max + 1):
                url = f"https://basemaps.cartocdn.com/rastertiles/voyager/{zoom}/{tx}/{ty}@2x.png"
                tasks[(tx, ty)] = client.get(url)

        responses = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for (tx, ty), resp in zip(tasks.keys(), responses):
            if isinstance(resp, Exception):
                continue
            try:
                resp.raise_for_status()
                tiles[(tx, ty)] = Image.open(io.BytesIO(resp.content)).convert("RGB")
            except Exception:
                pass

    if not tiles:
        # Fallback: white image
        img = Image.new("RGB", (w, h), (255, 255, 255))
    else:
        # Stitch tiles
        cols = tx_max - tx_min + 1
        rows = ty_max - ty_min + 1
        stitched = Image.new("RGB", (cols * tile_size, rows * tile_size), (240, 240, 240))
        for (tx, ty), tile_img in tiles.items():
            tile_img = tile_img.resize((tile_size, tile_size), Image.LANCZOS)
            px = (tx - tx_min) * tile_size
            py = (ty - ty_min) * tile_size
            stitched.paste(tile_img, (px, py))

        # Calculate pixel coords of bbox within stitched image
        total_lng_min = _tile_lng(tx_min, zoom)
        total_lng_max = _tile_lng(tx_max + 1, zoom)
        total_lat_max = _tile_lat(ty_min, zoom)
        total_lat_min = _tile_lat(ty_max + 1, zoom)

        sw = stitched.width
        sh = stitched.height
        crop_x1 = int((min_lng - total_lng_min) / (total_lng_max - total_lng_min) * sw)
        crop_x2 = int((max_lng - total_lng_min) / (total_lng_max - total_lng_min) * sw)

        # Latitude is non-linear in Mercator but approximate for small areas
        crop_y1 = int((total_lat_max - max_lat) / (total_lat_max - total_lat_min) * sh)
        crop_y2 = int((total_lat_max - min_lat) / (total_lat_max - total_lat_min) * sh)

        crop_x1 = max(0, crop_x1)
        crop_y1 = max(0, crop_y1)
        crop_x2 = min(sw, crop_x2)
        crop_y2 = min(sh, crop_y2)

        img = stitched.crop((crop_x1, crop_y1, crop_x2, crop_y2))
        img = img.resize((w, h), Image.LANCZOS)

    # Draw plot outline
    min_x, min_y = _to_3857.transform(min_lng, min_lat)
    max_x, max_y = _to_3857.transform(max_lng, max_lat)
    bbox_3857 = (min_x, min_y, max_x, max_y)
    img = _draw_plot_outline(img, geometry, bbox_3857)
    img = _draw_scale_bar(img, bbox_3857)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


# --- Public API ---

async def generate_snapshot(
    geometry_feature: dict,
    snapshot_type: SnapshotType,
) -> tuple[bytes, int, int]:
    """Generate a snapshot for a plot. Returns (jpeg_bytes, width, height)."""
    geometry = geometry_feature["geometry"]
    bbox = _bbox_from_geometry(geometry)
    bbox = _pad_bbox(bbox)

    if snapshot_type == "ortho":
        data = await _generate_ortho(geometry, bbox)
    else:
        data = await _generate_map(geometry, bbox)

    return data, settings.snapshot_width, settings.snapshot_height
