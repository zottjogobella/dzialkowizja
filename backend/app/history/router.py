from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.get("")
async def list_history():
    """Placeholder - will be implemented with auth."""
    return {"items": [], "total": 0}
