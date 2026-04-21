from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request

from app.audit.recorder import record
from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import User
from app.middleware.rate_limit_dep import rate_limit_search
from app.policy.daily_limit import enforce_daily_search_limit
from sqlalchemy.ext.asyncio import AsyncSession

from .schemas import SearchSuggestion
from .service import is_lot_query, search_addresses, search_lots

router = APIRouter()


@router.get("", response_model=list[SearchSuggestion])
async def search(
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_search),
    _dl: None = Depends(enforce_daily_search_limit),
) -> list[SearchSuggestion]:
    if is_lot_query(q):
        results = await search_lots(q, limit)
        query_type = "id_dzialki"
    else:
        results = await search_addresses(q, limit)
        query_type = "address"

    await record(
        db, user,
        action_type="search",
        request=request,
        query_text=q,
        target_id=results[0].label if results else None,
    )
    # query_type label kept for parity with SearchHistory enum, but the
    # audit table only carries action_type.
    _ = query_type
    return results
