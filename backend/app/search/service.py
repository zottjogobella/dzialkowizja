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


async def search_lots(q: str, limit: int = 5) -> list[SearchSuggestion]:
    import asyncio

    if not settings.geo_db_user:
        return []

    def _query() -> list[tuple]:
        conn = psycopg2.connect(
            host=settings.geo_db_host,
            port=settings.geo_db_port,
            dbname=settings.geo_db_name,
            user=settings.geo_db_user,
            password=settings.geo_db_password,
            connect_timeout=10,
        )
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


async def search_addresses(q: str, limit: int = 5) -> list[SearchSuggestion]:
    """Search addresses in gruntomat PRG data (addresses + lot_addresses + lots)."""
    import asyncio

    if not settings.geo_db_user:
        return []

    text_tokens = [t for t in q.split() if not t.isdigit()]
    digit_tokens = [t for t in q.split() if t.isdigit()]
    if not text_tokens and not digit_tokens:
        return []

    def _query() -> list[tuple]:
        conn = psycopg2.connect(
            host=settings.geo_db_host,
            port=settings.geo_db_port,
            dbname=settings.geo_db_name,
            user=settings.geo_db_user,
            password=settings.geo_db_password,
            connect_timeout=10,
        )
        try:
            addr_expr = (
                "COALESCE(miejscowosc, '') || ' ' || "
                "COALESCE(ulica, '')"
            )
            where_clauses = []
            params: list = []
            if text_tokens:
                where_clauses.append(f"({addr_expr}) ILIKE ALL(%s)")
                params.append([f"%{t}%" for t in text_tokens])
            if digit_tokens:
                where_clauses.append("numer LIKE %s")
                params.append(f"{digit_tokens[0]}%")

            if not where_clauses:
                return []

            where_sql = " AND ".join(where_clauses)
            has_numer = bool(digit_tokens)
            distinct_cols = "miejscowosc, ulica, numer" if has_numer else "miejscowosc, ulica"

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


async def resolve_address_to_plot(
    city: str, street: str, number: str
) -> str | None:
    """Match structured address against PRG and return id_dzialki via ST_Contains."""
    import asyncio

    if not settings.geo_db_user:
        return None

    def _query() -> str | None:
        conn = psycopg2.connect(
            host=settings.geo_db_host,
            port=settings.geo_db_port,
            dbname=settings.geo_db_name,
            user=settings.geo_db_user,
            password=settings.geo_db_password,
            connect_timeout=10,
        )
        try:
            with conn.cursor() as cur:
                # Try exact match first (city + street + number)
                where_parts = ["miejscowosc ILIKE %s"]
                params: list = [city]
                if street:
                    where_parts.append("ulica ILIKE %s")
                    params.append(street)
                if number:
                    where_parts.append("numer = %s")
                    params.append(number)

                where_sql = " AND ".join(where_parts)
                cur.execute(
                    f"SELECT le.id_dzialki"
                    f" FROM addresses a"
                    f" JOIN lots_enriched le ON ST_Contains(le.geom, a.geom)"
                    f" WHERE {where_sql}"
                    f" LIMIT 1",
                    params,
                )
                row = cur.fetchone()
                if row:
                    return row[0]

                # Fallback: try without number (street-level match)
                if number and street:
                    cur.execute(
                        "SELECT le.id_dzialki"
                        " FROM addresses a"
                        " JOIN lots_enriched le ON ST_Contains(le.geom, a.geom)"
                        " WHERE miejscowosc ILIKE %s AND ulica ILIKE %s"
                        " LIMIT 1",
                        (city, street),
                    )
                    row = cur.fetchone()
                    return row[0] if row else None

                return None
        finally:
            conn.close()

    try:
        return await asyncio.to_thread(_query)
    except Exception:
        return None
