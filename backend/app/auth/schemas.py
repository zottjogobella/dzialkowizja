from __future__ import annotations

from pydantic import BaseModel, EmailStr, field_validator

from .password import validate_password


class RegisterRequest(BaseModel):
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
    def password_strong_enough(cls, v: str) -> str:
        errors = validate_password(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str
    is_active: bool

    class Config:
        from_attributes = True
