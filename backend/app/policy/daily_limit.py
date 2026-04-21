"""Daily per-user search-limit enforcement.

FastAPI dependency layered on ``/api/search`` alongside the existing
per-minute rate limiter. Counts rows in ``activity_log`` with action_type='search'
written today in Europe/Warsaw. role=user only; admins and super_admins bypass.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import ActivityLog, Organization, User
from app.utils.time import now_warsaw, warsaw_midnight_utc


async def enforce_daily_search_limit(
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.role != "user":
        return
    if user.organization_id is None:
        return

    org = (
        await db.execute(select(Organization).where(Organization.id == user.organization_id))
    ).scalar_one_or_none()
    if org is None or not org.daily_search_limit_enabled:
        return

    today_utc = warsaw_midnight_utc()
    count = (
        await db.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.user_id == user.id,
                ActivityLog.action_type == "search",
                ActivityLog.created_at >= today_utc,
            )
        )
    ).scalar_one()

    if int(count) >= org.daily_search_limit:
        # Next local midnight. Adding timedelta(days=1) then rounding to
        # midnight handles DST correctly: the wall clock lands on 00:00
        # regardless of the 23- or 25-hour spring/fall day.
        warsaw_now = now_warsaw()
        reset_warsaw = (warsaw_now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        retry_after = max(1, int((reset_warsaw - warsaw_now).total_seconds()))
        raise HTTPException(
            status_code=429,
            detail={
                "code": "daily_limit_exceeded",
                "message": (
                    f"Wyczerpano dzienny limit wyszukiwań "
                    f"({org.daily_search_limit}). Reset o 00:00."
                ),
                "limit": org.daily_search_limit,
                "reset_at": reset_warsaw.isoformat(),
            },
            headers={"Retry-After": str(retry_after)},
        )
