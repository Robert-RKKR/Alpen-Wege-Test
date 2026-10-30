# Icons and flags: implementation proposal, step 1 (new table, nullable links, migration)

Status: **IMPLEMENTED 2026-10-30** with D1-D8 as recommended (see `icons_delivery.md` for what was built, measured and changed against this plan; host steps in `icons_deploy_runbook.md`). The text below is the plan as it was proposed; the drafts mentioned in sections 6, 7 and 9 are now the repo files `scripts/sql/icons_*.sql`, `scripts/seed_icons.py` and `app/assets/services/icon_svg.py`, and `icons_tools/` keeps only the migration test and the schema comparison.

This follows `icons_and_flags_proposal.md`. Your answers there, as I read them: SVG yes; the pictures in a dedicated assets table, not the photo table; SVG text in the table; a link from the other tables. You chose the name `asset_agg_icon` (the earlier proposal said `asset_cat_icon`; I use yours). Region scope (D6 there) is not decided yet; step 1 does not need it.

## 1. What I understood

1. New table `asset_agg_icon` in the assets app. Fields like `asset_agg_photo`, but with the SVG text instead of a file.
2. A new column `icon_id` (link to `asset_agg_icon`) on every table that has an `icon` text today (the 19 `core_ref_*` tables plus `core_ref_resource_type`, 20 in total), and on `compendium_cat_country` and `compendium_cat_region`. 22 tables.
3. **Step 1 (this document):** only add. All new columns are nullable, the old `icon` text stays and works as before.
4. **Step 2 (later, by you):** fill all links, make `icon_id` required, remove the old `icon` text. Section 8 lists what I would prepare now so that step 2 is easy.

Two small points I assumed. Each row gets **one** icon (`icon_id`, not a list). The link is always from the other table to the icon (many rows can share one icon).

## 2. What I measured in the repo and in the seed data

| Topic | Result |
|---|---|
| Tables with an `icon` text | 20 (19 in `models_ref` plus `core_ref_resource_type`, which sits in `app/core/models/resource_type.py`). All get it from `ReferenceBaseMixin`, so one change in `app/core/base.py` covers all 20. |
| Seed rows | 643 reference rows, **424 distinct icon texts**. 151 look like icon-library names (`ferris-wheel`, `triangle-alert`; used by compendium types and companies), 273 are app keys with a table prefix (`sport_hiking`, `ach_cat_distance`) for which no drawing exists anywhere. Many rows share one text (50 companies: `company`; 107 gear types: `gear_type`). |
| Case problem in the data | `ship` and `Ship` both exist in `core_ref_compendium_type`. Keys in the new table are lower case only, so both rows get the same icon. A Windows or OneDrive folder cannot hold `Ship.svg` and `ship.svg` side by side; the loader lower-cases for this reason. |
| Flags | 270 SVG files in `app/compendium/cards/flags/`, 2.4 MB in total, the largest is 184 KB, 149 are under 2 KB. **All 250 countries have a file** (checked by script). 20 files have no country (`eu`, `gb-eng`, `es-ct`, `un`, ...). They contain no script, no external link, no embedded picture, no DOCTYPE, all `viewBox="0 0 512 512"`. |
| Regions | 1,570 rows in the seed, all with `iso_code`: 26 cantons (`CH-ZH`) and 1,544 municipalities (`CH-ZH-AK`), one country. |
| How tables are created | `create_all` at start, no migration framework, one idempotent SQL script per change (`scripts/sql/*.sql`). `create_all` creates the new table by itself but never adds a column to an existing table. |
| Container order | The `api` container bind-mounts the repo and reloads, so the database must match **before** the new code arrives. |
| Errors on a bad link | The app has no handler for database integrity errors; an unknown id in a foreign key ends in `500` today (the photo link is checked by hand in `check_photo_link`). |

## 3. Design

### 3.1 The table `asset_agg_icon`

| Photo field | Icon table | Why |
|---|---|---|
| `id` | `id` | same |
| `name`, `name_de`, `name_pl` | same (`name` required) | same |
| `summary`, `summary_de`, `summary_pl` | same | same |
| `created_by`, `created_at`, `updated_at` | same, plus the `moddatetime` trigger `trg_set_updated_at` | the live schema (`test/alpenwege_schema_new.sql`) has this trigger on nearly every table, but the models declare it only for track, job and settings, so a fresh `create_all` database lacks it on the others. The new table gets it in the DDL **and** through `event.listen` in the model (like `job.py`), so both ways give the same result. |
| `is_public` | **dropped** (D1) | icons are read by everybody |
| `location`, `altitude_m`, `taken_at` | dropped | meaningless for a drawing |
| `path` (file) | replaced by `svg` (text, NOT NULL) | you asked for the SVG in the table |
| (new) | `key` (unique, lower case) | the same text the reference tables hold in `icon`; this is how rows find their icon (D2) |
| (new) | `sha256` of the stored text | ETag, duplicate check |

Database rules (all tested): `key` lower case `a-z 0-9 _ . -`, 1-100 characters; `svg` must start with `<svg` and be at most 1 MB; `sha256` is 64 hex characters.

### 3.2 The links

`icon_id uuid NULL REFERENCES asset_agg_icon (id) ON DELETE RESTRICT` plus an index, on the 22 tables. `RESTRICT` means an icon that is still used cannot be deleted. In Python: one `declared_attr` in `ReferenceBaseMixin` (same pattern as `created_by`), plus two plain columns in country and region.

### 3.3 API (new, folder `app/assets/routes/icon/`, same layout as `photo`)

- `GET /assets/icons` (list; filters `q`, `key`, `key_prefix`, `created_by`, dates; sort), `GET /assets/icons/{id}`, `POST` (multipart upload of an `.svg`), `PATCH` (name, summary, key, or a replacement SVG), `DELETE` (`409` with the usage counts of all 22 tables, like the photo delete).
- `GET /assets/icons/{id}/file` returns `image/svg+xml`, with `ETag` = sha256, `Cache-Control: private, max-age=3600`, `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; sandbox`.
- `GET /assets/icons/by-key/{key}/file`: same, found by key (so `by-key/flag_at/file` and `by-key/sport_hiking/file` work with today's `icon` texts before any link is set) (D5).
- `?format=png&size=64` on both file routes (cairosvg is already a dependency) (D5).
- The JSON of an icon does not contain the SVG text; the text comes only through `/file`.
- All 22 resources get `icon_id` in Create, Update and Read. Lists of POIs and regions would show `country.icon_id` too (D3).

### 3.4 The SVG cleaner (`app/assets/services/icon_svg.py`, prototype tested)

Every SVG goes through `clean_svg()` on upload and in the loader; the database never holds a file as it came. It parses with `defusedxml` (no DOCTYPE, no entities), keeps only allow-listed elements and attributes, keeps only links inside the file (`#id`; plus `data:` PNG/JPEG/WebP on `<image>`), keeps only `url(#id)`, removes `<script>`, `<style>`, `<foreignObject>`, animation and foreign namespaces (Inkscape metadata), and limits size (300 KB), element count, nesting and `<use>` count.

### 3.5 Access

New resource key `icon` in `init_seed.py`, put in `REF_KEYS`: administrator all, everybody else read only (as the reference tables). Rerun `init_seed.py` (idempotent) after the deploy.

## 4. Decisions (answer with a number and "recommended" or your change)

**D1. Drop `is_public` and owner rules for icons?**
The reference tables are readable by all groups. If an icon could be private, a public reference row could point to a picture that a viewer may not read (a broken image). With `icon` in `REF_KEYS` there is nothing to hide, so the column would only be a trap.
Options: (a) drop it, admin writes, all read; (b) keep it like the photo, with viewer/editor creating own icons.
Recommendation: **(a)**.

**D2. Extra columns `key` and `sha256`, and a fixed id for seeded icons.**
Without `key` there is nothing to match the 424 old texts or the 250 ISO codes to. The loader gives a seeded icon an id that is computed from its key (uuid5), so in step 2 your seed CSV files can contain `icon_id` and load the same on every database. Icons created through the API get a normal random id.
Recommendation: **yes**.

**D3. Link name and expand.**
The ref tables already have a field called `icon` (the text), so `?expand=icon` cannot exist until step 2 removes the text. Options: (a) only `icon_id` now, expand `icon` in step 2; (b) expand under a temporary name now.
Also: put `icon_id` into the short country and region objects that are nested in POI and region lists, so a front end gets the flag id without an extra call.
Recommendation: **(a)**, and **yes** to the short objects.

**D4. Bad `icon_id` (an id that does not exist).**
Checking by hand in every create, update and CSV route would touch about 66 files (22 resources, three routes each). Instead: one handler in `app/main.py` that turns the database error of a constraint named `*_icon_id_fkey` into `422`, and one check inside `import_csv` (it knows the columns) that gives row-level CSV errors. Your earlier route migration needed two review rounds for bulk edits, so fewer edited files is safer.
Recommendation: **central handler plus the check in `import_csv`**.

**D5. Two extras on the file route: lookup by key, and PNG.**
By key helps the front end during the transition and for flags by ISO code. PNG (sizes 16 to 1024) helps Office files and cards.
Recommendation: **yes to both**.

**D6. Upload limit.**
Largest flag is 184 KB. New setting `ICON_MAX_UPLOAD_KB`, default 300 (next to `PHOTO_MAX_UPLOAD_MB`).
Recommendation: **300**.

**D7. Card renderer in step 1.**
It keeps reading the flag files from disk (no change, no risk). In step 2 it can read the flag through `country.icon_id` with the files as fallback.
Recommendation: **unchanged in step 1**.

**D8. Artwork for the reference tables.**
Step 1 loads the 270 flags only. For the 424 reference texts a drawing is needed: the 151 library-style names could come from an icon set (I think they are Lucide names; the licence must be checked; please confirm which library the front end uses). The 273 app keys (`sport_hiking`, ...) need drawings that someone chooses or draws. Until then their `icon_id` stays NULL, which is fine for step 1.
Recommendation: **flags now, reference artwork when you have it** (the loader and the link script work for any folder of SVG files).

Accept everything: answer `D1-D8 recommended`.

## 5. Code changes after approval

| Area | Change |
|---|---|
| New | `app/assets/models/models_agg/icon.py` (registered in both `__init__.py`; trigger via `event.listen` like `job.py`), `app/assets/services/icon_svg.py`, `app/assets/routes/icon/` (`_router`, `create`, `get_many`, `get_one`, `update`, `delete`, `file`), icon schemas in `app/assets/schemas/asset.py`, setting `ICON_MAX_UPLOAD_KB`, router registered in `app/assets/routes/__init__.py` |
| `app/core/base.py` | `icon_id` in `ReferenceBaseMixin` (covers 20 models) |
| Country, region models | one `icon_id` column each |
| Schemas | `app/core/schemas/ref.py` (Base Create/Update/Read: all ref schemas inherit), `app/profile/schemas/access_policy.py` (resource type), `app/compendium/schemas/country.py`, `region.py` |
| Routes | **none** for the 22 resources: create and update pass `icon_id` through `model_dump(exclude_unset=True)` (read in sport type, region, country and resource type; the other 18 ref folders have the same shape and the review must confirm each) |
| Central | `app/main.py` (handler, D4), `app/core/utils/csv_import.py` (check, D4) |
| Seed | `scripts/init_seed.py` (resource type `icon`, `REF_KEYS`), `scripts/seed_icons.py`, `scripts/sql/icons_*.sql` |
| Tools and docs | route map and route rules for the new routes, tests, `scripts/icons_check.py` (live), Postman regeneration, README section, combined host runbook |

Implementation order: A cleaner and its tests; B model and DDL, with a check that a fresh `create_all` database equals a migrated one; C icon routes; D the 22 schemas, handler and CSV check; E seed, link, `init_seed`; F docs, Postman, runbook. Each part would get a backup tarball first, and a mutation check of its own tests, as before.

## 6. Migration process (step 1)

Scripts are in `Routing/icons_tools/` and would live in `scripts/sql/` and `scripts/`. Every SQL script is idempotent and runs in one transaction.

| # | Command | What it does |
|---|---|---|
| 0 | backup: `pg_dump` plus the repo tarball | the usual rule |
| 1 | `psql < icons_preflight.sql` | **read-only.** Checks that the 22 tables exist, no clashing `icon_id` column, every icon text can become a key, the extension is available. Prints OK / PROBLEM / NOTE (it reports `Ship / ship`). Fix any PROBLEM first. |
| 2 | `psql < icons_ddl.sql` | creates `asset_agg_icon` (rules, trigger, comments) and adds `icon_id`, the foreign key (RESTRICT), the index and a comment to the 22 tables |
| 3 | copy the new code (on the test stack the api container reloads) | the database already matches, so nothing breaks |
| 4 | `python scripts/init_seed.py` | adds the resource type `icon` and rebuilds the policy matrix |
| 5 | `python scripts/seed_icons.py --dir app/compendium/cards/flags --prefix flag_ --dash-to-underscore --name-template "Flag {STEM}"` | cleans and loads the 270 flags. `--dry-run` first. Existing keys are untouched (`--update` replaces). Exit code 1 if a file is rejected, the others are still loaded. |
| 6 | `psql < icons_link.sql` | sets `icon_id` where an icon with the matching key exists: reference tables by `lower(icon)`, countries by `flag_` + ISO code, regions by `flag_` + ISO code with `-` as `_`. Only fills empty links, never overwrites. Prints how many were linked and how many are still empty per table. Run it again after every later load. |
| 7 | checks (below) | |

Expected result on your seed data (measured): 270 icons; **250 of 250 countries linked**; regions 0 of 1,570 (no region artwork yet); reference rows 0 of 643 until their artwork is loaded, then all of them (also `ship` and `Ship`); a second run of step 6 links nothing.

Checks after the run:

```sql
SELECT count(*) FROM asset_agg_icon;                                              -- 270
SELECT count(*) FROM compendium_cat_country WHERE icon_id IS NULL;                -- 0
SELECT count(*) FROM compendium_cat_country c JOIN asset_agg_icon i ON i.id = c.icon_id
 WHERE i.key <> 'flag_' || lower(c.iso_code);                                     -- 0
```

**Backward compatible:** the old `icon` text and its data are untouched (compared by checksum in the test); the previous application version keeps working on the new schema, because its inserts and updates do not know `icon_id` and the column is nullable (tested).

**Rollback:** stop the new code, run `icons_rollback.sql` (drops the 22 columns and the table with its rows; the old text was never touched), start the old code. The icons can be rebuilt with step 5.

**Host:** nothing from this is on the host yet (like the earlier changes). The same steps go into the combined runbook `host_deploy_all_changes_runbook.md` as one more section; the flag files are already inside the repo, so only the code and `scripts/` folders need copying.

## 7. What was tested (sandbox, real PostgreSQL, your seed data)

| Test | Result |
|---|---|
| `test_icons_migration.py`: 643 reference rows, 250 countries, 1,570 regions, the 270 real flags; preflight, DDL twice, old-app inserts, table rules, trigger, seeding (dry run, second run, bad files), linking (manual link kept, 22 tables, idempotent), RESTRICT delete, rollback, rollback then DDL again (`pg_dump -s` equal) | 13 passed |
| `test_icon_svg_prototype.py`: all 270 flags cleaned and **rendered pixel for pixel the same** as the original; 22 further tests (script, event handlers, foreignObject, `<style>` import, animation, `javascript:` and external links, nested data SVG, external `url()`, DOCTYPE, entity bomb, external entity, foreign root with script, size, element count, depth, `<use>` flood, a typical outline icon) | 294 passed |
| Deliberate mistakes (mutation check, as in your earlier work) | 15 cleaner changes and 16 SQL and loader changes were each caught by a test. Two cleaner changes were first **not** caught (one was my wrong patch, one was a real test gap: a non-SVG root with a viewBox); the test was added and both are caught now. |

Not tested here, to be done in implementation: the SQLAlchemy models and a fresh `create_all` (the sandbox PostgreSQL has no PostGIS), `init_seed.py`, the routes and the handler (including how asyncpg reports the constraint name), and the real `moddatetime` extension (a stand-in with the same call was used). The cleaner prototype does not yet report what it removed; the upload response should list it (for example "removed `<style>`"), because silent removal can change how an icon looks.

## 8. Step 2 preview (your next step) and what to prepare now

Order, because old code must keep working in every state: (1) all rows linked (a query shows 0 NULL); (2) deploy code where `icon_id` is required in Create and the `icon` text is gone from schemas, seeds, tests and Postman; (3) `SET NOT NULL` on `icon_id`; (4) a last script drops the `icon` column (after a backup).

Points to settle before step 2, none needed for step 1:

1. **Regions must have an icon if `icon_id` becomes required.** The 1,544 municipalities have no own flag. Option: set them to the same icon row as their canton (and cantons to the country flag). That makes "required" true without a fallback rule, but a later change of the country flag then has to be repeated per region. Or keep `icon_id` optional on regions only.
2. **Seeds.** `init_seed.py` inserts the 16 resource types with an `icon` text by raw SQL; in step 2 it needs `icon_id`, so `seed_icons.py` must run first. The `push_data` CSV files get an `icon_id` column (that is what the fixed ids from D2 are for) and `order.json` gets `asset_agg_icon` before the `core_ref_*` tables.
3. **The 273 app keys need drawings** before they can be required (D8).
4. **Expand name** `icon` becomes free (D3), and the card renderer can switch to the database (D7).
5. `core_ref_resource_type` is created by `init_seed.py`, not by CSV; keep that in mind for the order.

## 9. Files in `Routing/icons_tools/`

| File | Purpose |
|---|---|
| `icons_preflight.sql` | read-only checks before the DDL |
| `icons_ddl.sql` | step 1 DDL (table, 22 links) |
| `icons_link.sql` | links by key, re-runnable |
| `icons_rollback.sql` | undo of step 1 |
| `seed_icons.py` | loader draft (cleaner, key from file name, fixed id, dry run) |
| `icon_svg_prototype.py` | cleaner prototype |
| `test_icon_svg_prototype.py`, `test_icons_migration.py` | the tests above (need `FLAGS_DIR` / `ALPEN_DIR`, pgserver, cairosvg, defusedxml) |
