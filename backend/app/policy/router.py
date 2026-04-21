"""Admin endpoints for org access policy — login hours + daily search limit."""

from __future__ import annotations

from datetime import time as _time

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.engine import get_db
from app.db.models import Organization, OrganizationLoginHours, User

from .schemas import LoginHoursDay, PolicyOut, PolicyUpdateIn

router = APIRouter()


def _target_org_id(actor: User) -> "uuid.UUID":  # noqa: F821
    if actor.organization_id is None:
        raise HTTPException(
            status_code=400,
            detail="Operacja wymaga organizacji — użyj /api/super-admin",
        )
    return actor.organization_id


async def _build_policy_out(db: AsyncSession, org: Organization) -> PolicyOut:
    rows = (
        await db.execute(
            select(OrganizationLoginHours)
            .where(OrganizationLoginHours.organization_id == org.id)
            .order_by(OrganizationLoginHours.day_of_week)
        )
    ).scalars().all()
    days = [
        LoginHoursDay(
            day_of_week=r.day_of_week,
            closed=r.closed,
            start_time=r.start_time.strftime("%H:%M") if r.start_time else None,
            end_time=r.end_time.strftime("%H:%M") if r.end_time else None,
        )
        for r in rows
    ]
    return PolicyOut(
        login_hours_enabled=org.login_hours_enabled,
        daily_search_limit_enabled=org.daily_search_limit_enabled,
        daily_search_limit=org.daily_search_limit,
        days=days,
    )


@router.get("/policy", response_model=PolicyOut)
async def get_policy(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyOut:
    org_id = _target_org_id(actor)
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacja nie znaleziona")
    return await _build_policy_out(db, org)


@router.put("/policy", response_model=PolicyOut)
async def update_policy(
    body: PolicyUpdateIn,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyOut:
    org_id = _target_org_id(actor)
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacja nie znaleziona")

    org.login_hours_enabled = body.login_hours_enabled
    org.daily_search_limit_enabled = body.daily_search_limit_enabled
    org.daily_search_limit = body.daily_search_limit

    # Replace all 7 day rows — simpler than diffing; volume is tiny.
    await db.execute(
        delete(OrganizationLoginHours).where(OrganizationLoginHours.organization_id == org_id)
    )
    for d in body.days:
        db.add(
            OrganizationLoginHours(
                organization_id=org_id,
                day_of_week=d.day_of_week,
                closed=d.closed,
                start_time=_time.fromisoformat(d.start_time + ":00") if d.start_time else None,
                end_time=_time.fromisoformat(d.end_time + ":00") if d.end_time else None,
            )
        )

    await db.commit()
    await db.refresh(org)
    return await _build_policy_out(db, org)
