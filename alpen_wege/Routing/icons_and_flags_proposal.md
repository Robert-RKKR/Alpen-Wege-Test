# Proposal: flags for countries and regions, and real icons for the reference tables

Status: PROPOSAL ONLY (2026-10-30). Nothing was changed in the repo. Decisions D1-D6 are open.

## 1. What I understood

You want (a) a flag for every country and for regions, stored in the database, and (b) a better answer for the `icon` column of all `core_ref_*` tables, which today is only a text name. You ask which format to use (SVG?), whether to store the pictures as photos, directly in each table, or in a new dedicated table in the `assets` app that the other tables point to.

Short answer: **SVG, stored in one new `assets` table (`asset_cat_icon`), and every table that needs a picture gets a nullable link (`icon_id`) to it.** Not the photo table.

Terms used below: *SVG* = a drawing stored as text (XML). It is sharp at any size and is usually a few KB. *Relation / link* = a column `icon_id` that holds the id of a row in another table (a foreign key).

## 2. What the repo has today (read from the code)

| Topic | Fact |
|---|---|
| Ref tables | 19 `core_ref_*` tables, about 640 seed rows. Column `icon` (text, NOT NULL) comes from `ReferenceBaseMixin` in `app/core/base.py`. The access policy table has an `icon` text too. |
| Icon values | Only key names like `sport_hiking`, `region_type_canton`. **There is no artwork for them anywhere in the repo.** The front end must map the name to a picture itself (unknown to me, see D5). |
| Card icons | The card templates draw 3 small icons inline (`type`, `altitude`, `difficulty`, in `render.py` / `parts.icon()`). This is a third, separate icon system. |
| Country flags | Already exist as files: `app/compendium/cards/flags/*.svg` (flag-icons library, MIT licence, square 512x512, one file per lower-case ISO code, plus extras such as `eu`, `es-ct`, `gb-eng`). Only the card renderer uses them (`flag_href()` turns the SVG into a 320 px PNG with cairosvg, cached). The API does not expose them. |
| Countries | 250 rows, `iso_code` unique text (`AT`, `CH`, ...). |
| Regions | About 1,570 rows in the seed file, almost all Swiss. Region types in the seed: Canton, District, Municipality. Only the 26 cantons carry a real ISO 3166-2 code (`CH-ZH`); municipalities have a longer code (`CH-ZH-AK`). |
| Photos | `asset_agg_photo`: the upload code accepts only JPEG/PNG/WebP, decodes and re-encodes the file, shrinks it to 2560 px and strips metadata. The row holds GPS, `taken_at`, altitude, owner and `is_public`. |

## 3. Your four ideas, judged

**Idea 1: store flags as photos (`asset_agg_photo`). Not recommended.**
The photo pipeline rejects SVG, and would turn a flag into a pixel picture (loses sharpness, grows in size). The row has GPS/time/altitude fields that are meaningless for a flag. Photos are private to their owner unless `is_public` is set, so every flag would have to be made public and protected from deletion by users. Photos and icons are different things; mixing them makes both rules harder.

**Idea 2: SVG text directly in each table (`flag_svg` column). Works, but not recommended.**
Simple, but the same picture is copied into every row that uses it, every list response must carry or skip the big text, and 19 ref tables plus 2 compendium tables would each need the same handling and the same upload and safety code. It breaks your rule "one concept applied the same way everywhere" as soon as one table wants a shared icon.

**Idea 3 / 4: one dedicated icon table in `assets`, other tables link to it. Recommended.**
One place to upload, check, cache and serve pictures. Any table can use any icon (for example a region type and a sport type can share a mountain symbol). Lists carry only the small `icon_id`; the picture is fetched from its own URL, so browsers cache it. This is the same pattern you already use for photos (`main_photo_id`), so the API, `?expand=` and the tests follow the existing way.

**Format: SVG as master.** Flags and UI icons are drawings, so vectors are the right source. When a PNG is needed (Office files, cards), render it on request: `GET .../file?format=png&size=64`. cairosvg is already a dependency of the card code. PNG/WebP as master would lose quality and cannot be recoloured.

## 4. Proposed design

### 4.1 New table `asset_cat_icon` (assets app, folder `models_cat`)

| Column | Meaning |
|---|---|
| `id` | UUID primary key |
| `key` | unique text, e.g. `flag_at`, `flag_ch_zh`, `sport_hiking`. Same naming idea as today's `icon` strings |
| `kind` | `flag` (fixed colours, never recoloured) or `symbol` (one colour, uses `currentColor` so the UI can colour it with the row's `color`) |
| `name` (+ de/pl) | readable name for admin screens |
| `svg` | the cleaned SVG text, NOT NULL |
| `sha256` | hash of the cleaned SVG, used as ETag and to find duplicates |
| `source`, `licence` | where the drawing comes from and under which licence (needed for flags and icon sets) |
| timestamps, `created_by` | as in every table |

### 4.2 Links

- `compendium_cat_country.icon_id` (nullable, FK to `asset_cat_icon`, `ON DELETE RESTRICT`).
- `compendium_cat_region.icon_id` (same).
- `core_ref_*.icon_id` (same, 19 tables).
- Rule: an icon that is still used cannot be deleted (409).
- The existing text column `icon` stays unchanged for now, so the front end keeps working. It can become optional and later be dropped (phase 4).

### 4.3 API (same structure as the other resources)

- `GET /assets/icons` (list, filters `kind`, `key`), `GET /assets/icons/{id}`, `POST` (upload an SVG), `PATCH`, `DELETE`. Write for admin only, read like the ref tables.
- `GET /assets/icons/{id}/file`: `image/svg+xml`, long cache, ETag = `sha256`; `?format=png&size=` for a picture.
- The JSON of an icon does **not** contain the SVG text (keeps lists small); the text comes only through `/file`.
- `?expand=icon` on countries, regions and the 19 ref resources (the expand mechanism already exists).
- Cards: `flag_href()` reads the flag through `country.icon_id` and falls back to the file in `flags/` when the link is empty. No visible change on the cards.
- New resource key `icon` in the access policy, plus Postman regeneration and tests, as for the assets app.

### 4.4 Safety (important for SVG)

An SVG can carry script code. So: only admin may upload; on upload the file is cleaned with an allow-list (no `<script>`, `<foreignObject>`, `on...=` attributes, external links), size limit (for example 200 KB); it is served with `X-Content-Type-Options: nosniff` and `Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'`. The flag-icons files are trusted but go through the same cleaner so there is one path.

### 4.5 Which flag for a region

Real flags exist only where there is something to show:

- **Countries:** all 250 from the files already in the repo (a script checks that every `iso_code` has a file; the card code prints the code instead of a flag if a file is missing, so it was never checked).
- **Cantons (26):** cantonal flag or coat of arms from Wikimedia Commons, added by hand. The licence must be checked per file; I have not verified it.
- **Districts and municipalities (about 1,500):** no flag. There is no source I can vouch for, and the licences of municipal coats of arms are uneven.
- **Fallback rule** when a region has no own picture: parent region, then the country. One helper, used by the API response and the cards, so the front end never shows an empty badge.

## 5. Decisions (answer with a number and "recommended" or your change)

**D1. Master format.** SVG (PNG only rendered on request) or PNG/WebP files?
Why it matters: decides sharpness, size and whether colours can follow `color`.
Recommendation: **SVG.**

**D2. Where do the pictures live?** (a) photo table, (b) a column in every table, (c) new `asset_cat_icon` table.
Recommendation: **(c)**, table name `asset_cat_icon`, path `/assets/icons`.

**D3. SVG text in the database or as files on disk (like photos)?**
Why it matters: you copy folders to the host by hand. Files on disk would have to be copied and kept in step with the database; text in the database travels with the data and the backup.
Recommendation: **text in the database** (`svg` column). Icons are small and rarely change; the flags folder stays only as the seed source.

**D4. Type of link.** (a) real nullable foreign key `icon_id` next to the old `icon` text, (b) no new column, only a naming rule (`flag_` + iso code) and a computed URL.
Why it matters: (a) is explicit and checked by the database; (b) needs no change in 21 tables but can silently point nowhere, and most regions have no natural key to build the name from.
Recommendation: **(a)**, and the old `icon` text stays until the front end no longer needs it.

**D5. Ref tables: now or later, and where do the icon names come from?**
Why it matters: today there are about 640 icon names and no artwork. The new link would be empty until someone provides drawings (an open-source icon set can fill most of them; the licence must be checked). I do not know which icon library the front end uses.
Recommendation: **build the structure for all tables now, but fill only flags first.** The ref tables are linked one by one when artwork exists (a script links by `icon.key == ref.icon`). Please tell me which icon library the front end uses today.

**D6. Regions.** Country flag as fallback for everything, own picture for the 26 cantons only, nothing for municipalities.
Recommendation: **yes.** (Alternative: skip cantons too and only use the fallback; cheapest.)

"Accept all recommendations" = answer `D1-D6 recommended`.

## 6. Phases (each can be delivered alone)

| Phase | Content | Touches |
|---|---|---|
| 1 | `asset_cat_icon`, upload with cleaning, `/file` with PNG option, access policy, tests, Postman | new files in `assets`, `scripts/sql`, policy seed |
| 2 | `country.icon_id`, seed 250 flags from `flags/`, `?expand=icon`, cards read from DB with file fallback | countries model/schema/routes, `cards/service.py`, `render.py` |
| 3 | `region.icon_id`, 26 cantons, fallback helper | regions model/schema/routes |
| 4 | `icon_id` on 19 ref tables, link by key when artwork exists; later make text `icon` optional | 19 models/schemas, ref routes |

Each phase would follow what we did before: a backup tarball first, a DDL script in `scripts/sql/`, tests, a live run, and one more step in the combined host runbook (nothing from this is deployed on the host yet).

## 7. What I did not verify

- (Since measured, see `icons_implementation_proposal.md`: the flags folder is 2.4 MB with 270 files, the largest 184 KB, and all 250 `iso_code` values have a matching file.)
- Licences of the cantonal flags and of any icon set for the ref tables.
- How the front end uses the `icon` text today.
