-- gunb_investments schema for "Aktywność inwestycyjna" feature.
--
-- Target DB: gruntomat (PostGIS, 145.239.2.73:5432). This table is NOT part
-- of the app's own Alembic-managed database — it lives alongside lots_enriched
-- so the investments endpoint can do spatial joins against plots directly.
--
-- Apply with:
--   PGPASSWORD=... psql -h 145.239.2.73 -U gruntomat -d gruntomat \
--       -f backend/scripts/gunb_investments_schema.sql
--
-- Source: GUNB RWDZ public CSV dumps (https://wyszukiwarka.gunb.gov.pl/pobranie.html)
-- Geometry: resolved from (jednostka_numer_ew + obreb_numer + numer_dzialki)
--           via ULDK GUGiK (https://uldk.gugik.gov.pl/) — EPSG:2180 polygon → centroid.

CREATE TABLE IF NOT EXISTS gunb_investments (
    id              SERIAL PRIMARY KEY,
    source_id       TEXT UNIQUE NOT NULL,  -- stable hash of numer_urzad + organ + parcel
    typ             TEXT,                  -- pozwolenie_budowa | zgloszenie | (future: warunki_zabudowy)
    status          TEXT,                  -- decyzja_wydana | brak_sprzeciwu | w_toku | ...
    data_wniosku    DATE,
    data_decyzji    DATE,
    inwestor        TEXT,
    organ           TEXT,                  -- nazwa_organu
    teryt_gmi       CHAR(7),               -- terc (7-char gmina TERYT, e.g. 1607014)
    wojewodztwo     TEXT,
    gmina           TEXT,
    miejscowosc     TEXT,
    adres           TEXT,                  -- ulica + nr domu
    opis            TEXT,                  -- nazwa_zamierzenia_bud / nazwa_zam_budowlanego
    kategoria       TEXT,                  -- kategoria obiektu (I..XXX)
    rodzaj_inwestycji TEXT,                -- rodzaj_inwestycji (raw)
    parcel_id       TEXT,                  -- pełny identyfikator (jedn._obreb.nr_dzialki) użyty do ULDK
    kubatura        NUMERIC,
    geom            GEOMETRY(Point, 2180), -- centroid działki z ULDK
    raw_data        JSONB,                 -- oryginalny wiersz CSV dla przyszłej analizy
    ingested_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS gunb_inv_geom_idx         ON gunb_investments USING GIST (geom);
CREATE INDEX IF NOT EXISTS gunb_inv_typ_idx          ON gunb_investments (typ);
CREATE INDEX IF NOT EXISTS gunb_inv_data_decyzji_idx ON gunb_investments (data_decyzji);
CREATE INDEX IF NOT EXISTS gunb_inv_data_wniosku_idx ON gunb_investments (data_wniosku);
CREATE INDEX IF NOT EXISTS gunb_inv_teryt_idx        ON gunb_investments (teryt_gmi);

-- Cache for ULDK geocoding (parcel_id -> point) so re-runs are fast and we
-- don't hammer GUGiK. Lives in a separate table so it can be reused by other
-- future features.
CREATE TABLE IF NOT EXISTS uldk_parcel_cache (
    parcel_id   TEXT PRIMARY KEY,
    geom        GEOMETRY(Point, 2180),
    resolved_at TIMESTAMP DEFAULT NOW(),
    not_found   BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS uldk_cache_geom_idx ON uldk_parcel_cache USING GIST (geom);
