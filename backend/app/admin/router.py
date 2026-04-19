"""Admin endpoints — manage org members and field restrictions.

All endpoints require role admin or super_admin. Admins are scoped to
their own organization; super_admins can act on any user via these
endpoints (their organization_id is None — see ``_target_org``).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.password import hash_password
from app.db.engine import get_db
from app.db.models import ActivityLog, RestrictedField, User
from app.permissions.fields import RESTRICTABLE_FIELDS

from .schemas import (
    ActivityOut,
    ActivityPage,
    CreateUserIn,
    FieldOut,
    RestrictionsResponse,
    RestrictionsUpdateIn,
    UserOut,
)

router = APIRouter()


def _target_org(actor: User) -> uuid.UUID:
    """Return the org an admin acts on. super_admin acting in /api/admin must
    pick an org explicitly via /api/super-admin endpoints; reaching here
    without one is a programmer error so we fail loudly.
    """
    if actor.organization_id is None:
        raise HTTPException(
            status_code=400,
            detail="Operacja wymaga organizacji — użyj /api/super-admin",
        )
    return actor.organization_id


def _ensure_same_org(actor: User, target: User) -> None:
    if actor.role == "super_admin":
        return
    if target.organization_id != actor.organization_id:
        raise HTTPException(status_code=403, detail="Brak uprawnień do tego użytkownika")


@router.post("/users", response_model=UserOut, status_code=201)
async def create_user(
    body: CreateUserIn,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    org_id = _target_org(actor)

    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Użytkownik z tym emailem już istnieje")

    new_user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="user",
        organization_id=org_id,
        invited_by_user_id=actor.id,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return UserOut(
        id=str(new_user.id),
        email=new_user.email,
        display_name=new_user.display_name,
        is_active=new_user.is_active,
        role=new_user.role,
        organization_id=str(new_user.organization_id) if new_user.organization_id else None,
        created_at=new_user.created_at.isoformat(),
        last_active_at=None,
        search_count_7d=0,
    )


@router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    _ensure_same_org(actor, target)
    if target.role != "user":
        raise HTTPException(status_code=400, detail="Można dezaktywować tylko zwykłych użytkowników")
    target.is_active = False
    await db.commit()
    return {"ok": True}


@router.put("/users/{user_id}/password")
async def set_user_password(
    user_id: uuid.UUID,
    body: dict,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    _ensure_same_org(actor, target)
    if target.role != "user":
        raise HTTPException(status_code=400, detail="Można zmienić hasło tylko zwykłym użytkownikom")
    password = body.get("password", "")
    from app.auth.password import validate_password

    errors = validate_password(password)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    target.password_hash = hash_password(password)
    await db.commit()
    return {"ok": True}


@router.get("/users", response_model=list[UserOut])
async def list_users(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[UserOut]:
    org_id = _target_org(actor)
    rows = await db.execute(
        select(User)
        .where(User.organization_id == org_id, User.role == "user")
        .order_by(User.created_at.desc())
    )
    users = rows.scalars().all()

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    counts: dict[uuid.UUID, int] = {}
    last_active: dict[uuid.UUID, datetime] = {}
    if users:
        ids = [u.id for u in users]
        agg = await db.execute(
            select(
                ActivityLog.user_id,
                func.count(ActivityLog.id).filter(
                    and_(
                        ActivityLog.action_type == "search",
                        ActivityLog.created_at >= cutoff,
                    )
                ),
                func.max(ActivityLog.created_at),
            )
            .where(ActivityLog.user_id.in_(ids))
            .group_by(ActivityLog.user_id)
        )
        for uid, cnt, last in agg.all():
            counts[uid] = int(cnt or 0)
            last_active[uid] = last

    return [
        UserOut(
            id=str(u.id),
            email=u.email,
            display_name=u.display_name,
            is_active=u.is_active,
            role=u.role,
            organization_id=str(u.organization_id) if u.organization_id else None,
            created_at=u.created_at.isoformat(),
            last_active_at=last_active[u.id].isoformat() if u.id in last_active and last_active[u.id] else None,
            search_count_7d=counts.get(u.id, 0),
        )
        for u in users
    ]


@router.get("/users/{user_id}/activity", response_model=ActivityPage)
async def user_activity(
    user_id: uuid.UUID,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> ActivityPage:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    _ensure_same_org(actor, target)

    total = (
        await db.execute(
            select(func.count()).select_from(ActivityLog).where(ActivityLog.user_id == user_id)
        )
    ).scalar_one()

    rows = await db.execute(
        select(ActivityLog)
        .where(ActivityLog.user_id == user_id)
        .order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    items = rows.scalars().all()

    return ActivityPage(
        items=[
            ActivityOut(
                id=str(a.id),
                action_type=a.action_type,
                target_id=a.target_id,
                query_text=a.query_text,
                ip_address=str(a.ip_address) if a.ip_address is not None else None,
                user_agent=a.user_agent,
                created_at=a.created_at.isoformat(),
            )
            for a in items
        ],
        total=int(total),
    )


@router.get("/restrictions", response_model=RestrictionsResponse)
async def list_restrictions(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RestrictionsResponse:
    org_id = _target_org(actor)
    rows = await db.execute(
        select(RestrictedField.field_key).where(RestrictedField.organization_id == org_id)
    )
    hidden = {r[0] for r in rows}
    fields = [
        FieldOut(
            key=key,
            label=spec["label"],
            description=spec["description"],
            is_restricted=key in hidden,
        )
        for key, spec in RESTRICTABLE_FIELDS.items()
    ]
    return RestrictionsResponse(fields=fields)


@router.put("/restrictions", response_model=RestrictionsResponse)
async def update_restrictions(
    body: RestrictionsUpdateIn,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RestrictionsResponse:
    org_id = _target_org(actor)

    unknown = [k for k in body.updates if k not in RESTRICTABLE_FIELDS]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Nieznane klucze pól: {', '.join(unknown)}",
        )

    to_add = [k for k, v in body.updates.items() if v]
    to_remove = [k for k, v in body.updates.items() if not v]

    if to_remove:
        await db.execute(
            delete(RestrictedField).where(
                RestrictedField.organization_id == org_id,
                RestrictedField.field_key.in_(to_remove),
            )
        )
    if to_add:
        # Idempotent insert — fetch existing then add only the new ones.
        existing_rows = await db.execute(
            select(RestrictedField.field_key).where(
                RestrictedField.organization_id == org_id,
                RestrictedField.field_key.in_(to_add),
            )
        )
        already = {r[0] for r in existing_rows}
        for key in to_add:
            if key not in already:
                db.add(RestrictedField(organization_id=org_id, field_key=key))

    await db.commit()
    return await list_restrictions(actor=actor, db=db)
