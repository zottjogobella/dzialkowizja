from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth.dependencies import require_auth
from app.config import settings

from . import google_places
from .schemas import ResolveRequest, ResolveResponse, SearchSuggestion
from .service import (
    is_lot_query,
    resolve_address_to_plot,
    search_addresses,
    search_lots,
)

router = APIRouter()


@router.get("", response_model=list[SearchSuggestion])
async def search(
    q: str = Query(min_length=2, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
    session_token: str | None = Query(default=None),
    _user=Depends(require_auth),
) -> list[SearchSuggestion]:
    if is_lot_query(q):
        return await search_lots(q, limit)

    # Use Google Places when key is available, fall back to local PRG search
    if settings.google_api_key:
        items = await google_places.autocomplete(q, session_token)
        return [
            SearchSuggestion(
                type="address",
                label=item["main_text"],
                secondary=item["secondary_text"],
                place_id=item["place_id"],
            )
            for item in items
        ]

    return await search_addresses(q, limit)


@router.post("/resolve", response_model=ResolveResponse)
async def resolve_place(
    body: ResolveRequest,
    _user=Depends(require_auth),
) -> ResolveResponse:
    """Resolve a Google Place to a plot via PRG address matching."""
    addr = await google_places.get_place_address(
        body.place_id, body.session_token
    )
    if addr is None:
        raise HTTPException(502, "Nie udało się pobrać adresu z Google")

    id_dzialki = await resolve_address_to_plot(
        city=addr["city"], street=addr["street"], number=addr["number"]
    )
    return ResolveResponse(id_dzialki=id_dzialki)
