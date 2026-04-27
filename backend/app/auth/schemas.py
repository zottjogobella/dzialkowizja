from __future__ import annotations

from pydantic import BaseModel, field_validator

from .password import validate_password


class RegisterRequest(BaseModel):
    email: str
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
    def password_strong_enough(cls, v: str) -> str:
        errors = validate_password(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class LoginRequest(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool
    role: str
    organization_id: str | None = None
    # Field keys hidden from this user right now (empty for admin/super_admin).
    # Frontend uses this list to drop layout-only sections cleanly without
    # relying solely on null payloads.
    restricted_keys: list[str] = []

    class Config:
        from_attributes = True
