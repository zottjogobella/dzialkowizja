#!/usr/bin/env python3
"""Fast GUNB RWDZ ingest — geocodes via lots_enriched JOIN, not ULDK HTTP.

Instead of calling the ULDK geocoder over HTTP for every parcel (which takes
~1-2 s per request and makes a full ingest take days), this script:

1. Downloads the 18 GUNB CSV ZIPs (16 voivodeships + 2 zgłoszenia).
2. Parses them and bulk-INSERTs into gunb_investments with parcel_id but
   **geom = NULL**.
3. Runs a single UPDATE … JOIN lots_enriched to fill in geom from the 39 M
   plots already in gruntomat_geo.

Total runtime: ~10-20 minutes for the full dataset vs ~4+ days with ULDK.

Usage::

    python backend/scripts/ingest_gunb_fast.py \\
        --db-host 145.239.2.73 --db-port 5433 \\
        --db-name gruntomat_geo --db-user gruntomat --db-password gruntomat_dev \\
        --full --date-from 2023-01-01
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import os
import sys
import time
import zipfile

import httpx
import psycopg2
import psycopg2.extras

csv.field_size_limit(2**31 - 1)

logger = logging.getLogger("ingest_gunb_fast")

GUNB_BASE = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie"

VOIVODESHIPS = [
    "dolnoslaskie", "kujawsko-pomorskie", "lubelskie", "lubuskie",
    "lodzkie", "mazowieckie", "malopolskie", "opolskie",
    "podkarpackie", "podlaskie", "pomorskie", "slaskie",
    "swietokrzyskie", "warminsko-mazurskie", "wielkopolskie",
    "zachodniopomorskie",
]

ZGLOSZENIA_DATASETS = ["zgloszenia_2016_2021", "zgloszenia_2022_up"]

UPSERT_SQL = """
INSERT INTO gunb_investments (
    source_id, typ, status, data_wniosku, data_decyzji, inwestor, organ,
    teryt_gmi, wojewodztwo, gmina, miejscowosc, adres, opis, kategoria,
    rodzaj_inwestycji, parcel_id, kubatura, raw_data, ingested_at
) VALUES (
    %(source_id)s, %(typ)s, %(status)s, %(data_wniosku)s, %(data_decyzji)s,
    %(inwestor)s, %(organ)s, %(teryt_gmi)s, %(wojewodztwo)s, %(gmina)s,
    %(miejscowosc)s, %(adres)s, %(opis)s, %(kategoria)s, %(rodzaj_inwestycji)s,
    %(parcel_id)s, %(kubatura)s,
    %(raw_data)s::jsonb, NOW()
)
ON CONFLICT (source_id) DO UPDATE SET
    typ = EXCLUDED.typ,
    status = EXCLUDED.status,
    data_wniosku = EXCLUDED.data_wniosku,
    data_decyzji = EXCLUDED.data_decyzji,
    inwestor = EXCLUDED.inwestor,
    organ = EXCLUDED.organ,
    teryt_gmi = EXCLUDED.teryt_gmi,
    wojewodztwo = EXCLUDED.wojewodztwo,
    gmina = EXCLUDED.gmina,
    miejscowosc = EXCLUDED.miejscowosc,
    adres = EXCLUDED.adres,
    opis = EXCLUDED.opis,
    kategoria = EXCLUDED.kategoria,
    rodzaj_inwestycji = EXCLUDED.rodzaj_inwestycji,
    parcel_id = EXCLUDED.parcel_id,
    kubatura = EXCLUDED.kubatura,
    raw_data = EXCLUDED.raw_data,
    ingested_at = NOW();
"""


def download_if_missing(url: str, local_path: str) -> str:
    os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
        logger.info("Using cached %s", local_path)
        return local_path
    logger.info("Downloading %s -> %s", url, local_path)
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        resp = client.get(url)
        resp.raise_for_status()
    with open(local_path, "wb") as f:
        f.write(resp.content)
    return local_path


def make_source_id(dataset: str, row: dict) -> str:
    raw = "|".join([
        dataset,
        row.get("numer_ewidencyjny_system", "") or row.get("numer_urzad", ""),
        row.get("organ_wydajacy_decyzje", "") or row.get("organ", ""),
        row.get("data_wplywu_wniosku_do_urzedu", "") or "",
    ])
    return hashlib.sha1(raw.encode()).hexdigest()


def make_parcel_id(row: dict) -> str | None:
    # Pozwolenia use "jednosta_numer_ew", zgłoszenia use "jednostki_numer".
    j = (row.get("jednosta_numer_ew") or row.get("jednostki_numer") or "").strip()
    o = (row.get("obreb_numer") or "").strip()
    n = (row.get("numer_dzialki") or "").strip()
    if not j or not o or not n:
        return None
    return f"{j}.{o}.{n}"


def parse_date(s: str | None) -> str | None:
    if not s or not s.strip():
        return None
    s = s.strip()[:10]
    if len(s) == 10 and s[4] == "-":
        return s
    return None


def iter_records(zip_path: str, dataset_label: str, kind: str, date_from: str | None):
    """Yield dicts ready for upsert from a GUNB ZIP."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
        if not csv_names:
            logger.warning("No CSV in %s", zip_path)
            return
        with zf.open(csv_names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace")
            reader = csv.DictReader(text, delimiter="#")
            for row in reader:
                # Date filter
                if kind == "rwd":
                    d = parse_date(row.get("data_wydania_decyzji"))
                    d_wniosku = parse_date(row.get("data_wplywu_wniosku_do_urzedu"))
                else:
                    d = parse_date(row.get("data_wplywu_wniosku_do_urzedu"))
                    d_wniosku = d

                event_date = d or d_wniosku
                if date_from and event_date and event_date < date_from:
                    continue

                parcel_id = make_parcel_id(row)
                source_id = make_source_id(dataset_label, row)

                if kind == "rwd":
                    typ = "pozwolenie_budowa"
                    status = "decyzja_wydana" if d else "w_toku"
                    organ = (row.get("organ_wydajacy_decyzje") or "").strip()
                    woj = (row.get("wojewodztwo") or "").strip()
                    gmina = (row.get("powiat_gmina") or "").strip()
                    kategoria = (row.get("kategoria_obiektu_budowlanego") or "").strip()
                    rodzaj = (row.get("rodzaj_inwestycji") or "").strip()
                else:
                    typ = "zgloszenie"
                    status = "zgloszenie"
                    organ = (row.get("organ") or "").strip()
                    woj = (row.get("wojewodztwo") or "").strip()
                    gmina = (row.get("powiat_gmina") or "").strip()
                    kategoria = (row.get("kategoria") or "").strip()
                    rodzaj = (row.get("rodzaj") or "").strip()

                yield {
                    "source_id": source_id,
                    "typ": typ,
                    "status": status,
                    "data_wniosku": d_wniosku,
                    "data_decyzji": d,
                    "inwestor": None,
                    "organ": organ or None,
                    "teryt_gmi": (row.get("jednosta_numer_ew") or "")[:6] or None,
                    "wojewodztwo": woj or None,
                    "gmina": gmina or None,
                    "miejscowosc": (row.get("miejscowosc") or "").strip() or None,
                    "adres": (row.get("ulica") or "").strip() or None,
                    "opis": (row.get("nazwa_zamierzenia_budowlanego") or row.get("opis") or "").strip()[:2000] or None,
                    "kategoria": kategoria or None,
                    "rodzaj_inwestycji": rodzaj or None,
                    "parcel_id": parcel_id,
                    "kubatura": None,
                    "raw_data": json.dumps({k: v for k, v in row.items() if v}, ensure_ascii=False),
                }


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--full", action="store_true")
    p.add_argument("--region", choices=VOIVODESHIPS)
    p.add_argument("--date-from")
    p.add_argument("--limit", type=int, default=None, help="Cap rows per dataset (for testing)")
    p.add_argument("--batch-size", type=int, default=5000)
    p.add_argument("--db-host", default=os.environ.get("GEO_DB_HOST", "145.239.2.73"))
    p.add_argument("--db-port", type=int, default=int(os.environ.get("GEO_DB_PORT", "5432")))
    p.add_argument("--db-name", default=os.environ.get("GEO_DB_NAME", "gruntomat_geo"))
    p.add_argument("--db-user", default=os.environ.get("GEO_DB_USER", "gruntomat"))
    p.add_argument("--db-password", default=os.environ.get("GEO_DB_PASSWORD", "gruntomat_dev"))
    args = p.parse_args()

    # Build plan
    plan = []
    if args.region:
        plan.append((args.region, f"{GUNB_BASE}/wynik_{args.region}.zip", f"./data/gunb/wynik_{args.region}.zip", "rwd"))
    elif args.full:
        for r in VOIVODESHIPS:
            plan.append((r, f"{GUNB_BASE}/wynik_{r}.zip", f"./data/gunb/wynik_{r}.zip", "rwd"))
        for d in ZGLOSZENIA_DATASETS:
            plan.append((d, f"{GUNB_BASE}/wynik_{d}.zip", f"./data/gunb/wynik_{d}.zip", "zgloszenia"))
    else:
        plan.append(("opolskie", f"{GUNB_BASE}/wynik_opolskie.zip", "./data/gunb/wynik_opolskie.zip", "rwd"))

    logger.info("Plan: %s", [p[0] for p in plan])

    conn = psycopg2.connect(
        host=args.db_host, port=args.db_port, dbname=args.db_name,
        user=args.db_user, password=args.db_password, connect_timeout=30,
    )

    total_seen = 0
    total_upserted = 0
    t0 = time.time()

    try:
        for label, url, local_path, kind in plan:
            try:
                zip_path = download_if_missing(url, local_path)
            except Exception:
                logger.exception("Failed to download %s — skipping", url)
                continue

            logger.info("Ingesting %s (%s)", label, kind)
            batch = []
            ds_seen = 0

            for rec in iter_records(zip_path, label, kind, args.date_from):
                total_seen += 1
                ds_seen += 1
                batch.append(rec)

                if len(batch) >= args.batch_size:
                    with conn.cursor() as cur:
                        psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch, page_size=1000)
                    conn.commit()
                    total_upserted += len(batch)
                    batch.clear()
                    if total_upserted % 25000 == 0:
                        elapsed = time.time() - t0
                        rate = total_upserted / elapsed if elapsed > 0 else 0
                        logger.info("  progress: upserted=%d  rate=%.0f rows/s  elapsed=%.0fs", total_upserted, rate, elapsed)

                if args.limit and ds_seen >= args.limit:
                    break

            if batch:
                with conn.cursor() as cur:
                    psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch, page_size=1000)
                conn.commit()
                total_upserted += len(batch)
                batch.clear()

            logger.info("Finished %s: ds_seen=%d total_upserted=%d", label, ds_seen, total_upserted)

        # STEP 2: Fill geom from lots_enriched JOIN — single SQL, no HTTP.
        logger.info("Geocoding via lots_enriched JOIN (this may take a few minutes)...")
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE gunb_investments gi
                SET geom = ST_Centroid(le.geom)
                FROM lots_enriched le
                WHERE le.id_dzialki = gi.parcel_id
                  AND gi.geom IS NULL
            """)
            geocoded = cur.rowcount
        conn.commit()
        logger.info("Geocoded %d rows via lots_enriched JOIN", geocoded)

    finally:
        conn.close()

    elapsed = time.time() - t0
    logger.info("=" * 60)
    logger.info("DONE in %.0fs", elapsed)
    logger.info("  rows seen:      %d", total_seen)
    logger.info("  rows upserted:  %d", total_upserted)
    logger.info("  rows geocoded:  %d (via lots_enriched JOIN)", geocoded)


if __name__ == "__main__":
    main()
