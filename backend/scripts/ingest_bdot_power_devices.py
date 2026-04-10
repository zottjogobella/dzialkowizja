"""Ingest BDOT10k point / polygon electric devices into bdot_power_devices.

Unlike OT_SULN_L (which is strictly overhead power LINES), electric devices
live in several BDOT10k classes and each class is a mixed bag of unrelated
'rodzaj' values, so every class is filtered down to the electro-only subset:

    OT_BUWT_P  (Point)   → 'słup energetyczny'
    OT_BUIT_P  (Point)   → 'transformator', 'zespół transformatorów'
    OT_BUIT_A  (Polygon) → 'zespół transformatorów'
    OT_KUPG_P  (Point)   → 'podstacja elektroenergetyczna', 'elektrownia', 'elektrociepłownia'
    OT_KUPG_A  (Polygon) → 'podstacja elektroenergetyczna', 'elektrownia', 'elektrociepłownia'

Everything else (sports fields in BUSP, chimneys and telecom masts in BUWT,
fuel pumps in BUIT, factories and mines in KUPG, …) is discarded.

The script downloads per-powiat GML zips from opendata.geoportal.gov.pl,
extracts the five XML layers, converts each to GeoJSON with ogr2ogr
(EPSG:2180 preserved), and bulk-inserts the matching features into
bdot_power_devices on the gruntomat database.

Usage:
    # Run on a single województwo (recommended for tests):
    python backend/scripts/ingest_bdot_power_devices.py --woj 16

    # Run on a single powiat (for debugging):
    python backend/scripts/ingest_bdot_power_devices.py --powiat 1601

    # Run on every województwo (WARNING: many GB of downloads):
    python backend/scripts/ingest_bdot_power_devices.py --all

Idempotent: for each powiat the script first deletes existing rows
matching source_powiat before inserting.

Requires a system `ogr2ogr` binary (same dependency as ingest_bdot_powerlines.py).
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import httpx
import psycopg2
from psycopg2.extras import execute_values

logger = logging.getLogger("ingest_bdot_power_devices")

WFS_CAP_URL = (
    "https://mapy.geoportal.gov.pl/wss/service/PZGIK/BDOT/WFS/PobieranieBDOT10k"
    "?service=WFS&version=2.0.0&request=GetFeature"
    "&typeNames=ms:BDOT10k_powiaty&PROPERTYNAME=TERYT,URL_GML"
)

DB_HOST = os.environ.get("GEO_DB_HOST", "145.239.2.73")
DB_PORT = int(os.environ.get("GEO_DB_PORT", "5432"))
DB_NAME = os.environ.get("GEO_DB_NAME", "gruntomat")
DB_USER = os.environ.get("GEO_DB_USER", "gruntomat")
DB_PASSWORD = os.environ.get("GEO_DB_PASSWORD", "gruntomat_dev")


# Per-class whitelist of 'rodzaj' values we accept + derived category tag.
# Keys are the BDOT10k class suffix without the 'OT_' prefix (matches filenames
# like 'PL.PZGiK.1833.1601__OT_BUWT_P.xml').
ACCEPTED: dict[str, dict[str, str]] = {
    "OT_BUWT_P": {
        "słup energetyczny": "slup",
    },
    "OT_BUIT_P": {
        "transformator": "transformator",
        "zespół transformatorów": "transformator",
    },
    "OT_BUIT_A": {
        "zespół transformatorów": "transformator",
    },
    "OT_KUPG_P": {
        "podstacja elektroenergetyczna": "podstacja",
        "elektrownia": "elektrownia",
        "elektrociepłownia": "elektrownia",
    },
    "OT_KUPG_A": {
        "podstacja elektroenergetyczna": "podstacja",
        "elektrownia": "elektrownia",
        "elektrociepłownia": "elektrownia",
    },
}

CLASS_SUFFIXES = tuple(f"{c}.xml" for c in ACCEPTED.keys())


def db_connect():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=15,
    )


def list_powiaty() -> dict[str, str]:
    """Return {teryt4: url_gml} for all powiaty via the WFS index."""
    logger.info("Fetching powiat index from WFS …")
    with httpx.Client(timeout=60) as client:
        resp = client.get(WFS_CAP_URL)
        resp.raise_for_status()
        xml = resp.text
    teryts = re.findall(r"<ms:TERYT>(\d+)</ms:TERYT>", xml)
    urls = re.findall(r"<ms:URL_GML>([^<]+)</ms:URL_GML>", xml)
    if len(teryts) != len(urls):
        raise RuntimeError(
            f"WFS index malformed: {len(teryts)} TERYTs vs {len(urls)} URLs"
        )
    return dict(zip(teryts, urls))


def download_zip(url: str, dest: Path) -> None:
    logger.info("Downloading %s", url)
    with httpx.Client(timeout=300, follow_redirects=True) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            with dest.open("wb") as f:
                for chunk in resp.iter_bytes(chunk_size=1 << 16):
                    f.write(chunk)
    logger.info("Saved %s (%.1f MB)", dest, dest.stat().st_size / 1e6)


def extract_device_xmls(zip_path: Path, out_dir: Path) -> dict[str, Path]:
    """Extract the 5 electric-device BDOT classes. Returns {class_name: path}.

    Class name is e.g. 'OT_BUWT_P'. Classes missing from the zip are simply
    not present in the returned dict.
    """
    results: dict[str, Path] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            if not member.endswith(CLASS_SUFFIXES):
                continue
            # Identify the class: last '__OT_XXXX_Y.xml' segment
            stem = Path(member).stem  # e.g. PL.PZGiK.1833.1601__OT_BUWT_P
            if "__" not in stem:
                continue
            class_name = stem.split("__")[-1]  # OT_BUWT_P
            if class_name not in ACCEPTED:
                continue
            zf.extract(member, out_dir)
            results[class_name] = out_dir / member
    if not results:
        logger.warning("No electric-device XMLs found in %s", zip_path)
    return results


def gml_to_geojson(gml_path: Path) -> Path:
    """Convert GML (EPSG:2180) to GeoJSON, keeping 2180 coordinates."""
    out = gml_path.with_suffix(".geojson")
    if out.exists():
        out.unlink()
    cmd = [
        "ogr2ogr",
        "-f",
        "GeoJSON",
        "-a_srs",
        "EPSG:2180",
        str(out),
        str(gml_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ogr2ogr failed on {gml_path.name}: returncode={proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return out


def _feature_rows(geojson_path: Path, class_name: str, teryt_powiat: str):
    """Yield DB rows for features in this GeoJSON that match the class whitelist."""
    with geojson_path.open() as f:
        data = json.load(f)
    woj = teryt_powiat[:2]
    whitelist = ACCEPTED[class_name]
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if geom is None:
            continue
        rodzaj = props.get("rodzaj")
        if rodzaj not in whitelist:
            continue
        kategoria = whitelist[rodzaj]
        wersja = props.get("wersja") or None
        yield (
            props.get("gml_id"),
            props.get("lokalnyId"),
            class_name,
            rodzaj,
            kategoria,
            woj,
            teryt_powiat,
            wersja,
            json.dumps(geom),
        )


def ingest_powiat(teryt: str, url: str, work_dir: Path) -> int:
    """Process one powiat end-to-end. Returns number of rows inserted."""
    zip_path = work_dir / f"{teryt}_GML.zip"
    powiat_dir = work_dir / teryt
    powiat_dir.mkdir(parents=True, exist_ok=True)
    try:
        download_zip(url, zip_path)
        xmls = extract_device_xmls(zip_path, powiat_dir)
        if not xmls:
            return 0

        all_rows: list[tuple] = []
        per_class_counts: dict[str, int] = {}
        for class_name, gml_path in xmls.items():
            try:
                gj = gml_to_geojson(gml_path)
            except RuntimeError as e:
                logger.warning("  skip %s: %s", class_name, e)
                continue
            class_rows = list(_feature_rows(gj, class_name, teryt))
            per_class_counts[class_name] = len(class_rows)
            all_rows.extend(class_rows)

        logger.info("  [%s] per-class rows: %s", teryt, per_class_counts)
        if not all_rows:
            logger.info("  [%s] 0 matching features", teryt)
            # Still clear any stale rows from a previous run:
            conn = db_connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM bdot_power_devices WHERE source_powiat = %s",
                        (teryt,),
                    )
                conn.commit()
            finally:
                conn.close()
            return 0

        conn = db_connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM bdot_power_devices WHERE source_powiat = %s",
                    (teryt,),
                )
                execute_values(
                    cur,
                    """
                    INSERT INTO bdot_power_devices
                        (gml_id, lokalny_id, source_class, rodzaj, kategoria,
                         source_woj, source_powiat, wersja, geom)
                    VALUES %s
                    ON CONFLICT (gml_id) DO NOTHING
                    """,
                    all_rows,
                    template=(
                        "(%s, %s, %s, %s, %s, %s, %s, %s::timestamp,"
                        " ST_SetSRID(ST_GeomFromGeoJSON(%s), 2180))"
                    ),
                    page_size=500,
                )
                cur.execute(
                    "SELECT COUNT(*) FROM bdot_power_devices WHERE source_powiat = %s",
                    (teryt,),
                )
                inserted = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        logger.info("  [%s] inserted %d rows", teryt, inserted)
        return inserted
    finally:
        shutil.rmtree(powiat_dir, ignore_errors=True)
        if zip_path.exists():
            zip_path.unlink()


def run(args: argparse.Namespace) -> int:
    if not shutil.which("ogr2ogr"):
        logger.error("ogr2ogr not found in PATH. Install gdal (brew install gdal).")
        return 2

    index = list_powiaty()
    logger.info("Index: %d powiaty", len(index))

    if args.powiat:
        teryts = [args.powiat] if args.powiat in index else []
        if not teryts:
            logger.error("Unknown powiat TERYT %s", args.powiat)
            return 2
    elif args.woj:
        teryts = sorted(t for t in index if t.startswith(args.woj))
        if not teryts:
            logger.error("No powiaty found for woj %s", args.woj)
            return 2
    elif args.all:
        teryts = sorted(index.keys())
    else:
        logger.error("Must pass --powiat NNNN, --woj NN, or --all")
        return 2

    logger.info("Processing %d powiaty", len(teryts))
    total = 0
    with tempfile.TemporaryDirectory(prefix="bdot_dev_") as tmp:
        tmp_path = Path(tmp)
        for i, teryt in enumerate(teryts, 1):
            url = index[teryt]
            logger.info("[%d/%d] powiat %s", i, len(teryts), teryt)
            try:
                total += ingest_powiat(teryt, url, tmp_path)
            except Exception:
                logger.exception("Failed powiat %s — continuing", teryt)

    logger.info("DONE. Total inserted: %d rows", total)
    return 0


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--woj",
        type=str,
        help="TERYT województwa (e.g. 16 for opolskie)",
    )
    group.add_argument(
        "--powiat",
        type=str,
        help="TERYT powiatu (4 digits, e.g. 1601)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run on every powiat in Poland (WARNING: many GB)",
    )
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
