# GET `?expand=`: implementation plan v2 (single-object GET endpoints)

Plan v2, 2026-10-24, reviewed 2026-10-25. **Status 2026-10-26: delivered to the repo with option B and all recommended answers (Appendix C); not yet deployed on your host (section 6 is your next step).** The whole change was built and tested on a copy of your repo (the tools are in `expand_tools/`, Appendix D). This plan replaces `get_expand_implementation_plan.md` (v1, 2026-10-21), which was written before the routes were restructured and before tracks, jobs and settings existed. Your decisions are in `get_expand_decisions.md`. Two independent reviewers checked this plan; what they changed is in Appendix E.

Four words used below: **scratch copy** = a copy of the repo in the sandbox (`/tmp`) where the scripts run first; **delivery** = copying the verified result from the scratch copy into the real repo in one go (this one is **D4**, after D1 to D3 of the routes work); **gate** = a question that must be answered before work continues; **link** = a field that points to another object (`created_by`, `main_region`, `sport_type`, ...).

## 0. What happens, in short

1. Every **single-object GET** (`GET .../{id}`) returns its links as IDs only, as you decided. With `?expand=` you ask for the full object behind a link: `GET /api/v1/compendium/pois/{id}?expand=main_region.country,created_by`.
2. **33 endpoints** get the option (list in section 3.1). **Lists, POST, PATCH, DELETE, CSV upload, WebSocket and all other GETs do not change.**
3. A dotted path goes at most 3 levels deep, one request may ask for at most 10 links, a wrong name answers `400` and lists the allowed names.
4. The code follows your standard: one new helper in `app/core/utils/` (like `scope.py`), `*Detail` schemas next to the `*Read` schemas, each `get_one.py` stays one file with one function, the route table is checked with `route_map.py`, tests in `tests/`, a live check in `scripts/`.
5. **No database change, no SQL.** New links between model classes exist only in Python (`create_all` is not affected). The Celery worker needs no rebuild.
6. **One decision is yours and matters** (question 7, section 2): who may see the profile of a user that is expanded. As you decided it, the new parameter would show every creator's whole profile to anyone with an account. I recommend a safer rule that is already built and tested (option B).

## 1. What was tested, and what was not

All of this ran on a copy of your repo (state of 2026-10-24: 505 `.py` files, hash `55209df87733162f`, the Phase 3 layout) with the real application code, a real Postgres 16 + PostGIS, Redis and a Celery worker. Your repo was not touched. An independent reviewer repeated the runs on his own copy; every number below was reproduced, except the live run of option B, the speed table, the other two library stacks and the Newman run, which he could not repeat.

| Test | Result |
|---|---|
| The change applied by one script (`apply_expand.py`) to a fresh copy | Applied without a `STOP`; the script refuses to run when a file is not what it expects |
| `pytest` | Before: 64 passed. After: **102 passed** (64 + 38 new). With option B of question 7: 107 passed |
| `route_map.py compare before after --expand` | `OK: 214 routes before, 214 after, identical except the routes that gained ?expand=`, 33 routes gained it. Without `--expand` the same compare fails (100 problems). It is strict: on the 33 routes it accepts only the new parameter, the `expand_plan` entry among the dependencies, `...Read_` becoming `...Detail_` in the 200 answer, and a `...Read` schema no longer used in the function body. A changed permission key, a wrong answer schema or a lost login dependency fails |
| `route_map.py probe`, `names` | 211 routes probed, 0 problems; 0 undefined names |
| Live: `scripts/expand_check.py` (new, 73 checks with a worker) | 73 of 73. Option B: 75 of 75 |
| Live: your `scripts/e2e_check.py --worker` (35 checks) on the changed code | 35 of 35, no traceback in the API log |
| Three library stacks, each with the final code | the oldest your `requirements.txt` allows (FastAPI 0.111.0, pydantic 2.7.0, SQLAlchemy 2.0.30, Python 3.10); the sandbox default (FastAPI 0.161.1, pydantic 2.14.1, SQLAlchemy 2.0.55, Python 3.10); the newest (FastAPI 0.162.0, pydantic 2.14.1, **SQLAlchemy 2.1.6**, Python 3.12). On all three: 102 passed, the compare is `OK`, and both live checks pass (73 and 35) |
| Postman | `build_postman.py` rebuilds your delivered collection byte for byte from the old API; from the new API it only adds a disabled query parameter `expand` (with the allowed names in its description) to the 33 "Get one" requests. A plain Newman run of the whole collection in my sandbox executes 219 requests; on the old code **37** assertions fail, on the new code **36**: the same file-upload requests and the calls that depend on an uploaded file (your Phase 3 run showed 0 failures with its own way of running; compare your run with your own earlier result, the rule is "the same set fails before and after"). No new failure |
| Deliberate mistakes | Twelve mistakes of mine and eighteen of the reviewer's were put into the changed code one at a time. In the first round three slipped through every check: the `expand` parameter written before the login parameter on one route, a changed permission key on one route, the access check removed from one route. Each now has a check (a test, the stricter compare, the live 404 check) and is caught. Also caught: wrong answer schema, wrong schema in `expand_plan`, older and newer swapped in the compare answer, a lost relationship, depth limit changed, the helper reading every link, track `metrics` dropped |
| `scripts/ast_compare.py` | **Not used.** It checks that route code did not change; here the code of the single GET functions changes on purpose. `route_map.py compare --expand`, the tests and the live checks replace it |

**Speed** (sandbox, local database, 120 requests each; measured on the first build, the later fixes only touch parsing; the host will differ, the ratios should not). The SELECT counts include the 2 statements of the login check (the caller and the caller's credentials):

| Request | Today | After the change |
|---|---|---|
| `GET /compendium/pois/{id}` | 5 SELECTs, 12.4 ms median | **3 SELECTs, 9.7 ms** |
| `GET /compendium/regions/{id}` | 6 SELECTs, 13.5 ms | **3 SELECTs, 9.6 ms** |
| the same POI with `?expand=compendium_type,main_region` (the two links you get today, now the full objects) | 5, 12.4 ms | 5, 12.6 ms |
| POI with `?expand=created_by` | n/a | 5, 12.3 ms (a user link costs 2 statements: the user and the credentials that load with it) |
| POI with 4 links, 3 levels deep | n/a | 9, 18.8 ms |
| country, reference table, event log without `expand` | 3, about 9 ms | 3, about 9 ms |

So the change does **not** slow anything down: a plain GET is cheaper than today, and only a caller who asks for links pays for them (about one small query per link). The worst case allowed (10 links) is about 20 statements.

**Not covered by any tool:** your host and Docker, your real data, and the copy from OneDrive to `~/jrdurt`. That is why section 6 has checks that **you** run in your container. **Not tested:** `GET /explorer/tracks/{id}` in Postman (the collection's upload request needs a file chosen by hand).

## 2. Decisions as I understood them

You answered the questions of v1 earlier; I carry them over. **Questions 7 to 10 are new** because the code grew (tracks, jobs, settings), I measured things, and the reviewers found a privacy point. Tell me the number of any line that is wrong.

| # | Topic | Chosen | What it means |
|---|---|---|---|
| 1 | Mechanism | `?expand=` | A comma-separated list of links, a whitelist per endpoint. No generic `depth=N` |
| 2 | Default and expanded | IDs only; full object | A link is only an ID unless asked for; asked for, it is the full object |
| 3 | Always expanded today | none | `compendium_type`, `main_region`, `poi`, `rarity`, `country`, `parent`, `region_type`, `post_type`, `region`, `entity_type` are also only IDs now. Speed checked above: cheaper, not slower |
| 4 | Depth and limits | 3 levels, 10 links, `400` | Several paths allowed, merged; a parent shared by several paths counts once; the whole value may be 1000 characters at most |
| 5 | Scope | single-object GETs only | Lists, POST, PATCH, DELETE unchanged |
| 6 | Clients | clean break | **Assumption: nothing besides your own scripts and Postman calls these GETs** (your answer for the URL change). A client that reads `compendium_type` or `main_region` of a single POI now has to ask for it |

**Questions for you (numbered, with my recommendation).** Answer "all recommended" or the numbers you want changed.

**7. Who sees which fields of an expanded user?** Today the profile of a user (`/profile/users/{id}` and the list) can be read by **administrators only**. Your rule is: whoever may read an object sees everything expanded inside it, including the whole profile of the creator. Option A below applies that rule literally, and then `?expand=created_by` on any object a guest may read hands out the creator's **email, birth date, height, heart rates, `is_active`, `last_active_at` and `user_group`** (which tells who is an administrator). Registration is open (`POST /profile/auth/register` creates a `guest` and returns a token at once), so "an account" means anyone. This reaches **27 of the 33 endpoints**: only the event log, the jobs, the settings, the access policies and the resource types are administrator-only. Compendium objects (POI, region, country, card, post, poi-region) are readable by `guest`, and their creators include editors, who are ordinary users; tracks and gear are created by ordinary users. In short: option A makes the new parameter a way around the rule that protects the user endpoints.
- **A.** As you decided: everybody sees the whole profile. Nothing more to build.
- **B.** Everybody sees `id` and `username`; the other profile fields are `null`, unless the caller is an administrator or the user himself. Built and tested (`apply_viewer.py`): +5 tests, +2 live checks, the helper gets a small hook, every one of the 33 routes passes the caller (a test enforces it). The answer keeps its shape; hidden fields are `null`; a forgotten caller hides fields, it never shows them.
- **C.** Only `id` and `username` for everybody except administrators.

Recommendation: **B** (C if the username itself is private). You can always see who made something, and nobody's health data is handed out. It is a one-line switch later in either direction (the alias `ExpandedUser`).

**8. Which endpoints get `expand`?** Section 3.1 has all 33 with the names each accepts. New since v1: tracks (`sport_type`, `difficulty_level`, `difficulty_sport`, `start_poi`, `end_poi`, `created_by`), the administrator's job (`user`), settings (`updated_by`), access policies (`resource_type`), resource types and compendium types. **Not included on purpose:** `/profile/users/{id}` and `/me` (a user has no link to another object), your own job `my-jobs/{id}` (no user, its `subject` is a type and an id), a Celery task, `main_photo`, `poi_access`, `gpx`, `geo_record` (no schema to show), and the object a log entry is about. Recommendation: **all 33**.

**9. A link that was not asked for: `null` or no key at all?** I return the key with the value `null` (`"main_region_id": "...", "main_region": null`). The answer always has the same shape, the Swagger schema is simple, and `null` is also what an empty link shows. The alternative is to leave the key out (needs hand-made JSON, and the Swagger schema would no longer match). Recommendation: **`null`**.

**10. Gate: is the Phase 3 layout deployed on your host?** My copy has the Phase 3 layout (505 files). If your host still runs older code, deploy Phase 3 first and this change after it; if the host already runs Phase 3, this change is deployed alone. Section 6 has the commands for both. Recommendation: tell me which one it is; I do not touch your host either way.

Defaults I chose (tell me if you want any of them changed): the answer field next to an ID keeps the name that already exists (`compendium_type`, `main_region`); for users it is `created_by_user`, `changed_by_user`, `updated_by_user` and, on the administrator's job, `user`, asked for as `created_by`, `changed_by`, `updated_by`, `user`. A plain gear answer still has no `created_by` (nothing is added; `expand=created_by` works). The event-log compare endpoint takes `changed_by` and `entity_type` and applies them to both entries; its `entity_type` is now `null` unless asked for. Nested objects are the full `*Detail` shape (more fields than the old slim nested objects: a region has `bbox`, the texts, `country_id`, ...).

**A limit that stays in every option:** an expanded object is shown by the rule "who may read the object you asked for", not by the policy of the linked object. Today the policies of `poi`, `region`, `country` and `ref` are `read: all` for all four groups, so nothing is revealed that could not be read anyway. If an administrator narrows one of them later, `tracks/{id}?expand=start_poi` would still show that POI.

## 3. What changes, in numbers

| Area | Before | After |
|---|---|---|
| Routes | 214 (212 HTTP, 2 WebSocket) | 214, same URLs, methods, tags and permissions; **33 GET operations gain one optional query parameter `expand`** |
| `.py` files under `app/` | 505, hash `55209df87733162f` | 506, hash `5a0dee4fcbd0cf7e` (the same for option B: it only adds a test file) |
| Delivery D4 (`deliver.py`) | | **5 files added, 57 changed, 0 deleted** (option B: 6 added). `README.md` and the Postman collection are copied by hand (the tool does not touch them) |
| Tests | 64 | 102 (107 with option B) |
| Read-only links in the models | | `created_by_user` on **45 of the 71 mapped classes** (once all model packages are imported; one declaration in `CreatorMixin`), and: `MgmtLogEvent.changed_by_user`, `MgmtLogJob.user`, `MgmtSettings.updated_by_user`, `ExplorerAggGear.company` and `.gear_type`, `ExplorerAggTrack.sport_type`, `.difficulty_level`, `.difficulty_sport`, `.start_poi`, `.end_poi`, `CoreRefDifficultySport.sport_type`. All `lazy="raise"` and `viewonly`: nothing is ever loaded by accident or written through them. One property `ProfileUsrUser.user_group` so that an expanded user shows its group like `/profile/users/me` does |

The 62 files by area:

| Area | Files | What |
|---|---|---|
| New | 5 | `app/core/utils/expand.py` (the helper, 172 lines), `tests/test_expand.py`, `tests/test_expand_wiring.py`, `tests/test_expand_routes.py`, `scripts/expand_check.py` |
| Models | 8 | `core/base.py`, `profile/models/user.py`, `management/models/{event_log,job,settings}.py`, `explorer/models/models_agg/{gear,track}.py`, `core/models/models_ref/core_ref_difficulty_sport.py` |
| Schemas | 14 | a `*Detail` class next to the `*Read` class in `core/schemas/ref.py` (4 classes), the six compendium schema files, `explorer/schemas/{gear,track}.py`, `management/schemas/{event_log,job,settings}.py`, `profile/schemas/access_policy.py` (2 classes); `profile/schemas/user_read.py` gets the alias `ExpandedUser` |
| Routes | 34 | the `get_one.py` of the 33 endpoints (the event-log compare is `compare.py`), plus `management/routes/settings/_shared.py` (`get_row` takes optional load options) |
| Tool | 1 | `scripts/route_map.py`: `compare --expand` and an optional query string for `probe` |

Existing `*Read`, `*Create`, `*Update` schemas stay as they are (lists, POST and PATCH keep using them). The two compare schemas `CompareEntryRef` and `EventLogCompare` are changed in place; only the compare route uses them. The `EAGER` lists in the `_shared.py` files stay: lists, create and update still use them.

### 3.1 The 33 endpoints

All paths start with `/api/v1`. "Names" are the links you can ask for at the first level.

| Endpoint | Names | Answer schema |
|---|---|---|
| `compendium/pois/{id}` | `compendium_type`, `main_region`, `created_by` | `PoiDetail` |
| `compendium/regions/{id}` | `country`, `region_type`, `parent`, `created_by` | `RegionDetail` |
| `compendium/countries/{id}` | `created_by` | `CountryDetail` |
| `compendium/cards/{id}` | `rarity`, `compendium_type`, `poi`, `created_by` | `CardDetail` |
| `compendium/posts/{id}` | `post_type`, `created_by` | `PostDetail` |
| `compendium/poi-regions/{id}` | `poi`, `region`, `created_by` | `PoiRegionDetail` |
| `explorer/gear/{id}` | `company`, `gear_type`, `created_by` | `GearDetail` |
| `explorer/tracks/{id}` | `sport_type`, `difficulty_level`, `difficulty_sport`, `start_poi`, `end_poi`, `created_by` | `TrackDetail` (`metrics` as before) |
| `core/{companies, gear-types}/{id}` | `created_by` | `RefBaseDetail` |
| `core/{14 factor tables, sport-types}/{id}` | `created_by` | `RefWithFactorDetail` |
| `core/compendium-types/{id}` | `created_by` | `CompendiumTypeDetail` (keeps `is_collectable`) |
| `core/difficulty-sports/{id}` | `sport_type`, `created_by` | `DifficultySportDetail` |
| `core/resource-types/{id}` | `created_by` | `ResourceTypeDetail` |
| `management/event-log/{id}` | `entity_type`, `changed_by` | `EventLogDetail` |
| `management/event-log/{id_1}/compare/{id_2}` | `entity_type`, `changed_by` (both entries) | `EventLogCompare` |
| `management/jobs/{id}` (administrator) | `user` | `JobAdminDetail` |
| `management/settings/{key}` | `updated_by` | `SettingDetail` |
| `profile/access-policies/{id}` | `resource_type` | `AccessPolicyDetail` |

Below a link you may ask for what that object offers: a **region** offers `country`, `region_type`, `parent`, `created_by`; a **POI** offers `compendium_type`, `main_region`, `created_by`; a **difficulty sport** offers `sport_type`, `created_by`; a **resource type** (below an access policy) offers `created_by`; a country, a reference row and a company offer `created_by`; a **user** and an **entity type** offer nothing. So `explorer/tracks/{id}?expand=start_poi.main_region.country` is a path of 3 levels and `compendium/pois/{id}?expand=main_region.parent.parent.country` (4 levels) is refused.

### 3.2 What clients see besides the new parameter

- **Single GET answers lose the nested objects they had by default** (now `null` unless asked for): POI `compendium_type`, `main_region`; region `country`, `region_type`, `parent`; card `rarity`, `compendium_type`, `poi`; post `post_type`; poi-region `poi`, `region`; event log `entity_type` (also in compare). The IDs next to them are unchanged.
- **New keys, all `null` unless asked for:** `created_by_user` (and `changed_by_user`, `updated_by_user`, `user`), the track links, gear `company` / `gear_type`, access policy `resource_type`.
- **Lists, POST, PATCH, DELETE answer exactly as before.** A list item still carries its nested objects, a single GET does not: this difference is on purpose.
- In `/openapi.json` the 33 operations get the new schema names (`ApiResponse_PoiRead_` becomes `ApiResponse_PoiDetail_`) and the parameter `expand` with the allowed names in its description. URLs, operation ids and the number of operations (212) do not change.
- A misspelled parameter name (`Expand`, `expand[]`) is ignored, like every unknown query parameter in this API; a parameter written twice keeps only the last value.
- The Postman collection is rebuilt (Appendix A.5): the 33 "Get one" requests get a disabled `expand` query parameter.

## 4. Rules for whoever implements this

1. **Backup first.** The repo has no git. Step E0.1 is not optional.
2. **The script is the change.** `expand_tools/apply_expand.py` makes exactly the change that was tested. It stops with `STOP: ...` when a file is not what it expects (for example edited since). If someone edits by hand instead, the result must be identical to the script's result (`diff -r`).
3. **Work on a scratch copy, deliver once** with `deliver.py` (dry run first). The repo never holds a half-done change. If a check fails, throw the scratch copy away and start again from `old/`.
4. **Single GETs only.** No change to lists, create, update, delete, CSV upload, WebSocket or any other GET. The `EAGER` lists stay.
5. **The checks of section 5.1 run in the scratch copy before delivering and on your host after deploying.**
6. **Nobody else edits `app/`, `tests/` or `scripts/` between the scratch copy and the delivery.** Same files, no git. `deliver.py` refuses to run if the repo differs from its base copy. Tripwire right before the delivery, after the backup of E0.1: `find app scripts tests README.md -newer Routing/backup_before_expand_<date>.tar.gz -type f` must list nothing.
7. **On the host the api container is stopped while `app/` is replaced** (section 6), otherwise `uvicorn --reload` restarts on half-copied code.
8. **No SQL, no worker rebuild.** The worker container imports the models (`app/worker/model_registry.py`) and keeps running its old code until your next normal rebuild; a worker started from the changed code processed a GPX track in my runs, so the next rebuild is safe.
9. **I never run SQL and never touch your host.** I change the repo in OneDrive; you copy it to `~/jrdurt` and run the checks.
10. **Access tokens on your host last 5 minutes** (rotation after 2.5). `scripts/expand_check.py` takes the new token from `X-Access-Token` and logs in again after a 401; for hand-made `curl` calls run the `TOKEN=` line again when you get a 401.

Who does what: **Claude** (this app) does E0.1 to E3 with the tools; **you** answer the questions, copy the repo to the host and run section 6.

## 5. Milestones

### 5.1 The checks

In the scratch copy before delivering (they run in about two minutes) and on your host after deploying (section 6). `<old>` is the untouched copy (on your host: the dump you took before deploying):

```bash
python scripts/route_map.py dump route_dumps/after_expand.json
python scripts/route_map.py compare <old>/route_dumps/before_expand.json route_dumps/after_expand.json --expand
        # NOTE 33 route(s) gained the query parameter expand / OK: 214 routes before, 214 after, identical except the routes that gained ?expand=
python scripts/route_map.py probe route_dumps/after_expand.json        # OK: probed 211 routes, 0 problem(s)
python scripts/route_map.py names                                      # OK: 0 undefined name(s)
python -m pytest -q                                                    # 102 passed (107 with option B)
python scripts/expand_check.py --gpx /tmp/full.gpx --worker            # 73 passed, 0 failed (75 with option B)
python scripts/e2e_check.py --gpx /tmp/full.gpx --worker               # 35 passed, 0 failed
```

`compare --expand` accepts a difference only on a GET route that gained exactly one query parameter named `expand`, and then only these: the parameter list, the `expand_plan` entry among the dependencies, `...Read_` becoming `...Detail_` in the 200 answer, and a `...Read` schema that the function no longer names. Everything else must be identical, nothing may be added or removed. `expand_check.py` is a live check like `e2e_check.py` (httpx, the seeded users, the compendium seed, a Celery worker for `--worker`); it creates and deletes a country, gear, a card, a post and a poi-region link, archives one track, changes and resets one setting. If it stops on an unexpected answer it prints which check came last, the summary, and still cleans up.

### 5.2 Steps

| Step | Who | What |
|---|---|---|
| E0.0 | You | Answer questions 7 to 10 |
| E0.1 | Claude | Backup: `tar czf Routing/backup_before_expand_<date>.tar.gz --exclude=__pycache__ app scripts tests README.md Routing/postman` from the repo root |
| E0.2 | Claude | Make the scratch copies: `old/` = a copy of the repo (never changed again), `work/` = a copy of `old/`; check that the repo still has 505 files and hash `55209df87733162f` (otherwise the script stops and the plan is adapted); baseline: `python scripts/route_map.py dump route_dumps/before_expand.json` in `old/` |
| E1 | Claude | In `work/`: `python expand_tools/apply_expand.py work` (7 steps: helper and the `ExpandedUser` alias; model links; `*Detail` schemas; the 33 routes; `route_map.py compare --expand`; the three test files and `expand_check.py`; README). Option B on top: `apply_viewer.py work` and `apply_viewer_tests.py work` |
| E2 | Claude | The checks of 5.1 in `work/` against Postgres, Redis and a Celery worker; Newman with the rebuilt collection |
| E3 | Claude | **Delivery D4.** `python deliver.py work <repo> old --dry-run` (expect `5 added, 57 changed, 0 deleted`; option B: `6 added`), then for real; copy `work/README.md` to the repo; rebuild the Postman collection from the new `/openapi.json` (A.5) and copy both files to `Routing/postman/`; note the file-list hash (506 files, `5a0dee4fcbd0cf7e`) in Appendix C |
| E4 | You | Deploy and check on your host (section 6) |

If `/tmp` is gone when E0.2 starts (a later session): `old/` and `work/` are made again from the repo with the recipe in Appendix D; nothing else is needed.

## 6. Your commands on the host

Container and folder names are the ones in your `docker-compose.yml`. The api container bind-mounts the repo (`.:/app`): files in `~/jrdurt` are what `/app` sees. Files that `sudo docker exec` creates in `route_dumps/` belong to root. Tokens are short-lived: `expand_check.py` handles that itself.

**If the host already runs Phase 3:**

```bash
cd ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                   # expect 505
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum              # must start with 55209df87733162f
        # if the count or the hash differs: STOP and tell me, the host does not run the state this plan started from
r() { sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/route_map.py "$@"; }
r dump route_dumps/host_before_expand.json                                                   # 214 routes (2 WebSocket)
B=~/before_expand_$(date +%F_%H%M); echo "rollback folder: $B"
mkdir "$B" && sudo docker stop alpen-api && mv app scripts tests "$B"/ && { cp README.md "$B"/ 2>/dev/null || true; }
# copy the folders app/, scripts/, tests/ (whole folders) and README.md from the OneDrive repo into ~/jrdurt (README.md replaces the old one)
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                   # expect 506
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum              # must start with 5a0dee4fcbd0cf7e
sudo docker start alpen-api
sleep 10 && sudo docker logs --tail 30 alpen-api                                             # started, no traceback
r dump route_dumps/host_after_expand.json
r compare route_dumps/host_before_expand.json route_dumps/host_after_expand.json --expand    # NOTE 33 route(s) ..., then OK
r probe route_dumps/host_after_expand.json                                                   # OK: probed 211 routes, 0 problem(s)
r names                                                                                      # OK: 0 undefined name(s)
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -3     # 102 passed (107 with option B)
sudo docker exec -w /app alpen-api sh -c "pip install -q httpx && python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx && python scripts/expand_check.py --gpx /tmp/full.gpx --worker" | tail -6
        # N passed, 0 failed (73 with option A, 75 with option B)
sudo docker exec -w /app alpen-api python scripts/e2e_check.py --gpx /tmp/full.gpx --worker | tail -2     # 35 passed
```

Then your Postman collection (the rebuilt one, `skip_deletes=true`) if you like; the folder **Cleanup (optional)** after it. The Celery container is not rebuilt.

**If the host still runs older code** (not Phase 3 yet): deploy Phase 3 first, from `Routing/backup_after_phase3_2026-10-24.tar.gz` (it is the state `55209df87733162f`), with the commands of `api_routes_phase3_uniform_layout.md`; then run the block above. Two small steps are easier to check than one big one.

`expand_check.py` needs the seeded users (`scripts/init_seed.py`) and the compendium data (`push_data/seed.py`; see side finding S1 if it stops at the seed user).

## 7. Rollback

There is no database change, so rollback is file-only.

| Situation | What to do |
|---|---|
| A check fails in the scratch copy | Nothing was delivered. Claude throws `work/` away, fixes and starts again from `old/` |
| Delivered to the repo, not yet deployed | Restore the repo from `Routing/backup_before_expand_<date>.tar.gz`: delete `app`, `scripts`, `tests`, `README.md` and `Routing/postman` first (needs the delete permission of the folder), then extract the archive |
| Deployed and a check fails on the host | The commands below, then restore the repo as in the line above |

```bash
cd ~/jrdurt && F=~/failed_expand_$(date +%F_%H%M) && sudo docker stop alpen-api && mkdir "$F" && mv app scripts tests "$F"/ && mv "$B"/* . && sudo docker start alpen-api
```

If `$B` is gone (a new shell), its name was printed when you made it: `ls -d ~/before_expand_*`. A folder that the container filled with `__pycache__` needs `sudo` to be removed. Nothing to undo in the worker (it was not rebuilt).

## 8. Risks and how they are covered

| Risk | Covered by |
|---|---|
| The new links break SQLAlchemy's setup (45 classes get one) | `test_all_mappers_configure`, the API starts, three library stacks tested |
| A route answers 500 because a schema field is missing on the model | `test_every_plain_field_of_a_detail_schema_exists_on_its_model`, one live check per endpoint, and `test_every_path_up_to_three_levels_builds_its_loader_options` (compiles every allowed path) |
| A link does not point to the model its schema expects | `test_every_link_is_a_relationship_to_the_model_of_its_target_schema` |
| A new `*Detail` schema or GET-by-id route is added later without being listed | `test_every_schema_with_links_is_listed`, `test_every_get_by_id_route_is_either_expandable_or_exempt` fail until it is classified |
| A route answers with another schema than the one its `expand` names come from | `test_the_answer_schema_of_every_expand_route_is_the_schema_of_its_expand_plan`, and the compare |
| One database row is reached by two paths in one request and the wrong one is filled | the helper reads only requested links; live check on a poi-region (`poi.main_region` and `region` are the same row) in both directions |
| `expand` is read before the login check (an unauthenticated caller learns names) | `test_the_login_check_comes_before_expand_in_every_route` (the order of the parameters of all 33 routes) and `test_a_missing_token_answers_401_even_with_a_bad_expand` (all 33 routes, no database) |
| A permission or an access check is lost or changed on one route | `compare --expand` (permissions must be identical), the live check "an unknown id answers 404 on 18 single GET routes" |
| Track `metrics` or the job `subject` (computed fields) get lost | `plan.render(..., metrics=...)`, `render(..., subject_type=..., subject_id=...)`; live checks with a worker |
| A very long or strange `expand` value | at most 1000 characters (`400` otherwise), error messages never repeat a long input, a random-input test; parsing a 1 MB value would have taken about 0.1 s |
| Library versions (`requirements.txt` is not pinned) | tested at the lowest allowed versions, today's and the newest; check the container's versions on the host (`pip list`) |
| Privacy of the creator's profile | question 7; with option B the helper hides fields from every viewer except administrators and the user himself |
| An expanded object is not checked against the policy of its own resource | stated in section 2 (limit); no difference under today's policies |
| A client relied on nested objects in single GETs | assumption 6; the README and Swagger explain `expand` |
| Costs | measured (section 1); at most 10 links, 3 levels, 1000 characters |
| A hidden or unprocessed track loads its links before the visibility check says 404 | small: a few extra queries for such a request; the answer is the same 404 |

## 9. Side findings (not part of the change)

- **S1. `push_data/seed.py` stops on a fresh database.** It creates its seed user with the group `admin` (line 134); the database only accepts `administrator` (check constraint `ck_profile_user_credentials_user_group`). A one-word fix. I did not change it; I seeded the sandbox with a patched copy.
- **S2. In one Newman run, "Create country" failed on the old code** because its random ISO code collided with an existing one. It passed on the other run. It is a property of the collection's random values, not of this change.
- **S3. `requirements.txt` is not pinned.** This change was tested at the lowest allowed versions and at the newest (SQLAlchemy 2.1 and Python 3.12 included), so a rebuild is not a worry today; pinning is still a good idea.

## 10. After the change: how to add `expand` to a new GET-by-id

1. Model: add a read-only link `relationship("X", foreign_keys=[...], lazy="raise", viewonly=True)` for every foreign key that should be expandable (`created_by_user` exists for every model with `CreatorMixin`).
2. Schema: `class XDetail(XRead)` next to `XRead`, with `link: YDetail | None = Link()` (`Link("created_by")` when the public name differs). The nested type must itself be a Detail schema.
3. Route: copy `compendium/routes/poi/get_one.py` (Appendix B). Declare `plan` after the auth parameter.
4. Tests: add `XDetail: Model` to `PAIRS` in `tests/test_expand_wiring.py` and the route to `EXPAND_ROUTES` in `tests/test_expand_routes.py` (the tests tell you when you forget).
5. Never read a link from the object yourself in a route; `plan.render` is the only place that does.

---

## Appendix A. What each step changes

**A.1 Helper and alias.** New `app/core/utils/expand.py`: `Link(expand_name=None)` marks a schema field as a link; `links_of(schema)` lists them (two links with one public name, or a link to a list of models, are refused when the schema is first used); `ExpandPlan.parse(schema, "a.b,c")` checks length (1000), names, depth (3) and link count (10) and raises `AppError(400, "Bad request", ...)` with `error_errors=[{field: "expand", ...}]`; `plan.load_options(Model)` returns `selectinload` options (one extra SELECT per link); `plan.render(obj, **extra)` returns a plain dict and reads only the requested links; `expand_plan(schema)` is the dependency that adds the documented `expand` parameter. The helper imports nothing from `profile` (that would make an import cycle with the access-policy schemas); the alias `ExpandedUser = UserRead` sits next to `UserRead` in `profile/schemas/user_read.py`. `core/schemas/ref.py` therefore imports `profile.schemas.user_read`: core knows profile's schema file, in the same way core routes already use `profile.permissions`.

**A.2 Models.** The links and the `user_group` property of section 3. `CreatorMixin.created_by_user` names its foreign key as a string (`f"{cls.__name__}.created_by"`); the string form works on all three tested SQLAlchemy versions, and no class name is duplicated. `MgmtLogEvent.entity_type` and `ProfileAccessPolicy.resource_type` keep their `lazy="joined"`, so their JOIN also runs when they are not asked for (a tiny table; unchanged from today).

**A.3 Schemas.** `RefBaseDetail`, `RefWithFactorDetail`, `DifficultySportDetail`, `CompendiumTypeDetail`, `CountryDetail`, `RegionDetail` (with a self reference `parent`), `PoiDetail`, `CardDetail`, `PostDetail`, `PoiRegionDetail`, `GearDetail`, `TrackDetail`, `EventLogDetail`, `JobAdminDetail`, `SettingDetail`, `ResourceTypeDetail`, `AccessPolicyDetail`. In `PoiDetail` and `CardDetail` the `compendium_type` is a `CompendiumTypeDetail` (it includes `is_collectable`, which the old nested object left out).

**A.4 Routes.** Pattern A (poi, card, region, post, poi-region): `.options(*EAGER)` becomes `.options(*plan.load_options(Model))`, `ok(obj)` becomes `ok(plan.render(obj))`, `EAGER` is no longer imported by that file. Pattern B (country, gear, the 19 reference tables, resource type, access policy, jobs): `db.get(...)` becomes `select(...).where(...).options(...)`. Special: the track route passes `metrics=build_metrics(geo_rec, geo_perf)` (it used to build `TrackRead` by hand); the admin job route passes `subject_type` and `subject_id` because `JobRead` builds `subject` from them; the settings route gives `get_row` the load options; the compare route renders each entry once.

**A.5 Documents and Postman.** README: the sentence about nested objects, the region example, a new section "Expanding linked objects (`?expand=`)", two bullets in "URL scheme and routes layout". Postman: `python Routing/postman/build_postman.py --openapi <new openapi.json> --out Routing/postman --host-var hostname --port-var port --api-var api_path --token-var access_token`, with the `openapi.json` of the changed API (`curl http://localhost:8000/openapi.json`); the generator stops if a route has no request. After it, run Newman as before (`skip_deletes=true`): the same file-upload requests fail as on the old code and nothing else.

## Appendix B. How a route looks after (the pattern, as tested)

```python
# app/compendium/routes/poi/get_one.py
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.schemas.poi import PoiDetail

from ._router import router


@router.get("/{poi_id}", response_model=ApiResponse[PoiDetail])
async def get_poi(
    poi_id: UUID,
    access: AccessContext = Depends(resource_access("poi", "read")),
    plan: ExpandPlan = Depends(expand_plan(PoiDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPoi)
        .where(CompendiumCatPoi.id == poi_id)
        .options(*plan.load_options(CompendiumCatPoi))
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="POI not found")
    return ok(plan.render(obj))
```

```python
# app/compendium/schemas/poi.py (added at the end of the file)
class PoiDetail(PoiRead):
    compendium_type: CompendiumTypeDetail | None = Link()
    main_region: RegionDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
```

## Appendix C. Execution log (the implementer fills this in)

| Date | Step | Result | Notes and deviations |
|---|---|---|---|
| 2026-10-26 | E0.1 backup | `Routing/backup_before_expand_2026-10-26.tar.gz` (app, scripts, tests, README.md, Routing/postman; 529 `.py` files in it) | Tripwire: 0 files newer than the backup |
| 2026-10-26 | E0.2 scratch copies, baseline | `old/` and `work/` made from the repo: 505 files, hash `55209df87733162f`; baseline dump 214 routes | The sandbox had been reset, so Python 3.12 (FastAPI 0.162.0, pydantic 2.14.1, SQLAlchemy 2.1.6), Postgres 16 + PostGIS and Redis were rebuilt from the recipe; compendium seed made with a copy of `push_data/seed.py` with `admin` changed to `administrator` (side finding S1) |
| 2026-10-26 | E1 `apply_expand.py` + `apply_viewer.py` + `apply_viewer_tests.py` (option B) | applied without a `STOP` | |
| 2026-10-26 | E2 checks in the scratch copy | pytest **107 passed**; `compare --expand`: NOTE 33 route(s) gained the query parameter expand, OK 214 / 214; probe 211 routes 0 problems; names 0; live `expand_check.py --worker` **75 of 75**; `e2e_check.py --worker` **35 of 35**; no traceback in API and worker logs; Appendix F greps: 33 / 33 / (empty) / 33 `viewer=` | Newman on old and new code: 219 requests, 36 failing assertions in both, **the same 36 requests** (all Upload CSV and Upload track) |
| 2026-10-26 | E3 delivery D4 | dry run `6 added, 57 changed, 0 deleted`, then for real: same numbers, `deliver.py` verified `app/` and `tests/` equal the work copy | The first real run stopped at its delete test (delete permission for the folder was missing) and left a 1-byte `app/.deliver_probe`; I enabled the permission, removed the file (the tool had refused the repo as "edited") and ran it again. No stray file is left |
| 2026-10-26 | E3 README and Postman | `README.md` copied; `Routing/postman/Alpen API.postman_collection.json` rebuilt (264 lines added, 0 removed: 33 disabled `expand` parameters; the old API still rebuilds the old file byte for byte); environment file unchanged; note added to `Routing/postman/README.md` | |
| 2026-10-26 | E3 hash and count | repo: **506 files, hash `5a0dee4fcbd0cf7e`**; a copy of the delivered repo: pytest 107 passed, compare OK, probe OK, names OK | |
| | E4 host checks (section 6) | **open: you** | Section 6 commands expect 506 files, the hash above, pytest 107, `expand_check.py` 75 |

Questions 7 to 10 as answered (2026-10-26, "all recommended"): 7 = **B** (everybody sees `id` and `username` of an expanded user; administrators and the user himself see the whole profile); 8 = all 33 endpoints; 9 = `null` for a link that was not asked for; 10 = no answer about the host, so section 6 covers both cases (I do not touch your host).

## Appendix D. The tools (`Routing/expand_tools/`)

| File | What |
|---|---|
| `apply_expand.py` | `python apply_expand.py REPO_COPY`: the whole change, with a `STOP:` guard on every edit. Option A of question 7 |
| `apply_viewer.py`, `apply_viewer_tests.py` | Only for option B of question 7, run after `apply_expand.py` on the same copy |
| `expand.py` | The helper; `apply_expand.py` copies it to `app/core/utils/expand.py` |
| `test_expand.py`, `test_expand_wiring.py`, `test_expand_routes.py` | The 38 new tests; copied to `tests/` (option B adds a fourth file with 5 tests) |
| `expand_check.py` | The live check; copied to `scripts/` |
| `measure.py` | The speed measurement of section 1 (Postgres runs with `log_statement='all'`); not part of the repo |

Recipe for a new scratch copy: `mkdir /tmp/ex && cd <repo> && tar cf - --exclude=__pycache__ app scripts tests requirements.txt requirements-dev.txt pytest.ini README.md | (mkdir /tmp/ex/old && cd /tmp/ex/old && tar xf -) && cp -a /tmp/ex/old /tmp/ex/work && python Routing/expand_tools/apply_expand.py /tmp/ex/work`. The python needs the packages of `requirements.txt` plus `pytest` and `httpx`; Postgres with PostGIS, Redis and a seeded database for the live checks.

## Appendix E. What the independent reviews changed (2026-10-25)

Two reviewers, both without access to my reasoning. **Reviewer 1** repeated everything on his own copy (every number reproduced) and put 18 mistakes into the changed code. **Reviewer 2** attacked the design, the security and the code.

| Finding | What I did |
|---|---|
| Option A is a way around the administrator-only user endpoints; registration is open; 27 of 33 endpoints; the plan understated it (said tracks and gear, "creators are administrators and editors") | Question 7 rewritten with the facts; recommendation **B**; option B kept built and tested; the live check of option A documents what it shows |
| `compare --expand` hid a changed permission key on all 33 routes | Made strict (permissions, answer schema and used classes are compared); the changed-permission mistake is now caught |
| Nothing proved that the login check comes before `expand` on all 33 routes; one route written the other way passed every check | Two new tests (order of the parameters; 401 with a bad `expand` on all 33 routes) |
| The access check removed from one route passed every check | New live check: an unknown id answers 404 on 18 single GET routes |
| Older and newer swapped in the compare answer passed the live check | The live check now tests the order and the actions of the two entries |
| `GearDetail` added `created_by` to every gear answer (a new disclosure) | Removed; a plain gear answer is unchanged; `expand=created_by` still works |
| `expand` had no length limit; a long junk value was repeated four times in the error | Limit of 1000 characters; errors never repeat a long input; a random-input test |
| Two links with the same public name overwrite each other; a link to a list gave a misleading message | Both refused with a clear message (tests) |
| A target's own policy is not applied | Stated as a limit in section 2 and in the risks |
| The speed row "today" was not the same content (the nested objects are now bigger) | The row says so |
| `expand_check.py` stopped with a traceback on the first wrong answer and left test data behind | It prints a FAIL line with the last check and the summary, and cleans up in any case (also resets the setting) |
| Wording and host commands: "option B of decision 2" (it is question 7); the tripwire listed `README.md` today; `mv README.md` would stop the chain when the host has none; the host hash check had no stop rule; the compare paths of 5.1; rollback situations; the Newman expectation; `D4` and `E0.x` not explained; `Lines 7 to 10` | Fixed in the text above |
| Not changed on purpose | `foreign_keys=f"{cls.__name__}.created_by"` (a lambda was suggested): the string form works on all three stacks and no class name is duplicated; the new relationships have `viewonly=True` unlike the older ones (it is safer); the helper imports from `sqlalchemy` and `fastapi` directly |

## Appendix F. Checks that need no tool

Run in the repo root after the delivery:

```bash
grep -rl 'expand_plan(' app/*/routes | wc -l                       # 33
grep -rn 'plan.render(' app | wc -l                                 # 33
grep -rl 'EAGER' --include=get_one.py app                            # prints nothing
grep -rn 'db.get(' --include=get_one.py app                          # only my_jobs/get_one.py and the two sub-record lines of track/get_one.py
for f in $(grep -rl 'plan.render(' app); do grep -q 'plan: ExpandPlan' $f || echo "$f"; done    # prints nothing
grep -rln 'created_by_user\|changed_by_user\|updated_by_user' app/*/routes    # only management/routes/event_log/compare.py (it builds its answer by hand)
```
