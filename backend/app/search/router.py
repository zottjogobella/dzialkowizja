from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def search():
    """Placeholder - will be implemented with geo DB."""
    return {"results": [], "total": 0}
