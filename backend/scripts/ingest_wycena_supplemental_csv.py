#!/usr/bin/env python3
"""Load wyceny_5_5M_union3_dedup_without_old_combined_ids.csv into wycena_supplemental.

CSV columns expected:
    id_dzialki, pow_dzialki, pow_buforu, procent_pow, cena_m2,
    wycena, wartosc_roszczenia, voltage, segment_rynku, pewnosc, source

Stored columns:
    id_dzialki      → wycena_supplemental.id_dzialki
    wycena          → wycena_supplemental.wartosc_dzialki   (total plot valuation)
    cena_m2         → wycena_supplemental.cena_m2
    pow_dzialki     → wycena_supplemental.pow_dzialki
    pow_buforu      → wycena_supplemental.pow_buforu
    segment_rynku   → wycena_supplemental.segment_rynku
    pewnosc         → wycena_supplemental.pewnosc
    source          → wycena_supplemental.source

Usage::

    python backend/scripts/ingest_wycena_supplemental_csv.py /path/to/wyceny.csv

Connection details come from the usual ``DATABASE_URL_SYNC`` env var.

Idempotent: truncates the table before inserting.
"""

from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
from pathlib import Path
from typing import Iterator

import psycopg2
import psycopg2.extras

logger = logging.getLogger("ingest_wycena_supplemental_csv")

BATCH_SIZE = 5000

csv.field_size_limit(sys.maxsize)


Row = tuple[
    str,            # id_dzialki
    float,          # wartosc_dzialki
    float | None,   # cena_m2
    float | None,   # pow_dzialki
    float | None,   # pow_buforu
    str | None,     # segment_rynku
    str | None,     # pewnosc
    str | None,     # source
]


def parse_database_url(url: str) -> dict:
    import urllib.parse

    if "+" in url.split("://", 1)[0]:
        scheme, rest = url.split("://", 1)
        url = scheme.split("+", 1)[0] + "://" + rest
    p = urllib.parse.urlparse(url)
    return {
        "host": p.hostname,
        "port": p.port or 5432,
        "dbname": (p.path or "/").lstrip("/"),
        "user": p.username,
        "password": p.password,
    }


def _parse_float(raw: str) -> float | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_str(raw: str) -> str | None:
    s = (raw or "").strip()
    return s or None


def read_rows(csv_path: Path) -> Iterator[Row]:
    """Stream deduped rows from the CSV.

    Plots can in principle appear more than once; keep the row with the
    largest ``wycena`` so the displayed valuation is the most conservative.
    """
    Kept = tuple[float, float | None, float | None, float | None, str | None, str | None, str | None]
    seen: dict[str, Kept] = {}
    total = 0
    bad = 0
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"id_dzialki", "wycena"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(
                f"CSV is missing required columns: {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )
        for row in reader:
            total += 1
            lot = (row.get("id_dzialki") or "").strip()
            wycena = _parse_float(row.get("wycena", ""))
            if not lot or wycena is None:
                bad += 1
                continue
            cena_m2 = _parse_float(row.get("cena_m2", ""))
            pow_dz = _parse_float(row.get("pow_dzialki", ""))
            pow_buf = _parse_float(row.get("pow_buforu", ""))
            segment = _parse_str(row.get("segment_rynku", ""))
            pewnosc = _parse_str(row.get("pewnosc", ""))
            source = _parse_str(row.get("source", ""))
            prev = seen.get(lot)
            if prev is None or wycena > prev[0]:
                seen[lot] = (wycena, cena_m2, pow_dz, pow_buf, segment, pewnosc, source)
            if total % 500_000 == 0:
                logger.info("... read %d rows (kept unique plots: %d)", total, len(seen))

    logger.info(
        "scanned %d rows → %d unique plots kept (%d dropped as malformed)",
        total,
        len(seen),
        bad,
    )
    for lot, vals in seen.items():
        yield (lot, *vals)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("csv_path", type=Path)
    ap.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL_SYNC"),
        help="Postgres URL (default: $DATABASE_URL_SYNC)",
    )
    args = ap.parse_args(argv)

    if not args.csv_path.exists():
        ap.error(f"CSV not found: {args.csv_path}")
    if not args.database_url:
        ap.error("DATABASE_URL_SYNC not set and --database-url not given")

    conn_kwargs = parse_database_url(args.database_url)
    logger.info("connecting to %s:%s/%s as %s",
                conn_kwargs["host"], conn_kwargs["port"],
                conn_kwargs["dbname"], conn_kwargs["user"])

    conn = psycopg2.connect(**conn_kwargs)
    try:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE wycena_supplemental RESTART IDENTITY")
            insert_sql = (
                "INSERT INTO wycena_supplemental"
                " (id_dzialki, wartosc_dzialki, cena_m2, pow_dzialki, pow_buforu,"
                "  segment_rynku, pewnosc, source)"
                " VALUES %s"
            )
            batch: list[Row] = []
            written = 0
            for r in read_rows(args.csv_path):
                batch.append(r)
                if len(batch) >= BATCH_SIZE:
                    psycopg2.extras.execute_values(cur, insert_sql, batch)
                    written += len(batch)
                    if written % 100_000 == 0:
                        logger.info("inserted %d rows", written)
                    batch.clear()
            if batch:
                psycopg2.extras.execute_values(cur, insert_sql, batch)
                written += len(batch)

        conn.commit()
        logger.info("done — %d rows in wycena_supplemental", written)
    except Exception:
        conn.rollback()
        logger.exception("ingest failed; rolled back")
        return 1
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
