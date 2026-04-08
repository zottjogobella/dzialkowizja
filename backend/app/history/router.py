from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import SearchHistory, User

router = APIRouter()


class HistoryItemOut(BaseModel):
    id: str
    query_text: str
    query_type: str
    result_count: int
    top_result_id: str | None
    created_at: str


class HistoryListOut(BaseModel):
    items: list[HistoryItemOut]
    total: int


@router.get("", response_model=HistoryListOut)
async def list_history(
    limit: int = Query(default=20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
) -> HistoryListOut:
    total_q = await db.execute(
        select(func.count()).select_from(SearchHistory).where(SearchHistory.user_id == user.id)
    )
    total = total_q.scalar_one()

    rows_q = await db.execute(
        select(SearchHistory)
        .where(SearchHistory.user_id == user.id)
        .order_by(SearchHistory.created_at.desc())
        .limit(limit)
    )
    rows = rows_q.scalars().all()

    return HistoryListOut(
        items=[
            HistoryItemOut(
                id=str(r.id),
                query_text=r.query_text,
                query_type=r.query_type,
                result_count=r.result_count,
                top_result_id=r.top_result_id,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ],
        total=total,
    )


class RecordSearchIn(BaseModel):
    query_text: str
    query_type: str  # 'lot' | 'address'
    result_count: int = 0
    top_result_id: str | None = None


@router.post("", status_code=201)
async def record_search(
    body: RecordSearchIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
) -> dict:
    entry = SearchHistory(
        user_id=user.id,
        query_text=body.query_text,
        query_type=body.query_type,
        result_count=body.result_count,
        top_result_id=body.top_result_id,
    )
    db.add(entry)
    await db.commit()
    return {"ok": True}


@router.delete("")
async def clear_history(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_auth),
) -> dict:
    from sqlalchemy import delete

    await db.execute(delete(SearchHistory).where(SearchHistory.user_id == user.id))
    await db.commit()
    return {"ok": True}
