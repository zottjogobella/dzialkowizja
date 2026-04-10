"""POC: raster → vector conversion for GESUT WMS tiles.

Purpose: explore whether we can turn the rendered-bitmap GESUT electric-line
layer (where GUGiK only exposes WMS, not WFS / WMTS / vector tiles) into a
stream of polylines that MapLibre can render natively. If this holds up it
becomes the basis for a wider WMS-to-vector tool — but for now, this module
is deliberately small and single-layer.

Pipeline:
  1. Decode PNG bytes (OpenCV).
  2. Threshold for red line pixels → binary mask.
  3. Zhang-Suen thinning (OpenCV ximgproc, contrib build) → 1-pixel skeleton.
  4. findContours on the skeleton → per-line pixel polyline.
  5. Douglas-Peucker simplification to drop noise / collinear points.
  6. Pixel → EPSG:2180 via the known tile bbox (linear, y inverted).

Reprojection to EPSG:4326 happens in the router layer via PostGIS so we do
not add a pyproj initialisation step into the hot path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VectorizationResult:
    # One polyline per element, each as a list of (x, y) in EPSG:2180.
    lines_2180: list[list[tuple[float, float]]]
    raw_contour_count: int
    kept_line_count: int
    non_zero_pixels: int


# GESUT default stylesheet paints the `przewod_elektroenergetyczny` layer in
# a saturated red. The thresholds below are wide enough to absorb the slight
# anti-alias halo without grabbing the yellow/orange hues used by gas or
# telecom layers. BGR order (OpenCV).
ELECTRIC_RED_LOWER = np.array([0, 0, 100], dtype=np.uint8)
ELECTRIC_RED_UPPER = np.array([80, 80, 255], dtype=np.uint8)

# Minimum polyline length (in original pixels) to keep. Anything shorter is
# almost certainly noise from junction artefacts or symbol fragments.
MIN_POLYLINE_PIXELS = 6

# Douglas-Peucker simplification tolerance in pixels. 0.8 drops the zig-zag
# noise Zhang-Suen leaves behind while preserving visible bends.
SIMPLIFY_EPSILON_PX = 0.8


def vectorize_electric_lines(
    png_bytes: bytes,
    bbox_2180: tuple[float, float, float, float],
) -> VectorizationResult:
    """Extract electric-line centerlines from a GESUT raster tile.

    `bbox_2180` is `(min_x, min_y, max_x, max_y)` — the ground extent the PNG
    covers, in EPSG:2180. Image origin is top-left, so pixel `(col, row)` maps
    to `(min_x + col*gsd_x, max_y - row*gsd_y)`.
    """
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)  # BGR; alpha dropped
    if img is None or img.size == 0:
        return VectorizationResult([], 0, 0, 0)

    h, w = img.shape[:2]
    min_x, min_y, max_x, max_y = bbox_2180
    gsd_x = (max_x - min_x) / w
    gsd_y = (max_y - min_y) / h

    # 1. Colour threshold.
    mask = cv2.inRange(img, ELECTRIC_RED_LOWER, ELECTRIC_RED_UPPER)
    non_zero = int(cv2.countNonZero(mask))
    if non_zero == 0:
        return VectorizationResult([], 0, 0, 0)

    # 2. Close tiny gaps that Zhang-Suen would otherwise split into separate
    # segments, then thin.
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    try:
        skeleton = cv2.ximgproc.thinning(
            closed, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN
        )
    except Exception:
        logger.exception("cv2.ximgproc.thinning failed; returning empty")
        return VectorizationResult([], 0, 0, non_zero)

    # 3. Contours on a 1-pixel skeleton give us each connected stroke as a
    # polyline. For strokes that are true curves (open) the contour traces
    # the pixels once; for closed loops it traces them as a ring. We treat
    # both the same for POC.
    contours, _ = cv2.findContours(
        skeleton, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE
    )

    lines_2180: list[list[tuple[float, float]]] = []
    for contour in contours:
        if len(contour) < MIN_POLYLINE_PIXELS:
            continue
        simplified = cv2.approxPolyDP(contour, SIMPLIFY_EPSILON_PX, closed=False)
        if len(simplified) < 2:
            continue
        coords: list[tuple[float, float]] = []
        for pt in simplified:
            px = float(pt[0, 0])
            py = float(pt[0, 1])
            x = min_x + px * gsd_x
            y = max_y - py * gsd_y  # PNG y grows downward; 2180 y grows upward
            coords.append((x, y))
        lines_2180.append(coords)

    return VectorizationResult(
        lines_2180=lines_2180,
        raw_contour_count=len(contours),
        kept_line_count=len(lines_2180),
        non_zero_pixels=non_zero,
    )
