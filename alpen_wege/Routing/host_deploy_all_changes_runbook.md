# Host deployment of everything that is in the repo (one step, copy by hand)

> **Update 2026-10-30 (icons):** the repo now also has the icons and flags (`asset_agg_icon`, `icon_id` on 22 tables, `/assets/icons`). There are five more SQL scripts (`icons_preflight`, `icons_ddl`, `icons_policy`, then after the start `icons_link`, and `icons_rollback` for the way back); the file count of `app` is now **589** (first hash f8fa67d645862f97), the test count 1343, the routes 254 (probe 251). The icon set can be created with one API call (`POST /assets/icons/upload-csv`), see `icons_deploy_runbook.md` section 5b. Run them in section 4 after the other SQL scripts and **before** `docker compose up -d --build`; the steps, the checks and the rollback are in `icons_deploy_runbook.md` (do not run `init_seed.py` on the host, `icons_policy.sql` does the icon part only).

> **Update 2026-10-27:** the repo has changed since this was written (explorer hierarchy phase 0, see `next_step/phase0_rank_delivery.md`): a fifth SQL script `hierarchy_phase0_ddl.sql` (run it last in section 4), the test count is now 262, the content hash in section 3 differs, and `push_data/seed.py` no longer has the `admin` group problem. Update 2026-10-27 (later): segments and routes are built too (`next_step/phase1_2_delivery.md`): the file count of `app` is now 543 (hash starts 7ac91878ccb7e673), the test count 362, the routes 231 (probe 228), the list routes 35. No further SQL script. Journeys (phase 3) are still to come; this file is rewritten once when they are done. Until then treat the numbers above as out of date.

Written 2026-10-26. Your host does not run the Phase 3 layout yet, so this is **one deployment of the whole current repo**: routes layout (Phase 3), management app and jobs, track pipeline, `?expand=` on single GETs, and filters / sorting on all lists. You copy the folders by hand; the commands below do the rest. Nothing in this file has been run against your host or your database; every command was written from the scripts and checks that passed in my sandbox (Postgres 16 + PostGIS, Redis, Celery worker, three library stacks).

What the repo contains, so you know what you are deploying:

| Part | What a client sees | Database |
|---|---|---|
| Routes layout (Phase 3) | every URL is `/api/v1/{app}/{resource}` (table in section 5); old URLs answer 404 | none |
| Management app and jobs | `/api/v1/management/...`, uploads and rescans return `job_id`, WebSocket | `management_x1_move.sql`, `management_x2_settings.sql`, `management_x3_jobs.sql` |
| Track pipeline | tracks, geo records, statistics, cards from visits | `track_pipeline_ddl.sql` |
| `?expand=` | **single-object GETs** (`GET .../{id}`) take `?expand=main_region.country,created_by` to show linked objects (3 levels, 10 links) | none |
| Filters, `sort`, paging | **list GETs** take filters (`q`, ids, ranges, dates, `bbox`, `near`), `sort`, and keep `limit`/`offset` (default 1000, as before) | none |
| gzip | answers are compressed when the client accepts it | none |
| Swagger / Postman | `/docs` has an overview text and a description for every filter; the Postman collection can run single requests alone (first ids) | none |

All four SQL scripts are idempotent and run in one transaction each, so a script that stops changes nothing and can be run again.

## 1. Look at the host first (before you touch anything)

```bash
cd ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                       # write the number down
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum   # write the first 16 characters down
P="sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege"
$P -c "SELECT version();"                                                        # PostgreSQL 15 or newer, PostGIS present
$P -c "SELECT to_regclass('public.core_log_event') AS old_event_log, to_regclass('public.mgmt_log_event') AS new_event_log, to_regclass('public.mgmt_settings') AS settings, to_regclass('public.mgmt_log_job') AS jobs, to_regclass('public.explorer_sub_geo_record') AS geo_record, to_regclass('public.profile_sub_statistic') AS statistic;"
$P -c "SELECT count(*) AS events, max(seq) AS max_seq FROM core_log_event;"      # skip this line if old_event_log above is empty; write the two numbers down
sudo docker exec alpen-redis redis-server --version                              # 6.2 or newer (GETDEL)
```

Send me the output if one of these is not what you expect: an `mgmt_*` table that exists while `core_log_event` also exists (code was deployed too early, see `management_deploy_runbook.md`, X1), PostgreSQL older than 15, Redis older than 6.2.

## 2. Backups (the rollback needs both)

```bash
cd ~/jrdurt
sudo docker exec alpen-postgres pg_dump -U alpenwege -d alpenwege -Fc > ~/backup_full_$(date +%F_%H%M).dump
ls -l ~/backup_full_*.dump                                                       # not empty
B=~/before_all_$(date +%F_%H%M); echo "rollback folder: $B"
mkdir "$B" && cp -r app scripts tests README.md requirements.txt docker-compose.yml Dockerfile "$B"/ 2>/dev/null; ls "$B"
```

## 3. Stop, copy, check the files

```bash
cd ~/jrdurt
sudo docker stop alpen-api alpen-celery          # the api would otherwise create empty mgmt_* tables with the new code
```

Now copy from your OneDrive repo into `~/jrdurt` (replace the existing ones, whole folders): `app/`, `scripts/`, `tests/`, `README.md`, `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `Dockerfile`, `docker-compose.yml`, `push_data/` and `designe/` if you use them. **Do not copy `Routing/`** (plans, tools and backups of this work; it is not part of the application). Remove `__pycache__` folders in `app/` first if you copy over a bind mount that the container wrote to (`sudo find app -name __pycache__ -prune -exec rm -rf {} +`).

```bash
cd ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                          # must be 507
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum                      # must start with 59a0472fc22afb1b
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | xargs sha256sum | sha256sum    # should start with ed98da707669c12f
        # if the count or the first hash differs: STOP and tell me. The second hash changes with line endings (Windows to Linux copies): a difference there alone is a question for me, not an error.
ls scripts/sql                                                                                       # management_x1_move.sql, management_x2_settings.sql, management_x3_jobs.sql, track_pipeline_ddl.sql
```

## 4. Database, rebuild, start

```bash
cd ~/jrdurt
P="sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege"
for f in track_pipeline_ddl management_x1_move management_x2_settings management_x3_jobs; do
  echo "== $f"; $P < scripts/sql/$f.sql || break          # in this order; stops at the first error, which changes nothing in that script
done
sudo docker compose up -d --build                          # rebuilds the images (the worker has no bind mount) and starts everything
sleep 15; sudo docker logs --tail 60 alpen-api             # started, no traceback
sudo docker logs --tail 60 alpen-celery                    # no ImportError, tasks listed
```

Expected: the first script ends with `COMMIT`; the second prints `NOTICE:  OK: <n> events, max seq <m>` with the two numbers you wrote down in section 1. If any script fails, paste the error to me and do not continue; `track_pipeline_ddl.sql` has precondition checks (PostgreSQL 15, no card without a POI, no duplicate pairs) that stop with a readable message. If the first script says it was already applied (nothing to do), that is fine.

## 5. Checks

```bash
cd ~/jrdurt
r() { sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/route_map.py "$@"; }
r dump route_dumps/host_after_all.json                                  # 214 routes (2 WebSocket)
r probe route_dumps/host_after_all.json                                 # OK: probed 211 routes, 0 problem(s)
r names                                                                 # OK: 0 undefined name(s)
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -3     # 223 passed
sudo docker exec -w /app alpen-api sh -c "pip install -q httpx && python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx"
sudo docker exec -w /app alpen-api python scripts/e2e_check.py --gpx /tmp/full.gpx --worker | tail -2           # 35 passed
sudo docker exec -w /app alpen-api python scripts/expand_check.py --gpx /tmp/full.gpx --worker | tail -2       # 75 passed (single GET with ?expand=)
sudo docker exec -w /app alpen-api python scripts/list_check.py --gpx /tmp/full.gpx --gzip --skip-policy-step | tail -3   # 0 failed (list filters, sort, limit; about 900 checks)
```

`e2e_check.py`, `expand_check.py` and `list_check.py` need the seeded users (`scripts/init_seed.py`, password `!Password@5005`) and the compendium data (`push_data/seed.py`; if it stops at the seed user, that is side finding S1 of the `?expand=` plan: the group `admin` must be `administrator`). They create and delete a few rows (gear, a card, a post, a track which is archived, not deleted) and the event log keeps the entries. `list_check.py` without `--skip-policy-step` also changes three read policies for a minute and puts them back; leave the flag on while anybody else uses the host.

Checks from the management runbook that are still yours (details: `management_deploy_runbook.md` section 4): `SELECT count(*), max(seq) FROM mgmt_log_event;` equals the numbers of section 1; `\dt mgmt_*` shows four tables and no `core_log_event`; `GET /api/v1/management/event-log?limit=3` works with an administrator token and `GET /api/v1/event-log` is 404; the demo job (`scripts/demo_job.py`) goes queued, running, succeeded; uploading a GPX file answers 202 with `job_id` and the job ends `succeeded`.

Quick hand test of the two options you asked about (replace `$TOKEN` and the id):

```bash
curl -s "http://localhost:8000/api/v1/compendium/pois?q=bahnhof&sort=-altitude_m&limit=5" -H "Authorization: Bearer $TOKEN"                 # a list: filter + sort + limit
curl -s "http://localhost:8000/api/v1/compendium/pois/<poi_id>?expand=main_region.country,compendium_type" -H "Authorization: Bearer $TOKEN"   # one object: depth
```

## 6. What changed for clients (tell your front end)

| Old | New |
|---|---|
| `/api/v1/auth/{register,login,refresh,logout}` | `/api/v1/profile/auth/...` |
| `/api/v1/users`, `/users/me`, `/users/{id}/...` | `/api/v1/profile/users/...` (the list takes `skip` as before) |
| `/api/v1/auth/access-policies` | `/api/v1/profile/access-policies` |
| `/api/v1/auth/resource-types` | `/api/v1/core/resource-types` |
| `/api/v1/ref/{slug}` | `/api/v1/core/{slug}` |
| `/api/v1/countries`, `/regions`, `/pois`, `/cards`, `/posts`, `/poi-regions` | `/api/v1/compendium/...` |
| `/api/v1/gear`, `/api/v1/tracks` | `/api/v1/explorer/gear`, `/api/v1/explorer/tracks` |
| `/api/v1/event-log...` | `/api/v1/management/event-log...` (administrator only) |
| `/api/v1/jobs`, `/jobs/{id}` (own jobs) | `/api/v1/management/my-jobs`, `/my-jobs/{id}` |
| `/api/v1/ws/ticket`, `WS /ws`, `WS /ws/jobs/{id}` | `/api/v1/management/ws/ticket`, `WS /api/v1/management/ws`, `WS /api/v1/management/ws/jobs/{id}` |

Also new for clients:

- **Single GET (`GET .../{id}`)** shows linked objects as IDs only; `?expand=a,b.c` fills the ones you name (3 levels, 10 links, a wrong name answers 400). An expanded user shows only `id` and `username` unless the caller is an administrator or that user.
- **List GET** keeps `limit` (default 1000, 100 on tracks, event log, jobs, my jobs; at most 500 on tracks and jobs) and `offset` (`skip` on users), and takes filters and `sort` (the names are in Swagger and in the README section "Lists: filters and sorting"). A negative `limit` or `offset` and out-of-range values answer 422 now (500 before). A filter name that a list does not know is ignored.
- `POST /explorer/tracks` and the rescan and reprocess endpoints return `job_id` (and a `Location` header). Old URLs answer 404 (clean break). 193 of 212 operation ids in `/openapi.json` change, so regenerate any client built from it.
- Your Postman collection is rebuilt in `Routing/postman/` (import both JSON files again).

## 7. Rollback

| Situation | What to do |
|---|---|
| A check in section 3 fails (files) | Nothing in the database was touched yet: `sudo docker stop alpen-api alpen-celery`, put `$B/*` back into `~/jrdurt`, `sudo docker compose up -d --build` |
| A SQL script fails | It changed nothing (one transaction). Paste the error; do not continue |
| The deployment is done and a check fails | Code: stop the containers, put `$B/*` back (`app`, `scripts`, `tests`, `README.md`, `requirements.txt`, `docker-compose.yml`, `Dockerfile`), `sudo docker compose up -d --build`. Database: the new tables (`mgmt_settings`, `mgmt_log_job`) can stay or be dropped; the event log tables were renamed, so the old code needs them back: restore the dump (`sudo docker exec -i alpen-postgres pg_restore -U alpenwege -d alpenwege --clean --if-exists < ~/backup_full_<date>.dump`) **only if nothing was written since the backup** (every write after it is lost); otherwise ask me for the inverse rename script first |

A folder that a container filled with `__pycache__` needs `sudo` to be removed.
