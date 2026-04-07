from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.db.geo import get_geo_pool

router = APIRouter()

PLOT_COLUMNS = """
    id_dzialki, gmina, numer_dzialki, miejscowosc, ulica, area,
    lot_type, is_buildable, zoning_symbol, zoning_name,
    zoning_max_height, zoning_max_coverage, zoning_min_green,
    building_count_bdot, building_count_egib, building_count_osm,
    is_nature_protected, nature_protection,
    nearest_road_name, nearest_road_class, nearest_road_distance_m,
    nearest_education_m, nearest_healthcare_m, nearest_shopping_m, nearest_transport_m,
    has_water, has_sewage, has_gas, has_electric, has_heating, has_telecom,
    utility_count
"""


@router.get("/{id_dzialki:path}")
async def get_plot(id_dzialki: str):
    pool = get_geo_pool()
    row = await pool.fetchrow(
        f"SELECT {PLOT_COLUMNS} FROM lots_enriched WHERE id_dzialki = $1",
        id_dzialki,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Działka nie znaleziona")
    return dict(row)
