from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, field_validator

from app.auth.password import validate_password


UserRoleLiteral = Literal["handlowiec", "prawnik"]


class CreateUserIn(BaseModel):
    email: str
    password: str
    display_name: str
    # Defaults to handlowiec so older frontend builds (which don't send role)
    # keep working while the UI rolls out the role selector.
    role: UserRoleLiteral = "handlowiec"

    @field_validator("display_name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nazwa musi mieć minimum 2 znaki")
        if len(v) > 100:
            raise ValueError("Nazwa może mieć maksimum 100 znaków")
        return v

    @field_validator("password")
    @classmethod
    def password_strong(cls, v: str) -> str:
        errors = validate_password(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class UpdateUserIn(BaseModel):
    """Partial update of a non-admin user. All fields optional — only those
    provided are changed.
    """

    email: str | None = None
    display_name: str | None = None
    role: UserRoleLiteral | None = None

    @field_validator("display_name")
    @classmethod
    def name_not_empty(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Nazwa musi mieć minimum 2 znaki")
        if len(v) > 100:
            raise ValueError("Nazwa może mieć maksimum 100 znaków")
        return v

    @field_validator("email")
    @classmethod
    def email_lower(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip().lower()
        if "@" not in v or len(v) < 3 or len(v) > 255:
            raise ValueError("Niepoprawny email")
        return v


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool
    role: str
    organization_id: str | None
    created_at: str
    last_active_at: str | None
    search_count_7d: int


class ActivityOut(BaseModel):
    id: str
    action_type: str
    target_id: str | None
    query_text: str | None
    ip_address: str | None
    user_agent: str | None
    created_at: str


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    total: int


class FieldOut(BaseModel):
    key: str
    label: str
    description: str
    group: str
    is_restricted: bool


class RestrictionsResponse(BaseModel):
    role: UserRoleLiteral
    fields: list[FieldOut]


class RestrictionsUpdateIn(BaseModel):
    """Per-role visibility update.

    ``role`` is the tier these toggles apply to (handlowiec or prawnik).
    ``updates`` maps field_key -> True (hide from that role) / False (show).
    """

    role: UserRoleLiteral
    updates: dict[str, bool]


class UserStatsOut(BaseModel):
    user_id: str
    display_name: str
    email: str
    searches_today: int
    searches_week: int
    searches_month: int


class TopPlotOut(BaseModel):
    query_text: str
    count: int


class OrgStatsOut(BaseModel):
    total_searches_today: int
    total_searches_week: int
    total_searches_month: int
    users: list[UserStatsOut]
    top_plots: list[TopPlotOut]
