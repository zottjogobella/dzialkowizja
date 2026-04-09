from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import require_auth

from .schemas import SearchSuggestion
from .service import is_lot_query, search_addresses, search_lots

router = APIRouter()


@router.get("", response_model=list[SearchSuggestion])
async def search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
    _user=Depends(require_auth),
) -> list[SearchSuggestion]:
    if is_lot_query(q):
        return await search_lots(q, limit)
    return await search_addresses(q, limit)
