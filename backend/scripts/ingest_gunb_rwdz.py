#!/usr/bin/env python3
"""Ingest GUNB RWDZ (Rejestr Wniosków, Decyzji i Zgłoszeń) into gruntomat.gunb_investments.

Data source
-----------
GUNB publishes public, daily-refreshed CSV dumps of RWDZ at:
    https://wyszukiwarka.gunb.gov.pl/pobranie.html

Per-voivodeship ZIPs (16 files) contain building-permit records ("rwd"):
    ./pliki_pobranie/wynik_{voivodeship}.zip        (1 CSV inside)

Nationwide notification ZIPs (zgłoszenia, 2 files):
    ./pliki_pobranie/wynik_zgloszenia_2016_2021.zip
    ./pliki_pobranie/wynik_zgloszenia_2022_up.zip

Columns are separated by `#`, encoded in UTF-8, no quoting.
The CSVs do NOT contain coordinates — only TERYT + parcel components.
We resolve geometry via ULDK GUGiK (https://uldk.gugik.gov.pl/), which accepts
an ID shaped like `{jednostka_numer_ew}.{obreb_numer}.{numer_dzialki}` (exactly
the components GUNB provides) and returns an EPSG:2180 polygon. We centroid it
client-side and persist the point.

A local `uldk_parcel_cache` table keeps the geocode lookups idempotent and
rate-limit-friendly so re-runs don't re-query GUGiK.

Usage
-----
    # Smoke test against a single voivodeship, default 100 rows:
    python backend/scripts/ingest_gunb_rwdz.py --limit 100

    # Specific region:
    python backend/scripts/ingest_gunb_rwdz.py --region opolskie --limit 500

    # Zgłoszenia (notifications) file:
    python backend/scripts/ingest_gunb_rwdz.py --dataset zgloszenia_2022_up --limit 200

    # Full run for one region (writes everything; still respects --date-from):
    python backend/scripts/ingest_gunb_rwdz.py --region opolskie --full

    # Full run across ALL regions + zgłoszenia (long; do not run casually):
    python backend/scripts/ingest_gunb_rwdz.py --full

Environment
-----------
Reads DB credentials from the standard backend env vars (same as `app.config`):
    GEO_DB_HOST / GEO_DB_PORT / GEO_DB_NAME / GEO_DB_USER / GEO_DB_PASSWORD

Or falls back to CLI flags --db-host / --db-user / --db-password / ...
"""

from __future__ import annotations

import argparse
import csv

# RWDZ CSVs occasionally contain fields (typically the free-text opis) that
# exceed Python's default 128 KB limit. Bump to platform max so the parser
# doesn't choke partway through a voivodeship.
csv.field_size_limit(2**31 - 1)
import hashlib
import io
import json
import logging
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Iterator

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("ingest_gunb_rwdz")

GUNB_BASE = "https://wyszukiwarka.gunb.gov.pl/pliki_pobranie"

VOIVODESHIPS = [
    "dolnoslaskie", "kujawsko-pomorskie", "lubelskie", "lubuskie", "lodzkie",
    "mazowieckie", "malopolskie", "opolskie", "podkarpackie", "podlaskie",
    "pomorskie", "slaskie", "swietokrzyskie", "warminsko-mazurskie",
    "wielkopolskie", "zachodniopomorskie",
]

ZGLOSZENIA_DATASETS = ["zgloszenia_2016_2021", "zgloszenia_2022_up"]

ULDK_URL = "https://uldk.gugik.gov.pl/"
ULDK_USER_AGENT = "dzialkowizja-rwdz-ingest/0.1 (+https://dzialkowizja.pl)"
ULDK_TIMEOUT = 15
ULDK_RATE_DELAY = 0.05  # 20 req/s soft cap; GUGiK comfortably handles more


# --- Data model --------------------------------------------------------------

@dataclass
class Record:
    source_id: str
    typ: str
    status: str | None
    data_wniosku: date | None
    data_decyzji: date | None
    inwestor: str | None
    organ: str | None
    teryt_gmi: str | None
    wojewodztwo: str | None
    gmina: str | None
    miejscowosc: str | None
    adres: str | None
    opis: str | None
    kategoria: str | None
    rodzaj_inwestycji: str | None
    parcel_id: str | None
    kubatura: float | None
    raw_data: dict


# --- CSV parsing -------------------------------------------------------------

def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    # GUNB uses "YYYY-MM-DD HH:MM:SS"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _clean(s: str | None) -> str | None:
    if s is None:
        return None
    s = s.strip()
    return s or None


def _parse_kubatura(s: str | None) -> float | None:
    s = _clean(s)
    if s is None:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _build_parcel_id(
    jednostka: str | None,
    obreb: str | None,
    dzialka: str | None,
) -> str | None:
    jednostka = _clean(jednostka)
    obreb = _clean(obreb)
    dzialka = _clean(dzialka)
    if not (jednostka and obreb and dzialka):
        return None
    return f"{jednostka}.{obreb}.{dzialka}"


def _hash_source_id(*parts: str | None) -> str:
    blob = "|".join((p or "") for p in parts)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()  # noqa: S324 (not crypto)


def _rwd_row_to_record(row: dict, dataset_label: str) -> Record | None:
    """Convert a parsed 'wynik_{voivodeship}.csv' row (pozwolenia na budowę)."""
    numer_urzad = _clean(row.get("numer_urzad"))
    organ = _clean(row.get("nazwa_organu"))
    jednostka = _clean(row.get("jednosta_numer_ew"))
    obreb = _clean(row.get("obreb_numer"))
    dzialka = _clean(row.get("numer_dzialki"))
    parcel_id = _build_parcel_id(jednostka, obreb, dzialka)

    source_id = _hash_source_id(
        dataset_label, numer_urzad, organ, parcel_id,
        row.get("data_wplywu_wniosku"), row.get("data_wydania_decyzji"),
    )

    data_decyzji = _parse_date(row.get("data_wydania_decyzji"))
    status = "decyzja_wydana" if data_decyzji else "w_toku"

    ulica = _clean(row.get("ulica"))
    nr_domu = _clean(row.get("nr_domu"))
    adres = " ".join(x for x in [ulica, nr_domu] if x) or None

    return Record(
        source_id=source_id,
        typ="pozwolenie_budowa",
        status=status,
        data_wniosku=_parse_date(row.get("data_wplywu_wniosku")),
        data_decyzji=data_decyzji,
        inwestor=_clean(row.get("nazwa_inwestor")),
        organ=organ,
        teryt_gmi=_clean(row.get("terc")),
        wojewodztwo=_clean(row.get("wojewodztwo")),
        gmina=None,  # not directly present; miejscowosc is the closest proxy
        miejscowosc=_clean(row.get("miasto")),
        adres=adres,
        opis=_clean(row.get("nazwa_zamierzenia_bud"))
            or _clean(row.get("nazwa_zam_budowlanego")),
        kategoria=_clean(row.get("kategoria")),
        rodzaj_inwestycji=_clean(row.get("rodzaj_inwestycji")),
        parcel_id=parcel_id,
        kubatura=_parse_kubatura(row.get("kubatura")),
        raw_data=row,
    )


def _zgloszenie_row_to_record(row: dict, dataset_label: str) -> Record | None:
    """Convert a parsed 'wynik_zgloszenia_*.csv' row (zgłoszenia)."""
    numer_urzad = _clean(row.get("numer_ewidencyjny_urzad"))
    numer_sys = _clean(row.get("numer_ewidencyjny_system"))
    organ = _clean(row.get("nazwa_organu"))
    jednostka = _clean(row.get("jednostki_numer"))
    obreb = _clean(row.get("obreb_numer"))
    dzialka = _clean(row.get("numer_dzialki"))
    parcel_id = _build_parcel_id(jednostka, obreb, dzialka)

    source_id = _hash_source_id(
        dataset_label, numer_sys, numer_urzad, organ, parcel_id,
        row.get("data_wplywu_wniosku_do_urzedu"),
    )

    stan = _clean(row.get("stan"))
    # normalise obvious states
    status_map = {
        "brak sprzeciwu": "brak_sprzeciwu",
        "sprzeciw": "sprzeciw",
    }
    status = status_map.get(stan.lower(), stan) if stan else None

    ulica = _clean(row.get("ulica"))
    nr_domu = _clean(row.get("nr_domu"))
    adres = " ".join(x for x in [ulica, nr_domu] if x) or None

    return Record(
        source_id=source_id,
        typ="zgloszenie",
        status=status,
        data_wniosku=_parse_date(row.get("data_wplywu_wniosku_do_urzedu")),
        data_decyzji=None,  # zgłoszenia don't have a decision date per row
        inwestor=None,      # zgłoszenia CSV does not expose investor name
        organ=organ,
        teryt_gmi=_clean(row.get("terc")),
        wojewodztwo=_clean(row.get("wojewodztwo_objekt")),
        gmina=None,
        miejscowosc=_clean(row.get("miasto")),
        adres=adres,
        opis=_clean(row.get("nazwa_zam_budowlanego")),
        kategoria=_clean(row.get("kategoria")),
        rodzaj_inwestycji=_clean(row.get("rodzaj_zam_budowlanego")),
        parcel_id=parcel_id,
        kubatura=_parse_kubatura(row.get("kubatura")),
        raw_data=row,
    )


def iter_csv_records(
    zip_path: str,
    dataset_label: str,
    row_mapper,
    date_from: date | None = None,
) -> Iterator[Record]:
    with zipfile.ZipFile(zip_path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
        if not names:
            raise RuntimeError(f"No CSV in {zip_path}")
        with zf.open(names[0]) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            reader = csv.DictReader(text, delimiter="#")
            for row in reader:
                rec = row_mapper(row, dataset_label)
                if rec is None:
                    continue
                if date_from and (rec.data_wniosku or rec.data_decyzji):
                    ref = rec.data_decyzji or rec.data_wniosku
                    if ref and ref < date_from:
                        continue
                yield rec


# --- Download helpers --------------------------------------------------------

def download_if_missing(url: str, dest_path: str) -> str:
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 0:
        logger.info("Using cached %s", dest_path)
        return dest_path
    logger.info("Downloading %s -> %s", url, dest_path)
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": ULDK_USER_AGENT})
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest_path, "wb") as out:  # noqa: S310
        while True:
            chunk = resp.read(1024 * 64)
            if not chunk:
                break
            out.write(chunk)
    return dest_path


# --- ULDK geocoder -----------------------------------------------------------

class UldkClient:
    """Thin ULDK (GUGiK) client with a PostgreSQL-backed cache."""

    def __init__(self, conn):
        self.conn = conn
        self._session_hits = 0
        self._session_misses = 0
        self._session_notfound = 0
        self._last_call = 0.0

    def _cache_get(self, parcel_id: str):
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT ST_X(geom), ST_Y(geom), not_found"
                " FROM uldk_parcel_cache WHERE parcel_id = %s",
                (parcel_id,),
            )
            return cur.fetchone()

    def _cache_set(self, parcel_id: str, xy: tuple[float, float] | None):
        with self.conn.cursor() as cur:
            if xy is None:
                cur.execute(
                    "INSERT INTO uldk_parcel_cache (parcel_id, geom, not_found)"
                    " VALUES (%s, NULL, TRUE)"
                    " ON CONFLICT (parcel_id) DO UPDATE SET"
                    "   geom = EXCLUDED.geom,"
                    "   not_found = EXCLUDED.not_found,"
                    "   resolved_at = NOW()",
                    (parcel_id,),
                )
            else:
                x, y = xy
                cur.execute(
                    "INSERT INTO uldk_parcel_cache (parcel_id, geom, not_found)"
                    " VALUES (%s, ST_SetSRID(ST_MakePoint(%s, %s), 2180), FALSE)"
                    " ON CONFLICT (parcel_id) DO UPDATE SET"
                    "   geom = EXCLUDED.geom,"
                    "   not_found = EXCLUDED.not_found,"
                    "   resolved_at = NOW()",
                    (parcel_id, x, y),
                )

    def _fetch(self, parcel_id: str) -> tuple[float, float] | None:
        # No per-call sleep: when running under a ThreadPoolExecutor the
        # shared _last_call counter is racy anyway, and with 16+ workers
        # the effective request rate is bounded by per-request latency,
        # not by a software-side delay. Throttle by lowering
        # --geocode-workers instead if GUGiK ever starts pushing back.
        params = {
            "request": "GetParcelById",
            "id": parcel_id,
            "result": "geom_wkt",
            "srid": "2180",
        }
        url = f"{ULDK_URL}?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": ULDK_USER_AGENT})

        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=ULDK_TIMEOUT) as resp:  # noqa: S310
                    body = resp.read().decode("utf-8", errors="replace")
                break
            except Exception as exc:
                logger.warning("ULDK error for %s (attempt %d): %s", parcel_id, attempt + 1, exc)
                time.sleep(0.5 * (attempt + 1))
        else:
            return None

        # ULDK returns two lines: "0\n<wkt>" on success, "1\n..." on error.
        lines = body.splitlines()
        if not lines or not lines[0].strip().startswith("0"):
            return None
        if len(lines) < 2:
            return None
        wkt = lines[1].strip()
        # Strip SRID prefix
        if ";" in wkt:
            wkt = wkt.split(";", 1)[1]
        if not wkt.startswith("POLYGON") and not wkt.startswith("MULTIPOLYGON"):
            return None
        # crude centroid via coord average — good enough for point indexing
        try:
            inner = wkt[wkt.index("(("):].strip("() ")
            # for MULTIPOLYGON keep first ring
            if "),(" in inner:
                inner = inner.split("),(", 1)[0]
            inner = inner.strip("() ")
            pts = []
            for pair in inner.split(","):
                xs, ys = pair.strip().split()
                pts.append((float(xs), float(ys)))
            if not pts:
                return None
            cx = sum(p[0] for p in pts) / len(pts)
            cy = sum(p[1] for p in pts) / len(pts)
            return (cx, cy)
        except Exception:
            logger.warning("Failed to parse WKT for %s: %s", parcel_id, wkt[:80])
            return None

    def resolve(self, parcel_id: str) -> tuple[float, float] | None:
        cached = self._cache_get(parcel_id)
        if cached is not None:
            x, y, not_found = cached
            if not_found:
                self._session_notfound += 1
                return None
            self._session_hits += 1
            return (x, y)
        xy = self._fetch(parcel_id)
        self._cache_set(parcel_id, xy)
        self._session_misses += 1
        if xy is None:
            self._session_notfound += 1
        return xy

    def resolve_many(
        self, parcel_ids: list[str | None], workers: int = 16
    ) -> list[tuple[float, float] | None]:
        """Resolve a batch of parcel IDs in parallel.

        DB access (cache reads/writes) stays on the calling thread —
        psycopg2 connections are not thread-safe — so only the outbound
        HTTP calls are parallelised. The caller gets results back in the
        same order as the input list.
        """
        import concurrent.futures

        results: list[tuple[float, float] | None] = [None] * len(parcel_ids)
        to_fetch: list[tuple[int, str]] = []

        # Pass 1: sequential cache lookup.
        for idx, pid in enumerate(parcel_ids):
            if pid is None:
                results[idx] = None
                continue
            cached = self._cache_get(pid)
            if cached is not None:
                x, y, not_found = cached
                if not_found:
                    self._session_notfound += 1
                    results[idx] = None
                else:
                    self._session_hits += 1
                    results[idx] = (x, y)
            else:
                to_fetch.append((idx, pid))

        if not to_fetch:
            return results

        # Pass 2: parallel HTTP fetches (no DB touch inside threads).
        def _job(item: tuple[int, str]) -> tuple[int, str, tuple[float, float] | None]:
            i, pid = item
            return i, pid, self._fetch(pid)

        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            fetched = list(ex.map(_job, to_fetch))

        # Pass 3: back on the main thread, persist to cache and fill results.
        for idx, pid, xy in fetched:
            self._cache_set(pid, xy)
            self._session_misses += 1
            if xy is None:
                self._session_notfound += 1
            results[idx] = xy

        return results

    def stats(self) -> dict:
        return {
            "cache_hits": self._session_hits,
            "cache_misses_fetched": self._session_misses,
            "not_found": self._session_notfound,
        }


# --- DB upsert ---------------------------------------------------------------

UPSERT_SQL = """
INSERT INTO gunb_investments (
    source_id, typ, status, data_wniosku, data_decyzji, inwestor, organ,
    teryt_gmi, wojewodztwo, gmina, miejscowosc, adres, opis, kategoria,
    rodzaj_inwestycji, parcel_id, kubatura, geom, raw_data, ingested_at
) VALUES (
    %(source_id)s, %(typ)s, %(status)s, %(data_wniosku)s, %(data_decyzji)s,
    %(inwestor)s, %(organ)s, %(teryt_gmi)s, %(wojewodztwo)s, %(gmina)s,
    %(miejscowosc)s, %(adres)s, %(opis)s, %(kategoria)s, %(rodzaj_inwestycji)s,
    %(parcel_id)s, %(kubatura)s,
    CASE WHEN %(gx)s IS NULL THEN NULL
         ELSE ST_SetSRID(ST_MakePoint(%(gx)s, %(gy)s), 2180) END,
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
    geom = COALESCE(EXCLUDED.geom, gunb_investments.geom),
    raw_data = EXCLUDED.raw_data,
    ingested_at = NOW();
"""


def upsert_batch(conn, rows: list[tuple[Record, tuple[float, float] | None]]):
    params = []
    for rec, xy in rows:
        gx, gy = (xy if xy else (None, None))
        params.append({
            "source_id": rec.source_id,
            "typ": rec.typ,
            "status": rec.status,
            "data_wniosku": rec.data_wniosku,
            "data_decyzji": rec.data_decyzji,
            "inwestor": rec.inwestor,
            "organ": rec.organ,
            "teryt_gmi": rec.teryt_gmi,
            "wojewodztwo": rec.wojewodztwo,
            "gmina": rec.gmina,
            "miejscowosc": rec.miejscowosc,
            "adres": rec.adres,
            "opis": rec.opis,
            "kategoria": rec.kategoria,
            "rodzaj_inwestycji": rec.rodzaj_inwestycji,
            "parcel_id": rec.parcel_id,
            "kubatura": rec.kubatura,
            "gx": gx,
            "gy": gy,
            "raw_data": json.dumps(rec.raw_data, ensure_ascii=False),
        })
    with conn.cursor() as cur:
        psycopg2.extras.execute_batch(cur, UPSERT_SQL, params, page_size=200)
    conn.commit()


# --- Orchestration -----------------------------------------------------------

def dataset_plan(
    region: str | None,
    dataset: str | None,
    full: bool,
) -> list[tuple[str, str, str, str]]:
    """Return list of (label, url, local_path, kind) to process.

    kind in {"rwd", "zgloszenia"}.
    """
    plan: list[tuple[str, str, str, str]] = []

    def _rwd(reg: str):
        return (
            reg,
            f"{GUNB_BASE}/wynik_{reg}.zip",
            f"./data/gunb/wynik_{reg}.zip",
            "rwd",
        )

    def _zgl(ds: str):
        return (
            ds,
            f"{GUNB_BASE}/wynik_{ds}.zip",
            f"./data/gunb/wynik_{ds}.zip",
            "zgloszenia",
        )

    if dataset:
        if dataset in ZGLOSZENIA_DATASETS:
            plan.append(_zgl(dataset))
        elif dataset in VOIVODESHIPS:
            plan.append(_rwd(dataset))
        else:
            raise SystemExit(f"Unknown --dataset {dataset}")
        return plan

    if region:
        if region not in VOIVODESHIPS:
            raise SystemExit(f"Unknown --region {region}")
        plan.append(_rwd(region))
        return plan

    if full:
        for r in VOIVODESHIPS:
            plan.append(_rwd(r))
        for d in ZGLOSZENIA_DATASETS:
            plan.append(_zgl(d))
        return plan

    # Default smoke test: the smallest voivodeship.
    plan.append(_rwd("opolskie"))
    return plan


def run(args):
    conn = psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password,
        connect_timeout=15,
    )
    conn.autocommit = False
    uldk = UldkClient(conn)

    plan = dataset_plan(args.region, args.dataset, args.full)
    logger.info("Plan: %s", [p[0] for p in plan])

    date_from: date | None = None
    if args.date_from:
        date_from = datetime.strptime(args.date_from, "%Y-%m-%d").date()

    total_seen = 0
    total_upserted = 0
    total_with_geom = 0
    total_missing_parcel = 0
    total_geocoded_now = 0

    try:
        for label, url, local_path, kind in plan:
            try:
                zip_path = download_if_missing(url, local_path)
            except Exception:
                logger.exception("Failed to download %s", url)
                continue

            mapper = _rwd_row_to_record if kind == "rwd" else _zgloszenie_row_to_record
            logger.info("Ingesting %s (%s)", label, kind)

            rec_buffer: list[Record] = []
            per_dataset_seen = 0
            limit = args.limit if not args.full else None

            def flush_buffer():
                nonlocal total_upserted, total_with_geom, total_missing_parcel, total_geocoded_now
                if not rec_buffer:
                    return
                parcel_ids = [r.parcel_id for r in rec_buffer]
                before_misses = uldk._session_misses
                resolved = uldk.resolve_many(parcel_ids, workers=args.geocode_workers)
                total_geocoded_now += uldk._session_misses - before_misses
                rows: list[tuple[Record, tuple[float, float] | None]] = []
                for rec, xy in zip(rec_buffer, resolved):
                    if rec.parcel_id is None:
                        total_missing_parcel += 1
                    if xy is not None:
                        total_with_geom += 1
                    rows.append((rec, xy))
                upsert_batch(conn, rows)
                total_upserted += len(rows)
                rec_buffer.clear()

            for rec in iter_csv_records(zip_path, label, mapper, date_from=date_from):
                total_seen += 1
                per_dataset_seen += 1
                rec_buffer.append(rec)

                if len(rec_buffer) >= args.batch_size:
                    flush_buffer()
                    if total_upserted % (args.batch_size * 5) == 0:
                        logger.info(
                            "  progress: seen=%d upserted=%d geom=%d uldk=%s",
                            total_seen, total_upserted, total_with_geom, uldk.stats(),
                        )

                if limit and per_dataset_seen >= limit:
                    break

            flush_buffer()

            logger.info(
                "Finished %s: seen=%d, upserted_total=%d, geom_total=%d",
                label, per_dataset_seen, total_upserted, total_with_geom,
            )
    finally:
        conn.close()

    logger.info("=" * 60)
    logger.info("DONE")
    logger.info("  rows seen:             %d", total_seen)
    logger.info("  rows upserted:         %d", total_upserted)
    logger.info("  rows with geometry:    %d", total_with_geom)
    logger.info("  rows missing parcel:   %d", total_missing_parcel)
    logger.info("  geocoded this run:     %d", total_geocoded_now)
    logger.info("  uldk stats:            %s", uldk.stats())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--limit", type=int, default=100,
                   help="Cap rows per dataset (default 100; ignored with --full).")
    p.add_argument("--full", action="store_true",
                   help="Ingest everything in the planned datasets (no --limit).")
    p.add_argument("--region", choices=VOIVODESHIPS,
                   help="Only ingest a single voivodeship (rwd).")
    p.add_argument("--dataset", help="Specific dataset label (voivodeship or zgloszenia_*).")
    p.add_argument("--date-from", dest="date_from",
                   help="YYYY-MM-DD — skip rows strictly older than this.")
    p.add_argument("--batch-size", type=int, default=200)
    p.add_argument("--geocode-workers", type=int, default=16,
                   help="Parallel ULDK geocode workers per batch (default 16).")

    p.add_argument("--db-host", default=os.environ.get("GEO_DB_HOST", "145.239.2.73"))
    p.add_argument("--db-port", type=int, default=int(os.environ.get("GEO_DB_PORT", "5432")))
    p.add_argument("--db-name", default=os.environ.get("GEO_DB_NAME", "gruntomat"))
    p.add_argument("--db-user", default=os.environ.get("GEO_DB_USER", "gruntomat"))
    p.add_argument("--db-password", default=os.environ.get("GEO_DB_PASSWORD", "gruntomat_dev"))

    args = p.parse_args()
    run(args)


if __name__ == "__main__":
    main()
