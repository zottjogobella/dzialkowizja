from __future__ import annotations

from pydantic import BaseModel


class SearchSuggestion(BaseModel):
    type: str  # "lot" or "address"
    label: str
    secondary: str
    id_dzialki: str | None = None
    lng: float | None = None
    lat: float | None = None
    # Ownership-complication flags from the roszczenia sheet, surfaced as
    # badges in the dropdown. None when the plot isn't covered by the sheet.
    has_sluzebnosci: bool | None = None
    has_10_or_more_owners: bool | None = None
    has_state_owner: bool | None = None
    # True when the plot is in the sheet but has no KW. None when not covered.
    no_kw_in_sheet: bool | None = None
