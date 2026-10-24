# API routes: one standard structure and one URL scheme (proposal v2)

Status 2026-10-24: **accepted with "ok" (all recommended options)**. The steps are in `api_routes_implementation_plan.md`. No code has been changed yet. This replaces v1 of 2026-10-21.
Corrections found while testing: `tracks` has 9 endpoints (also `/reprocess`); the reference tables have 3 special cases (`sport_type`, `difficulty_sport`, `compendium_type`); the Swagger token URL is metadata only (section 6); the runbook lines to change are 39, 40 and 46; the README has 61 lines with old paths.
Date: 2026-10-23

## 0. My understanding of your request

1. You want one clear rule for how files in every `routes/` folder are organised, flexible but with a defined way to change (v1 of this file, your two ideas merged into one standard).
2. New: during the same change, every URL becomes `/api/v1/{app}/{model}` instead of `/api/v1/{model}`, for example `/api/v1/management/settings`.

Item 2 means URLs **do change now**. In v1 I promised "URLs do not change". That promise is gone, so the safety check has to change too (section 8).

Short glossary:

- **Endpoint**: one URL plus one HTTP method, for example `GET /pois/{id}`.
- **Router**: the FastAPI object that groups endpoints under one URL prefix.
- **Factory**: one function that builds many nearly identical routers (`core/routes/ref.py`).
- **OpenAPI**: the JSON list of all routes that the running API publishes at `/openapi.json`. I use it to prove that nothing changed except what we planned.
- **App**: one folder under `app/` (`core`, `compendium`, `explorer`, `profile`, `management`).

## 1. What changed since v1

The repo moved on while this proposal waited. I re-read all route files on 2026-10-23.

- A new `management` app exists (event log, settings, jobs, broadcast, Celery, WebSocket). It is implemented in the repo but **not deployed** on your host yet.
- `core/routes` now holds only the 19 reference tables. The event log moved to `management`.
- `explorer/routes/track.py` exists (593 lines, 9 endpoints).
- `poi.py` (208 lines) and `card.py` (203 lines) already have the `rescan` endpoints, so by my rule they are already "size L".
- `jobs` exists twice: `management/routes/jobs.py` (my jobs, at `/jobs`) and `management/routes/admin_jobs.py` (all jobs, at `/management/jobs`). With the new URL rule both would land on the same URL. See decision 10.

## 2. URLs today and URLs after the change

| Today | After | Notes |
|---|---|---|
| `/auth/register`, `/auth/login`, `/auth/refresh`, `/auth/logout` | `/profile/auth/...` | decision 8 |
| `/users`, `/users/me`, `/users/{id}/activate`, `/deactivate`, `/group` | `/profile/users/...` | |
| `/auth/access-policies` | `/profile/access-policies` | decision 9 |
| `/auth/resource-types` | `/core/resource-types` | decision 9 |
| `/countries`, `/regions`, `/pois`, `/cards`, `/posts`, `/poi-regions` | `/compendium/...` | `/pois/{id}/rescan` and `/cards/{id}/rescan` move with them |
| `/gear`, `/tracks` | `/explorer/...` | `/tracks/{id}/geometry`, `/performance`, `/restore` move with it |
| `/ref/{slug}` (19 tables) | `/core/{slug}` | decision 7, no slug clashes (checked) |
| `/jobs`, `/jobs/{id}` (my jobs) | `/management/my-jobs`, `/management/my-jobs/{id}` | decision 10 |
| `/ws`, `/ws/ticket`, `/ws/jobs/{id}` | `/management/ws`, `/management/ws/ticket`, `/management/ws/jobs/{id}` | WebSocket paths move too |
| `/management/event-log`, `/settings`, `/jobs` (admin), `/broadcast`, `/celery` | unchanged | already follow the rule |
| `/health`, `/docs`, `/openapi.json` | unchanged | not part of the API versioned tree |

## 3. The URL standard

**U1.** Every endpoint is `/api/v1/{app}/{resource}[/{id}[/{action}]]`. `{app}` is the name of the app package whose `routes/` folder holds the file.

**U2.** The app prefix is written **once**, in that app's `routes/__init__.py` (`APIRouter(prefix="/compendium")`). Resource files only know their own part (`/pois`). `main.py` adds only `/api/v1`. A new resource file can never end up outside its app by accident.

**U3.** The resource part keeps today's rule: plural, kebab-case (`/poi-regions`), uncountable names stay as they are (`/gear`).

**U4.** No exceptions: authentication endpoints also live under an app (`/profile/auth/login`). Only `/health` and the documentation URLs stay outside.

**U5.** One URL means one thing. Admin and user views of the same data are not given the same path. Own-data-only lists are named `my-...` (decision 10).

## 4. The file standard (unchanged from v1, refreshed)

### Rule 1. The unit is a "resource"

A resource is one table (for example `poi`) or one feature (for example `auth`). Every resource is one importable unit that exposes **one object named `router`**.

### Rule 2. Two allowed sizes

**Size S: one file**

```
routes/poi.py          # all methods of the resource
```

**Size L: one folder**

```
routes/poi/
    __init__.py        # imports the endpoint files in order, exports `router`
    _router.py         # router = APIRouter(prefix="/pois", tags=["Compendium - POI"])
    _shared.py         # optional: helpers used by 2 or more endpoint files
    get_many.py        # GET    /pois
    get_one.py         # GET    /pois/{poi_id}
    create.py          # POST   /pois
    update.py          # PATCH  /pois/{poi_id}
    delete.py          # DELETE /pois/{poi_id}
    upload_csv.py      # POST   /pois/upload-csv
    rescan.py          # POST   /pois/{poi_id}/rescan
```

**Switch rule.** Use size S while the file is under about 250 lines and has no custom endpoint with its own workflow. Use size L when the file passes about 250 lines, or when it contains a custom workflow endpoint (a rescan with a lock and a job, a GPX upload, geometry or performance calculations). A small helper endpoint such as `/stats` does not force a folder.

Result for today's files: `poi`, `card`, `track` become folders. `event_log` (175 lines), `ws` (234 lines), `celery`, `settings`, `broadcast`, `gear`, `country`, `region`, `post`, `poi_region` stay files.

`from .poi import router` is identical for a file and for a folder, so changing size touches no other file.

### Rule 3. Inside a folder

- One endpoint per file by default. A small group that always changes together may share a file named after the group (for example `me.py` with `GET /me` and `PUT /me`).
- All endpoint files import the shared router from `_router.py` and decorate with it. FastAPI refuses to include a child router whose paths are `""` without a prefix, so each endpoint file must not own a router. I will confirm this on the first folder I build.
- `__init__.py` imports every endpoint file explicitly. A file not imported there does not exist for FastAPI.
- **Order matters:** import endpoints with fixed paths (`/upload-csv`, `/stats`, `/entity-types`) before endpoints with `/{id}` paths.

### Rule 4. Names

| Thing | Rule | Example |
|---|---|---|
| File or folder | singular, snake_case, model name without the app prefix | `poi_region` |
| URL resource part | plural, kebab-case | `/poi-regions` |
| Exported object | always `router` | `router` |
| Tag | `"<App> - <Resource>"` | `"Compendium - POI Region"` |
| Endpoint file in a folder | verb or action | `get_many.py`, `create.py`, `rescan.py` |
| Function | `list_x`, `get_x`, `create_x`, `update_x`, `delete_x`, `upload_csv` | unchanged |

One resource per unit. A file must never hold two resources (`access_policy.py` does today).

### Rule 5. Registration

Each app has one `routes/__init__.py` that builds **one** `router` with the app prefix (U2) and includes each resource on one line. `main.py` imports exactly one router per app (today it imports `auth_router` and `users_router` for profile, plus one router for each other app). Explicit list, no automatic discovery (decision 5).

### Rule 6. Shared code

- Used by 2 or more resources: `app/core/utils/` (for example one `apply_scope`).
- Used by endpoints of one resource: that resource's `_shared.py`.
- Route files never import from other route files. Two cases today: `admin.py` imports `_user_to_read` from `me.py`, and `admin_jobs.py` imports `JOB_STATUSES` from `jobs.py`.

### Rule 7. Schemas mirror routes

`schemas/<resource>.py`, one file per resource with its Create, Update and Read classes. Never split per method. `core/schemas/ref.py` stays one file because 19 tables share it. Models are not touched.

## 5. Where each app ends up

```
core/routes/
    __init__.py            # router prefix "/core"
    ref/
        __init__.py        # includes the 19 tables (no extra prefix, see decision 7)
        _factory.py        # today's _build_ref_router, moved unchanged
        company.py ... 16 small files
        sport_type.py, difficulty_sport.py, compendium_type.py   # special cases
    resource_type.py       # moved from profile/access_policy.py (decision 9)

compendium/routes/
    __init__.py            # router prefix "/compendium"
    country.py  region.py  post.py  poi_region.py     # size S
    poi/   card/                                       # size L (rescan)

explorer/routes/
    __init__.py            # router prefix "/explorer"
    gear.py                # size S
    track/                 # size L (9 endpoints, 593 lines)

profile/routes/
    __init__.py            # ONE router, prefix "/profile": includes auth, user, access_policy
    auth/                  # login.py  logout.py  refresh.py  register.py (sub-prefix "/auth")
    user/                  # me.py  admin.py  _shared.py (sub-prefix "/users")
    access_policy.py       # split out of today's access_policy.py

management/routes/
    __init__.py            # ONE router, prefix "/management" (user and admin routes together)
    event_log.py  settings.py  broadcast.py  celery.py  ws.py
    my_jobs.py             # today's jobs.py   -> /management/my-jobs
    jobs.py                # today's admin_jobs.py -> /management/jobs (administrator)
```

The factory stays for the 19 reference tables (it avoids 17 copies), but each table has its own findable file.

## 6. Places that hard-code old URLs

I searched the whole repo. These do **not** follow automatically and must change in the same step. The first three fail silently or half-silently, so they are the dangerous ones.

| Where | What breaks if forgotten |
|---|---|
| `app/core/utils/upload_limit.py:13` (`self.path = "/api/v1/tracks"`, exact match) | The 413 "file too large" guard stops working. No error anywhere. |
| `app/profile/dependencies/current_user.py:19` (`tokenUrl="/api/v1/auth/login"`) | The token URL in `/openapi.json` points at a dead URL. (Correction after testing: this is metadata only; Swagger's own login dialog never worked, because the login route takes JSON. See the plan, S4.) |
| `Location` header in `compendium/routes/poi.py:192`, `card.py:187`, `explorer/routes/track.py:189` and `:592` (`/api/v1/jobs/{id}`) | The 202 responses point clients to a URL that no longer exists. |
| `app/main.py:116-122` | Prefix handling (changes by design). |
| `app/profile/routes/access_policy.py:31` and `:164` | Comments only. |
| `scripts/ws_check.py:21` and `:36`, `scripts/smoke_tracks.sh` (auth/login, tracks, jobs calls) | Your check scripts fail. |
| `README.md` (61 lines match the broad pattern in the plan, Appendix B) | Wrong documentation. |
| `Routing/management_deploy_runbook.md` (lines 39, 40, 46) | The deploy checks use `/jobs`, `/ws`, `/tracks`. |

Plans in `Routing/` (track pipeline, expand, management plan, security tests) mention old URLs as history. I would not rewrite them, but new work should use the new URLs. `tests/` contains no URL tests, so nothing automatic currently protects paths. The checks in `api_routes_implementation_plan.md` (section 1 and 5.1) close that gap.

Fix for the hard-coded strings: one small file `app/core/utils/api_paths.py` with `API_V1`, `job_url(job_id)` and `TRACK_UPLOAD_PATH`. The four `Location` headers and the upload guard use it, so the next move is a one-line change.

## 7. What this proposal does not do

- It does not merge the copied CRUD files into one generic factory (that changes behaviour: geometry conversion, eager loading, sort orders).
- It does not change permissions, schemas, models, or permission keys (`poi`, `gear`, `ref`, ...). Keys are separate from URLs.
- It does not decide how link tables (`m2m`) and sub tables are exposed (top-level or nested like `/explorer/tracks/{id}/pois`).
- It does not touch Swagger tags or function names. Note: FastAPI builds each `operationId` from the function name and the path, so operation ids change with the URLs. This only matters if you generate a client from `/openapi.json`.

## 8. Migration plan and safety check

> **Superseded by `api_routes_implementation_plan.md`** (2026-10-24). The plan has the real steps, the tested tools (`route_map.py`, `ast_compare.py`, tests) and the host commands. The text below is the first idea; where it differs (for example `openapi_before.json` and `check_route_map.py` became `route_map.py dump` and `compare`), the plan is right.

**Prerequisites.** The repo has no git. Before step 1: make a full backup copy of the repo folder, and make sure nobody (you or the VS Code agent) edits route files while this runs. The expand plan and the track pipeline plan touch the same files.

**Phase 1: structure only, URLs unchanged**

| Step | Change |
|---|---|
| P1-0 | Save the baseline `openapi_before.json` |
| P1-1 | `core`: `ref.py` becomes the `ref/` package (factory + 19 small files) |
| P1-2 | `profile`: split `access_policy.py`; `auth/` and `user/` folders; `_user_to_read` to `user/_shared.py` |
| P1-3 | `management`: rename files (`jobs.py` to `my_jobs.py`, `admin_jobs.py` to `jobs.py`); move `JOB_STATUSES` out of a route file |
| P1-4 | `poi`, `card`, `track` become folders |
| P1-5 | (optional, decision 4) one shared `apply_scope` |

Check after every step: save `/openapi.json` as `openapi_after.json`; both files must be **identical** with sorted keys. Then call `/health`.

**Phase 2: URLs change**

| Step | Change |
|---|---|
| P2-1 | Add `api_paths.py`; use it for the four `Location` headers and the upload guard |
| P2-2 | Put the app prefix into each app's `routes/__init__.py`; merge profile into one router; `ref` under core; `resource_type` to core; `my-jobs`; `ws` under management; adjust `main.py` |
| P2-3 | Update `tokenUrl`, `ws_check.py`, `smoke_tracks.sh`, README, the runbook, the two comments |
| P2-4 | Run the route-map check, then the smoke script and `ws_check.py`, then log in through the Swagger "Authorize" button |

**Route-map check (new, replaces "identical").** I write a small script `scripts/check_route_map.py`. It reads `openapi_before.json`, `openapi_after.json` and the mapping table in section 2. It must report exactly this: every old path has its new path with the same methods and the same request and response shapes, no path disappeared, and no path appeared that is not in the table. Because `tests/` has no URL tests, this script is the safety net. The 401 sweep from the security test proposal can run on top of it afterwards.

## 9. Order relative to your other work

- **Management deploy (runbook).** The runbook still uses `/api/v1/jobs` and `/ws`. If we deploy first and change URLs afterwards, you get a clean "before" baseline from the real deployed API and one change at a time. I recommend this order.
- **Expand plan (`?expand=`).** Not started in code. Its own plan already says to do expand first and re-baseline OpenAPI after. If expand starts before this migration, it will touch `poi`, `card`, `gear`, `track` route files that Phase 1 moves. Do not run both at the same time.

## 10. Decisions for you

Reply with the numbers, for example "all recommended", or "1 recommended, 7 B, 10 A". Decisions 1 to 6 are the same as in v1, so if you already answered those, you only need 7 to 12.

**1. Which file standard?**
Why it matters: the main rule everything else follows.
- A. File or folder with a switch rule (section 4).
- B. Always a folder, one file per method (about 30 resources today, so well over 150 small files with repeated imports).
- C. Always one file per resource (`poi.py` and `track.py` keep growing).

Recommendation: **A**.

**2. When does a file become a folder?**
- A. Over about 250 lines, or it holds a custom workflow endpoint.
- B. Only by line count.
- C. Case by case.

Recommendation: **A**.

**3. Reference tables (19 tables in `ref.py`)**
- A. One small file per table that calls the shared factory.
- B. One registry file, as today, moved into `ref/`.
- C. One folder per table (about 100 near-empty files).

Recommendation: **A**.

**4. Shared `apply_scope` helper (copied into 7 files)**
- A. Do it as step P1-5, after the structure moves.
- B. Do it together with the structure.
- C. Leave the copies.

Recommendation: **A**.

**5. How routers are registered**
- A. Explicit: one line per resource in the app's `routes/__init__.py`.
- B. Automatic scan of the folder.

Recommendation: **A**.

**6. Schemas**
- A. Mirror the route name, one file per resource, never split per method.
- B. Also split per method.

Recommendation: **A**.

**7. URL of the 19 reference tables**
Why it matters: today `/ref/companies`. Your rule gives `/core/companies`. Keeping "ref" gives `/core/ref/companies`, but that is a third level that breaks `{app}/{model}`.
- A. `/api/v1/core/companies` (strict rule, no clashes, checked).
- B. `/api/v1/core/ref/companies`.

Recommendation: **A**.

**8. Login, refresh, logout, register, users**
Why it matters: `auth` is not a table, so the rule does not say where it goes.
- A. `/api/v1/profile/auth/login` and `/api/v1/profile/users/me` (no exceptions, rule U4).
- B. Keep `/api/v1/auth/...` as the one exception, and `/api/v1/profile/users/...` for users.

Recommendation: **A**. Cost: `tokenUrl`, scripts and README change (listed in section 6).

**9. Resource types and access policies**
Why it matters: today both sit under `/auth` and share one file, but the resource-type model lives in `core` and the policy model in `profile`.
- A. `/api/v1/core/resource-types` (route file moves to `core/routes`) and `/api/v1/profile/access-policies`.
- B. Both under `/api/v1/profile/...`, route files stay in `profile`.

Recommendation: **A**, because U1 says the app in the URL is the app that holds the route file, and the model is in `core`.

**10. The two `jobs` resources**
Why it matters: with the new rule, "my jobs" (`/jobs`) and "all jobs for administrators" (`/management/jobs`) land on the same URL, and one would silently hide the other.
- A. One `/management/jobs`: administrators see all, normal users see only their own. Fewer URLs, but the response has two different shapes depending on the role, so I would need to merge two route files and two schemas.
- B. Keep two, the admin one at `/management/admin/jobs`.
- C. Own jobs at `/management/my-jobs`, admin at `/management/jobs` (no code merge, the admin URL does not change).

Recommendation: **C**.

**11. Old URLs after the change**
Why it matters: every client that calls an old URL gets a 404. The API is version 0.1.0 and the management endpoints are not deployed yet.
- A. Clean break: old URLs disappear.
- B. Keep old URLs for a transition period (second copy of the routers, hidden from Swagger, with a deprecation header), remove later.

Recommendation: **A**, if nothing besides your own scripts calls the API today. **Fact I need from you:** is there a mobile app, web frontend or other client that already calls these URLs? If yes, tell me which and I will switch to B.

**12. Order and start**
- A. Deploy the management app first (runbook), then Phase 1, then Phase 2, never at the same time as the expand plan.
- B. Phase 1 and 2 first, then deploy management once with the new URLs (one deploy, but if something fails you cannot tell whether the cause is the deploy or the refactor).
- C. Approve the standard only, schedule the migration later.

Recommendation: **A**.
