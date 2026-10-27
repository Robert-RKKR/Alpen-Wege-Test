# Postman collection for the Alpen Wege API

Made on 2026-10-24 and rebuilt on 2026-10-26 from the API's own OpenAPI description (all 212 routes, 246 requests). Tested with Newman against a running API (Postgres, Redis, Celery worker): 192 requests, 231 assertions, 0 failures, and the folders also pass one by one with their Delete calls.

Rebuilt again on 2026-10-27 for segments and routes: folders `explorer / segments` (8 requests) and `explorer / routes` (11 requests), 268 requests in total. Test with a GPX file: `Create segment from a GPX file` (choose the file in the body), `1. Create route`, `2. Put the segment into the route`, `Get one route`. The Cleanup folder starts with two requests that delete every route and segment the collection made. Newman against a live API: the only failing requests are the Upload CSV calls with no file chosen.

Rebuilt on 2026-10-27: the Create and Update bodies of `difficulty-levels`, `difficulty-sports`, `rarities` and `visibilities` now carry the required `rank`, and their List requests have `rank_min` and `rank_max` (12 requests changed, same 245 requests).

## Files

| File | What |
|---|---|
| `Alpen API.postman_collection.json` | The collection: one folder per app (`profile`, `core`, `compendium`, `explorer`, `management`, plus `health` and `Cleanup (optional)`), one folder per model inside |
| `Alpen API local.postman_environment.json` | Variables: `hostname`, `port`, `api_path` (`api/v1`), `<who>_email` and `<who>_password` for admin, editor, viewer, guest, `new_user_password`, `skip_deletes`, `access_token` |
| `build_postman.py` | Builds both files from `openapi.json` and stops if a route of the API has no request (or the other way round). Run it again after the API changes |

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
