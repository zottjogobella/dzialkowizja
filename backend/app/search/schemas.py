from __future__ import annotations

from pydantic import BaseModel


class SearchSuggestion(BaseModel):
    type: str  # "lot" or "address"
    label: str
    secondary: str
    id_dzialki: str | None = None
    lng: float | None = None
    lat: float | None = None
    place_id: str | None = None


class ResolveRequest(BaseModel):
    place_id: str
    session_token: str | None = None


class ResolveResponse(BaseModel):
    id_dzialki: str | None = None
