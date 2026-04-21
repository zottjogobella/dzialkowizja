# Org access policy — login hours & daily search limit

**Status:** draft
**Date:** 2026-04-21

## Goal

Let an organization's admin restrict when their users can access the app and
how many searches each user can run per day. Super-admin and admin roles are
unaffected — the policy applies to `role=user` only, matching the existing
`rate_limit_search` exemption pattern.

## Requirements

### Login hours
- Per-organization schedule, per day of week (Mon–Sun).
- Each day is either *closed* or has a `start_time`/`end_time` window.
- Enforced on login AND on every authenticated request — a user who is
  already logged in when the window closes is kicked out on their next API
  call.
- All time comparisons use **Europe/Warsaw** (DST-aware); the server clock
  is the only source of truth, client clocks cannot bypass.
- Admin toggle `login_hours_enabled` turns the feature off globally for the
  org (24/7 access).

### Daily search limit
- Per-user per-day cap on the `/api/search` autocomplete endpoint.
- Day boundary = midnight Europe/Warsaw.
- Hard block (HTTP 429) when exceeded. Other endpoints (plot detail, MPZP,
  etc.) are not affected.
- Coexists with the existing per-minute `rate_limit_search` dependency —
  the per-minute limiter is abuse protection, the daily limit is a quota.
- Admin toggle `daily_search_limit_enabled` turns the feature off
  (unlimited).

### Defaults on deploy
Every organization (including existing ones) gets:
- Login hours: enabled, Mon–Fri 09:00–18:00, Sat–Sun closed.
- Daily search limit: enabled, 40 searches/user/day.

Existing users trying to use the app outside Mon–Fri 09:00–18:00 on the
first deploy will be blocked — this is intentional.

## Data model

### `organizations` — three new columns

| column | type | default | note |
|---|---|---|---|
| `login_hours_enabled` | bool NOT NULL | `true` | off = 24/7 |
| `daily_search_limit_enabled` | bool NOT NULL | `true` | off = unlimited |
| `daily_search_limit` | int NOT NULL | `40` | only meaningful when enabled; must be >= 1 |

### `organization_login_hours` — new table

| column | type | note |
|---|---|---|
| `organization_id` | UUID FK → organizations ON DELETE CASCADE | PK part |
| `day_of_week` | SMALLINT, CHECK IN (0..6) | PK part; 0=Mon, 6=Sun |
| `closed` | bool NOT NULL default false | |
| `start_time` | TIME without tz, nullable | required when `closed=false` |
| `end_time` | TIME without tz, nullable | required when `closed=false`, `> start_time` |

Each org always has exactly 7 rows. Seeded during migration and on
organization creation.

### Alembic migration 009

1. Add three columns to `organizations` with the defaults above.
2. Create `organization_login_hours` table.
3. Backfill 7 rows for every existing org: days 0–4 open 09:00–18:00,
   days 5–6 closed.
4. `create_organization` in super-admin router also seeds these rows.

## Backend

### Timezone helper (`app/utils/time.py`, new module)

```python
from zoneinfo import ZoneInfo
WARSAW = ZoneInfo("Europe/Warsaw")

def now_warsaw() -> datetime: ...
def warsaw_midnight_utc() -> datetime:
    """Start of 'today' in Warsaw, expressed as UTC for DB comparisons."""
```

### `app/policy/` (new module)

`app/policy/login_hours.py`:
- `is_within_hours(org, now_warsaw) -> bool` — looks up today's schedule
  row, returns False if closed or outside window.
- `load_schedule(db, org_id) -> dict[int, Schedule]` — fetches all 7 rows.

`app/policy/dependencies.py`:
- `enforce_login_hours(user, db)`: **plain async function** (not a dep).
  If `user.role != "user"` or `user.organization_id is None` → return.
  Otherwise fetch the org row and today's schedule row explicitly
  (`select(Organization, OrganizationLoginHours)` — no lazy relationship
  access). If `!login_hours_enabled` → return. Compute Warsaw now and
  raise `HTTPException(403, detail={"code": "outside_hours",
  "message": <Polish>, "schedule": {day_of_week, start_time, end_time} | {closed: true}})`.
  Called from two places: `require_auth` (every authenticated request)
  and `/api/auth/login` (before issuing a session).
- `enforce_daily_search_limit`: **FastAPI dep**. If role≠user or
  `organization_id is None` → return. Fetch org; if toggle off → return.
  Count `SearchHistory` rows (user_id=X, created_at >= warsaw_midnight_utc()).
  If count >= limit → `HTTPException(429, detail={"code":
  "daily_limit_exceeded", "limit": N, "reset_at": <ISO>})`.

Both deps fetch the org directly by `user.organization_id` — do not rely
on the `User.organization` relationship (lazy-loading is unsafe here).

### Integration points

- `app/auth/router.py::login` — after `is_active` check, call
  `enforce_login_hours(user, db)` directly.
- `app/auth/dependencies.py::require_auth` — after the 401-if-None guard,
  call `enforce_login_hours(user, db)`. Existing call sites
  `Depends(require_auth)` remain unchanged.
- `app/search/router.py::search` — add `Depends(enforce_daily_search_limit)`
  alongside the existing `Depends(rate_limit_search)`.

### Admin API — `app/admin/router.py`

```
GET  /api/admin/policy   → PolicyOut
PUT  /api/admin/policy   → PolicyOut (echoes saved state)
```

`PolicyOut` shape:
```jsonc
{
  "login_hours_enabled": true,
  "daily_search_limit_enabled": true,
  "daily_search_limit": 40,
  "days": [
    {"day_of_week": 0, "closed": false, "start_time": "09:00", "end_time": "18:00"},
    // ...7 entries, ordered by day_of_week
  ]
}
```

`PUT` validation:
- For each day: if `closed=false`, both times required and `end_time > start_time`.
- `daily_search_limit >= 1` when enabled.
- Exactly 7 days, unique `day_of_week`.

Authorization: `require_admin` (already exempts super-admin outside an
org — same behavior as restrictions endpoint).

## Frontend

### API client (`frontend/src/lib/api/client.ts`)

- `ApiError` already carries status + parsed detail. Extend the response
  handling so callers can inspect `detail.code`.
- Central interceptor for 403 `outside_hours`: clear local auth store,
  store a flash message (`localStorage` or a one-shot store), redirect to
  `/auth/login`.
- Central interceptor for 429 `daily_limit_exceeded`: show a toast with
  the Polish message (no logout).

### Login page

When a flash message is present (from the interceptor or from a failed
login response), render it above the form:

> "Poza godzinami pracy (09:00–18:00 pn–pt). Spróbuj ponownie w godzinach
> otwarcia."

For failed `/api/auth/login` with `outside_hours`, show the same message
under the password input.

### New admin page `/admin/policy`

Nav link added in `frontend/src/routes/admin/+layout.svelte` as 4th entry
**"Limity"** (after Ukryte pola).

Page layout:
1. **Section "Godziny logowania"** — toggle `login_hours_enabled`.
   When on, show a 7-row grid:
   ```
   Poniedziałek  [☐ zamknięte]  [09:00] – [18:00]
   Wtorek        [☐ zamknięte]  [09:00] – [18:00]
   ...
   Niedziela     [☑ zamknięte]  (inputs disabled)
   ```
2. **Section "Dzienny limit wyszukiwań"** — toggle
   `daily_search_limit_enabled`. When on, show number input (min 1).
3. **"Zapisz"** button — PUT /api/admin/policy. Show saved indicator
   identical to restrictions page pattern.

No live counter badge on the user side in this iteration.

## Error/UX behavior summary

| Situation | HTTP | Detail code | UX |
|---|---|---|---|
| `/api/auth/login` outside window | 403 | `outside_hours` | Error under form |
| Authenticated request outside window | 403 | `outside_hours` | Auto-logout → login page with flash |
| `/api/search` over daily limit | 429 | `daily_limit_exceeded` | Toast, request aborted |
| `/api/search` over per-minute (existing) | 429 | (unchanged) | Toast |

## Testing

Unit / integration (pytest, backend):
- `is_within_hours` — cases: closed day, before start, inside, after end, boundary at `end_time` (exclusive).
- DST boundary (last Sun of Mar / Oct) — Warsaw time still resolves correctly; local time `02:30` during spring-forward is not hit by our schedules but the helper must not crash.
- `/api/auth/login` with user in closed-day org → 403 `outside_hours`.
- `require_auth` kicks out a user whose session is valid but current time is outside window → 403.
- `/api/search` 40 times → 40 OK, 41st → 429 `daily_limit_exceeded`.
- Admin PUT `/api/admin/policy` validation: overlapping/invalid times rejected; valid shape persists and GET echoes it.

E2E (playwright): skipped for this iteration — existing admin pages don't have e2e either.

Manual smoke: set own org's hours to "closed today", confirm logout, unset, confirm restored access.

## Non-goals / deferred

- Per-user overrides.
- Per-org timezone.
- Multiple windows per day.
- Weekly / monthly search caps.
- Live "searches remaining today" counter in the UI.
- Rolling 24-hour limit (we use calendar-day Europe/Warsaw).
- Audit-log entries for policy-blocked attempts (can be added later by
  reusing `ActivityLog`).

## Files touched (rough map)

Backend new:
- `backend/alembic/versions/009_org_access_policy.py`
- `backend/app/policy/__init__.py`
- `backend/app/policy/login_hours.py`
- `backend/app/policy/dependencies.py`
- `backend/app/utils/__init__.py`, `backend/app/utils/time.py`

Backend modified:
- `backend/app/db/models.py` (new `OrganizationLoginHours`, three org columns)
- `backend/app/auth/router.py` (login-time check)
- `backend/app/auth/dependencies.py` (`require_auth` composes `enforce_login_hours`)
- `backend/app/admin/router.py` + `schemas.py` (policy endpoints)
- `backend/app/search/router.py` (add daily-limit dep)
- `backend/app/super_admin/router.py` (seed 7 day rows on org create)

Frontend new:
- `frontend/src/routes/admin/policy/+page.svelte`

Frontend modified:
- `frontend/src/routes/admin/+layout.svelte` (nav entry)
- `frontend/src/lib/api/client.ts` (interceptors for the two codes)
- `frontend/src/routes/auth/login/+page.svelte` (flash message)
