"""Daily per-user search-limit enforcement.

FastAPI dependency layered on the plot-detail endpoint. Counts rows
in ``activity_log`` with action_type='plot_view' written today in
Europe/Warsaw — i.e. real plot opens, not autocomplete keystrokes.
Limit is per (org, user.role) — handlowiec and prawnik can have
different caps. admins and super_admins bypass.

The product label remains "limit wyszukiwań" because that is how the
end user perceives a search: typing in the box and opening a plot.
The autocomplete requests on /api/search are not counted.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import (
    RESTRICTABLE_ROLES,
    ActivityLog,
    OrganizationRolePolicy,
    User,
)
from app.utils.time import now_warsaw, warsaw_midnight_utc


async def enforce_daily_search_limit(
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> None:
    if user.role not in RESTRICTABLE_ROLES:
        return
    if user.organization_id is None:
        return

    pol = (
        await db.execute(
            select(OrganizationRolePolicy).where(
                OrganizationRolePolicy.organization_id == user.organization_id,
                OrganizationRolePolicy.role == user.role,
            )
        )
    ).scalar_one_or_none()
    if pol is None or not pol.daily_search_limit_enabled:
        return

    today_utc = warsaw_midnight_utc()
    count = (
        await db.execute(
            select(func.count())
            .select_from(ActivityLog)
            .where(
                ActivityLog.user_id == user.id,
                ActivityLog.action_type == "plot_view",
                ActivityLog.created_at >= today_utc,
            )
        )
    ).scalar_one()

    if int(count) >= pol.daily_search_limit:
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
                    f"({pol.daily_search_limit}). Reset o 00:00."
                ),
                "limit": pol.daily_search_limit,
                "reset_at": reset_warsaw.isoformat(),
            },
            headers={"Retry-After": str(retry_after)},
        )
