# Postman collection for the Alpen Wege API

Made on 2026-10-24 from the API's own OpenAPI description (all 212 routes, 245 requests). Tested with Newman against a running API (Postgres, Redis, Celery worker): 192 requests, 231 assertions, 0 failures, and the folders also pass one by one with their Delete calls.

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

## Collection Runner (all calls in one run)

Set `skip_deletes` to `true` in the environment, run the folders in the order shown, then run **Cleanup (optional)**: it deletes everything in an order that respects the links. Upload CSV and Upload track need a file chosen in their body (they fail without one). After the run set `skip_deletes` back to `false` so the single Delete calls work.

## Notes

- **WebSocket** requests cannot be part of an importable collection. `management / ws / WebSocket ticket` saves `ws_ticket` and its description gives the two WebSocket URLs.
- **Login editor / viewer / guest** replace `access_token`, so you act as that user until you run **Login admin** again. **Logout** kills the token and then logs in as admin again in its test script.
- **List all jobs** (`management / jobs`) has `created_from` and `created_to` switched on, because the API answers 500 when either is missing (known bug, not fixed yet).
- **Create access policy** only accepts the groups `administrator`, `editor`, `viewer`, `guest`; any other name gives a 500 instead of a 422. The call makes a helper resource type first so no real policy is touched.
- Upload CSV and Register leave test data behind (rows, a user); the Cleanup folder does not remove them.
