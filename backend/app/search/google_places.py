from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None

_BASE_URL = "https://places.googleapis.com/v1"


async def init_client() -> None:
    global _client
    if not settings.google_api_key:
        logger.info("Google API key not set — Places client disabled")
        return
    _client = httpx.AsyncClient(
        timeout=5.0,
        headers={
            "X-Goog-Api-Key": settings.google_api_key,
            "Content-Type": "application/json",
        },
    )


async def close_client() -> None:
    global _client
    if _client:
        await _client.aclose()
        _client = None


async def autocomplete(
    query: str, session_token: str | None = None
) -> list[dict]:
    """Call Google Places Autocomplete (New) and return suggestions."""
    if _client is None:
        return []

    body: dict = {
        "input": query,
        "includedRegionCodes": ["pl"],
        "languageCode": "pl",
    }
    if session_token:
        body["sessionToken"] = session_token

    try:
        resp = await _client.post(f"{_BASE_URL}/places:autocomplete", json=body)
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Google Places autocomplete failed")
        return []

    data = resp.json()
    results: list[dict] = []
    for s in data.get("suggestions", []):
        pred = s.get("placePrediction")
        if not pred:
            continue
        fmt = pred.get("structuredFormat", {})
        results.append(
            {
                "place_id": pred.get("placeId", ""),
                "main_text": fmt.get("mainText", {}).get("text", ""),
                "secondary_text": fmt.get("secondaryText", {}).get("text", ""),
            }
        )
    return results


async def get_place_address(
    place_id: str, session_token: str | None = None
) -> dict | None:
    """Get structured address components from Google Place Details.

    Returns {"city": ..., "street": ..., "number": ...} or None on error.
    """
    if _client is None:
        return None

    headers = {"X-Goog-FieldMask": "addressComponents"}
    if session_token:
        headers["X-Goog-SessionToken"] = session_token

    try:
        resp = await _client.get(
            f"{_BASE_URL}/places/{place_id}", headers=headers
        )
        resp.raise_for_status()
    except httpx.HTTPError:
        logger.exception("Google Place Details failed for %s", place_id)
        return None

    data = resp.json()
    city = ""
    street = ""
    number = ""
    for comp in data.get("addressComponents", []):
        types = comp.get("types", [])
        text = comp.get("longText", "") or comp.get("shortText", "")
        if "locality" in types:
            city = text
        elif "route" in types:
            street = text
        elif "street_number" in types:
            number = text

    if not city and not street:
        return None

    return {"city": city, "street": street, "number": number}
