from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator

from app.auth.password import validate_password


class CreateUserIn(BaseModel):
    email: EmailStr
    password: str
    display_name: str

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
    is_restricted: bool


class RestrictionsResponse(BaseModel):
    fields: list[FieldOut]


class RestrictionsUpdateIn(BaseModel):
    """Map of field_key -> True (hide from user) / False (show)."""

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
