"""Request/response shapes for the admin policy endpoints."""

from __future__ import annotations

from datetime import time
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


PolicyRoleLiteral = Literal["handlowiec", "prawnik"]


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
    role: PolicyRoleLiteral
    login_hours_enabled: bool
    daily_search_limit_enabled: bool
    daily_search_limit: int
    days: list[LoginHoursDay]


class PolicyUpdateIn(BaseModel):
    role: PolicyRoleLiteral
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
