from __future__ import annotations

import re

import psycopg2

from app.config import settings

from .schemas import SearchSuggestion

_LOT_PATTERN = re.compile(r"^\d{6}_\d")


def is_lot_query(q: str) -> bool:
    """Match lot ID patterns: full TERYT (240302_1...) or partial with digits/dots/slashes."""
    if _LOT_PATTERN.match(q):
        return True
    cleaned = q.replace(".", "").replace("/", "").replace("_", "").replace(" ", "")
    return len(cleaned) > 0 and cleaned.replace("-", "").isdigit()


def _geo_connect():
    return psycopg2.connect(
        host=settings.geo_db_host,
        port=settings.geo_db_port,
        dbname=settings.geo_db_name,
        user=settings.geo_db_user,
        password=settings.geo_db_password,
        connect_timeout=10,
    )


async def search_lots(q: str, limit: int = 5) -> list[SearchSuggestion]:
    import asyncio

    if not settings.geo_db_user:
        return []

    def _query() -> list[tuple]:
        conn = _geo_connect()
        try:
            prefix = q
            upper = prefix[:-1] + chr(ord(prefix[-1]) + 1)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id_dzialki, COALESCE(gmina, ''), COALESCE(miejscowosc, '')"
                    " FROM lots_enriched"
                    " WHERE id_dzialki >= %s AND id_dzialki < %s"
                    " ORDER BY id_dzialki LIMIT %s",
                    (prefix, upper, limit),
                )
                return cur.fetchall()
        finally:
            conn.close()

    try:
        rows = await asyncio.to_thread(_query)
    except Exception:
        return []

    return [
        SearchSuggestion(
            type="lot",
            label=row[0],
            secondary=", ".join(filter(None, [row[2], row[1]])),
        )
        for row in rows
    ]


def _parse_address_query(q: str) -> dict:
    """Parse user input into city, street, and number components.

    Handles formats like:
      "Poznańska 1, Poznań"  -> city=Poznań, street=Poznańska, number=1
      "Poznań, Poznańska 1"  -> city=Poznań, street=Poznańska, number=1
      "Poznań"               -> city=Poznań
      "Poznańska 1"          -> street=Poznańska, number=1
    """
    # Strip commas from digits (e.g., "1," -> "1")
    q = q.strip()

    # Split on comma
    parts = [p.strip() for p in q.split(",") if p.strip()]

    city_tokens: list[str] = []
    street_tokens: list[str] = []
    number = ""

    if len(parts) >= 2:
        # Two parts: one is likely city, other is street+number
        # Heuristic: shorter part or part without digits is the city
        for part in parts:
            tokens = part.split()
            digits = [t for t in tokens if t.isdigit()]
            words = [t for t in tokens if not t.isdigit()]
            if digits:
                street_tokens.extend(words)
                number = digits[0]
            elif not city_tokens:
                city_tokens = words
            else:
                street_tokens.extend(words)
    else:
        # Single part: split into words
        tokens = parts[0].split() if parts else []
        digits = [t for t in tokens if t.isdigit()]
        words = [t for t in tokens if not t.isdigit()]
        if digits:
            number = digits[0]
        # All non-digit tokens could be city or street
        # We'll search across both columns
        city_tokens = words
        street_tokens = words

    return {
        "city_tokens": city_tokens,
        "street_tokens": street_tokens,
        "number": number,
    }


async def search_addresses(q: str, limit: int = 5) -> list[SearchSuggestion]:
    """Search addresses in gruntomat PRG data using f_unaccent + trigram indexes."""
    import asyncio

    if not settings.geo_db_user:
        return []

    parsed = _parse_address_query(q)
    city_tokens = parsed["city_tokens"]
    street_tokens = parsed["street_tokens"]
    number = parsed["number"]

    if not city_tokens and not street_tokens and not number:
        return []

    def _query() -> list[tuple]:
        conn = _geo_connect()
        try:
            where_clauses: list[str] = []
            params: list = []

            # Build WHERE using f_unaccent for diacritics-insensitive search
            # Each token is matched against the relevant column
            if city_tokens and street_tokens and city_tokens != street_tokens:
                # Separate city and street tokens (comma-separated input)
                for t in city_tokens:
                    where_clauses.append(
                        "f_unaccent(miejscowosc) ILIKE f_unaccent(%s)"
                    )
                    params.append(f"%{t}%")
                for t in street_tokens:
                    where_clauses.append(
                        "f_unaccent(ulica) ILIKE f_unaccent(%s)"
                    )
                    params.append(f"%{t}%")
            else:
                # Same tokens — search across both columns
                tokens = city_tokens or street_tokens
                for t in tokens:
                    where_clauses.append(
                        "(f_unaccent(miejscowosc) ILIKE f_unaccent(%s)"
                        " OR f_unaccent(ulica) ILIKE f_unaccent(%s))"
                    )
                    params.extend([f"%{t}%", f"%{t}%"])

            if number:
                where_clauses.append("numer LIKE %s")
                params.append(f"{number}%")

            if not where_clauses:
                return []

            where_sql = " AND ".join(where_clauses)
            has_numer = bool(number)
            distinct_cols = (
                "miejscowosc, ulica, numer"
                if has_numer
                else "miejscowosc, ulica"
            )

            with conn.cursor() as cur:
                cur.execute(
                    f"WITH matching AS ("
                    f" SELECT DISTINCT ON ({distinct_cols})"
                    f"  id, miejscowosc, ulica, numer, geom"
                    f" FROM addresses"
                    f" WHERE {where_sql}"
                    f" ORDER BY {distinct_cols}"
                    f" LIMIT %s"
                    f")"
                    f" SELECT m.miejscowosc, m.ulica, m.numer, le.id_dzialki"
                    f" FROM matching m"
                    f" LEFT JOIN lots_enriched le"
                    f"  ON ST_Contains(le.geom, m.geom)",
                    (*params, limit),
                )
                return cur.fetchall()
        finally:
            conn.close()

    try:
        rows = await asyncio.to_thread(_query)
    except Exception:
        return []

    results = []
    for row in rows:
        miejscowosc, ulica, numer, id_dzialki = row
        miejscowosc = miejscowosc or ""
        ulica = ulica or ""
        numer = numer or ""
        if ulica:
            label = f"{ulica} {numer}".strip() if numer else ulica
            secondary = miejscowosc
        else:
            label = f"{miejscowosc} {numer}".strip() if numer else miejscowosc
            secondary = ""
        results.append(
            SearchSuggestion(
                type="address",
                label=label,
                secondary=secondary,
                id_dzialki=id_dzialki,
            )
        )
    return results
