"""Ingest BDOT10k OT_SULN_L (linie elektroenergetyczne) into bdot_power_lines.

The script downloads per-powiat GML zips from opendata.geoportal.gov.pl, extracts
the OT_SULN_L layer, converts it to GeoJSON with ogr2ogr (CRS stays EPSG:2180),
and bulk-inserts the features into bdot_power_lines on the gruntomat database.

Source URL pattern (discovered via the WFS BDOT10k_powiaty index):
    https://opendata.geoportal.gov.pl/bdot10k/schemat2021/{woj2}/{teryt4}_GML.zip

Usage:
    # Run on a single województwo (recommended for tests):
    python backend/scripts/ingest_bdot_powerlines.py --woj 16

    # Run on a single powiat (for debugging):
    python backend/scripts/ingest_bdot_powerlines.py --powiat 1605

    # Run on every województwo (DO NOT run without thinking — many GB):
    python backend/scripts/ingest_bdot_powerlines.py --all

Idempotent: for each powiat the script first deletes existing rows
matching source_powiat before inserting, so re-running the same powiat
produces the same row count.

Requires a system `ogr2ogr` binary (from gdal). Install on macOS with
`brew install gdal` and on Debian/Ubuntu with `apt install gdal-bin`.

Requires `psycopg2` and `httpx` from backend/pyproject.toml.
"""

from __future__ import annotations

import argparse
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

logger = logging.getLogger("ingest_bdot_powerlines")

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


# BDOT10k 'rodzaj' → short class label used for filtering in the UI.
NAPIECIE_KLASA = {
    "linia elektroenergetyczna najwyższego napięcia": "najwyzsze",
    "linia elektroenergetyczna wysokiego napięcia": "wysokie",
    "linia elektroenergetyczna średniego napięcia": "srednie",
    "linia elektroenergetyczna niskiego napięcia": "niskie",
}


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
    """Return {teryt4: url_gml} for all 380 powiaty via the WFS index."""
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


def extract_suln_xml(zip_path: Path, out_dir: Path) -> Path | None:
    """Extract the OT_SULN_L file from the zip. Returns the extracted path,
    or None if the zip has no SULN layer (possible for rare powiaty)."""
    with zipfile.ZipFile(zip_path) as zf:
        suln_members = [n for n in zf.namelist() if n.endswith("OT_SULN_L.xml")]
        if not suln_members:
            logger.warning("No OT_SULN_L.xml in %s", zip_path)
            return None
        if len(suln_members) > 1:
            logger.warning("Multiple OT_SULN_L.xml in %s: %s", zip_path, suln_members)
        member = suln_members[0]
        zf.extract(member, out_dir)
        return out_dir / member


def gml_to_geojson(gml_path: Path) -> Path:
    """Convert the GML (EPSG:2180) to a GeoJSON keeping 2180 coordinates."""
    out = gml_path.with_suffix(".geojson")
    if out.exists():
        out.unlink()
    # -a_srs is critical: ogr2ogr sometimes loses the SRS tag on odd GMLs.
    # The BDOT files declare EPSG:2180 on every geometry so we just pass it through.
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
            f"ogr2ogr failed: returncode={proc.returncode}\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return out


def _feature_rows(geojson_path: Path, teryt_powiat: str):
    """Yield (gml_id, lokalny_id, rodzaj, napiecie_klasa, source_woj, source_powiat,
    wersja, geom_geojson) tuples from the GeoJSON file."""
    import json

    with geojson_path.open() as f:
        data = json.load(f)
    woj = teryt_powiat[:2]
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry")
        if geom is None:
            continue
        rodzaj = props.get("rodzaj")
        klasa = NAPIECIE_KLASA.get(rodzaj or "")
        wersja = props.get("wersja") or None
        yield (
            props.get("gml_id"),
            props.get("lokalnyId"),
            rodzaj,
            klasa,
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
        suln_path = extract_suln_xml(zip_path, powiat_dir)
        if suln_path is None:
            return 0
        geojson_path = gml_to_geojson(suln_path)
        rows = list(_feature_rows(geojson_path, teryt))
        if not rows:
            logger.info("  [%s] 0 features in OT_SULN_L", teryt)
            return 0

        conn = db_connect()
        try:
            with conn.cursor() as cur:
                # Idempotent: drop any previous rows from this powiat
                cur.execute(
                    "DELETE FROM bdot_power_lines WHERE source_powiat = %s",
                    (teryt,),
                )
                # Bulk insert. We rely on ST_GeomFromGeoJSON + ST_Force2D +
                # ST_SetSRID to normalise; features already have srid 2180 but
                # GeoJSON drops the CRS so we reassign explicitly.
                execute_values(
                    cur,
                    """
                    INSERT INTO bdot_power_lines
                        (gml_id, lokalny_id, rodzaj, napiecie_klasa,
                         source_woj, source_powiat, wersja, geom)
                    VALUES %s
                    ON CONFLICT (gml_id) DO NOTHING
                    """,
                    rows,
                    template=(
                        "(%s, %s, %s, %s, %s, %s, %s::timestamp,"
                        " ST_SetSRID(ST_GeomFromGeoJSON(%s), 2180))"
                    ),
                    page_size=500,
                )
                # execute_values with page_size reports only the last batch's
                # rowcount, so query the table directly instead.
                cur.execute(
                    "SELECT COUNT(*) FROM bdot_power_lines WHERE source_powiat = %s",
                    (teryt,),
                )
                inserted = cur.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        logger.info("  [%s] inserted %d rows", teryt, inserted)
        return inserted
    finally:
        # Clean up extracted files to save disk
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
    with tempfile.TemporaryDirectory(prefix="bdot_") as tmp:
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
        help="TERYT województwa (e.g. 16 for opolskie, 32 for zachodniopomorskie)",
    )
    group.add_argument(
        "--powiat",
        type=str,
        help="TERYT powiatu (4 digits, e.g. 1605)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Run on every powiat in Poland (WARNING: many GB of downloads)",
    )
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
