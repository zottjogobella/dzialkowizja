"""Login-hours enforcement.

Called from ``/api/auth/login`` (before issuing a session) and from
``require_auth`` (on every authenticated request — a user logged in at
17:50 is kicked out at 18:01 on their next API call). role=user only;
admins and super_admins bypass.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Organization, OrganizationLoginHours, User
from app.utils.time import now_warsaw


async def enforce_login_hours(user: User, db: AsyncSession) -> None:
    """Raise HTTPException(403, code=outside_hours) when the user is outside
    their org's configured window. Silent return otherwise (including for
    admins, super_admins, users with no org, or orgs with the feature off).
    """
    if user.role != "user":
        return
    if user.organization_id is None:
        return

    org = (
        await db.execute(select(Organization).where(Organization.id == user.organization_id))
    ).scalar_one_or_none()
    if org is None or not org.login_hours_enabled:
        return

    now = now_warsaw()
    # Python weekday(): Mon=0, Sun=6 — matches our schema.
    dow = now.weekday()

    schedule = (
        await db.execute(
            select(OrganizationLoginHours).where(
                OrganizationLoginHours.organization_id == org.id,
                OrganizationLoginHours.day_of_week == dow,
            )
        )
    ).scalar_one_or_none()

    if schedule is None:
        # Missing day row — treat as closed, loudly. Should never happen
        # because create_organization seeds all 7 rows; if it does, the
        # user shouldn't sneak through.
        raise HTTPException(
            status_code=403,
            detail={
                "code": "outside_hours",
                "message": "Brak skonfigurowanych godzin logowania dla tego dnia.",
                "schedule": {"day_of_week": dow, "closed": True},
            },
        )

    if schedule.closed:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "outside_hours",
                "message": "Logowanie niedostępne w tym dniu.",
                "schedule": {"day_of_week": dow, "closed": True},
            },
        )

    current_time = now.time()
    if not (schedule.start_time <= current_time < schedule.end_time):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "outside_hours",
                "message": (
                    f"Poza godzinami pracy "
                    f"({schedule.start_time.strftime('%H:%M')}–"
                    f"{schedule.end_time.strftime('%H:%M')})."
                ),
                "schedule": {
                    "day_of_week": dow,
                    "closed": False,
                    "start_time": schedule.start_time.strftime("%H:%M"),
                    "end_time": schedule.end_time.strftime("%H:%M"),
                },
            },
        )
