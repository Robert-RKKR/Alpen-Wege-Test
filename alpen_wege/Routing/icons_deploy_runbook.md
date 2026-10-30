# Icons and flags, step 1: deploy on the host (copy by hand)

Written 2026-10-30. Nothing in this file has been run against your host or your database. Every command was written from scripts that passed in my sandbox (Postgres 16 + PostGIS, Redis, Celery worker; results in `icons_delivery.md`).

**Order matters:** the new code reads the new columns, and the running api would create the table but never the columns (`create_all` does not alter tables). So: stop, copy, **database first**, then start.

This runbook assumes the host already runs the current repo (the combined runbook `host_deploy_all_changes_runbook.md` is done). If not, do this in the combined runbook instead: run the four icon SQL scripts of section 4 here right after its SQL scripts and before `docker compose up -d --build`.

## 1. Look first (changes nothing)

```bash
cd ~/jrdurt
P="sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege"
$P -c "SELECT to_regclass('public.asset_agg_icon') AS icon_table, (SELECT count(*) FROM core_ref_resource_type) AS resource_types, (SELECT count(*) FROM compendium_cat_country) AS countries, (SELECT count(*) FROM compendium_cat_region) AS regions;"
$P -c "SELECT count(*) FROM core_ref_resource_type WHERE key = 'icon';"        # 0 before, 1 after
$P -c "SELECT extname FROM pg_extension WHERE extname = 'moddatetime';"          # must be there (the other tables use it)
```

Write the numbers down (countries 250 and regions 1,570 on your seed data).

## 2. Backups

```bash
cd ~/jrdurt
sudo docker exec alpen-postgres pg_dump -U alpenwege -d alpenwege -Fc > ~/backup_icons_$(date +%F_%H%M).dump
ls -l ~/backup_icons_*.dump                                                      # not empty
B=~/before_icons_$(date +%F_%H%M); echo "rollback folder: $B"
mkdir "$B" && cp -r app scripts tests README.md "$B"/ && ls "$B"
```

## 3. Stop, copy, check the files

```bash
cd ~/jrdurt
sudo docker stop alpen-api alpen-celery
```

Copy from your OneDrive repo into `~/jrdurt` (replace whole folders): `app/`, `scripts/`, `tests/`, `README.md`. Do **not** copy `Routing/`. The 270 flag files are already inside `app/compendium/cards/flags/`. What changed since the state before the icons: 25 new files (`app/assets/.../icon*`, `app/core/utils/integrity.py`, seven scripts (`seed_icons.py`, `icons_check.py` and five SQL files), two test files) and 23 changed ones; for the icon set (section 5b) also the new routes `upload-csv` and `link` (`app/assets/routes/icon/upload_csv.py`, `link.py`, `app/assets/services/icon_csv.py`, `icon_link.py`), `scripts/make_icon_set.py`, the folder `scripts/icon_sources/` (207 files), `scripts/sql/icons_list_keys.sql` and `tests/test_icon_set.py` (`seed_icons.py` and the README changed again) (the models, schemas and routes of the 22 tables, `app/main.py`, `app/config.py`, the CSV import, the event logger, `init_seed.py`, three test files, the README).

```bash
cd ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                          # must be 589
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum                      # must start with f8fa67d645862f97
ls scripts/sql | grep icons_                                                                         # icons_ddl.sql icons_link.sql icons_policy.sql icons_preflight.sql icons_rollback.sql
```

(Those two numbers are for the repo of 2026-10-30. If the count or the first hash differs, stop and tell me: another file differs from the repo I tested.)

## 4. Database, rebuild, start

```bash
cd ~/jrdurt
P="sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege"
$P < scripts/sql/icons_preflight.sql        # read only: every line OK, INFO or NOTE; a PROBLEM line means stop and tell me
```

Expected on your seed data: all 22 tables `OK`, `NOTE    icon texts that differ only in case: Ship / ship` (harmless: both rows get the same icon), 424 distinct icon texts. The `NOTE` can show more cases if you added values by hand.

```bash
$P < scripts/sql/icons_ddl.sql              # the table asset_agg_icon and icon_id on 22 tables; idempotent, one transaction
$P < scripts/sql/icons_policy.sql           # resource type "icon" and its 7 policy rows; adds only these (init_seed.py would rebuild ALL policies)
sudo docker compose up -d --build           # the worker has no bind mount, so it needs the rebuild
sleep 15; sudo docker logs --tail 60 alpen-api       # started, no traceback
sudo docker logs --tail 60 alpen-celery              # no ImportError
```

Do not run `init_seed.py` on the host: it deletes every policy row and builds them again from the script (your hand-made changes would be lost). `icons_policy.sql` does only the icon part. Run it **before** the api starts (as above): a policy that was looked up before it existed stays cached for 5 minutes. If it was late, wait 5 minutes or `sudo docker exec alpen-redis redis-cli --scan --pattern 'access_policy:*:icon' | xargs -r sudo docker exec -i alpen-redis redis-cli del`.

## 5. Load the flags and link them

```bash
cd ~/jrdurt
sudo docker exec alpen-api python /app/scripts/seed_icons.py --dir /app/app/compendium/cards/flags --prefix flag_ --dash-to-underscore --name-template "Flag {STEM}" --dry-run
#   270 files: 270 accepted (dry run), 0 rejected
sudo docker exec alpen-api python /app/scripts/seed_icons.py --dir /app/app/compendium/cards/flags --prefix flag_ --dash-to-underscore --name-template "Flag {STEM}"
#   270 files: 270 accepted (270 new, 0 updated, 0 unchanged), 0 rejected
$P < scripts/sql/icons_link.sql             # prints, per table, how many were linked and how many are still empty
```

`seed_icons.py` needs the user `admin@alpenwege.dev` (it is `created_by` of the icons); another user: `--admin-email`. Expected output of `icons_link.sql` on your data: countries `250 linked now, 0 still without icon_id`; regions `0 linked now, 1570 still` (no region artwork yet); the 20 reference tables `0 linked now` (no artwork for them yet). Run it again after every later load of icons: it fills only empty links and never changes one that is set.

```bash
$P -c "SELECT count(*) FROM asset_agg_icon;"                                                                   # 270
$P -c "SELECT count(*) FROM compendium_cat_country WHERE icon_id IS NULL;"                                     # 0
$P -c "SELECT count(*) FROM compendium_cat_country c JOIN asset_agg_icon i ON i.id = c.icon_id WHERE i.key <> 'flag_' || lower(c.iso_code);"   # 0
```

### 5b. The icons of all reference values (the icon set)

The flags are only part of it. `icons_import.csv` (next to `icon_set.xlsx` in `Routing/icons_import/`, also made by `scripts/make_icon_set.py`) has a graphic for every icon text of the reference tables and the resource types (438 keys). Two ways to load it; both do the same (same code):

**A. One API call (Postman or curl, nothing to copy to the host).** Log in as administrator, then:

```bash
curl -s -X POST "http://localhost:8000/api/v1/assets/icons/upload-csv?dry_run=true" -H "Authorization: Bearer $TOKEN" -F "file=@icons_import.csv"   # checks and counts, saves nothing
curl -s -X POST "http://localhost:8000/api/v1/assets/icons/upload-csv"              -H "Authorization: Bearer $TOKEN" -F "file=@icons_import.csv"   # creates the icons, then links the rows
```

In Postman: folder `assets / icons`, request **Upload icons CSV (dry run)**, then **Upload icons CSV (import all)** (the file `icons_import.csv` is chosen in the body; put it into the Postman working directory). Expected answer of the dry run on a database that has the flags and no icon set yet: `"inserted": 438, "updated": 0, "unchanged": 0, "rejected": 0`, `errors` empty, and `linked` per table (with `link=true`, the default). The real call returns the same numbers with `dry_run: false`; a second call returns `"unchanged": 438` and `"linked": {}`. A rejected row is named by row number in `errors`. `update=true` replaces icons whose key exists. **Link only:** `POST /api/v1/assets/icons/link` (`dry_run=true` counts first). Both routes are administrator only; they are not logged row by row in the event log (the created icons are).

**B. The script** (the same thing from a shell on the host):

```bash
cd ~/jrdurt
cp <your OneDrive>/Routing/icons_import/icons_import.csv ~/jrdurt/icons_import.csv      # the api container sees ~/jrdurt as /app
sudo docker exec alpen-api python /app/scripts/seed_icons.py --csv /app/icons_import.csv --dry-run
#   438 rows: 438 accepted (dry run), 0 rejected
sudo docker exec alpen-api python /app/scripts/seed_icons.py --csv /app/icons_import.csv
#   438 rows: 438 accepted (438 new, 0 updated, 0 unchanged), 0 rejected   (on a database that already has a key: "... unchanged")
$P < scripts/sql/icons_link.sql
```

Check either way: `$P < scripts/sql/icons_list_keys.sql | head -5` shows `icon_exists = t` for every row and `rows_linked` equal to `rows_using`.

`seed_icons.py --csv` and the API both accept an Excel export: in `icon_set.xlsx` save the sheet `import` as CSV UTF-8. Keys that your host has in addition (values added by hand since the seed) show up as `icon_exists = f` in `icons_list_keys.sql`: add a row for them to `scripts/icon_sources/icon_map.csv` (or a quick badge: kind `badge`, 1 to 3 letters, a colour), run `make_icon_set.py` and import again.

## 6. Checks

```bash
cd ~/jrdurt
r() { sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/route_map.py "$@"; }
r dump route_dumps/host_after_icons.json                 # 254 routes (2 WebSocket)
r probe route_dumps/host_after_icons.json                # OK: probed 251 routes, 0 problem(s)
r names                                                  # OK: 0 undefined name(s)
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -3     # 1343 passed
sudo docker exec -w /app alpen-api sh -c "pip install -q httpx && python scripts/icons_check.py --expect-flags 270" | tail -3   # 101 of 101 checks passed
```

`icons_check.py` needs the seeded users (password `!Password@5005`, `admin`, `editor`, `viewer`, `guest` @alpenwege.dev). If your host has other logins, run it on a copy of the database or skip it and use Postman. It creates and deletes a few rows (a company, a country, a region, a region type, a resource type, some icons); the event log keeps the entries. Hand test:

```bash
curl -s "http://localhost:8000/api/v1/assets/icons?key_prefix=flag_&limit=3" -H "Authorization: Bearer $TOKEN"        # a list of icons without the SVG text
curl -s "http://localhost:8000/api/v1/assets/icons/by-key/flag_ch/file" -H "Authorization: Bearer $TOKEN"            # the SVG
curl -s "http://localhost:8000/api/v1/assets/icons/by-key/flag_ch/file?format=png&size=64" -H "Authorization: Bearer $TOKEN" -o ch.png
curl -s "http://localhost:8000/api/v1/compendium/countries?q=switzerland" -H "Authorization: Bearer $TOKEN"          # icon_id of the flag in the answer
```

Postman: import `Routing/postman/Alpen API.postman_collection.json` again, and put `sample_icon.svg` into the Postman working directory next to the other sample files.

## 7. What changed for clients (tell your front end)

- Every reference value (the 19 `core` tables and `resource-types`), every country and every region has a new field **`icon_id`** (an id or `null`) in every answer, also where it is nested (a POI shows `main_region.icon_id`, a region `country.icon_id`). The old text `icon` is unchanged. Create and update accept `icon_id` (`null` removes it; an unknown id answers `422`, code `icon_not_found`; a CSV import names the row).
- New under `/api/v1/assets/icons`: list, upload (`multipart`, `201`), get one, **the picture** (`GET .../{id}/file`, or `GET .../by-key/{key}/file`, as SVG or `?format=png&size=64`, with `ETag`), replace the SVG (`PUT .../{id}/file`), update, delete (`409` while used). Everybody who is logged in reads, only the administrator writes.
- `by-key` works today with the text in `icon`: `GET /assets/icons/by-key/{icon text in lower case}/file` returns the picture as soon as an icon with that key exists.
- Nothing was removed and no URL changed.

## 8. Rollback

| Situation | What to do |
|---|---|
| A check in section 3 fails | The database was not touched: `sudo docker stop alpen-api alpen-celery`, put `$B/*` back into `~/jrdurt`, `sudo docker compose up -d --build` |
| A SQL script fails | It changed nothing (one transaction). Paste the error; do not continue |
| Done, and something is wrong | Stop the containers, then `$P < scripts/sql/icons_rollback.sql` (drops the 22 `icon_id` columns and `asset_agg_icon` **with its rows**; the old `icon` text was never touched), put `$B/*` back, `sudo docker compose up -d --build`. The icons can be loaded again with `seed_icons.py`. The resource type `icon` and its policy rows may stay: `DELETE FROM profile_access_policy a USING core_ref_resource_type r WHERE r.id = a.resource_type_id AND r.key = 'icon'; DELETE FROM core_ref_resource_type WHERE key = 'icon';` removes them. A full restore from `~/backup_icons_<date>.dump` is only for the case that the rollback script fails (every write after the backup is lost) |

The old code works on the new schema too (the columns are nullable and it does not know them), so if only the new code is faulty you can put the old code back **without** running the rollback script and keep the data.
