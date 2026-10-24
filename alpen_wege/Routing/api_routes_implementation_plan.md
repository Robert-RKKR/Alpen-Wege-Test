# API routes: implementation plan (file standard + URL scheme `/api/v1/{app}/{resource}`)

Plan v3, 2026-10-24. **No code in your repo has been changed.** v1 and v2 of this plan were each checked by an independent reviewer; their findings are fixed here (Appendix D).
Background and reasons: `api_routes_structure_proposal.md`. Tools and scripts: folder `api_routes_tools/` (read its `README.md`).

> **Update 2026-10-24 (later): Phase 3.** The file-or-folder rule of this plan (size S file, size L folder) was replaced by one layout for every resource: a folder with one file per action, and type folders `m2m/`, `ref/`, `sub/`. Phase 3 is delivered and verified: see `api_routes_phase3_uniform_layout.md`. Where this plan says "size S", `poi.py`-style single files, `ref/_factory.py` or "6 known failing tests" (your fixes removed them; the suite is now 64 passed), the Phase 3 document is right. The file counts and hashes in sections 3 and 6 are from before Phase 3 (now 505 files, hash `55209df87733162f`).

## 0. What happens, in short

1. **Phase 1, structure.** The route files are reorganised into one standard. A resource is a **size S** unit (one file, for example `country.py`) or a **size L** unit (one folder, for example `poi/`, with one file per endpoint); both export `router`. **No URL changes.** Check: the route table is identical.
2. **Phase 2, URLs.** Every URL becomes `/api/v1/{app}/{resource}`, for example `/api/v1/compendium/pois` and `/api/v1/management/settings`. Check: the route table equals the old one after the URL rules.
3. **Wrap-up.** README and runbook use the new URLs; tests keep the standard from drifting.

No database change, no SQL. No schema, model or permission change. Swagger tags and function names stay the same.

Four words used below: **scratch copy** = a copy of the repo in the sandbox (`/tmp`) where the scripts run first; **delivery** = copying the verified result from the scratch copy into the real repo in one go; **gate** = a question that must be answered before work continues; **tripwire** = a command that shows whether someone else changed files.

## 1. What was tested, and what was not

All of this ran on a copy of your repo (state of 2026-10-24) with the real application code. Your repo was not touched.

| Test | Result |
|---|---|
| Both phases step by step, 214 routes (212 HTTP + 2 WebSocket), compared after every step | Phase 1: identical. Phase 2: equal to the URL rules. All 12 steps |
| Four FastAPI versions: 0.111.1 (the oldest release I could install; `requirements.txt` allows from 0.111.0), 0.115.14, 0.161.1, 0.162.0. The reviewers also ran Python 3.12 with only `requirements.txt` installed | Same result everywhere |
| Live run: Postgres 16 + PostGIS, Redis, a Celery worker, uvicorn, seeded users. After Phase 2: 35 of 35 checks, authenticated GET of all 8 resource lists, 23 MB upload refused with 413. After Phase 1 (old URLs): your original `smoke_tracks.sh` and `ws_check.py` ran clean, 413 still works. The second reviewer repeated the live run with the section 6 commands, with Celery still on the OLD code (so "no worker rebuild" holds) | All passed, no traceback in uvicorn or Celery |
| Your `scripts/ws_check.py` and `scripts/smoke_tracks.sh` with the edits of step 2.5 | All 5 GPX variants reach `ready`, archive and restore work, the demo job streams over the WebSocket |
| `pytest` | Before: 44 pass, **6 fail** (known: `test_matching.py` x5, `test_gpx_pipeline.py::test_straight_line_distance`). After: 56 pass (44 + 12 new), the same 6 fail |

**Four layers catch mistakes**, because no single check sees everything. Each was measured with deliberate mistakes on the migrated copy; the second reviewer ran 59 more.

| Layer | Tool | What it sees | Mistakes it caught |
|---|---|---|---|
| Declarations | `route_map.py` `compare`, `probe` | URL, method, function name, tags, parameters, request and response shapes, security, permission key and action of every route; the model and slug a reference-table route was built with; the middleware list and exception handlers of the app; a route hidden by another | wrong permission key, misspelled prefix, forgotten router, dropped login dependency, shadowed route, two routes on one URL, model or slug swapped between two reference files, middleware removed or reordered, exception handler removed |
| Code | `ast_compare.py` | What every route function and every top-level constant does, comments and formatting ignored | dropped `apply_scope` call, dropped `check_object_access`, typo in `Location`, wrong guard path, `\|` changed to `&`, added `response_model_exclude_none`, old call signature left, swapped parameters, changed envelope code, disabled WebSocket ticket check, forgotten `Location` rewrite, changed message text, changed `JOB_STATUSES`, changed alias, changed WebSocket close code |
| Names | `route_map.py names` (also a pytest test) | A name used inside a function that its module does not define | forgotten import, leftover renamed helper, dropped `settings = ...` (4 of 4) |
| Behaviour | `pytest` (12 new tests) and the live checks | middleware really installed and watching the real route, no `/api/v1` literal in route files, `apply_scope` for all/own/public, shadowed routes, file-and-folder duplicates, endpoint files not imported | upload-guard middleware removed or path changed, shared `apply_scope` broken, `/stats` after `/{job_id}`, `/api/v1` literal in a route file, file next to folder, endpoint file not imported |

The first reviewer's run with only the declaration layer caught 3 of 14 body-level mistakes; the second reviewer found 15 mistakes that slipped through all three layers of v2. Those classes (undefined names, swapped reference model or slug, removed or reordered middleware, changed constants, a new constant in an old file) are now caught by the added checks, and the script guards (section 4, rule 2) stop on a statement they do not know.

**Not covered by any tool:** everything that needs your data and your host. That is why every phase ends with checks that **you** run in your container (section 6). **Not tested:** your host and Docker, the library versions in your containers (`requirements.txt` does not pin them) and the copy from OneDrive to `~/jrdurt`.

## 2. Decisions as I understood them

You answered "ok" to the proposal, so I take **all recommended options**. Tell me the number of any line that is wrong.

| # | Topic | Chosen | What it means |
|---|---|---|---|
| 1 | File standard | A | A resource is a file (size S) or a folder (size L); both export `router` |
| 2 | When a file becomes a folder | A | Over about 250 lines, or it holds a custom workflow endpoint (rescan, GPX upload, geometry) |
| 3 | The 19 reference tables | A | One small file per table, built by the shared function (the function stays) |
| 4 | Shared `apply_scope` | A | Own step 1.5 after the moves; 8 copies (`track` has one too) |
| 5 | Router registration | A | Explicit list in each app's `routes/__init__.py` |
| 6 | Schemas | A | Unchanged now; one file per resource |
| 7 | Reference table URLs | A | `/api/v1/core/{slug}`, for example `/api/v1/core/companies` |
| 8 | Login, users | A | `/api/v1/profile/auth/login`, `/api/v1/profile/users/me` |
| 9 | Resource types, access policies | A | `/api/v1/core/resource-types` and `/api/v1/profile/access-policies` |
| 10 | The two `jobs` | C | Own jobs `/api/v1/management/my-jobs`; administrator view stays `/api/v1/management/jobs` |
| 11 | Old URLs | A | Clean break: old URLs answer 404. **Assumption: nothing besides your own scripts calls the API.** Gate: Claude asks you at step 0.1 and again before step 2.1 |
| 12 | Order | A | Deploy the management app first (runbook), then Phase 1, then Phase 2, never at the same time as the expand plan or other edits of the route files |

**Question 13 (side finding, not part of the migration):** `GET /api/v1/management/jobs` answers **500** unless both `created_from` and `created_to` are given. The bug is in your code today (reproduced on the untouched original). Fix: section 9, S1. **Recommendation: fix it as its own small change after the migration.** Say "fix now" to have it earlier.

## 3. What changes, in numbers

| Area | Before | After |
|---|---|---|
| Routes | 214 (212 HTTP, 2 WebSocket) | 214, same functions and permissions, other URLs |
| `.py` files under `app/` | 223 | 279 after Phase 1, 280 after Phase 2 |
| Files in the `routes/` folders (with `__init__.py`) | 28 | 83 |
| New helper files | | `core/utils/api_paths.py`, `core/utils/scope.py` |
| Changed outside `routes/` | | `main.py`, `core/utils/upload_limit.py`, `profile/dependencies/current_user.py`, `management/jobs/kinds.py` |
| Old files deleted (11) | `compendium/routes/{card,poi}.py`, `core/routes/ref.py`, `explorer/routes/track.py`, `management/routes/admin_jobs.py`, `profile/routes/{admin,login,logout,me,refresh,register}.py` | replaced by folders and renames |

**URL rules** (`api_routes_tools/route_rules.json` holds the same; counts are operations, 214 in total):

| Step | Old prefix | New prefix | Ops |
|---|---|---|---|
| 2.1 | `/api/v1/countries`, `/regions`, `/pois`, `/cards`, `/posts`, `/poi-regions` | `/api/v1/compendium/...` | 6, 6, 7, 7, 6, 6 |
| 2.1 | `/api/v1/gear`, `/api/v1/tracks` | `/api/v1/explorer/gear`, `/api/v1/explorer/tracks` | 6, 9 |
| 2.2 | `/api/v1/ref/{slug}` (19 tables) | `/api/v1/core/{slug}` | 114 |
| 2.2 | `/api/v1/auth/resource-types` | `/api/v1/core/resource-types` | 6 |
| 2.3 | `/api/v1/auth/{register,login,refresh,logout}` | `/api/v1/profile/auth/...` | 4 |
| 2.3 | `/api/v1/auth/access-policies` | `/api/v1/profile/access-policies` | 6 |
| 2.3 | `/api/v1/users`, `/users/me`, `/users/{id}/...` | `/api/v1/profile/users/...` | 7 |
| 2.4 | `/api/v1/jobs`, `/jobs/{id}` | `/api/v1/management/my-jobs`, `/my-jobs/{id}` | 2 |
| 2.4 | `/api/v1/ws/ticket`, `WS /ws`, `WS /ws/jobs/{id}` | `/api/v1/management/ws/...` | 3 |
| none | `/api/v1/management/*`, `/health` | unchanged | 18 + 1 |

**What clients see besides the URLs** (measured): 193 of 212 operation ids in `/openapi.json` change (FastAPI builds them from the path); 29 generated form schema names (`Body_..._post`) change; the Swagger tag groups are the same 37 but in another order; the Swagger token URL changes to `/api/v1/profile/auth/login` (only OpenAPI metadata, see S4).

## 4. Rules for whoever implements this

1. **Backup first.** The repo has no git. Step 0.2 is not optional.
2. **Move only.** No logic change, no renamed functions, no "while I am here" fixes. The only edits beyond moving are the ones listed in the steps. The scripts stop with `STOP: ...` when an old file has a function, constant or table they do not know (for example something the expand plan added); then the plan, not the file, is adjusted.
3. **Work on scratch copies, deliver once per phase.** The scripts run in about two minutes on a copy in `/tmp`; the result is copied into the real repo with `deliver.py` (dry run first). The repo never holds a half-migrated tree. If a check fails, throw the scratch copy away and start again from `old/`; do not patch around it.
4. **The checks of section 5.1 run after every step and at the end of each phase, before delivering.** `run_all.sh` does all of them and stops when a test other than the six known ones fails.
5. **Nobody else edits `app/`, `tests/` or `scripts/` between step 0.3 and the end of Phase 2** (VS Code agent, expand plan, track pipeline). Same files, no git. `deliver.py` refuses to run if the repo differs from its BASE copy, so a foreign edit stops the delivery instead of being overwritten. Tripwire before each delivery: `find app scripts tests -newer Routing/backup_before_routes_<date>.tar.gz -type f` (for D2 use `backup_after_phase1_<date>.tar.gz`); after step 0.3 it must list exactly the three tool files.
6. **Delete the old file when its folder appears.** With `poi.py` next to `poi/` Python silently uses the folder. `deliver.py` deletes removed files; the test of step 2.6 catches leftovers.
7. **On the host the api container is stopped while `app/` is replaced** (section 6), otherwise `uvicorn --reload` restarts on half-copied code.
8. **I never run SQL and never touch your host.** I change the repo in OneDrive; you copy it to `~/jrdurt` and run the checks.

Who does what: **Claude** (this app) or **VS Code Claude** following the tables in Appendix A. **You** do the host steps and the checks of section 6.

## 5. Milestones

### 5.1 The checks

After **every step**, in the repo root (`run_all.sh` does this in the scratch copy; on your host it is the container, section 6):

```bash
python scripts/route_map.py dump route_dumps/after_<step>.json
python scripts/route_map.py compare route_dumps/before.json route_dumps/after_<step>.json                    # Phase 1: must say "identical"
python scripts/route_map.py compare route_dumps/before.json route_dumps/after_<step>.json \
        --rules scripts/route_rules.json --step <N>                                                          # Phase 2: N = 0, 1, 2, 3, 4 (steps 2.5 and 2.6 use 4)
```

At the **end of each phase**, before delivering:

```bash
python scripts/route_map.py probe route_dumps/after_<last step>.json          # "OK: probed 211 routes, 0 problem(s)"
python scripts/route_map.py names                                              # "OK: 0 undefined name(s)"
python scripts/ast_compare.py <old copy> <scratch copy> [--phase 1]            # "OK: 0 unexpected difference(s)"  (--phase 1 at the end of Phase 1)
python -m pytest -q                                                            # exactly the 6 known failures
```

`compare` prints `OK: 214 routes before, 214 after, ...` or lists every problem (`MISSING`, `UNEXPECTED`, `DIFF`, `UNMAPPED`, `COLLISION`).

### M0. Prerequisites

| Step | Who | What |
|---|---|---|
| 0.0 | You | **The management app is deployed first** (`management_deploy_runbook.md`, its checks passed). The baselines must come from the code that is about to be moved |
| 0.1 | Claude | Allow the delete permission for the repo folder (`deliver.py` also tests this before it copies anything). **Ask you the gate question: does any app, web front end or other client call these URLs besides your own scripts?** Confirm that nothing else edits the repo (rule 5) |
| 0.2 | Claude | Backup: `tar czf Routing/backup_before_routes_<date>.tar.gz --exclude=__pycache__ app scripts tests README.md` from the repo root |
| 0.3 | Claude | Put `route_map.py`, `ast_compare.py`, `route_rules.json` into the real repo's `scripts/`. Then make the scratch copies in `/tmp`: `old/` = a copy of the repo **including these three files** (never changed again), `work/` = a copy of `old/` |
| 0.4 | Claude | Sandbox baseline: in `work/` run `python scripts/route_map.py dump route_dumps/before.json` |
| 0.5 | You | Host baseline (commands in 6.1): `route_dumps/host_before.json`, the library versions, the 6 known pytest failures, and the file-list hash. Claude runs the same hash command in the repo and compares. **The host dump must list 214 routes and the hashes must be equal.** Otherwise the host runs other code than the OneDrive repo: stop and tell me |

If `/tmp` is gone when Phase 2 starts (days later): `old/` = extract `backup_before_routes` and add the three tool files; `work/` = extract `backup_after_phase1` (it must equal the repo: `diff -r`); `before.json` = dump from `old/` with the same Python as before.

### M1. Structure, URLs unchanged (Phase 1)

Run in the scratch copy: `AW_ROOT=work AW_OLD=old ... bash run_all.sh phase1`. Appendix A has the tables for a manual implementation.

**1.1 `core/routes/ref/` package.** Delete `ref.py`. Create `ref/__init__.py`, `ref/_factory.py` and 19 table files. `_factory.py` is today's `_build_ref_router`, renamed `build_ref_router`, body unchanged, with its imports. Each table file is a few lines that call it (A.1; the three special tables keep their `# Special:` comment). `ref/__init__.py` keeps today's registration order and the prefix `/ref`. `core/routes/__init__.py` becomes `router = APIRouter()` including `ref.router`.

**1.2 `profile/routes/`.**
- `auth/` folder: `_router.py` (`router = APIRouter()`), `__init__.py`, and `register.py`, `login.py`, `refresh.py`, `logout.py` moved in; in each, `router = APIRouter()` becomes `from ._router import router`.
- `user/` folder: `_router.py`, `__init__.py`, `_shared.py` (holds `user_to_read`, was `_user_to_read` in `me.py`), `me.py`, `admin.py`. `admin.py` imports from `._shared`, **not from `me.py`**.
- `access_policy.py` is split in two, each exporting `router`: `resource_type.py` (6 endpoints, prefix `/resource-types`, tag `Auth - Resource Types`) and `access_policy.py` (6 endpoints, prefix `/access-policies`, tag `Auth - Access Policies`).
- `profile/routes/__init__.py` builds one `router` that contains `auth_router` (`/auth`, tag `Auth`: the auth actions, resource types, access policies) and `users_router` (`/users`, tag `Users`) exactly like today. `main.py` includes this one router instead of `auth_router` and `users_router`.

**1.3 `management/routes/`.** Move `JOB_STATUSES` from `jobs.py` to `management/jobs/kinds.py`. Rename `jobs.py` to `my_jobs.py` and `admin_jobs.py` to `jobs.py` (prefixes unchanged). Update `management/routes/__init__.py` (names `my_jobs_router`, `jobs_router`). This removes the route-to-route import.

**1.4 Folders `poi/`, `card/`, `track/`.** Each becomes a folder with `_router.py`, `_shared.py`, `__init__.py` and one file per endpoint (A.2). `__init__.py` lists the endpoint modules in a tuple `ENDPOINT_MODULES`, fixed paths first. The old `poi.py`, `card.py`, `track.py` are deleted.

**1.5 One `apply_scope`.** New `core/utils/scope.py` with `apply_scope(stmt, model, access)`. The eight local copies are removed: `country.py`, `region.py`, `post.py`, `poi_region.py`, `gear.py`, `poi/_shared.py`, `card/_shared.py`, `track/_shared.py` (the track version took `(stmt, access)`; the caller now passes `ExplorerAggTrack`). The reference tables keep their own inline "own"-only filter (finding F3 of the security proposal): **not changed here**.

**Delivery D1.**
1. Snapshot for D2: `cp -a work work_after_d1`.
2. `python deliver.py work <repo> old --dry-run`, read the list (expect: 67 added, 12 changed, 11 deleted), then run it without `--dry-run`.
3. In the repo: `tar czf Routing/backup_after_phase1_<date>.tar.gz --exclude=__pycache__ app scripts tests README.md`, and note the file-list hash: `find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum` (279 files). Put the hash into Appendix C.

Then your host deploy and checks (6.2). **Phase 1 is done when:** every step said `identical`, the end-of-phase checks are clean, and 6.2 passed on your host.

### M2. URLs (Phase 2)

**Gate before 2.1 (decision 11).** Claude asks you once more whether anything besides your scripts calls these URLs and waits for the answer. If yes: stop; the plan changes to keep the old URLs for a while.

Run in the scratch copy: `... bash run_all.sh phase2`.

**2.0 `core/utils/api_paths.py` with the OLD values, and `tests/test_api_paths.py`.** No behaviour change. It replaces the four hand-written `Location` headers (`poi/rescan.py`, `card/rescan.py`, `track/create.py`, `track/reprocess.py`) with `job_url(job["id"])`, the upload guard's path with `TRACK_UPLOAD_PATH`, and `main.py`'s `"/api/v1"` with `API_V1`. The tests then fail if a moved route and one of these constants disagree, if the guard is not installed, or if a route file contains `/api/v1`. (compare `--step 0`)

**2.1 Compendium and explorer.** `compendium/routes/__init__.py`: `APIRouter(prefix="/compendium")`; `explorer/routes/__init__.py`: `APIRouter(prefix="/explorer")`; `TRACK_UPLOAD_PATH` becomes `/api/v1/explorer/tracks`. (`--step 1`)

**2.2 Core.** `core/routes/__init__.py`: `APIRouter(prefix="/core")`; `ref/__init__.py` loses its `/ref` prefix. `resource_type.py` moves from `profile/routes/` to `core/routes/` and is included in the core router; its tags stay `["Auth", "Auth - Resource Types"]` so Swagger groups it as before. (`--step 2`)

**2.3 Profile.** `profile/routes/__init__.py`: `APIRouter(prefix="/profile")` including `auth_router`, `user_router` and `access_policy.router`. `auth/_router.py` gets `prefix="/auth", tags=["Auth"]`; `user/_router.py` gets `prefix="/users", tags=["Users"]`. The `access_policy.py` router tags become `["Auth", "Auth - Access Policies"]` (same Swagger grouping as before). `current_user.py`: `tokenUrl=f"{API_V1}/profile/auth/login"`. (`--step 3`)

**2.4 Management.** One router with `prefix="/management"` containing `my_jobs` (prefix `/my-jobs`), `ws` (its paths `/ws`, `/ws/ticket`, `/ws/jobs/{job_id}` stay in `ws.py`), `event_log`, `settings`, `jobs`, `broadcast`, `celery`. `job_url` becomes `/api/v1/management/my-jobs/{id}`. The comment in `track/reprocess.py` ("GET /jobs/{id} is owner-only") names the new URL. (`--step 4`)

**2.5 Scripts.** `scripts/ws_check.py`: line 21 `/api/v1/ws/ticket` becomes `/api/v1/management/ws/ticket`; line 36 `/api/v1/ws/jobs/...` and `/api/v1/ws` become `/api/v1/management/ws/jobs/...` and `/api/v1/management/ws`. `scripts/smoke_tracks.sh` (12 lines): `$API/auth/login` becomes `$API/profile/auth/login`, the 9 `$API/tracks` become `$API/explorer/tracks`, the 2 `$API/jobs/$JID` become `$API/management/my-jobs/$JID`. Add `scripts/e2e_check.py` (optional live check). **These edits must be in the repo before the Phase 2 host checks**, because section 6.3 uses these scripts.

**2.6 The standard enforces itself.** Add `tests/test_routes_standard.py` (6 tests, see tools README). It passes only after 2.4.

**Delivery D2.** `python deliver.py work <repo> work_after_d1 --dry-run` (expect: 5 added, 19 changed, 1 deleted), then for real; note the file-list hash again (280 files) in Appendix C. Then your host deploy and checks (6.3).
**Phase 2 is done when:** every step passed with its step number, the final `compare ... --rules scripts/route_rules.json` (no `--step`) says `OK`, the end-of-phase checks are clean, and 6.3 passed on your host.

### M3. Documents and clean-up

| Step | What |
|---|---|
| 3.1 | `README.md`: every URL and table row with an old path. The check is the broad pattern in Appendix B: **61 matching lines today, must be 0**. Appendix B also lists the lines that need a sentence and not only a prefix, and line 429 (administrator URLs, unchanged) which must be written in full. Add the section "URL scheme and routes layout" (about 30 lines: URL rule, the apps, size S and size L, how to add a resource) |
| 3.2 | `Routing/management_deploy_runbook.md`: lines 39, 40 and 46 use the new URLs (lines 38 and 45 describe the old `/event-log` and stay). Add a short "changed URLs" note for your front end: the table in section 3 and the client-visible items listed there |
| 3.3 | Delete `route_dumps/after_*.json` in the repo and on the host (`sudo rm`, they belong to root), keep `before.json` / `host_before.json` and the last dump. Keep the host backups at least 14 days |

## 6. Your commands on the host

Container and folder names are the ones in your `docker-compose.yml`. The api container bind-mounts the repo (`.:/app`): files in `~/jrdurt` are what `/app` sees. The Celery worker imports none of the files moved here and needs no rebuild (`kinds.py` only gains a constant it never reads; the next normal rebuild picks it up). Files that `sudo docker exec` creates in `route_dumps/` belong to root. Access tokens last only a few minutes (`JWT_EXPIRE_MINUTES` in `.env`; they also rotate after half of that): run each block right after its `TOKEN=` line and log in again if a block takes longer.

### 6.1 Before M1 (step 0.5)

```bash
cd ~/jrdurt
cp -a ~/jrdurt ~/jrdurt_backup_before_routes_$(date +%F)      # skip if you already made one today
# copy scripts/route_map.py and scripts/route_rules.json from the OneDrive repo into ~/jrdurt/scripts/  (uvicorn reloads once: harmless)
sudo docker exec alpen-api pip show fastapi sqlalchemy | grep -E "^(Name|Version)"
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/route_map.py dump route_dumps/host_before.json     # expect: 214 routes (2 WebSocket)
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -8                # 6 failed, 44 passed
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum                                           # note it: Claude compares it with the OneDrive repo
```

### 6.2 After Phase 1 (old URLs still valid)

```bash
cd ~/jrdurt
B=~/before_phase1_$(date +%F_%H%M); echo "rollback folder: $B"          # write the name down
mkdir "$B" && sudo docker stop alpen-api && mv app scripts tests "$B"/    # if you keep host-only files in scripts/ or tests/, copy them back from there
# copy the new app/, scripts/ and tests/ folders (whole folders) from the OneDrive repo into ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                       # expect 279
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum                   # must equal the hash Claude noted at delivery D1
sudo docker start alpen-api
sleep 10 && sudo docker logs --tail 30 alpen-api                                                   # started, no traceback
r() { sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/route_map.py "$@"; }
r dump route_dumps/host_after_1.json
r compare route_dumps/host_before.json route_dumps/host_after_1.json                              # OK: 214 routes before, 214 after, identical
r probe route_dumps/host_after_1.json                                                              # OK: probed 211 routes, 0 problem(s)
r names                                                                                            # OK: 0 undefined name(s)
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -8     # 6 failed (the known ones), the rest passed
```

`probe` sends no login, so it never runs a handler. These run the handlers, with the **old** URLs (they must still work after Phase 1):

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@alpenwege.dev","password":"!Password@5005"}' | jq -r .response_data.access_token)
for p in pois cards countries regions posts poi-regions gear tracks ref/companies auth/resource-types auth/access-policies users/me jobs management/settings; do
  printf "%s=%s " $p $(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/$p); done; echo      # all 200
head -c 23000000 /dev/zero > /tmp/big.gpx
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer $TOKEN" -F name=big -F "gpx_file=@/tmp/big.gpx;type=application/gpx+xml" http://localhost:8000/api/v1/tracks   # 413
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/ws_check.py --token "$TOKEN" --seconds 5 > /tmp/ws.txt; head -1 /tmp/ws.txt   # {"type": "sync", ...}
EMAIL=admin@alpenwege.dev PASSWORD='!Password@5005' bash scripts/smoke_tracks.sh | grep -E ": ready|Done|FAIL"           # five lines ending ": ready", then "=== Done ==="  (it uploads 5 test tracks per run)
```

Paste the result lines if anything differs.

### 6.3 After Phase 2 (new URLs)

Same deploy as 6.2 with `B=~/before_phase2_$(date +%F_%H%M)`, `host_after_2.json`, expected file count **280** and the hash Claude noted at D2. The compare line becomes:

```bash
r compare route_dumps/host_before.json route_dumps/host_after_2.json --rules scripts/route_rules.json     # OK: 214 routes before, 214 after, mapped by rules
```

Then the same handler checks with the **new** URLs (`scripts/smoke_tracks.sh` and `ws_check.py` already have them from step 2.5):

```bash
TOKEN=$(curl -s http://localhost:8000/api/v1/profile/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@alpenwege.dev","password":"!Password@5005"}' | jq -r .response_data.access_token)
for p in compendium/pois compendium/cards compendium/countries compendium/regions compendium/posts compendium/poi-regions explorer/gear explorer/tracks core/companies core/resource-types profile/access-policies profile/users/me management/my-jobs management/settings; do
  printf "%s=%s " $p $(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/$p); done; echo      # all 200
for p in pois jobs ref/companies users/me; do printf "old %s=%s " $p $(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/$p); done; echo   # all 404
head -c 23000000 /dev/zero > /tmp/big.gpx
curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer $TOKEN" -F name=big -F "gpx_file=@/tmp/big.gpx;type=application/gpx+xml" http://localhost:8000/api/v1/explorer/tracks   # 413 (mandatory: this is the silent-failure check)
curl -s http://localhost:8000/openapi.json | jq -r '.components.securitySchemes.OAuth2PasswordBearer.flows.password.tokenUrl'    # /api/v1/profile/auth/login
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/ws_check.py --token "$TOKEN" --seconds 5 > /tmp/ws.txt; head -1 /tmp/ws.txt   # {"type": "sync", ...}
EMAIL=admin@alpenwege.dev PASSWORD='!Password@5005' bash scripts/smoke_tracks.sh | grep -E ": ready|Done|FAIL"     # five lines ending ": ready", then "=== Done ==="
```

Optional full live check (writes test data: one archived track, event-log rows, a job):

```bash
sudo docker exec -w /app alpen-api sh -c "python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx && pip install -q httpx && python scripts/e2e_check.py --base http://localhost:8000 --gpx /tmp/full.gpx --worker" | tail -3     # 35 passed, 0 failed
```

## 7. Rollback

| Situation | How |
|---|---|
| A step fails in the scratch copy | Throw `work/` away, copy `old/` again, start over. The repo has not changed yet |
| Delivered to OneDrive, not deployed, you want to go back | Delete `app`, `scripts`, `tests` in the repo first, then extract the matching `Routing/backup_*.tar.gz` (before Phase 1, or after Phase 1 for going back from Phase 2). **Never extract over the migrated tree**: old files next to new folders break the imports (tested). Then re-create `old/` and `work/` |
| A check fails on the host after a phase | `cd ~/jrdurt && F=~/failed_$(date +%F_%H%M) && sudo docker stop alpen-api && mkdir "$F" && mv app scripts tests "$F"/ && mv "$B"/* . && sudo docker start alpen-api` (`$B` = the rollback folder from the deploy step; type its printed name if the variable is gone). The commands only move: `rm -rf` fails on the root-owned `__pycache__` files. No database change, so nothing else to undo. **Also restore the repo in OneDrive from the matching tar**, otherwise your next copy deploys the migrated code again |
| Everything, back to before Phase 1 | The same, with the Phase 1 rollback folder; or from the host backup: move `app scripts tests` away and `cp -a ~/jrdurt_backup_before_routes_<date>/{app,scripts,tests} .` |

## 8. Risks and how they are covered

| Risk | Covered by |
|---|---|
| A moved route loses its permission check or login dependency | `compare` (permission key, action, groups, `security` of every route); `ast_compare` |
| A route disappears (file not imported, router not included) | `compare` (`MISSING`); step 2.6 test "every endpoint file is imported" |
| A route is hidden by another (`/stats` and `/{id}`, two routes on one URL) | `probe` (also in pytest from step 2.6); `dump` stops on a duplicate method and path. Tested: `/{job_id}` before `/stats` gives 422 |
| Something inside a function or a constant changes (dropped call, typo, swapped parameter, changed code) | `ast_compare` |
| A forgotten import or a leftover renamed helper | `names` (and its pytest test) |
| Wrong table behind a reference route; middleware or exception handler lost | `compare` (captured model and slug, middleware list, exception handlers) |
| Upload-size guard silently stops (it matches one exact path) | `test_api_paths.py` (middleware installed, path equals the real route); mandatory 413 check in 6.2 and 6.3 |
| `Location` header points to a dead URL | `test_api_paths.py` and `ast_compare`; the live checks follow the header |
| Old file left next to the new folder | `deliver.py` deletes it; test of step 2.6; the loop in Appendix B |
| Host runs other code than the repo | The host baseline must show 214 routes (0.5); the file-list hash of 6.1, 6.2 and 6.3 must equal the hash Claude noted in the repo |
| Library versions change between two builds of the image | Every dump records the FastAPI version; `compare` warns when the two dumps differ (for example after a rebuild between phases) |
| A client calls an old URL | The gate (0.1 and before 2.1); old URLs give 404 (tested) |
| Half-copied files during `--reload` | The api container is stopped while copying; the repo is changed from a scratch copy in one delivery |
| Another edit of the repo in between | Rule 5: tripwire, and `deliver.py` refuses when the repo differs from its BASE copy |

## 9. Side findings (not part of the migration)

**S1. Admin job list returns 500 (question 13).** In `app/management/routes/admin_jobs.py` (named `jobs.py` after step 1.3), function `list_all_jobs`: the tuple `(T.created_at >= created_from, created_from)` builds `created_at >= None` before the `if value is not None` test, and SQLAlchemy raises. So `GET /management/jobs` fails unless both dates are given (original tree: no dates 500, both dates 200, only one date 500). Verified fix: replace the loop by plain conditions (17 lines).

```python
    base = select(T)
    if status is not None:
        base = base.where(T.status == status)
    if kind is not None:
        base = base.where(T.kind == kind)
    if user_id is not None:
        base = base.where(T.user_id == user_id)
    if task_name is not None:
        base = base.where(T.task_name == task_name)
    if subject_type is not None:
        base = base.where(T.subject_type == subject_type)
    if subject_id is not None:
        base = base.where(T.subject_id == subject_id)
    if created_from is not None:
        base = base.where(T.created_at >= created_from)
    if created_to is not None:
        base = base.where(T.created_at < created_to)
```

After the fix: no filter 200, `status=succeeded` 200, only `created_from` 200, only `created_to` 200, `status=bogus` 422.

**S2. Library versions are not pinned.** `requirements.txt` says `fastapi>=0.111.0`, so each image build can pick another FastAPI. The migration works on 0.111.1, 0.115.14, 0.161.1 and 0.162.0; every dump records the version. Pinning is a separate decision.

**S3. Not investigated:** when that 500 happened, curl received the 500 but a Python `httpx` client got "connection reset by peer" on the same request. It may be a sandbox effect.

**S4. Swagger's login dialog never worked.** The login route takes JSON `{email, password}`; the Swagger "Authorize" dialog sends a form, which gives 422. This is the same on the original tree (checked). So changing `tokenUrl` has no effect on a working feature. A working Swagger login would need a form login route; separate topic.

**S5. Latent bug: "public" scope on compendium data.** `apply_scope` for scope `public` reads `model.is_public`, but the compendium models (poi, card, country, region, post, poi_region) have no such column, so such a policy would end in a 500. No seeded policy uses it (guests read compendium with scope `all`). Worth knowing for the security test proposal; not touched here.

## 10. After the migration

- The security test proposal (`test_scenarios_security_proposal.md`) and the expand plan (`get_expand_implementation_plan.md`) mention old URLs and file paths. Their next versions should use the new ones; `route_map.py dump` lists everything.
- New routes follow the standard: size S file or size L folder, URL `/api/v1/{app}/{resource}`. Six checks of it are enforced by `test_routes_standard.py` (URL shape, every route served by its own function, no undefined names, no file next to a folder, every endpoint file imported, route file size); the rest is convention.
- Open follow-ups from the proposal: how link tables (`m2m`) and sub tables are exposed (top level or nested), tag names (kept as they are on purpose), schemas stay one file per resource.

---

## Appendix A. Exact moves (for a manual implementation)

### A.1 Reference tables (`core/routes/ref/`)

Each table file has this shape (here `company.py`):

```python
from app.core.models.models_ref import CoreRefCompany
from app.core.schemas.ref import RefBaseCreate, RefBaseRead, RefBaseUpdate

from ._factory import build_ref_router

router = build_ref_router(
    model=CoreRefCompany, create_schema=RefBaseCreate, update_schema=RefBaseUpdate,
    read_schema=RefBaseRead, slug="companies",
)
```

| File | Model | Schemas (create, update, read) | Slug |
|---|---|---|---|
| `company.py` | `CoreRefCompany` | `RefBase*` | `companies` |
| `gear_type.py` | `CoreRefGearType` | `RefBase*` | `gear-types` |
| `achievement_category.py` | `CoreRefAchievementCategory` | `RefWithFactor*` | `achievement-categories` |
| `achievement_scope.py` | `CoreRefAchievementScope` | `RefWithFactor*` | `achievement-scopes` |
| `achievement_type.py` | `CoreRefAchievementType` | `RefWithFactor*` | `achievement-types` |
| `difficulty_level.py` | `CoreRefDifficultyLevel` | `RefWithFactor*` | `difficulty-levels` |
| `point_reason.py` | `CoreRefPointReason` | `RefWithFactor*` | `point-reasons` |
| `post_type.py` | `CoreRefPostType` | `RefWithFactor*` | `post-types` |
| `rarity.py` | `CoreRefRarity` | `RefWithFactor*` | `rarities` |
| `region_type.py` | `CoreRefRegionType` | `RefWithFactor*` | `region-types` |
| `schedule_status.py` | `CoreRefScheduleStatus` | `RefWithFactor*` | `schedule-statuses` |
| `snow_condition.py` | `CoreRefSnowCondition` | `RefWithFactor*` | `snow-conditions` |
| `trail_condition.py` | `CoreRefTrailCondition` | `RefWithFactor*` | `trail-conditions` |
| `visibility.py` | `CoreRefVisibility` | `RefWithFactor*` | `visibilities` |
| `waypoint_type.py` | `CoreRefWaypointType` | `RefWithFactor*` | `waypoint-types` |
| `weather_condition.py` | `CoreRefWeatherCondition` | `RefWithFactor*` | `weather-conditions` |
| `sport_type.py` | `CoreRefSportType` | `SportTypeCreate`, `RefWithFactorUpdate`, `RefWithFactorRead` | `sport-types` |
| `difficulty_sport.py` | `CoreRefDifficultySport` | `DifficultySportCreate`, `DifficultySportUpdate`, `DifficultySportRead` | `difficulty-sports` |
| `compendium_type.py` | `CoreRefCompendiumType` | `CompendiumTypeCreate`, `CompendiumTypeUpdate`, `CompendiumTypeRead` | `compendium-types` |

Order in `ref/__init__.py`: as in this table (today's registration order).

### A.2 Resource folders (step 1.4)

Folder layout (example `poi/`):

```python
# poi/_router.py
from fastapi import APIRouter

router = APIRouter(prefix="/pois", tags=["Compendium - POI"])

# poi/__init__.py
from ._router import router
from . import upload_csv, rescan, get_many, create, get_one, update, delete

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (upload_csv, rescan, get_many, create, get_one, update, delete,)

__all__ = ["router"]
```

Why one shared router: FastAPI refuses to include a child router whose paths are `""` (our list and create endpoints) without a prefix (`Prefix and path cannot be both empty`; tested on 0.111, 0.115, 0.161). Why the order: with the same method, `/{job_id}` declared before `/stats` makes `/stats` answer 422 (tested).

Every endpoint file starts with its imports (absolute imports first), then `from ._router import router` (and `from ._shared import ...` if needed), then the function **copied unchanged** with its decorator.

| Folder | File | Function (unchanged) | Method and path (relative to the folder's prefix) |
|---|---|---|---|
| `poi/` | `upload_csv.py` | `upload_csv` | POST `/upload-csv` |
| | `rescan.py` | `rescan_poi` | POST `/{poi_id}/rescan` |
| | `get_many.py` | `list_pois` | GET `""` |
| | `create.py` | `create_poi` | POST `""` |
| | `get_one.py` | `get_poi` | GET `/{poi_id}` |
| | `update.py` | `update_poi` | PATCH `/{poi_id}` |
| | `delete.py` | `delete_poi` | DELETE `/{poi_id}` |
| | `_shared.py` | `EAGER` (was `_EAGER`: `compendium_type`, `main_region`), `apply_scope` until step 1.5 | |
| `card/` | same seven files | `upload_csv`, `rescan_card`, `list_cards`, `create_card`, `get_card`, `update_card`, `delete_card` | prefix `/cards`, tag `Compendium - Card` |
| | `_shared.py` | `EAGER` (`rarity`, `compendium_type`, `poi`), `apply_scope` until 1.5 | |
| `track/` | `create.py` | `create_track` (keeps `logger` and `settings = get_settings()`) | POST `""` |
| | `get_many.py` | `list_tracks` | GET `""` |
| | `get_one.py` | `get_track` | GET `/{track_id}` |
| | `geometry.py` | `get_track_geometry` | GET `/{track_id}/geometry` |
| | `performance.py` | `get_track_performance` | GET `/{track_id}/performance` |
| | `update.py` | `update_track` | PATCH `/{track_id}` |
| | `archive.py` | `archive_track` | DELETE `/{track_id}` |
| | `restore.py` | `restore_track` | POST `/{track_id}/restore` |
| | `reprocess.py` | `reprocess_track` | POST `/{track_id}/reprocess` |
| | `_shared.py` | `apply_visibility`, `ensure_visible`, `build_metrics` (were `_apply_visibility`, `_ensure_visible`, `_build_metrics`), `apply_scope` until 1.5 | |

`track/` prefix `/tracks`, tag `Explorer - Track`; order in `__init__.py`: `create, get_many, get_one, geometry, performance, update, archive, restore, reprocess`. Each file that logs defines `logger = logging.getLogger(__name__)` itself (the logger names change from `...routes.track` to `...routes.track.<file>`).

### A.3 Profile and management

| From | To |
|---|---|
| `profile/routes/{register,login,refresh,logout}.py` | `profile/routes/auth/` (same names) |
| `profile/routes/me.py` (`get_me`, `update_me`, `_user_to_read`) | `profile/routes/user/me.py` (endpoints) and `user/_shared.py` (`user_to_read`) |
| `profile/routes/admin.py` | `profile/routes/user/admin.py` (imports `user_to_read` from `._shared`) |
| `profile/routes/access_policy.py`, the six `*_resource_type*` functions | `resource_type.py` (step 1.2; moves to `core/routes/` in step 2.2) |
| `profile/routes/access_policy.py`, the six `*_access_polic*` functions | `access_policy.py` |
| `management/routes/jobs.py` (own jobs) | `management/routes/my_jobs.py` |
| `management/routes/admin_jobs.py` | `management/routes/jobs.py` |
| `JOB_STATUSES` in `management/routes/jobs.py` | `management/jobs/kinds.py` |

### A.4 The two new helper files

```python
# app/core/utils/scope.py  (step 1.5)
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.profile.permissions import AccessContext


def apply_scope(stmt, model, access: "AccessContext"):
    # Narrow a SELECT to the rows the caller may see:
    #   "own"    -> rows created by the caller
    #   "public" -> rows created by the caller or marked is_public
    #   "all"    -> no filter
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)  # noqa: E712
        )
    return stmt


# app/core/utils/api_paths.py  (step 2.0 with the old values; 2.1 and 2.4 change the two values shown here)
API_V1 = "/api/v1"


def job_url(job_id) -> str:
    # Where the owner reads one of their jobs (Location header of the 202 responses).
    return f"{API_V1}/management/my-jobs/{job_id}"      # step 2.0: f"{API_V1}/jobs/{job_id}"


# POST to this path uploads a GPX file; UploadSizeLimitMiddleware matches this exact path.
TRACK_UPLOAD_PATH = f"{API_V1}/explorer/tracks"         # step 2.0: f"{API_V1}/tracks"
```

## Appendix B. Checks that need no tool

```bash
# 1. no file next to a folder of the same name (must print nothing)
for f in app/*/routes/*.py; do [ -d "${f%.py}" ] && echo "DUPLICATE: $f"; done

# 2. no full old URL left in code and scripts (must print nothing; the tools quote old URLs on purpose)
grep -rnE '/api/v1/(jobs|tracks|auth|users|ref|ws|pois|cards|countries|regions|posts|poi-regions|gear)\b' app scripts --include=*.py --include=*.sh | grep -v -e api_paths.py -e e2e_check.py -e ast_compare.py
grep -nE '\$API/(auth|tracks|jobs)' scripts/smoke_tracks.sh          # must print nothing (the script writes $API/... without /api/v1)

# 3. no old comment (must print nothing)
grep -rn 'GET /jobs' app

# 4. README.md: 61 lines match today, must be 0 after step 3.1
NAMES='auth|users|ref|jobs|ws|tracks|gear|pois|cards|countries|regions|posts|poi-regions'
grep -cE "/api/v1/($NAMES)\b|(^|[^A-Za-z0-9_/.-])/($NAMES)([/\`{ ),.;:]|\$)" README.md
```

README lines that the pattern finds but that need a sentence, not just a prefix: line 116 keeps "Base path: `/api/v1`" but every table path below needs its app prefix (`/profile/users/me`, `/explorer/gear`, `/core/{slug}`, `/compendium/countries`); line 142 "all under `/ref/`" becomes "all under `/core/`"; line 206 "Same pattern for: `/regions`, ..." needs the `/compendium` prefix; line 395 (tree comment `# /jobs, /ws, /management/*`) becomes `# /management/* (event-log, settings, jobs, my-jobs, ws, celery, broadcast)`; line 420 (`POST /tracks`, `/tracks/{id}/reprocess`, `/pois/{id}/rescan`, `/cards/{id}/rescan`) and line 442 (`GET /jobs/{id}`). **Line 429 is different:** `/jobs/stats` and `/jobs/{id}` there are the administrator URLs `/api/v1/management/jobs/...`, which do not change. A blind replacement of `/jobs` would turn them into `my-jobs`; write them in full (`/api/v1/management/jobs/stats`, `/api/v1/management/jobs/{id}`) so that the pattern no longer flags them. Optional, already wrong today: the README tree lists `app/auth/` and `app/users/` (they are in `app/profile/`), and line 101 says the token comes in an `Authorization` header while the code sets `X-Access-Token`.

## Appendix C. Execution log (the implementer fills this in)

| Step | Date | Result (paste the compare line, hashes where asked) |
|---|---|---|
| 0.0 management deployed | 2026-10-24 | you confirmed: deployed and checked |
| 0.1 permission, gate answered, nothing else editing | 2026-10-24 | delete permission granted; gate answered: no production clients, only test; repo unchanged since the verified copy (diff empty) |
| 0.2 backup (tar) | 2026-10-24 | `Routing/backup_before_routes_2026-10-24.tar.gz` (128 KB); repo hash before: `d140004c7fcdd2fe`, 223 files |
| 0.3 tool files in repo, `old/` and `work/` | 2026-10-24 | 3 tool files in `scripts/`; scratch copies in `/tmp/ms/` |
| 0.4 sandbox baseline | 2026-10-24 | 214 routes (2 WebSocket) written to route_dumps/before.json |
| 0.5 host baseline (214 routes?), hash | **open: you** | run 6.1 and compare the hash with `d140004c7fcdd2fe` (223 files, the state before the migration) |
| 1.1 ref package | 2026-10-24 | OK: 214 routes before, 214 after, identical |
| 1.2 profile | 2026-10-24 | OK: 214 routes before, 214 after, identical |
| 1.3 management | 2026-10-24 | OK: 214 routes before, 214 after, identical |
| 1.4 poi, card, track | 2026-10-24 | OK: 214 routes before, 214 after, identical |
| 1.5 apply_scope | 2026-10-24 | OK: 214 routes before, 214 after, identical |
| End of Phase 1 (probe, names, ast_compare, pytest) | 2026-10-24 | probed 211, 0 problems; 0 undefined names; 0 unexpected differences (158 vs 152 definitions); pytest 6 failed (known), 44 passed |
| D1 delivered, `work_after_d1`, tar after Phase 1, hash (279 files) | 2026-10-24 | 67 added, 12 changed, 11 deleted; hash `0b93dc0ed51f28a3`, 279 files; `Routing/backup_after_phase1_2026-10-24.tar.gz` |
| Phase 1 host deploy and checks (6.2), hash equal? | **skipped as a separate stage** | D1 and D2 are both in the repo now; deploy once with 6.3 (or deploy `backup_after_phase1` first with 6.2 if you want the staged rollback point) |
| Gate before 2.1: no other client? | 2026-10-24 | no production clients, only test: clean break accepted |
| 2.0 api_paths | 2026-10-24 | OK: mapped by rules up to step 0 |
| 2.1 compendium, explorer | 2026-10-24 | OK: mapped by rules up to step 1 |
| 2.2 core | 2026-10-24 | OK: mapped by rules up to step 2 |
| 2.3 profile | 2026-10-24 | OK: mapped by rules up to step 3 |
| 2.4 management | 2026-10-24 | OK: mapped by rules up to step 4 |
| 2.5 scripts | 2026-10-24 | OK (step 4 rules); ws_check.py 2 lines, smoke_tracks.sh 12 lines, e2e_check.py added |
| 2.6 standard test | 2026-10-24 | OK (step 4 rules); tests/test_routes_standard.py added |
| End of Phase 2 (all rules, probe, names, ast_compare, pytest) | 2026-10-24 | OK: 214 routes before, 214 after, mapped by rules; probed 211, 0 problems; 0 undefined names; 0 unexpected differences; pytest 6 failed (known), 56 passed |
| D2 delivered, hash (280 files) | 2026-10-24 | 5 added, 19 changed, 1 deleted; hash `a46f5b90d224a976`, 280 files; repo == work copy |
| Phase 2 host deploy and checks (6.3), hash equal? | **open: you** | expected file count 280, hash `a46f5b90d224a976` |
| 3.1 README | 2026-10-24 | broad pattern: 61 lines before, 0 after; new section "URL scheme and routes layout"; project tree and `X-Access-Token` corrected |
| 3.2 runbook and client note | 2026-10-24 | lines 39, 40, 46 updated; section 3b "Changed URLs" added |
| 3.3 clean up | **open** | `route_dumps/` exists only in the scratch copies, not in the repo; host dumps and backups: yours |

## Appendix D. What the independent reviews changed

**Review of v1** (2 blockers, 5 major):

| Finding | Fix |
|---|---|
| Blocker: the host checks used scripts whose URL edits came later | The edits are step 2.5, before the Phase 2 host checks; the standard test is step 2.6 |
| Blocker: the rollback failed (restoring over the new tree, `rm -rf` on root-owned files, only `app/` restored) | Section 7: delete before extracting, move instead of delete, `app scripts tests` together |
| "Authorize" check cannot pass | Replaced by the `tokenUrl` check and S4 |
| Safety net over-claimed; only 3 of 14 body-level mistakes caught | `ast_compare.py`, hardened `test_api_paths.py`, the probe inside pytest, mandatory 413 check |
| README check missed lines 395, 420, 442 and a code comment | Broad pattern (61 lines), hand list, comment fixed in step 2.4 |
| Runbook line numbers wrong | Lines 39, 40, 46 |
| Missing gates | Gate question, permission step, tripwire, file counts, scratch copy and one delivery |
| Phase 1 host check never ran a handler | 6.2 has the authenticated checks with the old URLs |

**Review of v2** (no blocker; 6 major):

| Finding | Fix |
|---|---|
| Undefined names pass every layer | `route_map.py names` and a pytest test; part of the end-of-phase checks |
| Swapped model or slug between reference files, removed or reordered middleware, changed constants slip through | `compare` records the captured model and slug, the middleware list and the exception handlers; `ast_compare` compares all top-level constants |
| `run_all.sh` did not enforce its pytest gate | It stops unless exactly the 6 known tests fail; it stops when pytest is missing |
| The scripts only stopped on unknown functions | They also stop on any unknown top-level statement, and on a reference table they do not know |
| `deliver.py` could overwrite or delete foreign edits, and could stop half way | BASE argument (refuses when the repo differs), delete test first, identity check afterwards |
| Scratch copies live in `/tmp` and may be gone at Phase 2 | Recovery from the two tar files (section M0) and the `work_after_d1` snapshot |
| Minor: tripwire per phase, rollback folder names with date, shell function instead of a variable for `R`, `ws_check` output without `head` pipe, token lifetime note, test data note, `smoke_tracks.sh` grep, README line 429, file-list hash instead of a count, host rollback also in OneDrive, wording and undefined terms, tidy generated files | Fixed |
