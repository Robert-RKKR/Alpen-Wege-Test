# Postman collection for the Alpen Wege API

Made on 2026-10-24 and rebuilt on 2026-10-26 from the API's own OpenAPI description (all 212 routes, 246 requests). Tested with Newman against a running API (Postgres, Redis, Celery worker): 192 requests, 231 assertions, 0 failures, and the folders also pass one by one with their Delete calls.

Rebuilt again on 2026-10-27 for segments and routes: folders `explorer / segments` (8 requests) and `explorer / routes` (11 requests), 268 requests in total. Test with a GPX file: `Create segment from a GPX file` (choose the file in the body), `1. Create route`, `2. Put the segment into the route`, `Get one route`. The Cleanup folder starts with two requests that delete every route and segment the collection made. Newman against a live API: the only failing requests are the Upload CSV calls with no file chosen.

Rebuilt on 2026-10-27: the Create and Update bodies of `difficulty-levels`, `difficulty-sports`, `rarities` and `visibilities` now carry the required `rank`, and their List requests have `rank_min` and `rank_max` (12 requests changed, same 245 requests).

Rebuilt on 2026-10-28 for the new `assets` app and the card graphic (242 routes, 285 requests; a backup of the old files is `backup_before_postman_assets_2026-10-28.tar.gz` in the folder above). Newman against a live API with a Celery worker: 299 calls including the helper calls of the scripts, 320 assertions, 0 failures.

Rebuilt on 2026-10-30 for the icons (250 routes, 297 requests; a backup of the old files is `backup_before_postman_icons_2026-10-30.tar.gz` in the folder above). Newman against a live API with a Celery worker and the 270 flags loaded: 311 calls including the helper calls of the scripts, 381 assertions; the only failing requests are the 28 Upload CSV calls with no file chosen.

- **New folder `assets / icons`** (9 requests): List icons, **Upload icon**, Get one icon, Icon file (the SVG), Icon file as PNG, Icon file by key, Replace the SVG of an icon, Update icon, Delete icon. Upload icon (admin) points at `sample_icon.svg` (next to the collection; put it in the Postman working directory too), saves `icon_id` and `icon_key`, and checks that the answer lists what the cleaning removed (nothing for the sample file). The file requests check the headers (`image/svg+xml`, `ETag` = SHA-256, `nosniff`, `Content-Security-Policy` with `sandbox`); the PNG request has `format=png&size=64` switched on.
- **All icons in one call** (added 2026-10-30, later; 252 routes, 300 requests; Newman: 314 calls, 389 assertions, only the 28 Upload CSV requests without a file fail): `assets / icons / Upload icons CSV (dry run)` (checks and counts, saves nothing), `Upload icons CSV (import all)` (creates the 438 icons of `icons_import.csv` and, with `link=true`, sets `icon_id` on every reference row, resource type, country and region whose icon text or code matches a key) and `Link rows to icons by key` (for later). Both CSV requests point at `icons_import.csv` (next to the collection; put it in the Postman working directory). The import can be run again: existing keys are `unchanged`; switched-off parameters: `update` (replace what exists), `dry_run`, `link`.
- **Icon mechanism** (the same as the photo mechanism). The Create and Update bodies of the 19 reference tables, `core / resource-types`, `compendium / countries` and `compendium / regions` start with `"icon_id": "{{icon_id}}"` and their tests check that the answer has that icon. When `icon_id` is empty the pre-request script takes the first icon of `assets / icons` (a flag, when the flags are loaded); when there is no icon at all the field is cut out of the body, so every request still works. The build stops when the API accepts `icon_id` in a body that no request sends (`ASSET_LINKS` now has `icon_id`). The Cleanup folder deletes the icons this collection made **last**, after the countries, regions and reference values that used them (a used icon answers 409). Folder order in a Runner run is unchanged (core before assets), so run **Upload icon** once first if you want every created row to use the icon you uploaded; without it they use the first icon of the list.

- **New folder `assets`**: `photos` (List, Upload photo, Get one, Photo file, Update, Delete) and `gpx` (List, Get one, Download, Update, Delete). In the other folders: `compendium / cards` has `Card graphic (render)` and `Render the card files again (job)`. The render request lists all its query parameters with a description (`format`, `lang` switched on; `ratio`, `style`, `dpi`, `download` switched off with an example value, 2026-10-30: tick one to try it).
- **Photo mechanism.** `assets / photos / Upload photo` saves `photo_id`. From then on every request that can carry a photo uses it: the Create and Update bodies of `compendium / pois`, `cards` and `posts` start with `"main_photo_id": "{{photo_id}}"`, and their tests check that the answer has that photo. When `photo_id` is empty the pre-request script takes the first photo of `assets / photos`; when there is no photo at all the field is cut out of the body (so the request still works without a photo). `Remove the main photo of the ...` (PATCH with `null`) frees a photo so that `Delete photo` can remove it (it answers 409 while a card, POI, post, gear, segment or track still uses it). Build safety net: `build_postman.py` stops when the API accepts a body field named in `ASSET_LINKS` (now `main_photo_id` and `avatar_photo_id`) and no request of the collection sends it, so a new photo relation cannot be forgotten; add new field names to `ASSET_LINKS`.
- **GPX files.** A GPX file is made by `explorer / tracks / Upload track`, which now also saves `gpx_id` (`Get one track` does too); `assets / gpx` works with it.
- **Folder order for the Collection Runner** is now: profile, core, explorer, assets, compendium, management, Cleanup. Explorer comes before assets (the GPX files exist by then) and assets before compendium (cards, POIs and posts get their photo).
- **Sample files.** The upload requests of photo, track and segment point at `sample_photo.jpg` and `sample_track.gpx` (next to the collection). Put both into the Postman working directory (Settings, General, Working directory; Newman: `--working-dir <this folder>`) or choose another file in the body once.
- **Raw JSON bodies** are all written the same way (4 spaces, one member per line; the build checks it). The one that was on a single line (`Update setting`) is formatted now too. Bodies with a variable in place of a value, such as `"value": {{setting_value}}`, stay as they are because Postman fills them in before sending.
- The Cleanup folder deletes the photos the collection uploaded (after the cards, posts and POIs that use them). GPX files stay, because a track keeps its file.

## Files

| File | What |
|---|---|
| `Alpen API.postman_collection.json` | The collection: one folder per app (`profile`, `core`, `explorer`, `assets`, `compendium`, `management`, plus `health` and `Cleanup (optional)`), one folder per model inside |
| `Alpen API local.postman_environment.json` | Variables: `hostname`, `port`, `api_path` (`api/v1`), `<who>_email` and `<who>_password` for admin, editor, viewer, guest, `new_user_password`, `skip_deletes`, `access_token` |
| `build_postman.py` | Builds both files from `openapi.json` and stops if a route of the API has no request (or the other way round), if a photo field of the API is not filled by the collection, or if a raw body is not formatted. Run it again after the API changes |
| `sample_photo.jpg`, `sample_track.gpx`, `sample_icon.svg`, `icons_import.csv` | Files for the upload requests (photo with a GPS position in its EXIF data; a 200-point GPX track; a small outline icon; the CSV with the graphics of all 438 icons) |

## Use

1. Postman, Import, choose both JSON files. Select the environment **Alpen API local**.
2. Run **profile / auth / Login admin**. It saves the token in `access_token` with your script. Every other call uses it.
3. Use any call. Tokens last a few minutes; the collection stores the newest token automatically (the API sends it in the header `X-Access-Token`). On a 401, log in again.

URL of every request: `http://{{hostname}}:{{port}}/{{api_path}}/<app>/<resource>`.

Your variable names are different? Build the files with your names:

```bash
curl http://localhost:8000/openapi.json > openapi.json
python build_postman.py --openapi openapi.json --out . --host-var hostname --port-var port --api-var api_path --token-var access_token
```

## What each model folder has

List, Create, Get one, Update, Delete, and Upload CSV where the API has it. Create saves the new id in a variable (`country_id`, `poi_id`, ...) that Get, Update, Delete and the models that depend on it use. Random values come from the pre-request scripts (`random_name`, `random_key`, `random_iso_code`; the Register call keeps your own random e-mail and name script). Order of Create calls for linked data: core `region-types`, `compendium-types`, `post-types`, `companies`, `gear-types`, then compendium `countries`, `regions`, `pois`, `cards`, `posts`, `poi-regions`, explorer `gear`.

## Running one request alone (first ids)

Every model has an id variable (`company_id`, `poi_id`, `track_id`, `log_id`, `setting_key`, ...). Create saves it; these also fill it from the **first row of the list**, so Get one, Update and Delete can run without a Create before them:

- **Collect first IDs (optional) / Collect first IDs (all lists)** (second folder, after `profile`): one request that reads the first row of every list (`limit=1`) and saves all ids at once. An id that Create already saved is kept; set `collect_overwrite` to `true` in the environment to replace them. The console shows what was saved, kept, empty or failed.
- **List requests** save the first id when the variable is empty (as before).
- **Get one, Update, Delete** (and Rescan, the track calls, event log, settings, jobs, Celery task detail) have a pre-request script: when their variable is empty they take the id of the first row of their list themselves and write it to the console.

**Careful:** a Delete request whose variable is empty deletes the first row of the list (and "Archive track" archives the first track). The Cleanup folder does not use this fallback. Set `skip_deletes` to `true` to skip all Delete requests of the model folders.

## Collection Runner (all calls in one run)

Set `skip_deletes` to `true` in the environment, run the folders in the order shown, then run **Cleanup (optional)**: it deletes everything in an order that respects the links. Upload CSV and Upload track need a file chosen in their body (they fail without one). After the run set `skip_deletes` back to `false` so the single Delete calls work.

## Notes

- **WebSocket** requests cannot be part of an importable collection. `management / ws / WebSocket ticket` saves `ws_ticket` and its description gives the two WebSocket URLs.
- **Login editor / viewer / guest** replace `access_token`, so you act as that user until you run **Login admin** again. **Logout** kills the token and then logs in as admin again in its test script.
- **List all jobs** (`management / jobs`) used to need `created_from` and `created_to` (the API answered 500 without them); that bug is fixed together with the list filters (2026-10-26), so they are switched off now.
- **List requests** list every filter and `sort` of their endpoint as query parameters, all switched off (added 2026-10-26).
- **Compare two events** answers 400 when the first two rows of the event log belong to different objects (accepted by its test).
- **Create access policy** only accepts the groups `administrator`, `editor`, `viewer`, `guest`; any other name gives a 500 instead of a 422. The call makes a helper resource type first so no real policy is touched.
- Upload CSV and Register leave test data behind (rows, a user); the Cleanup folder does not remove them.
- **`expand` (rebuilt 2026-10-26):** the 33 "Get one" requests that take `?expand=` (pois, regions, countries, cards, posts, poi-regions, gear, tracks, the 19 reference tables and resource types, event log and its compare, administrator job, settings, access policies) have a switched-off query parameter `expand`. Switch it on and type the links, for example `main_region.country,created_by`; its description lists the allowed names. Without it a link is only an ID. See the README section "Expanding linked objects".
