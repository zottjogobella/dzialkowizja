from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("/{id_dzialki}")
async def get_plot(id_dzialki: str):
    """Placeholder - will be implemented with geo DB."""
    return {"detail": "Not implemented"}
