from __future__ import annotations

from pydantic import BaseModel


class Listing(BaseModel):
    id: int
    name: str | None = None
    property_type: str | None = None
    deal_type: str | None = None
    price: str | None = None
    price_per_meter: float | None = None
    area: str | None = None
    city: str | None = None
    url: str | None = None
    site: str | None = None
    publish_date: str | None = None
