# Icons and flags, step 1: delivered to the repo (2026-10-30)

Implements `icons_implementation_proposal.md`. You said "ok implement", so I took **D1-D8 as recommended** (nothing in your message changed one). The repo is changed; **nothing is deployed on the host** (steps: `icons_deploy_runbook.md`). Backups before the work: `backup_before_icons_2026-10-30.tar.gz` (repo) and `backup_before_postman_icons_2026-10-30.tar.gz` (Postman folder).

## What is in the repo

| Part | Files |
|---|---|
| Table `asset_agg_icon` (id, name/summary in 3 languages, `key`, `svg` text, `sha256`, creator, timestamps, `updated_at` trigger; no `is_public`, no file) | `app/assets/models/models_agg/icon.py` |
| Nullable `icon_id` (FK, RESTRICT, indexed) on **22 tables**: 20 reference tables (one change in `ReferenceBaseMixin`), `compendium_cat_country`, `compendium_cat_region` | `app/core/base.py`, `country.py`, `region.py` |
| SVG cleaner (allow-list; reports what it removed), upload reading, file serving (ETag, 304, PNG, safe headers), usage list for the 409 | `app/assets/services/icon_svg.py`, `icon_upload.py`, `icon_files.py`, `icon_usage.py` |
| 8 routes under `/api/v1/assets/icons`: list, upload, get one, update, delete, `{id}/file`, `by-key/{key}/file`, `PUT {id}/file` (replace the SVG) | `app/assets/routes/icon/` |
| `icon_id` in Create, Update, Read (also in the short country and region objects that are nested in other answers) | `app/core/schemas/ref.py`, `app/profile/schemas/access_policy.py`, `app/compendium/schemas/country.py`, `region.py` |
| An unknown `icon_id` answers 422 `icon_not_found` (create, update; one handler) and names the row in a CSV import (one check) | `app/main.py`, `app/core/utils/integrity.py`, `app/core/utils/csv_import.py` |
| Upload guard for icons (300 KB, `ICON_MAX_UPLOAD_KB`); the other messages are unchanged | `app/core/utils/upload_limit.py`, `api_paths.py`, `config.py` |
| Event log: an icon's create, update and delete entries do not hold the SVG text | `app/management/utils/event_logger.py`, `seed_entity_types.py` |
| Resource type `icon`, policies: administrator all, everybody else read | `scripts/init_seed.py`, `scripts/sql/icons_policy.sql` |
| Migration and loader | `scripts/sql/icons_preflight.sql`, `icons_ddl.sql`, `icons_link.sql`, `icons_rollback.sql`, `scripts/seed_icons.py` |
| Live check (73 checks) | `scripts/icons_check.py` |
| Tests | `tests/test_icon_svg.py` (305), `tests/test_icons.py` (23); three registries extended: `test_expand_routes.py`, `test_expand_wiring.py`, `test_list_routes.py` |
| **Swagger** | the overview text in `app/main.py` (also lists the `assets` app now), every `icon_id` field has a description in every Create, Update and Read schema, every icon route has a summary and description, the 22 CSV-import descriptions list `icon_id` automatically |
| README | new section "Icons and flags", the assets table, the variable `ICON_MAX_UPLOAD_KB`, the reference data and CSV notes |

## What I measured

| Check | Result |
|---|---|
| Whole test suite | **866 passed** (before: 538) |
| Deliberate mistakes in the new code (37 in the unit-tested code and 10 more through the live check) | all caught except 1: removing the delete route's own usage check changes nothing from outside, because the database `RESTRICT` rule refuses the delete and the route answers the same 409 (an equivalent mutant; the database rule is the real safety net). One test was too weak (a table missing from the DDL loop was not seen) and is stronger now |
| Live check `scripts/icons_check.py` against a running API (Postgres 16 + PostGIS, Redis, seeded users, the 270 flags) | **73 of 73** |
| Migration: database built by the OLD code and migrated with `icons_ddl.sql` against a database that `create_all` builds from the NEW code | **identical**: 1,342 statements each, 0 differences (script: `icons_tools/schema_diff.sh`) |
| Migration tests on real data (643 reference rows, 250 countries, 1,570 regions, 270 flags; preflight, DDL twice, old code on the new schema, loader, link, RESTRICT, rollback) | 13 passed (`icons_tools/test_icons_migration.py`) |
| `icons_policy.sql` | gives exactly the 7 rows `init_seed.py` gives, also when run twice |
| Routes | 252 (2 WebSocket); 8 new, none removed, none changed except the 22 CSV-import descriptions; probe 249 routes 0 problems; 0 undefined names |
| Postman (rebuilt, 296 requests) with Newman against a live API with a Celery worker | 311 calls, 381 assertions; the only failures are the 28 Upload CSV requests with no file chosen (as before) |
| Compared with the backup | exactly 25 new and 23 changed files; no stray file in the repo |

Versions of that sandbox: Python 3.12 (your image is `python:3.12-slim`), FastAPI 0.162.0, Starlette 1.10.0, pydantic 2.14.2, SQLAlchemy 2.1.6, asyncpg 0.32.0, PostgreSQL 16.10 + PostGIS 3.5 (your host: `postgis/postgis:15`; I did not run it on 15).

## Where it differs from the proposal, and what I found while building

1. **Replace the SVG:** `PUT /assets/icons/{id}/file` (multipart) instead of "PATCH with a file". `PATCH` changes names, summaries and the key only. Same result, cleaner HTTP.
2. **The cleaner reports what it removed** (`response_details.removed`, for example `["<script> x1", "onclick x1"]`). The proposal said the prototype did not do this yet; the repo version does, and it is tested.
3. **`scripts/sql/icons_policy.sql` is new.** `init_seed.py` deletes and rebuilds every policy row, so on the host it would erase hand-made policies. The new script adds only the `icon` resource type and its 7 rows. Fresh databases still use `init_seed.py`.
4. **A bug the live check found:** the first version of the "unknown icon_id" handler never matched, because asyncpg keeps "is not present in table" in a separate detail field. The handler now matches the start of the message ("insert or update on table ...", not the delete side), and unit tests pin both cases.
5. **Behaviour change you should know about:** the event log's `ignore_fields` setting was only applied to updates. It now also applies to the created and deleted entries (needed so that an icon's 300 KB SVG is never copied into the log). The only other entity with `ignore_fields` is `profile_usr_user` (`last_active_at`, `updated_at`): its created and deleted entries no longer contain those two fields.
6. **Three registry tests had to be extended** (`test_expand_routes`, `test_expand_wiring`, `test_list_routes`): they keep an exact list of routes, expandable schemas and list routes. This is the safety net working as intended.
7. **`Routing/api_routes_list.md` was already out of date** (228 routes, before the assets app). It is regenerated from the route table (249 routes under `/api/v1`) with a new script `api_routes_tools/make_routes_list.py`.
8. Names are lower case: `key` must be lower case and is lower-cased on upload and in the filters; `ship` and `Ship` (both in `core_ref_compendium_type`) share the icon `ship`.
9. The upload size guard now stores its limit as `(bytes, number, unit)`, so the message for an icon says "KB" and the existing messages ("MB") are unchanged.

## Not done, on purpose

- **Nothing on the host.** Not run against your host or its database.
- **Card renderer unchanged** (D7): it still reads the flag files from disk.
- **No artwork for the reference tables or regions** (D8): 424 icon texts (151 library-style, 273 app keys) and the 1,570 regions have no icon yet; their `icon_id` is empty, which step 1 allows. Which icon library does your front end use for the `icon` text? That decides where the 151 + 273 drawings come from.
- **Step 2** (all links filled, `icon_id` required, `icon` text dropped) is yours; its points are in section 8 of `icons_implementation_proposal.md`. One thing to settle first: regions need an icon if it becomes required (the 1,544 municipalities have no own flag).

## Files

`icons_implementation_proposal.md` (plan), `icons_deploy_runbook.md` (host steps), `icons_tools/` (migration test, schema comparison), `postman/` (rebuilt collection, `sample_icon.svg`), `api_routes_list.md` (regenerated), `host_deploy_all_changes_runbook.md` (a banner points to the icons runbook).

## Addendum 2026-10-30 (later): the icon set, graphics for every icon text

You sent `icon_names.csv` (437 icon texts with the names of the rows that use them) and asked for an Excel and a way to create all icons with graphics. Delivered in the repo and in `Routing/icons_import/`:

| Part | What |
|---|---|
| `Routing/icons_import/icon_set.xlsx` | sheet `README`, sheet `icons` (the list to edit), sheet `import` (finished, with the SVG text); formulas recalculated, 0 errors |
| `Routing/icons_import/icons_import.csv`, `icon_preview.html` | the CSV to load, and a page that shows every icon |
| `scripts/icon_sources/icon_map.csv` | one row per key (438: your 437 plus `image`, the icon text of the resource type `icon`): names in 3 languages, kind, value, colour, tag; the source of truth |
| `scripts/icon_sources/lucide/` | the 205 Lucide SVG files that are used, with the ISC licence text |
| `scripts/make_icon_set.py` | map -> CSV with the SVG of every icon (`--svg-dir`, `--preview`); standard library only; refuses a wrong map and says which row |
| `scripts/seed_icons.py --csv` | loads that CSV (cleaned like an upload; `--update`, `--dry-run`; names and summaries too); `--dir` for folders (flags) as before |
| `scripts/sql/icons_list_keys.sql` | the query you asked for earlier |
| `tests/test_icon_set.py` | 461 tests |

How the 437 keys got a graphic: 113 have exactly the name of a Lucide icon; 242 others are mapped by hand to a fitting Lucide glyph (including the Font-Awesome-looking names such as `masks-theater` -> `drama`); the 67 difficulty grades are generated badges (T3, IV, WI4) in the colour of the value in your seed data; the 15 difficulty and visibility levels are generated bars; the 6 rarities are the Lucide gem in the colour of the value. Sports that would look the same carry a small two-letter tag (six bike sports: RD, GR, MT, EN, DH and plain). 47 rows are marked `redraw` in the Excel (the same glyph several times in one table): replace those first when you have better artwork.

What I measured: all 438 graphics pass the cleaner unchanged and draw something (438 tests); the Excel sheet `icons` saved as CSV regenerates `icons_import.csv` byte for byte and the sheet `import` equals it row for row; on a fresh database with your real seed icon texts (flags + CSV + `icons_link.sql`): 438 keys, 0 without an icon, **660 of 660 reference rows linked** (`Ship` and `ship` share one icon), the pictures are served as SVG and PNG by key; 13 deliberate mistakes in the generator, importer and map were each caught; whole suite **1,327 passed**.

Honest limits: placeholders are Lucide outlines, not custom drawings; the corner tag is white text on a dark label (made for a light screen); the PNG text of a grade badge uses the fonts of the machine that draws it (Arial or a similar sans-serif); I did not run any of this on your host.

Countries: nothing more is needed. The 270 flags are loaded with `seed_icons.py --dir ...flags` (runbook section 5) and `icons_link.sql` links the 250 countries by `flag_<iso code>`. Regions still have no icon.

## Addendum 2026-10-30 (last): all icons through the API

You asked for the import as an API call. Done, in the repo:

| Part | What |
|---|---|
| `POST /api/v1/assets/icons/upload-csv` | multipart `file` = the CSV (`key`, `svg`, optional names); options `dry_run` (check and count, save nothing), `update` (replace icons whose key exists), `link` (default on: afterwards set `icon_id` where the icon text or code matches a key). Administrator only. Answer: `inserted`, `updated`, `unchanged`, `rejected` + `errors` (by row number), `notes` (what the cleaner removed), `linked`, `still_without_icon` |
| `POST /api/v1/assets/icons/link` | only the linking (`dry_run`); the API version of `icons_link.sql`; needs the update permission on reference data |
| `app/assets/services/icon_csv.py`, `icon_link.py` | the logic; `scripts/seed_icons.py --csv` now uses the same code, so API and script cannot differ |
| Limits | `ICON_CSV_MAX_UPLOAD_MB` 5, `ICON_CSV_MAX_ROWS` 2000, checked by the size guard (413) and the route |
| Postman | three requests in `assets / icons`: Upload icons CSV (dry run), Upload icons CSV (import all), Link rows to icons by key; the collection now has 300 requests and `icons_import.csv` next to it as the sample file |
| Tests | `tests/test_icon_import.py` (16), `scripts/icons_check.py` (101 checks, 28 new), Newman |

What I measured: your real `icons_import.csv` against a live API (fresh database, your seed icon texts, 2 countries, the 270 flags loaded): dry run `inserted 438`, database unchanged (270 icons before and after); import `inserted 438`, 660 of 660 reference rows and both countries linked, 0 keys without an icon; a second import `unchanged 438, linked {}`; `update=true` with nothing different changes nothing. Deliberate mistakes: 9 in the routes and services broken one at a time and run through the live check, 12 more through the unit tests, 4 on the permission checks, all caught (after one unit test was strengthened: the old SVG text must never be read when an icon is replaced). Newman: 314 calls, 389 assertions, only the 28 Upload CSV requests without a file fail (as before). Whole suite: **1,343 passed**. Routes: 254 (2 WebSocket), probe 251 routes 0 problems.

Behaviour to know: the import is all-or-nothing for the accepted rows (one commit; wrong rows are skipped and named, as the other CSV imports do); `update=true` needs the update permission on icons and `link=true` needs it on reference data (both administrator-only by default, checked before anything is saved); `dry_run` runs the real code including the linking and then rolls back, so its counts are exact; the bulk linking is not written to the event log row by row (the created and replaced icons are, without the SVG text); an icon id comes from its key (uuid5), or a random one if that id belongs to an icon whose key was renamed. Not run on your host.
