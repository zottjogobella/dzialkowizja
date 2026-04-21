# Org Access Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-organization login hours + daily search limit so org admins can restrict when users access the app and how many searches each user runs per day.

**Architecture:** Three new columns on `organizations` + a new `organization_login_hours` table (7 rows per org). A plain async `enforce_login_hours(user, db)` runs inside `require_auth` (kicks out users mid-session) and inside `/api/auth/login` (blocks login). A FastAPI `enforce_daily_search_limit` dep on `/api/search` counts `SearchHistory` rows since midnight Warsaw. All time comparisons use `zoneinfo.ZoneInfo("Europe/Warsaw")` so DST is handled and client clocks cannot bypass. Admin UI gets a new "Limity" tab at `/admin/policy`. The policy applies only to `role=user` — admins and super_admins remain exempt, matching `rate_limit_search` semantics.

**Tech Stack:** FastAPI, SQLAlchemy async, asyncpg, Alembic, Svelte 5 (runes), SvelteKit, TypeScript, Tailwind. Python 3.12 `zoneinfo`. Redis-backed rate limiter already exists and stays as-is.

**Verification strategy:** This repo has no pytest suite. Each backend task ends with a `curl` / `docker compose` verification. Each frontend task ends with `npm run check` + a manual browser smoke. The stack boots via `docker compose up -d`; alembic runs automatically.

**Spec:** `docs/superpowers/specs/2026-04-21-org-access-policy-design.md`

---

## File Structure

Backend new:
- `backend/alembic/versions/009_org_access_policy.py` — migration with backfill
- `backend/app/utils/__init__.py`, `backend/app/utils/time.py` — `WARSAW` + helpers
- `backend/app/policy/__init__.py`
- `backend/app/policy/login_hours.py` — pure logic + `enforce_login_hours`
- `backend/app/policy/daily_limit.py` — FastAPI dep + SQL counter
- `backend/app/policy/router.py` — admin `GET/PUT /api/admin/policy`
- `backend/app/policy/schemas.py` — Pydantic input/output models
- `frontend/src/routes/admin/policy/+page.svelte` — UI

Backend modified:
- `backend/app/db/models.py` — new `OrganizationLoginHours`, three org columns
- `backend/app/auth/router.py` — call `enforce_login_hours` on login
- `backend/app/auth/dependencies.py` — `require_auth` calls `enforce_login_hours`
- `backend/app/search/router.py` — add daily-limit dep to `/api/search`
- `backend/app/super_admin/router.py` — seed 7 day rows on org create
- `backend/app/main.py` or wherever admin is included — include new policy router

Frontend modified:
- `frontend/src/lib/api/client.ts` — parse error body, handle two new codes
- `frontend/src/routes/auth/login/+page.svelte` — show flash from localStorage
- `frontend/src/routes/admin/+layout.svelte` — nav entry

---

## Task 1: Alembic migration — schema + backfill

**Files:**
- Create: `backend/alembic/versions/009_org_access_policy.py`

- [ ] **Step 1: Write the migration**

Create `backend/alembic/versions/009_org_access_policy.py`:

```python
"""Add login-hours schedule and daily search limit per organization.

Adds three columns to ``organizations`` controlling the two features, plus
a new ``organization_login_hours`` table carrying 7 rows per org (one per
day of week). Backfills every existing organization with the product
default: Mon-Fri 09:00-18:00 open, Sat-Sun closed, login-hours enabled,
daily search limit enabled at 40.
"""

from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column(
            "login_hours_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "daily_search_limit_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "organizations",
        sa.Column(
            "daily_search_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("40"),
        ),
    )

    op.create_table(
        "organization_login_hours",
        sa.Column(
            "organization_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("day_of_week", sa.SmallInteger(), primary_key=True),
        sa.Column(
            "closed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("start_time", sa.Time(), nullable=True),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.CheckConstraint(
            "day_of_week >= 0 AND day_of_week <= 6",
            name="ck_login_hours_dow_range",
        ),
        sa.CheckConstraint(
            "closed OR (start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
            name="ck_login_hours_window",
        ),
    )

    # Backfill every existing org with Mon-Fri 09:00-18:00, Sat-Sun closed.
    op.execute(
        """
        INSERT INTO organization_login_hours (organization_id, day_of_week, closed, start_time, end_time)
        SELECT o.id, dow, FALSE, TIME '09:00', TIME '18:00'
        FROM organizations o
        CROSS JOIN generate_series(0, 4) AS dow
        """
    )
    op.execute(
        """
        INSERT INTO organization_login_hours (organization_id, day_of_week, closed, start_time, end_time)
        SELECT o.id, dow, TRUE, NULL, NULL
        FROM organizations o
        CROSS JOIN generate_series(5, 6) AS dow
        """
    )


def downgrade() -> None:
    op.drop_table("organization_login_hours")
    op.drop_column("organizations", "daily_search_limit")
    op.drop_column("organizations", "daily_search_limit_enabled")
    op.drop_column("organizations", "login_hours_enabled")
```

- [ ] **Step 2: Run the migration**

```bash
docker compose up -d appdb
docker compose run --rm backend alembic upgrade head
```

Expected: output ends with `Running upgrade 008 -> 009, Add login-hours schedule...`.

- [ ] **Step 3: Verify the schema**

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c "\d organizations" | grep -E "login_hours|daily_search"
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c "\d organization_login_hours"
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c "SELECT day_of_week, closed, start_time, end_time FROM organization_login_hours ORDER BY organization_id, day_of_week LIMIT 14;"
```

Expected:
- Three new `organizations` columns listed.
- `organization_login_hours` table shown with the PK, FK and two check constraints.
- Per-org rows: days 0-4 `(f, 09:00:00, 18:00:00)`, days 5-6 `(t, NULL, NULL)`.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/009_org_access_policy.py
git commit -m "Add migration for per-org login hours and daily search limit"
```

---

## Task 2: SQLAlchemy model additions

**Files:**
- Modify: `backend/app/db/models.py`

- [ ] **Step 1: Add new columns to `Organization`**

In `backend/app/db/models.py`, locate the `Organization` class. After the existing `stats_enabled` line, add:

```python
    login_hours_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    daily_search_limit_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    daily_search_limit: Mapped[int] = mapped_column(Integer, default=40, server_default="40")
```

Then, inside `Organization`, add a relationship for the schedule rows (below `restricted_fields`):

```python
    login_hours: Mapped[list[OrganizationLoginHours]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
```

- [ ] **Step 2: Add the `OrganizationLoginHours` model**

At the bottom of `backend/app/db/models.py`, add:

```python
class OrganizationLoginHours(Base):
    """Per-day login window for an organization.

    Exactly 7 rows per org (day_of_week 0..6, Mon=0). ``closed=TRUE`` means
    no access on that day; otherwise ``start_time`` and ``end_time`` define
    an inclusive-start, exclusive-end window interpreted in Europe/Warsaw.
    """

    __tablename__ = "organization_login_hours"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="login_hours")
```

- [ ] **Step 2a: Update imports in `models.py`**

At the top of `backend/app/db/models.py`, change the existing imports so both `time` (the type) and `SmallInteger` are available:

```python
from datetime import datetime, time
```

And in the SQLAlchemy import:

```python
from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, LargeBinary, Numeric, SmallInteger, String, Text, Time, func
```

- [ ] **Step 3: Verify the app still imports**

```bash
docker compose run --rm backend python -c "from app.db.models import OrganizationLoginHours, Organization; print(Organization.__table__.columns.keys())"
```

Expected: output includes `login_hours_enabled`, `daily_search_limit_enabled`, `daily_search_limit`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/db/models.py
git commit -m "Add OrganizationLoginHours model and policy columns"
```

---

## Task 3: Timezone helper

**Files:**
- Create: `backend/app/utils/__init__.py`, `backend/app/utils/time.py`

- [ ] **Step 1: Create the package init**

`backend/app/utils/__init__.py`:

```python
```

(Empty file — just marks the package.)

- [ ] **Step 2: Create the helper module**

`backend/app/utils/time.py`:

```python
"""Europe/Warsaw time helpers.

All org access-policy checks happen in Warsaw local time so that admin
schedules configured as "09:00-18:00" always mean what Polish users
expect, with DST handled by the zoneinfo database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

WARSAW = ZoneInfo("Europe/Warsaw")


def now_warsaw() -> datetime:
    """Return current time as a timezone-aware datetime in Europe/Warsaw."""
    return datetime.now(WARSAW)


def warsaw_midnight_utc() -> datetime:
    """Start of 'today' in Warsaw, expressed as a UTC-aware datetime.

    Useful for comparing against ``created_at`` columns (stored in UTC with
    tz). DST-aware: during spring-forward the local day still starts at
    00:00, which maps to a single unambiguous UTC instant.
    """
    warsaw_midnight = now_warsaw().replace(hour=0, minute=0, second=0, microsecond=0)
    return warsaw_midnight.astimezone(timezone.utc)
```

- [ ] **Step 3: Quick import sanity check**

```bash
docker compose run --rm backend python -c "from app.utils.time import WARSAW, now_warsaw, warsaw_midnight_utc; print(now_warsaw().isoformat()); print(warsaw_midnight_utc().isoformat())"
```

Expected: two ISO timestamps, the Warsaw one offset `+01:00` or `+02:00` depending on DST, the UTC one with `+00:00`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/utils/__init__.py backend/app/utils/time.py
git commit -m "Add Europe/Warsaw time helpers for access policy"
```

---

## Task 4: Login-hours enforcement (policy module)

**Files:**
- Create: `backend/app/policy/__init__.py`, `backend/app/policy/login_hours.py`

- [ ] **Step 1: Create the package init**

`backend/app/policy/__init__.py`:

```python
```

(Empty file.)

- [ ] **Step 2: Create the login-hours module**

`backend/app/policy/login_hours.py`:

```python
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
```

- [ ] **Step 3: Smoke test — import and call**

```bash
docker compose run --rm backend python -c "from app.policy.login_hours import enforce_login_hours; print(enforce_login_hours)"
```

Expected: prints `<function enforce_login_hours at 0x...>` (no ImportError).

- [ ] **Step 4: Commit**

```bash
git add backend/app/policy/__init__.py backend/app/policy/login_hours.py
git commit -m "Add enforce_login_hours policy check"
```

---

## Task 5: Wire login-hours into login endpoint

**Files:**
- Modify: `backend/app/auth/router.py`

- [ ] **Step 1: Add the call after is_active check**

In `backend/app/auth/router.py::login`, replace the block:

```python
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Konto jest nieaktywne")

    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.client.host if request.client else None)
```

With:

```python
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Konto jest nieaktywne")

    from app.policy.login_hours import enforce_login_hours
    await enforce_login_hours(user, db)

    ip = request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or (request.client.host if request.client else None)
```

(Import is inline to keep the current module's import order; move to top later if preferred.)

- [ ] **Step 2: Verify login still works at an in-hours time**

```bash
docker compose up -d
curl -i -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<some test user email>","password":"<their password>"}'
```

Expected during 09:00-18:00 Mon-Fri Warsaw: HTTP 200 with user JSON.
Expected outside that window: HTTP 403 with body `{"detail":{"code":"outside_hours",...}}`.

- [ ] **Step 3: Manually verify the blocked path**

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "UPDATE organization_login_hours SET closed=TRUE, start_time=NULL, end_time=NULL WHERE day_of_week=(EXTRACT(ISODOW FROM now() AT TIME ZONE 'Europe/Warsaw')::int - 1);"

curl -i -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<same test user>","password":"<their password>"}'
```

Expected: HTTP 403, body contains `"code":"outside_hours"`.

Then restore:

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "UPDATE organization_login_hours SET closed=FALSE, start_time='09:00', end_time='18:00' WHERE day_of_week=(EXTRACT(ISODOW FROM now() AT TIME ZONE 'Europe/Warsaw')::int - 1);"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/auth/router.py
git commit -m "Block login outside configured org hours"
```

---

## Task 6: Wire login-hours into require_auth

**Files:**
- Modify: `backend/app/auth/dependencies.py`

- [ ] **Step 1: Update `require_auth` to call the policy check**

Replace the existing `require_auth` in `backend/app/auth/dependencies.py`:

```python
async def require_auth(
    user: User | None = Depends(get_current_user),
) -> User:
    """Raises 401 if not authenticated."""
    if user is None:
        raise HTTPException(status_code=401, detail="Nie jesteś zalogowany")
    return user
```

With:

```python
async def require_auth(
    user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Raises 401 if not authenticated, 403 outside_hours if the org's
    login-hours policy blocks this request."""
    if user is None:
        raise HTTPException(status_code=401, detail="Nie jesteś zalogowany")
    from app.policy.login_hours import enforce_login_hours
    await enforce_login_hours(user, db)
    return user
```

- [ ] **Step 2: Verify existing authenticated endpoints still work**

```bash
# Log in, save cookie jar:
curl -i -c /tmp/dz.cookies -X POST http://localhost:8000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"<user>","password":"<pass>"}'

# During in-hours, this must return 200:
curl -i -b /tmp/dz.cookies http://localhost:8000/api/auth/me
```

Expected: HTTP 200 with user JSON.

- [ ] **Step 3: Verify the kick-out path**

Log in normally (in-hours), then simulate the window closing:

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "UPDATE organization_login_hours SET closed=TRUE, start_time=NULL, end_time=NULL WHERE day_of_week=(EXTRACT(ISODOW FROM now() AT TIME ZONE 'Europe/Warsaw')::int - 1);"

curl -i -b /tmp/dz.cookies http://localhost:8000/api/auth/me
```

Expected: HTTP 403 with body `{"detail":{"code":"outside_hours",...}}`.

Restore:

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "UPDATE organization_login_hours SET closed=FALSE, start_time='09:00', end_time='18:00' WHERE day_of_week=(EXTRACT(ISODOW FROM now() AT TIME ZONE 'Europe/Warsaw')::int - 1);"
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/auth/dependencies.py
git commit -m "Enforce login hours on every authenticated request"
```

---

## Task 7: Daily search-limit dependency

**Files:**
- Create: `backend/app/policy/daily_limit.py`
- Modify: `backend/app/search/router.py`

- [ ] **Step 1: Create the dep module**

`backend/app/policy/daily_limit.py`:

```python
"""Daily per-user search-limit enforcement.

FastAPI dependency layered on ``/api/search`` alongside the existing
per-minute rate limiter. Counts rows in ``search_history`` written today
in Europe/Warsaw. role=user only; admins and super_admins bypass.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_auth
from app.db.engine import get_db
from app.db.models import Organization, SearchHistory, User
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
            .select_from(SearchHistory)
            .where(
                SearchHistory.user_id == user.id,
                SearchHistory.created_at >= today_utc,
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
```

Note: `SearchHistory` already ordered by `(user_id, created_at)` via its index — the count is cheap.

- [ ] **Step 2: Wire the dep into `/api/search`**

In `backend/app/search/router.py`, change the endpoint signature:

```python
@router.get("", response_model=list[SearchSuggestion])
async def search(
    request: Request,
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
    user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
    _rl: None = Depends(rate_limit_search),
) -> list[SearchSuggestion]:
```

To:

```python
from app.policy.daily_limit import enforce_daily_search_limit


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
```

- [ ] **Step 3: Verify the happy path**

```bash
curl -i -b /tmp/dz.cookies 'http://localhost:8000/api/search?q=wa&limit=3'
```

Expected: HTTP 200, JSON array.

- [ ] **Step 4: Verify the block path — set limit to 0**

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "UPDATE organizations SET daily_search_limit=0 WHERE id=(SELECT organization_id FROM users WHERE email='<test user>');"

curl -i -b /tmp/dz.cookies 'http://localhost:8000/api/search?q=wa&limit=3'
```

Expected: HTTP 429 with body `{"detail":{"code":"daily_limit_exceeded","limit":0,...}}`.

Restore:

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "UPDATE organizations SET daily_search_limit=40 WHERE id=(SELECT organization_id FROM users WHERE email='<test user>');"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/policy/daily_limit.py backend/app/search/router.py
git commit -m "Enforce per-user daily search limit via SearchHistory count"
```

---

## Task 8: Seed schedule rows on organization create

**Files:**
- Modify: `backend/app/super_admin/router.py`

- [ ] **Step 1: Extend `create_organization` to seed 7 day rows**

In `backend/app/super_admin/router.py`, find `create_organization`. Replace the body from `org = Organization(...)` through the `return OrganizationOut(...)` block with:

```python
    from datetime import time as _time

    from app.db.models import OrganizationLoginHours

    org = Organization(name=body.name, slug=body.slug, created_by_user_id=actor.id)
    db.add(org)
    await db.flush()  # need org.id for the child rows before commit

    # Default schedule: Mon-Fri 09:00-18:00 open, Sat-Sun closed.
    for dow in range(0, 5):
        db.add(
            OrganizationLoginHours(
                organization_id=org.id,
                day_of_week=dow,
                closed=False,
                start_time=_time(9, 0),
                end_time=_time(18, 0),
            )
        )
    for dow in range(5, 7):
        db.add(
            OrganizationLoginHours(
                organization_id=org.id,
                day_of_week=dow,
                closed=True,
                start_time=None,
                end_time=None,
            )
        )

    await db.commit()
    await db.refresh(org)
    return OrganizationOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        created_at=org.created_at.isoformat(),
        user_count=0,
        activity_count_30d=0,
        stats_enabled=org.stats_enabled,
    )
```

- [ ] **Step 2: Verify via super-admin endpoint**

Log in as a super_admin (steps 1-2 of Task 6 but with super_admin creds):

```bash
curl -i -b /tmp/dz.cookies -X POST http://localhost:8000/api/super-admin/organizations \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $(grep csrf /tmp/dz.cookies | awk '{print $7}')" \
  -d '{"name":"Test Org","slug":"test-org-001"}'

docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "SELECT day_of_week, closed, start_time, end_time FROM organization_login_hours WHERE organization_id=(SELECT id FROM organizations WHERE slug='test-org-001') ORDER BY day_of_week;"
```

Expected: 7 rows, days 0-4 `(f, 09:00, 18:00)`, days 5-6 `(t, NULL, NULL)`.

Clean up:

```bash
docker compose exec appdb psql -U dzialkowizja -d dzialkowizja -c \
  "DELETE FROM organizations WHERE slug='test-org-001';"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/super_admin/router.py
git commit -m "Seed default login hours when creating an organization"
```

---

## Task 9: Admin policy API — schemas + router

**Files:**
- Create: `backend/app/policy/schemas.py`, `backend/app/policy/router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Create Pydantic schemas**

`backend/app/policy/schemas.py`:

```python
"""Request/response shapes for the admin policy endpoints."""

from __future__ import annotations

from datetime import time

from pydantic import BaseModel, field_validator, model_validator


class LoginHoursDay(BaseModel):
    day_of_week: int  # 0=Mon .. 6=Sun
    closed: bool
    start_time: str | None = None  # "HH:MM"
    end_time: str | None = None  # "HH:MM"

    @field_validator("day_of_week")
    @classmethod
    def _dow_range(cls, v: int) -> int:
        if not (0 <= v <= 6):
            raise ValueError("day_of_week musi być w zakresie 0..6")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _format(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            time.fromisoformat(v if len(v) == 8 else v + ":00")
        except ValueError:
            raise ValueError("Nieprawidłowy format godziny, oczekiwano HH:MM")
        return v[:5]

    @model_validator(mode="after")
    def _window_valid(self) -> "LoginHoursDay":
        if self.closed:
            return self
        if self.start_time is None or self.end_time is None:
            raise ValueError("Otwarty dzień wymaga start_time i end_time")
        s = time.fromisoformat(self.start_time + ":00")
        e = time.fromisoformat(self.end_time + ":00")
        if not (e > s):
            raise ValueError("end_time musi być większe od start_time")
        return self


class PolicyOut(BaseModel):
    login_hours_enabled: bool
    daily_search_limit_enabled: bool
    daily_search_limit: int
    days: list[LoginHoursDay]


class PolicyUpdateIn(BaseModel):
    login_hours_enabled: bool
    daily_search_limit_enabled: bool
    daily_search_limit: int
    days: list[LoginHoursDay]

    @field_validator("daily_search_limit")
    @classmethod
    def _limit_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Limit musi być >= 1")
        return v

    @model_validator(mode="after")
    def _seven_unique_days(self) -> "PolicyUpdateIn":
        if len(self.days) != 7:
            raise ValueError("Wymagane dokładnie 7 wpisów dni tygodnia")
        if {d.day_of_week for d in self.days} != set(range(0, 7)):
            raise ValueError("Dni tygodnia muszą obejmować 0..6 bez duplikatów")
        return self
```

- [ ] **Step 2: Create the router**

`backend/app/policy/router.py`:

```python
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
```

- [ ] **Step 3: Mount the router under `/api/admin`**

In `backend/app/main.py`, find the imports block inside `create_app()` (starts with `from app.admin.router import ...`). Add this import next to `super_admin_router`:

```python
    from app.policy.router import router as policy_router
```

Then find the `app.include_router(admin_router, prefix="/api/admin", tags=["admin"])` line and add a sibling include directly after it:

```python
    app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
    app.include_router(policy_router, prefix="/api/admin", tags=["admin"])
    app.include_router(super_admin_router, prefix="/api/super-admin", tags=["super-admin"])
```

(Only the middle line is new — the surrounding lines are shown for context so you place it correctly.)

- [ ] **Step 4: Verify the endpoints**

As an org admin, log in (reuse cookie jar approach). Then:

```bash
curl -i -b /tmp/dz.cookies http://localhost:8000/api/admin/policy
```

Expected: 200 with the full policy shape.

```bash
CSRF=$(awk '/dzialkowizja_csrf/{print $7}' /tmp/dz.cookies)
curl -i -b /tmp/dz.cookies -X PUT http://localhost:8000/api/admin/policy \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $CSRF" \
  -d '{
    "login_hours_enabled": true,
    "daily_search_limit_enabled": true,
    "daily_search_limit": 50,
    "days": [
      {"day_of_week":0,"closed":false,"start_time":"09:00","end_time":"17:00"},
      {"day_of_week":1,"closed":false,"start_time":"09:00","end_time":"17:00"},
      {"day_of_week":2,"closed":false,"start_time":"09:00","end_time":"17:00"},
      {"day_of_week":3,"closed":false,"start_time":"09:00","end_time":"17:00"},
      {"day_of_week":4,"closed":false,"start_time":"09:00","end_time":"17:00"},
      {"day_of_week":5,"closed":true},
      {"day_of_week":6,"closed":true}
    ]
  }'
```

Expected: 200 with same payload echoed (daily_search_limit now 50, Friday closes at 17:00).

Restore defaults:

```bash
curl -b /tmp/dz.cookies -X PUT http://localhost:8000/api/admin/policy \
  -H 'Content-Type: application/json' \
  -H "X-CSRF-Token: $CSRF" \
  -d '{
    "login_hours_enabled": true,
    "daily_search_limit_enabled": true,
    "daily_search_limit": 40,
    "days": [
      {"day_of_week":0,"closed":false,"start_time":"09:00","end_time":"18:00"},
      {"day_of_week":1,"closed":false,"start_time":"09:00","end_time":"18:00"},
      {"day_of_week":2,"closed":false,"start_time":"09:00","end_time":"18:00"},
      {"day_of_week":3,"closed":false,"start_time":"09:00","end_time":"18:00"},
      {"day_of_week":4,"closed":false,"start_time":"09:00","end_time":"18:00"},
      {"day_of_week":5,"closed":true},
      {"day_of_week":6,"closed":true}
    ]
  }'
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/policy/schemas.py backend/app/policy/router.py backend/app/main.py
git commit -m "Add admin API for org access policy"
```

---

## Task 10: Frontend API client — parse error body, handle new codes

**Files:**
- Modify: `frontend/src/lib/api/client.ts`

- [ ] **Step 1: Rewrite `client.ts` to parse detail codes**

Replace the full contents of `frontend/src/lib/api/client.ts` with:

```typescript
export type ApiErrorDetail = {
	code?: string;
	message?: string;
	[key: string]: unknown;
};

export class ApiError extends Error {
	status: number;
	detail: ApiErrorDetail | string | null;
	constructor(res: Response, detail: ApiErrorDetail | string | null) {
		super(`API error: ${res.status}`);
		this.status = res.status;
		this.detail = detail;
	}
	get code(): string | undefined {
		if (this.detail && typeof this.detail === 'object' && 'code' in this.detail) {
			return (this.detail as ApiErrorDetail).code;
		}
		return undefined;
	}
}

function getCsrfToken(): string {
	if (typeof document === 'undefined') return '';
	return (
		document.cookie
			.split('; ')
			.find((c) => c.startsWith('dzialkowizja_csrf='))
			?.split('=')[1] ?? ''
	);
}

async function parseError(res: Response): Promise<ApiErrorDetail | string | null> {
	try {
		const data = await res.clone().json();
		if (data && typeof data === 'object' && 'detail' in data) {
			return (data as { detail: ApiErrorDetail | string }).detail;
		}
		return null;
	} catch {
		return null;
	}
}

function storeOutsideHoursFlash(detail: ApiErrorDetail | string | null) {
	if (typeof localStorage === 'undefined') return;
	const message =
		detail && typeof detail === 'object' && typeof detail.message === 'string'
			? detail.message
			: 'Logowanie poza godzinami pracy.';
	try {
		localStorage.setItem('dzialkowizja_login_flash', message);
	} catch {
		// storage full / disabled — ignore
	}
}

export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
	const res = await fetch(path, {
		...init,
		credentials: 'include',
		headers: {
			...(init?.headers as Record<string, string>)
		}
	});

	if (res.status === 401) {
		window.location.href = '/auth/login';
		throw new ApiError(res, await parseError(res));
	}

	if (res.status === 403) {
		const detail = await parseError(res);
		if (detail && typeof detail === 'object' && detail.code === 'outside_hours') {
			storeOutsideHoursFlash(detail);
			window.location.href = '/auth/login';
			throw new ApiError(res, detail);
		}
		// fall through — caller inspects and renders normally.
	}

	return res;
}

async function throwForResponse(res: Response): Promise<never> {
	throw new ApiError(res, await parseError(res));
}

export async function apiGet<T>(path: string): Promise<T> {
	const res = await apiFetch(path);
	if (!res.ok) await throwForResponse(res);
	return res.json();
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
	const res = await apiFetch(path, {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			'X-CSRF-Token': getCsrfToken()
		},
		body: body ? JSON.stringify(body) : undefined
	});
	if (!res.ok) await throwForResponse(res);
	return res.json();
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
	const res = await apiFetch(path, {
		method: 'PUT',
		headers: {
			'Content-Type': 'application/json',
			'X-CSRF-Token': getCsrfToken()
		},
		body: body ? JSON.stringify(body) : undefined
	});
	if (!res.ok) await throwForResponse(res);
	return res.json();
}

export async function apiDelete(path: string): Promise<void> {
	const res = await apiFetch(path, {
		method: 'DELETE',
		headers: {
			'X-CSRF-Token': getCsrfToken()
		}
	});
	if (!res.ok) await throwForResponse(res);
}
```

Behavior changes vs original:
- `ApiError` now carries `detail` and `code`.
- `apiFetch` intercepts `403 outside_hours` → stashes a flash message in `localStorage` → redirects to login.
- 401 redirect behavior is unchanged.
- Other errors are raised as `ApiError` and handled by callers (so daily-limit 429 flows up to the search caller as-is — we'll render it in a toast where appropriate, but the minimal change here is to expose the code).

- [ ] **Step 2: Type-check the frontend**

```bash
docker compose exec frontend npm run check
```

Expected: `0 errors and 0 warnings` (or current baseline unchanged).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/lib/api/client.ts
git commit -m "Surface API error detail/code; intercept outside_hours to flash + login"
```

---

## Task 11: Login page — show flash + handle outside_hours login response

**Files:**
- Modify: `frontend/src/routes/auth/login/+page.svelte`

- [ ] **Step 1: Read the flash on mount and extend error handling**

In `frontend/src/routes/auth/login/+page.svelte`, replace the `<script lang="ts">` block (lines 1–31 of the current file) with:

```html
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { user, authStatus } from '$lib/stores/auth';
	import { apiPost, ApiError } from '$lib/api/client';
	import type { User } from '$lib/types/auth';

	let email = $state('');
	let password = $state('');
	let showPassword = $state(false);
	let error = $state('');
	let loading = $state(false);

	onMount(() => {
		if (typeof localStorage === 'undefined') return;
		const flash = localStorage.getItem('dzialkowizja_login_flash');
		if (flash) {
			error = flash;
			localStorage.removeItem('dzialkowizja_login_flash');
		}
	});

	async function handleLogin() {
		error = '';
		loading = true;
		try {
			const res = await apiPost<User>('/api/auth/login', { email, password });
			user.set(res);
			authStatus.set('authenticated');
			goto('/');
		} catch (e: unknown) {
			if (e instanceof ApiError) {
				if (e.code === 'outside_hours') {
					const detail = typeof e.detail === 'object' && e.detail ? e.detail : null;
					error =
						(detail && typeof (detail as { message?: string }).message === 'string'
							? (detail as { message: string }).message
							: 'Logowanie poza godzinami pracy.');
				} else if (e.status === 401) {
					error = 'Nieprawidłowy login lub hasło';
				} else {
					error = 'Wystąpił błąd. Spróbuj ponownie.';
				}
			} else {
				error = 'Wystąpił błąd. Spróbuj ponownie.';
			}
		} finally {
			loading = false;
		}
	}
</script>
```

- [ ] **Step 2: Type-check**

```bash
docker compose exec frontend npm run check
```

Expected: no new errors.

- [ ] **Step 3: Manual smoke**

- Set the current weekday to closed via SQL (as in Task 6 step 3).
- In a browser, attempt to log in — expect the outside-hours message under the form.
- While already logged in, close the window via SQL, then navigate to any authenticated page — expect redirect to `/auth/login` with the same message rendered.
- Restore the schedule.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/routes/auth/login/+page.svelte
git commit -m "Show outside-hours flash and API error on login screen"
```

---

## Task 12: Admin policy UI page

**Files:**
- Create: `frontend/src/routes/admin/policy/+page.svelte`

- [ ] **Step 1: Write the page**

`frontend/src/routes/admin/policy/+page.svelte`:

```html
<script lang="ts">
	import { onMount } from 'svelte';
	import { apiGet, apiPut, ApiError } from '$lib/api/client';

	type Day = {
		day_of_week: number;
		closed: boolean;
		start_time: string | null;
		end_time: string | null;
	};

	type Policy = {
		login_hours_enabled: boolean;
		daily_search_limit_enabled: boolean;
		daily_search_limit: number;
		days: Day[];
	};

	const DAY_LABELS = [
		'Poniedziałek',
		'Wtorek',
		'Środa',
		'Czwartek',
		'Piątek',
		'Sobota',
		'Niedziela'
	];

	let policy: Policy | null = $state(null);
	let loading = $state(true);
	let saving = $state(false);
	let error: string | null = $state(null);
	let savedAt: number | null = $state(null);
	let noOrg = $state(false);

	async function load() {
		loading = true;
		noOrg = false;
		error = null;
		try {
			policy = await apiGet<Policy>('/api/admin/policy');
		} catch (e) {
			if (e instanceof ApiError && e.status === 400) {
				noOrg = true;
			} else {
				error = 'Nie udało się pobrać polityki';
			}
		} finally {
			loading = false;
		}
	}

	function setDayClosed(dow: number, closed: boolean) {
		if (!policy) return;
		const day = policy.days.find((d) => d.day_of_week === dow);
		if (!day) return;
		day.closed = closed;
		if (closed) {
			day.start_time = null;
			day.end_time = null;
		} else {
			day.start_time = day.start_time ?? '09:00';
			day.end_time = day.end_time ?? '18:00';
		}
	}

	async function save() {
		if (!policy) return;
		error = null;
		saving = true;
		try {
			policy = await apiPut<Policy>('/api/admin/policy', policy);
			savedAt = Date.now();
		} catch (e) {
			if (e instanceof ApiError) {
				const detail = typeof e.detail === 'object' && e.detail ? e.detail : null;
				const msg = detail && typeof (detail as { message?: string }).message === 'string'
					? (detail as { message: string }).message
					: null;
				error = msg ?? 'Nie udało się zapisać zmian';
			} else {
				error = 'Nie udało się zapisać zmian';
			}
		} finally {
			saving = false;
		}
	}

	onMount(load);
</script>

<h1 class="mb-2 text-xl font-semibold text-[var(--color-primary)]">Limity</h1>
<p class="mb-6 max-w-2xl text-sm text-[var(--color-text-muted)]">
	Ustaw godziny logowania i dzienny limit wyszukiwań dla użytkowników w Twojej organizacji. Administratorzy nie podlegają tym ograniczeniom.
</p>

{#if loading}
	<p class="text-sm text-[var(--color-text-muted)]">Ładowanie...</p>
{:else if noOrg}
	<div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center">
		<p class="text-sm text-[var(--color-text-muted)]">
			Konto super admina nie jest przypisane do organizacji.
		</p>
	</div>
{:else if !policy}
	<p class="text-sm text-red-600">{error ?? 'Nie udało się pobrać polityki'}</p>
{:else}
	{#if error}
		<p class="mb-3 text-sm text-red-600">{error}</p>
	{/if}

	<section class="mb-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
		<label class="mb-3 flex items-center gap-2 text-sm font-medium">
			<input type="checkbox" class="h-4 w-4" bind:checked={policy.login_hours_enabled} />
			Godziny logowania aktywne
		</label>
		<p class="mb-4 text-xs text-[var(--color-text-muted)]">
			Gdy wyłączone — użytkownicy mogą logować się 24/7.
		</p>

		<div class="space-y-2" class:opacity-50={!policy.login_hours_enabled}>
			{#each policy.days as day (day.day_of_week)}
				<div class="flex items-center gap-3 rounded-md border border-[var(--color-border)] p-3">
					<div class="w-28 text-sm">{DAY_LABELS[day.day_of_week]}</div>
					<label class="flex items-center gap-2 text-sm">
						<input
							type="checkbox"
							class="h-4 w-4"
							checked={day.closed}
							disabled={!policy.login_hours_enabled}
							onchange={(e) => setDayClosed(day.day_of_week, (e.currentTarget as HTMLInputElement).checked)}
						/>
						zamknięte
					</label>
					<input
						type="time"
						class="rounded border border-[var(--color-border)] px-2 py-1 text-sm"
						value={day.start_time ?? ''}
						disabled={!policy.login_hours_enabled || day.closed}
						oninput={(e) => (day.start_time = (e.currentTarget as HTMLInputElement).value)}
					/>
					<span class="text-sm text-[var(--color-text-muted)]">–</span>
					<input
						type="time"
						class="rounded border border-[var(--color-border)] px-2 py-1 text-sm"
						value={day.end_time ?? ''}
						disabled={!policy.login_hours_enabled || day.closed}
						oninput={(e) => (day.end_time = (e.currentTarget as HTMLInputElement).value)}
					/>
				</div>
			{/each}
		</div>
	</section>

	<section class="mb-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
		<label class="mb-3 flex items-center gap-2 text-sm font-medium">
			<input type="checkbox" class="h-4 w-4" bind:checked={policy.daily_search_limit_enabled} />
			Dzienny limit wyszukiwań aktywny
		</label>
		<p class="mb-4 text-xs text-[var(--color-text-muted)]">
			Reset o 00:00 czasu środkowoeuropejskiego. Gdy wyłączone — brak limitu.
		</p>
		<label class="flex items-center gap-2 text-sm">
			Limit na użytkownika / dzień
			<input
				type="number"
				min="1"
				class="w-24 rounded border border-[var(--color-border)] px-2 py-1 text-sm"
				bind:value={policy.daily_search_limit}
				disabled={!policy.daily_search_limit_enabled}
			/>
		</label>
	</section>

	<button
		type="button"
		class="rounded bg-[var(--color-accent)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
		disabled={saving}
		onclick={save}
	>
		{saving ? 'Zapisywanie…' : 'Zapisz'}
	</button>

	{#if savedAt}
		<p class="mt-3 text-xs text-[var(--color-text-muted)]">Zapisano</p>
	{/if}
{/if}
```

- [ ] **Step 2: Type-check**

```bash
docker compose exec frontend npm run check
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/admin/policy/+page.svelte
git commit -m "Add /admin/policy page for login hours and daily search limit"
```

---

## Task 13: Admin nav link

**Files:**
- Modify: `frontend/src/routes/admin/+layout.svelte`

- [ ] **Step 1: Add "Limity" to the nav array**

In `frontend/src/routes/admin/+layout.svelte`, locate the `links` array:

```typescript
const links = [
    { href: '/admin/users', label: 'Użytkownicy' },
    { href: '/admin/stats', label: 'Statystyki' },
    { href: '/admin/restrictions', label: 'Ukryte pola' }
];
```

Add the new entry so it becomes:

```typescript
const links = [
    { href: '/admin/users', label: 'Użytkownicy' },
    { href: '/admin/stats', label: 'Statystyki' },
    { href: '/admin/restrictions', label: 'Ukryte pola' },
    { href: '/admin/policy', label: 'Limity' }
];
```

- [ ] **Step 2: Type-check + manual browser check**

```bash
docker compose exec frontend npm run check
```

Browser: as an admin, visit `/admin/policy` directly, then confirm the "Limity" link appears in the sidebar and is highlighted on that path.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/routes/admin/+layout.svelte
git commit -m "Add Limity admin nav entry"
```

---

## Task 14: End-to-end smoke

This isn't a code change — it's the acceptance checklist the implementer runs after Task 13.

- [ ] **A. Login-hours happy path**
  - Log in as a regular user during 09:00-18:00 Mon-Fri → succeeds.
  - Navigate around the app → no unexpected logouts.

- [ ] **B. Login-hours block path**
  - As admin, set the current weekday to closed via `/admin/policy` → save.
  - In a private window, try logging in as a regular user → 403 with outside-hours message shown under the login form.
  - Restore the schedule.

- [ ] **C. Kick-out path**
  - Log in as a user in-hours (normal tab).
  - As admin, set the current weekday to closed in another tab → save.
  - In the user's tab, perform any authenticated action (e.g. /admin? no — user won't have admin. Perform a search instead) → user is redirected to login with the outside-hours flash message visible.
  - Restore the schedule.

- [ ] **D. Admin exempt**
  - Set the current weekday to closed.
  - Log in as an admin → succeeds.
  - Restore the schedule.

- [ ] **E. Daily-limit path**
  - Set `daily_search_limit` to 3 for your own org via `/admin/policy`.
  - Log in as a regular user and run 3 searches → all 200.
  - Run a 4th → 429 with the daily-limit message (as a toast or thrown ApiError; at minimum the search UI shows the failure).
  - Restore `daily_search_limit` to 40.

- [ ] **F. Admin bypasses daily limit**
  - Set `daily_search_limit` to 1 (strictest). As an admin, run 5 searches → all 200.
  - Restore.

- [ ] **G. Existing-org default seeding**
  - `SELECT COUNT(*) FROM organization_login_hours GROUP BY organization_id;` → every org has exactly 7 rows.

- [ ] **H. New-org seeding**
  - As super_admin, create a new org via `/super-admin/organizations`.
  - Verify 7 rows exist for it with the default Mon-Fri 09-18 / Sat-Sun closed schedule.
  - Delete the test org.

If any step fails, open a follow-up fix commit. Do **not** mark the plan complete with a red check above.

---

## Deployment notes

- Running the migration on prod automatically enables login-hours (09:00-18:00 Mon-Fri) and the 40/day cap for every organization. **Communicate this to existing org admins before deploy** — any user trying to use the app outside Mon-Fri 09-18 Warsaw will be blocked starting the instant alembic finishes.
- Admins can disable either feature from the `/admin/policy` page immediately after deploy.
- No Redis state migration — daily limit reads `search_history` directly. Per-minute rate limiter state remains untouched.
- DST-safety: `zoneinfo` resolves spring-forward and fall-back automatically. Schedules defined as "09:00" map to whatever UTC offset Warsaw currently uses.
