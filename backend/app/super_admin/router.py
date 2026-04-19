"""Super-admin endpoints — organizations, admins, global audit view.

Distinct from ``/api/admin`` because super_admin lives outside any
organization (organization_id is None) and operates across all of them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_super_admin
from app.auth.password import hash_password
from app.db.engine import get_db
from app.db.models import ActivityLog, Organization, User

from .schemas import (
    AdminOut,
    CreateAdminIn,
    CreateOrganizationIn,
    GlobalActivityPage,
    GlobalActivityRow,
    OrganizationOut,
)

router = APIRouter()


@router.get("/organizations", response_model=list[OrganizationOut])
async def list_organizations(
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[OrganizationOut]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    rows = await db.execute(select(Organization).order_by(Organization.created_at.desc()))
    orgs = rows.scalars().all()
    if not orgs:
        return []

    ids = [o.id for o in orgs]
    user_counts_q = await db.execute(
        select(User.organization_id, func.count(User.id))
        .where(User.organization_id.in_(ids))
        .group_by(User.organization_id)
    )
    user_counts = {oid: int(cnt) for oid, cnt in user_counts_q.all()}

    activity_q = await db.execute(
        select(ActivityLog.organization_id, func.count(ActivityLog.id))
        .where(
            and_(
                ActivityLog.organization_id.in_(ids),
                ActivityLog.created_at >= cutoff,
            )
        )
        .group_by(ActivityLog.organization_id)
    )
    activity_counts = {oid: int(cnt) for oid, cnt in activity_q.all()}

    return [
        OrganizationOut(
            id=str(o.id),
            name=o.name,
            slug=o.slug,
            created_at=o.created_at.isoformat(),
            user_count=user_counts.get(o.id, 0),
            activity_count_30d=activity_counts.get(o.id, 0),
        )
        for o in orgs
    ]


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
async def create_organization(
    body: CreateOrganizationIn,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> OrganizationOut:
    existing = await db.execute(select(Organization).where(Organization.slug == body.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Slug jest już zajęty")
    org = Organization(name=body.name, slug=body.slug, created_by_user_id=actor.id)
    db.add(org)
    await db.commit()
    await db.refresh(org)
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        created_at=org.created_at.isoformat(),
        user_count=0,
        activity_count_30d=0,
    )


@router.delete("/organizations/{organization_id}")
async def delete_organization(
    organization_id: uuid.UUID,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    org = (
        await db.execute(select(Organization).where(Organization.id == organization_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacja nie znaleziona")
    member_count = (
        await db.execute(
            select(func.count()).select_from(User).where(User.organization_id == organization_id)
        )
    ).scalar_one()
    if member_count:
        raise HTTPException(
            status_code=400,
            detail="Organizacja ma członków — najpierw ich usuń lub przenieś",
        )
    await db.delete(org)
    await db.commit()
    return {"ok": True}


@router.get("/admins", response_model=list[AdminOut])
async def list_admins(
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminOut]:
    rows = await db.execute(
        select(User, Organization)
        .join(Organization, User.organization_id == Organization.id, isouter=True)
        .where(User.role == "admin")
        .order_by(User.created_at.desc())
    )
    return [
        AdminOut(
            id=str(u.id),
            email=u.email,
            display_name=u.display_name,
            is_active=u.is_active,
            organization_id=str(u.organization_id) if u.organization_id else None,
            organization_name=org.name if org else None,
            created_at=u.created_at.isoformat(),
        )
        for u, org in rows.all()
    ]


@router.post("/admins", response_model=AdminOut, status_code=201)
async def create_admin(
    body: CreateAdminIn,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminOut:
    org_id = uuid.UUID(body.organization_id)
    org = (
        await db.execute(select(Organization).where(Organization.id == org_id))
    ).scalar_one_or_none()
    if org is None:
        raise HTTPException(status_code=404, detail="Organizacja nie znaleziona")

    existing = await db.execute(select(User).where(User.email == body.email.lower()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Użytkownik z tym emailem już istnieje")

    new_admin = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
        role="admin",
        organization_id=org_id,
        invited_by_user_id=actor.id,
    )
    db.add(new_admin)
    await db.commit()
    await db.refresh(new_admin)

    return AdminOut(
        id=str(new_admin.id),
        email=new_admin.email,
        display_name=new_admin.display_name,
        is_active=new_admin.is_active,
        organization_id=str(new_admin.organization_id),
        organization_name=org.name,
        created_at=new_admin.created_at.isoformat(),
    )


@router.delete("/admins/{user_id}")
async def remove_admin(
    user_id: uuid.UUID,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    if target.role != "admin":
        raise HTTPException(status_code=400, detail="Cel nie jest adminem")
    target.is_active = False
    await db.commit()
    return {"ok": True}


@router.put("/admins/{user_id}/password")
async def set_admin_password(
    user_id: uuid.UUID,
    body: dict,
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    target = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="Użytkownik nie znaleziony")
    if target.role != "admin":
        raise HTTPException(status_code=400, detail="Cel nie jest adminem")
    password = body.get("password", "")
    from app.auth.password import validate_password

    errors = validate_password(password)
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))
    target.password_hash = hash_password(password)
    await db.commit()
    return {"ok": True}


@router.get("/activity", response_model=GlobalActivityPage)
async def global_activity(
    actor: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
    organization_id: uuid.UUID | None = Query(default=None),
    user_id: uuid.UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> GlobalActivityPage:
    where = []
    if organization_id is not None:
        where.append(ActivityLog.organization_id == organization_id)
    if user_id is not None:
        where.append(ActivityLog.user_id == user_id)

    total_q = select(func.count()).select_from(ActivityLog)
    if where:
        total_q = total_q.where(*where)
    total = (await db.execute(total_q)).scalar_one()

    base = (
        select(ActivityLog, User, Organization)
        .join(User, ActivityLog.user_id == User.id)
        .join(Organization, ActivityLog.organization_id == Organization.id, isouter=True)
        .order_by(ActivityLog.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    if where:
        base = base.where(*where)
    rows = await db.execute(base)

    items = [
        GlobalActivityRow(
            id=str(a.id),
            user_id=str(u.id),
            user_email=u.email,
            organization_id=str(o.id) if o else None,
            organization_name=o.name if o else None,
            action_type=a.action_type,
            target_id=a.target_id,
            query_text=a.query_text,
            ip_address=str(a.ip_address) if a.ip_address is not None else None,
            created_at=a.created_at.isoformat(),
        )
        for a, u, o in rows.all()
    ]

    return GlobalActivityPage(items=items, total=int(total))
