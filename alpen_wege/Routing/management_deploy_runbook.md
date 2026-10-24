# Management app: deploy runbook (all of X1 to X7 is already in the repo)

Written 2026-10-23. The code for every milestone of `management_implementation_plan.md` is in the repo. Nothing has been run against your database, Docker or Redis yet. This file is the one-time order to deploy it. The checks per milestone are in the plan (sections X1.4 to X7.8); run them after the deploy.

## 1. Before you start

```bash
cd ~/jrdurt
P="sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege"
$P -c "SELECT version();"
$P -c "SELECT count(*) AS events, max(seq) AS max_seq FROM core_log_event;"          # write these two numbers down
$P -c "SELECT to_regclass('public.mgmt_log_event') AS a, to_regclass('public.mgmt_settings') AS b, to_regclass('public.mgmt_log_job') AS c, to_regclass('public.mgmt_ref_entity_type') AS d;"   # all four must be empty
sudo docker exec alpen-redis redis-server --version                                  # 6.2 or newer (GETDEL)
sudo docker exec alpen-postgres pg_dump -U alpenwege -d alpenwege -Fc -t core_log_event -t core_ref_entity_type > ~/backup_event_log_$(date +%F).dump
ls -l ~/backup_event_log_*.dump
```

If any `mgmt_*` table already exists, stop and tell me.

## 2. Deploy in this order

```bash
cd ~/jrdurt
sudo docker stop alpen-api alpen-celery                    # 1. stop both (the api would otherwise create empty mgmt_* tables)
# 2. copy / pull ALL changed files to ~/jrdurt (the whole app/, scripts/, tests/, README.md, requirements.txt, designe/)
for f in management_x1_move management_x2_settings management_x3_jobs; do
  sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/$f.sql || break   # 3. DDL, in this order, stop at the first error
done
sudo docker compose up -d --build                          # 4. rebuild the worker image (it has no bind mount), start everything
sudo docker logs --tail 60 alpen-api                       # 5. started, no traceback
sudo docker logs --tail 60 alpen-celery                    #    no ImportError, tasks listed
```

Expected from the first script: a line `NOTICE:  OK: <n> events, max seq <m>` with the numbers you wrote down. If a script fails, nothing is changed by it (one transaction); paste the error.

## 3. What changed for clients (tell your front end)

- `GET /api/v1/event-log...` is gone. It is now `GET /api/v1/management/event-log...` (administrator only, same answers).
- `POST /explorer/tracks`, `POST /explorer/tracks/{id}/reprocess`, `POST /compendium/pois/{id}/rescan`, `POST /compendium/cards/{id}/rescan` return `job_id` (and a `Location` header). `TrackCreated.task_id` is replaced by `job_id`. The reprocess and rescan responses carry `{job_id}` instead of `null`.
- New: `/api/v1/management/my-jobs`, `/api/v1/management/ws/ticket`, `WS /api/v1/management/ws`, `WS /api/v1/management/ws/jobs/{id}`, `/api/v1/management/{jobs,settings,broadcast,celery}`. See the README section "Jobs, WebSocket and management".
- Since the routes migration (`api_routes_implementation_plan.md`) every URL is `/api/v1/{app}/{resource}`; see the table in section 3b below.

## 3b. Changed URLs (routes migration, tell your front end)

| Old | New |
|---|---|
| `/api/v1/auth/{register,login,refresh,logout}` | `/api/v1/profile/auth/...` |
| `/api/v1/users`, `/users/me`, `/users/{id}/...` | `/api/v1/profile/users/...` |
| `/api/v1/auth/access-policies` | `/api/v1/profile/access-policies` |
| `/api/v1/auth/resource-types` | `/api/v1/core/resource-types` |
| `/api/v1/ref/{slug}` | `/api/v1/core/{slug}` |
| `/api/v1/countries`, `/regions`, `/pois`, `/cards`, `/posts`, `/poi-regions` | `/api/v1/compendium/...` |
| `/api/v1/gear`, `/api/v1/tracks` | `/api/v1/explorer/gear`, `/api/v1/explorer/tracks` |
| `/api/v1/jobs`, `/jobs/{id}` (own jobs) | `/api/v1/management/my-jobs`, `/my-jobs/{id}` |
| `/api/v1/ws/ticket`, `WS /ws`, `WS /ws/jobs/{id}` | `/api/v1/management/ws/ticket`, `WS /api/v1/management/ws`, `WS /api/v1/management/ws/jobs/{id}` |
| `/api/v1/management/*`, `/health` | unchanged |

Old URLs answer 404 (clean break). Also visible to clients: 193 of 212 operation ids in `/openapi.json` change (FastAPI builds them from the path), 29 generated form schema names (`Body_..._post`) change, the Swagger tag groups come in another order, and the token URL in the OpenAPI document is now `/api/v1/profile/auth/login`.

## 4. Checks to run after the deploy (short list, details in the plan)

1. `$P -c "SELECT count(*), max(seq) FROM mgmt_log_event;"` equals the numbers from step 1; `\dt mgmt_*` shows four tables; no `core_log_event`.
2. Admin token: `GET /api/v1/management/event-log?limit=3` works, `GET /api/v1/event-log` is 404; `GET /api/v1/management/settings` lists 9 settings.
3. Demo job: `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/demo_job.py --user-id <YOUR_USER_ID> --seconds 8`, then `GET /api/v1/management/my-jobs/<id>` goes queued, running, succeeded; `python scripts/ws_check.py --token "$TOKEN"` (same container, same env) shows the live messages.
4. Upload a GPX file: the 202 has `job_id`; the job ends `succeeded` with `visits_added` and `cards_added`.
5. Unit tests: `sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"`. **Six tests fail already without the management code** (`tests/test_matching.py` calls `nearest_visit()` with an argument it no longer takes, and `tests/test_gpx_pipeline.py::test_straight_line_distance`). They belong to the GPX pipeline code, not to this change. The 20 new management tests pass.

## 5. Rollback

Stop both containers, restore the previous code, and ask me for the inverse rename script. `mgmt_settings` and `mgmt_log_job` can simply be dropped. The dump from step 1 is the safety net for the event log.
