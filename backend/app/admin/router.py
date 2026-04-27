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
from app.db.models import (
    RESTRICTABLE_ROLES,
    ActivityLog,
    Organization,
    RestrictedField,
    SearchHistory,
    User,
)
from app.permissions.fields import RESTRICTABLE_FIELDS

from .schemas import (
    ActivityOut,
    ActivityPage,
    CreateUserIn,
    FieldOut,
    OrgStatsOut,
    RestrictionsResponse,
    RestrictionsUpdateIn,
    TopPlotOut,
    UpdateUserIn,
    UserOut,
    UserStatsOut,
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
        role=body.role,
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
    if target.role not in RESTRICTABLE_ROLES:
        raise HTTPException(status_code=400, detail="Można dezaktywować tylko zwykłych użytkowników")
    target.is_active = False
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: uuid.UUID,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    _ensure_same_org(actor, target)
    if target.role not in RESTRICTABLE_ROLES:
        raise HTTPException(status_code=400, detail="Można aktywować tylko zwykłych użytkowników")
    target.is_active = True
    await db.commit()
    return {"ok": True}


@router.patch("/users/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UpdateUserIn,
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    _ensure_same_org(actor, target)
    if target.role not in RESTRICTABLE_ROLES:
        raise HTTPException(
            status_code=400, detail="Można edytować tylko handlowców i prawników"
        )

    if body.email is not None and body.email != target.email:
        clash = await db.execute(
            select(User.id).where(User.email == body.email, User.id != target.id)
        )
        if clash.scalar_one_or_none():
            raise HTTPException(
                status_code=409, detail="Inny użytkownik ma już ten email"
            )
        target.email = body.email
    if body.display_name is not None:
        target.display_name = body.display_name
    if body.role is not None:
        target.role = body.role

    await db.commit()
    await db.refresh(target)
    return UserOut(
        id=str(target.id),
        email=target.email,
        display_name=target.display_name,
        is_active=target.is_active,
        role=target.role,
        organization_id=str(target.organization_id) if target.organization_id else None,
        created_at=target.created_at.isoformat(),
        last_active_at=None,
        search_count_7d=0,
    )


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
    if target.role not in RESTRICTABLE_ROLES:
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
        .where(User.organization_id == org_id, User.role.in_(RESTRICTABLE_ROLES))
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


def _validate_role(role: str) -> str:
    if role not in RESTRICTABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Nieznana rola: {role} (dozwolone: {', '.join(RESTRICTABLE_ROLES)})",
        )
    return role


@router.get("/restrictions", response_model=RestrictionsResponse)
async def list_restrictions(
    role: str = Query(..., description="handlowiec | prawnik"),
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> RestrictionsResponse:
    _validate_role(role)
    org_id = _target_org(actor)
    rows = await db.execute(
        select(RestrictedField.field_key).where(
            RestrictedField.organization_id == org_id,
            RestrictedField.role == role,
        )
    )
    hidden = {r[0] for r in rows}
    fields = [
        FieldOut(
            key=key,
            label=spec["label"],
            description=spec["description"],
            group=spec["group"],
            is_restricted=key in hidden,
        )
        for key, spec in RESTRICTABLE_FIELDS.items()
    ]
    return RestrictionsResponse(role=role, fields=fields)  # type: ignore[arg-type]


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
                RestrictedField.role == body.role,
                RestrictedField.field_key.in_(to_remove),
            )
        )
    if to_add:
        # Idempotent insert — fetch existing then add only the new ones.
        existing_rows = await db.execute(
            select(RestrictedField.field_key).where(
                RestrictedField.organization_id == org_id,
                RestrictedField.role == body.role,
                RestrictedField.field_key.in_(to_add),
            )
        )
        already = {r[0] for r in existing_rows}
        for key in to_add:
            if key not in already:
                db.add(
                    RestrictedField(
                        organization_id=org_id, role=body.role, field_key=key
                    )
                )

    await db.commit()
    return await list_restrictions(role=body.role, actor=actor, db=db)


@router.get("/stats", response_model=OrgStatsOut)
async def org_stats(
    actor: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> OrgStatsOut:
    """Aggregate search statistics for the admin's organization."""
    org_id = _target_org(actor)

    # Check if stats are enabled for this org
    org = (await db.execute(select(Organization).where(Organization.id == org_id))).scalar_one_or_none()
    if org is None or not org.stats_enabled:
        raise HTTPException(status_code=403, detail="Statystyki nie sa wlaczone dla tej organizacji")

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Get org user ids
    user_rows = await db.execute(
        select(User.id, User.display_name, User.email)
        .where(User.organization_id == org_id)
    )
    org_users = {uid: (name, email) for uid, name, email in user_rows.all()}
    if not org_users:
        return OrgStatsOut(
            total_searches_today=0,
            total_searches_week=0,
            total_searches_month=0,
            users=[],
            top_plots=[],
        )

    user_ids = list(org_users.keys())

    # Total searches by period
    counts = await db.execute(
        select(
            func.count().filter(SearchHistory.created_at >= today_start),
            func.count().filter(SearchHistory.created_at >= week_ago),
            func.count().filter(SearchHistory.created_at >= month_ago),
        ).where(SearchHistory.user_id.in_(user_ids))
    )
    today_count, week_count, month_count = counts.one()

    # Per-user breakdown
    per_user = await db.execute(
        select(
            SearchHistory.user_id,
            func.count().filter(SearchHistory.created_at >= today_start),
            func.count().filter(SearchHistory.created_at >= week_ago),
            func.count().filter(SearchHistory.created_at >= month_ago),
        )
        .where(SearchHistory.user_id.in_(user_ids))
        .group_by(SearchHistory.user_id)
    )
    user_stats_map: dict[uuid.UUID, tuple[int, int, int]] = {}
    for uid, d, w, m in per_user.all():
        user_stats_map[uid] = (int(d), int(w), int(m))

    user_stats = [
        UserStatsOut(
            user_id=str(uid),
            display_name=org_users[uid][0],
            email=org_users[uid][1],
            searches_today=user_stats_map.get(uid, (0, 0, 0))[0],
            searches_week=user_stats_map.get(uid, (0, 0, 0))[1],
            searches_month=user_stats_map.get(uid, (0, 0, 0))[2],
        )
        for uid in org_users
    ]
    user_stats.sort(key=lambda u: u.searches_month, reverse=True)

    # Top searched plots (last 30 days)
    top_q = await db.execute(
        select(
            SearchHistory.query_text,
            func.count().label("cnt"),
        )
        .where(
            SearchHistory.user_id.in_(user_ids),
            SearchHistory.created_at >= month_ago,
        )
        .group_by(SearchHistory.query_text)
        .order_by(func.count().desc())
        .limit(20)
    )
    top_plots = [
        TopPlotOut(query_text=qt, count=int(cnt))
        for qt, cnt in top_q.all()
    ]

    return OrgStatsOut(
        total_searches_today=int(today_count),
        total_searches_week=int(week_count),
        total_searches_month=int(month_count),
        users=user_stats,
        top_plots=top_plots,
    )
