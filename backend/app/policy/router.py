"""Admin endpoints for org access policy — login hours + daily search limit.

Per-role: handlowiec and prawnik have independent schedules and limits.
GET takes ``?role=handlowiec|prawnik``; PUT carries the role in the body.
"""

from __future__ import annotations

import uuid
from datetime import time as _time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.engine import get_db
from app.db.models import (
    RESTRICTABLE_ROLES,
    Organization,
    OrganizationLoginHours,
    OrganizationRolePolicy,
    User,
)

from .schemas import LoginHoursDay, PolicyOut, PolicyUpdateIn

router = APIRouter()


def _target_org_id(actor: User) -> uuid.UUID:
    if actor.organization_id is None:
        raise HTTPException(
            status_code=400,
            detail="Operacja wymaga organizacji — użyj /api/super-admin",
        )
    return actor.organization_id


def _validate_role(role: str) -> str:
    if role not in RESTRICTABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Nieznana rola: {role} (dozwolone: {', '.join(RESTRICTABLE_ROLES)})",
        )
    return role


async def _get_or_seed_role_policy(
    db: AsyncSession, org_id: uuid.UUID, role: str
) -> OrganizationRolePolicy:
    """Fetch the (org, role) policy row, seeding defaults if it's missing.

    Orgs created before migration 015 already have rows for both roles;
    the seed path covers brand-new orgs the create endpoint forgot to
    initialize, so the admin UI never 500s on first load.
    """
    pol = (
        await db.execute(
            select(OrganizationRolePolicy).where(
                OrganizationRolePolicy.organization_id == org_id,
                OrganizationRolePolicy.role == role,
            )
        )
    ).scalar_one_or_none()
    if pol is not None:
        return pol
    pol = OrganizationRolePolicy(
        organization_id=org_id,
        role=role,
        login_hours_enabled=True,
        daily_search_limit_enabled=True,
        daily_search_limit=40,
    )
    db.add(pol)
    await db.flush()
    return pol


async def _build_policy_out(
    db: AsyncSession, org_id: uuid.UUID, role: str
) -> PolicyOut:
    pol = await _get_or_seed_role_policy(db, org_id, role)
    rows = (
        await db.execute(
            select(OrganizationLoginHours)
            .where(
                OrganizationLoginHours.organization_id == org_id,
                OrganizationLoginHours.role == role,
            )
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
    # Brand-new role: no rows yet → seed sensible defaults so the UI has
    # something to render. Mon–Fri 9-18 open, weekend closed.
    if not days:
        days = _default_days()
        for d in days:
            db.add(
                OrganizationLoginHours(
                    organization_id=org_id,
                    role=role,
                    day_of_week=d.day_of_week,
                    closed=d.closed,
                    start_time=_time.fromisoformat(d.start_time + ":00") if d.start_time else None,
                    end_time=_time.fromisoformat(d.end_time + ":00") if d.end_time else None,
                )
            )
        await db.flush()
    return PolicyOut(
        role=role,  # type: ignore[arg-type]
        login_hours_enabled=pol.login_hours_enabled,
        daily_search_limit_enabled=pol.daily_search_limit_enabled,
        daily_search_limit=pol.daily_search_limit,
        days=days,
    )


def _default_days() -> list[LoginHoursDay]:
    days: list[LoginHoursDay] = []
    for dow in range(0, 5):
        days.append(LoginHoursDay(day_of_week=dow, closed=False, start_time="09:00", end_time="18:00"))
    for dow in range(5, 7):
        days.append(LoginHoursDay(day_of_week=dow, closed=True, start_time=None, end_time=None))
    return days


@router.get("/policy", response_model=PolicyOut)
async def get_policy(
    role: str = Query(..., description="handlowiec | prawnik"),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyOut:
    _validate_role(role)
    org_id = _target_org_id(actor)
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacja nie znaleziona")
    out = await _build_policy_out(db, org_id, role)
    await db.commit()  # _build may seed missing rows
    return out


@router.put("/policy", response_model=PolicyOut)
async def update_policy(
    body: PolicyUpdateIn,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PolicyOut:
    _validate_role(body.role)
    org_id = _target_org_id(actor)
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacja nie znaleziona")

    pol = await _get_or_seed_role_policy(db, org_id, body.role)
    pol.login_hours_enabled = body.login_hours_enabled
    pol.daily_search_limit_enabled = body.daily_search_limit_enabled
    pol.daily_search_limit = body.daily_search_limit

    # Replace all 7 day rows for this role — simpler than diffing; volume is tiny.
    await db.execute(
        delete(OrganizationLoginHours).where(
            OrganizationLoginHours.organization_id == org_id,
            OrganizationLoginHours.role == body.role,
        )
    )
    for d in body.days:
        db.add(
            OrganizationLoginHours(
                organization_id=org_id,
                role=body.role,
                day_of_week=d.day_of_week,
                closed=d.closed,
                start_time=_time.fromisoformat(d.start_time + ":00") if d.start_time else None,
                end_time=_time.fromisoformat(d.end_time + ":00") if d.end_time else None,
            )
        )

    await db.commit()
    return await _build_policy_out(db, org_id, body.role)
