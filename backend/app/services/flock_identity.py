"""Canonical identity keys shared by enrollment, ORM writes and migration."""
from __future__ import annotations

import unicodedata


def identity_key(value: str, *, hostname: bool = False) -> str:
    if not isinstance(value, str) or any(unicodedata.category(c).startswith("C") for c in value):
        raise ValueError("Flock identity must be text without control characters")
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if hostname:
        normalized = normalized.rstrip(".")
    if not normalized:
        raise ValueError("Flock identity cannot be blank")
    return normalized
