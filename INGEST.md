# Data ingest runbook

Operational steps for refreshing locally-loaded datasets (transactions,
listings, RWDZ investments, `roszczenia.csv`). These run outside the deploy
pipeline — `alembic upgrade head` handles schema, but row data has to be
pushed in manually with the scripts under `backend/scripts/`.

See `SERVER.md` for SSH details. The compose file on prod is
`/home/deploy/dzialkowizja/docker-compose.prod.yml`.

## Roszczenia (KW + owner lookup)

Source: `roszczenia_keep_all_price55_sorted_prg_teryt.csv` (gitignored —
contains KW numbers and owner names). Schema lives in migrations
`003_roszczenia.py`, `004_roszczenia_rename_col.py`,
`005_roszczenia_kw_entities.py`, `011_roszczenia_owner_flags.py`,
`012_roszczenia_wartosc_old.py`.

The ingest script **truncates the table before inserting**, so each run
fully replaces the dataset — safe to re-run after schema changes.

### When to re-run

- After migration `005_roszczenia_kw_entities` (adds `kw` + `entities`
  columns — without a re-ingest the UI section "Księga wieczysta i
  właściciel" stays hidden because those columns are NULL).
- After migration `011_roszczenia_owner_flags` (adds
  `has_sluzebnosci`/`has_10_or_more_owners`/`has_state_owner` — without
  a re-ingest the S/10/P badges in the search dropdown never show).
- After migration `012_roszczenia_wartosc_old` (adds
  `wartosc_dzialki_old` — without a re-ingest the "Poprzednio"
  subtext in the Wartość działki panel stays hidden).
- After any future migration that adds/renames a column populated from
  the CSV.
- When a fresh `roszczenia*.csv` lands.

### Run on prod

```bash
ssh deploy@45.137.213.188
cd /home/deploy/dzialkowizja

# CSV lives in backend/ on the host (gitignored). The script accepts any
# path; "backend/roszczenia*.csv" is gitignored so any variant works.
docker compose -f docker-compose.prod.yml exec backend \
  python scripts/ingest_roszczenia_csv.py \
    /app/backend/roszczenia_keep_all_price55_sorted_prg_teryt.csv
```

If the CSV isn't on the host yet, copy it from your laptop first:

```bash
scp backend/roszczenia_keep_all_price55_sorted_prg_teryt.csv \
    deploy@45.137.213.188:/home/deploy/dzialkowizja/backend/
```

### Run locally

```bash
docker compose exec backend \
  python scripts/ingest_roszczenia_csv.py \
    /app/backend/roszczenia_keep_all_price55_sorted_prg_teryt.csv
```

The backend container mounts the repo, so the file appears at
`/app/backend/roszczenia_keep_all_price55_sorted_prg_teryt.csv`.

### Expected output

```
YYYY-MM-DD HH:MM:SS INFO connecting to appdb:5432/dzialkowizja as app
YYYY-MM-DD HH:MM:SS INFO scanned 482977 rows → 482977 unique plots kept (0 dropped as malformed)
YYYY-MM-DD HH:MM:SS INFO inserted 20000 rows
...
YYYY-MM-DD HH:MM:SS INFO done — 482977 rows in roszczenia
```

Takes ~30 s on prod.

### Verify

Pick any plot from the CSV (first column) and hit the API — you should
get a 200 with populated `kw` and `entities`, not a 404:

```bash
curl -s -b cookies.txt \
  "https://gruntify.duckdns.org/api/roszczenia/240205_2.0011.249%2F86" \
  | jq .
```

(Cookies needed because endpoint is behind auth; log in via the UI once
and export cookies, or run the curl from inside the backend container.)

## GUNB RWDZ (permit and zgłoszenie records)

Source: voivodeship CSVs from GUNB's RWDZ portal. Loaded into
`gruntomat.gunb_investments` (not the app DB — it's spatial data).

```bash
docker compose -f docker-compose.prod.yml exec backend \
  python scripts/ingest_gunb_rwdz.py /app/backend/rwdz_YYYY/*.csv
```

See the script's docstring for column mapping and dedup behaviour.
