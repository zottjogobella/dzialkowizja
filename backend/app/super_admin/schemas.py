from __future__ import annotations

import re

from pydantic import BaseModel, EmailStr, field_validator

from app.auth.password import validate_password


class CreateOrganizationIn(BaseModel):
    name: str
    slug: str

    @field_validator("name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 255:
            raise ValueError("Nazwa: 2–255 znaków")
        return v

    @field_validator("slug")
    @classmethod
    def slug_ok(cls, v: str) -> str:
        v = v.strip().lower()
        if not re.fullmatch(r"[a-z0-9-]{2,64}", v):
            raise ValueError("Slug: a-z, 0-9, '-', 2–64 znaków")
        return v


class OrganizationOut(BaseModel):
    id: str
    name: str
    slug: str
    created_at: str
    user_count: int
    activity_count_30d: int


class CreateAdminIn(BaseModel):
    email: EmailStr
    password: str
    display_name: str
    organization_id: str

    @field_validator("display_name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 100:
            raise ValueError("Nazwa: 2–100 znaków")
        return v

    @field_validator("password")
    @classmethod
    def pw_ok(cls, v: str) -> str:
        errors = validate_password(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class AdminOut(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool
    organization_id: str | None
    organization_name: str | None
    created_at: str


class GlobalActivityRow(BaseModel):
    id: str
    user_id: str
    user_email: str
    organization_id: str | None
    organization_name: str | None
    action_type: str
    target_id: str | None
    query_text: str | None
    ip_address: str | None
    created_at: str


class GlobalActivityPage(BaseModel):
    items: list[GlobalActivityRow]
    total: int
