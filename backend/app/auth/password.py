from __future__ import annotations

import re

import bcrypt

# Timing-attack prevention: always compare against something
_DUMMY_HASH = bcrypt.hashpw(b"timing-attack-prevention-dummy", bcrypt.gensalt()).decode()

# Password policy
MIN_LENGTH = 8
MAX_LENGTH = 128


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


def verify_password_timing_safe(plain: str, hashed: str | None) -> bool:
    """Always runs bcrypt comparison to prevent timing-based user enumeration."""
    if hashed is None:
        verify_password(plain, _DUMMY_HASH)
        return False
    return verify_password(plain, hashed)


def validate_password(password: str) -> list[str]:
    """Returns list of validation errors. Empty list = valid."""
    errors: list[str] = []

    if len(password) < MIN_LENGTH:
        errors.append(f"Hasło musi mieć minimum {MIN_LENGTH} znaków")
    if len(password) > MAX_LENGTH:
        errors.append(f"Hasło może mieć maksimum {MAX_LENGTH} znaków")
    if not re.search(r"[a-z]", password):
        errors.append("Hasło musi zawierać małą literę")
    if not re.search(r"[A-Z]", password):
        errors.append("Hasło musi zawierać wielką literę")
    if not re.search(r"\d", password):
        errors.append("Hasło musi zawierać cyfrę")

    return errors
