# Tools for the routes migration

Written and tested on 2026-10-24 for `Routing/api_routes_implementation_plan.md`. Nothing here is part of the app yet. The plan says when each file goes into the repo.

## Files that go into the repo

| File | Goes to | What it does |
|---|---|---|
| `route_map.py` | `scripts/route_map.py` | `dump` writes every route of the app (function name, tags, parameters, request and response shapes, security, permission keys) to a JSON file. `compare` checks two dumps: identical (structure steps) or equal after the old-to-new URL rules (URL steps). `probe` sends every route one request without a token, straight into the app (no database needed) and checks that the right function answers and that secured routes say 401. `names` imports every module of the app and reports names that a function uses but its module does not define (a forgotten import). `dump` also records the classes (models, schemas, errors) each route function uses, the middleware list and the exception handlers. Needs only the app itself (no pytest, no httpx) |
| `ast_compare.py` | `scripts/ast_compare.py` | Compares the **code** of every route function and every top-level constant before and after (comments and formatting ignored), allowing only the rewrites the plan lists. Catches what `route_map.py` cannot see: a dropped call, a typo inside a function, a changed decorator option, a changed constant. Needs an untouched copy of the old repo. `--phase 1` at the end of the structure phase, `--phase 3` for the uniform layout (no rewrites; the new explicit reference-table functions are allowed) |
| `route_rules.json` | `scripts/route_rules.json` | The old-to-new URL rules, each with a step number (0 to 4). `compare --rules ... --step N` applies only the rules up to step N |
| `test_api_paths.py` | `tests/test_api_paths.py` | Six tests: the upload-size guard is installed and watches the real `create_track` route; the `Location` header helper and the Swagger token URL equal real routes; no route file contains `/api/v1`; the shared `apply_scope` filters correctly for scope all, own and public |
| `test_routes_standard.py` | `tests/test_routes_standard.py` | Eight tests that keep the uniform layout from drifting: every URL is `/api/v1/{app}/{resource}`; every route is served by its own function (the probe, so a shadowed route fails); no module uses an undefined name; no loose files in `routes/` (every resource is a folder); type folders only `m2m`, `ref`, `sub`; every module is imported by its folder's `__init__.py`; no file next to a folder of the same name; endpoint files under 300 lines |
| `e2e_check.py` | `scripts/e2e_check.py` (optional) | A live check against a running api with the seeded dev users. Needs `pip install httpx`. 35 checks |

## Folder `migrate/` (optional)

Python scripts that apply the steps of the plan to a copy of the repo. You can follow the plan by hand instead; the tables in the plan contain the same information.

| File | What |
|---|---|
| `m1_1_ref.py`, `m1_2_profile.py`, `m1_3_management.py`, `m1_4_folders.py`, `m1_5_scope.py` | Steps 1.1 to 1.5 |
| `m2_urls.py` | Steps 2.0 to 2.6 (`python m2_urls.py <step>`) |
| `m3_uniform.py` | Phase 3, steps 1 to 5: every resource becomes a folder with one file per action, reference tables written out, `m2m/` and `ref/` type folders (`python m3_uniform.py <step>`) |
| `run_all.sh` | `phase1`, `phase2`, `phase3`, `all`: runs the steps in order and checks after every step; at the end of each phase also `probe`, `names`, `ast_compare` and a pytest gate (phases 1 and 2: stops unless exactly the 6 known tests fail; phase 3: no test may fail). `phase3` needs `route_dumps/before3.json` and `AW_OLD` = the repo before phase 3 |
| `deliver.py` | `deliver.py WORK REPO BASE [--dry-run]`: copies the result from the scratch copy into the real repo in one go. Refuses when the repo differs from BASE (someone edited it), when a folder is wrong, or when deleting is not allowed; checks the result afterwards |
| `mig_lib.py` | Shared helpers |

The scripts only work on the exact repo state of 2026-10-24: they stop with `STOP: ...` if an old file has a function, constant or table they do not know.

```bash
AW_ROOT=<scratch copy> AW_OLD=<untouched copy> AW_PY=<python that can import app> AW_PYLIB=<folder with autoflake> bash migrate/run_all.sh [phase1|phase2|all]
python migrate/deliver.py <scratch copy> <real repo> <base copy> --dry-run
```

`AW_PYLIB` is made with `pip install --target <folder> autoflake` (the scripts use it to remove unused imports in the files they generate).

Sandbox setup used for the tests (Python 3.10 in the sandbox, 3.12 in your Docker image; both worked):

```bash
uv venv /tmp/venv && uv pip install --python /tmp/venv/bin/python -r requirements.txt pytest httpx
uv pip install --python /tmp/venv/bin/python --target /tmp/pylib autoflake
```

For the live run the sandbox also needs Postgres 16 with PostGIS and Redis (they were installed with micromamba into `/tmp/mamba`, which is not permanent).
