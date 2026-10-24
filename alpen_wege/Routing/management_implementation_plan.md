# Management app, job tracking, runtime settings, WebSocket and Celery API: implementation plan (v1)

Status: **implemented in the repo on 2026-10-23, not yet deployed or run against your database.** Deploy with `management_deploy_runbook.md`. After the implementation an integration test against real Postgres, PostGIS, Redis, a Celery worker and a uvicorn server found three defects, which are fixed in the code and are not reflected in the code samples below: (1) `process_track_gpx` now fails the track and job while the track is still `processing` on the last retry; (2) the `moddatetime` trigger is also created by `create_all` through an `after_create` listener on `MgmtLogJob` and `MgmtSettings`; (3) a duplicate execution of `process_track_gpx` closes the job (`skipped`, reason `archived` or `already_processed`) when this execution is the one that moved it from queued to running (`self.request.job_id` is set), otherwise it keeps the job. Also changed: `changed_at` of `MgmtLogEvent` has `index=True`, float settings reject NaN. This document is authoritative for design and checks; the repo is authoritative for the code. It turns `management_app_and_job_tracking_proposal.md` (v2, all eight decisions accepted) into milestones and was written against the **current** repo, that is after the track pipeline was implemented by the VS Code agent. Where it differs from the proposal, section 1.2 lists the reason; this file wins.

Repo root = the folder that contains `app/` and `docker-compose.yml`. Docker runs on your Linux host (`~/jrdurt`), so every changed file must be on the host before you run SQL, build or tests.

---

## 0. How to read and use this plan

### 0.1 Milestones

| M | What | Needs | Size |
|---|---|---|---|
| X0 | Pre-flight and backup (you run, paste output) | nothing | XS |
| X1 | Move event log and entity types to `management` (rename in place) | X0 | M |
| X2 | `mgmt_settings`: registry, service, API | X1 | M |
| X3 | `mgmt_log_job`: model, service, `TrackedTask`, publisher, `/jobs`, demo task | X2 | L |
| X4 | WebSocket (ticket, general and dedicated socket, broadcast, control) | X3 | L |
| X5 | Celery API (read-only) | X3 | M |
| X6 | Retention and stale-job reaper (beat tasks) | X2, X3 | S |
| X7 | Plug into GPX, reprocess and rescan code; docs | X3 (X4 for live push) | L |

Order: X0, X1, X2, X3, then X4, X5, X6 in any order, X7 last. X7 can start right after X3 if you want real jobs earlier; the WebSocket then just starts delivering them once X4 is in.

### 0.2 Working protocol (same as the track plan)

1. Read the files a milestone touches (listed per milestone) and copy their patterns.
2. Make the changes.
3. You run the checks of that milestone and paste the output.
4. Only then the next milestone.

I never run SQL, Docker or pytest myself (my shell may be unavailable). Every command below is for you to run on the host.

### 0.3 Deploy sequence that every milestone with DDL follows

The `api` container bind-mounts the repo with `--reload` and runs `create_all` on start, so code must never reach the container before the database matches it. The **worker has no bind mount** (the Dockerfile does `COPY . .`), so it only sees new code after a rebuild.

```bash
cd ~/jrdurt
sudo docker stop alpen-api alpen-celery                      # 1. stop both
sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/<script>.sql   # 2. DDL
# 3. copy / pull the code changes to ~/jrdurt
sudo docker compose up -d --build                            # 4. rebuild worker image, start all
sudo docker logs --tail 50 alpen-api                         # 5. no traceback
sudo docker logs --tail 50 alpen-celery
```

Milestones without DDL (X5, X6, X7) skip step 2 and still need step 4 because the worker code changed.

### 0.4 Code conventions (verified in the repo, same as the track plan)

- Import headers `# Standard library`, `# Third-party`, `# Local application`.
- `Mapped[...]` with `mapped_column(..., comment=...)`; every new column gets a `comment`.
- Responses: `ok`, `ok_list`, `fail`, `AppError` from `app.core.utils.responses`. `ok(data, code=202, message="Accepted")` also needs `status_code=202` on the route.
- `get_db` commits after the route returns. Where order matters (before enqueue or publish), commit explicitly.
- Management routes: `require_groups("administrator")` (same as the existing event log). User routes: `get_current_active_user`.
- Event logging stays explicit (`log_*` in API routes, never in the worker).
- Settings for infrastructure only through `app/config.py`. Runtime settings through `mgmt_settings` (X2).
- Database changes only through `scripts/sql/*.sql` that you run.
- Scripts that import `app`: `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`, run as `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/<name>.py`.
- Tests: pure pytest without a database, run with `sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"`.

---

## 1. Decisions

### 1.1 Confirmed decisions (do not re-ask)

| Topic | Decision |
|---|---|
| Job id | Own UUID in Postgres (`mgmt_log_job`), passed to Celery as `task_id` |
| WebSocket | One socket per client, auto-subscribed to `aw:all` (broadcast) and `aw:user:{id}` (my jobs); optional dedicated socket per job |
| WebSocket login | One-time ticket |
| Delivery | Redis Pub/Sub plus database snapshot (`sync`), no replay |
| What is a job | Only user-started (or admin-script-started) work |
| GPX job | One job covers processing and POI detection |
| Progress | Redis only; database written on status or stage change |
| Retention | Jobs and events, both global settings, default 30 days, `0` = keep forever |
| Postponed | Push messages for a closed app, cancel endpoint, Celery actions (revoke, purge) |
| New app | `app/management`, table prefix `mgmt_`, module key `mgmt`, API prefix `/api/v1/management` |
| Moved | `core_log_event` to `mgmt_log_event`, `core_ref_entity_type` to `mgmt_ref_entity_type` (rename in place), event-log URL to `/api/v1/management/event-log` (no alias) |
| Settings | Registry in code, values in `mgmt_settings`, 30 s cache, infrastructure and secrets stay in `.env`, changes written to the event log |
| Celery API | Read-only, administrator only. No task arguments, keyword arguments or Celery task results (return values). The job row that is joined in carries the small public `result` summary that the owner also sees through `/jobs` |
| Job owner | `user_id` may be NULL (system or admin-script job); `/management/jobs` shows all users |
| Broadcast | `POST /management/broadcast` in v1, not stored for offline users |

### 1.2 Differences from proposal v2 (found while reading the current code)

| # | Proposal v2 said | Plan does | Why |
|---|---|---|---|
| C1 | Close a socket when its token id is blacklisted (check every 60 s) | **Control messages**: logout and user deactivation publish `aw:ctl:{user_id}`; sockets close on it. A hard lifetime (default 1 h) is the backstop | `TokenRefreshMiddleware` rotates the token and **blacklists the old one on every request past half-life**. Polling the blacklist would close healthy sockets |
| C2 | App-level `ping` message and settings `ws.ping_interval_s`, `ws.pong_timeout_s`, `ws.token_check_interval_s` | Dropped. Uvicorn sends protocol-level pings (default every 20 s, timeout 20 s) and drops dead peers | Less code; those values cannot change at runtime anyway |
| C3 | One message type `job.update` | Adds `job.progress` (small: job id, stage, percent) and `control` | Progress arrives up to once per second; sending the full job each time is wasteful |
| C4 | `TrackCreated` gets `job_id` | `TrackCreated.task_id` **already exists** (raw Celery id). It is replaced by `job_id` (same value, because job id = Celery task id) | Avoid two names for one id |
| C5 | Celery API shows Celery state per task id | Shows the **job row** plus a **live location** from `inspect` (active on worker X, reserved, scheduled, or not known) | Every task is sent with `ignore_result=True`, so the result backend holds nothing and `AsyncResult.state` would always say `PENDING` |
| C6 | Finding: no time limits, `autodiscover_tasks` broken | Both **already fixed** by the VS Code agent (per-task `soft_time_limit`/`time_limit`, `include=[...]`, `acks_late`, `worker_prefetch_multiplier=1`) | |
| C7 | - | New setting `jobs.stale_after_hours` (default 24, `0` = off) and beat task `mgmt.reap_stale_jobs` | A job whose task was dropped (for example an archived pending track) would stay `queued` forever; retention only deletes finished jobs |
| C8 | - | One active job per (kind, subject) enforced by a partial unique index; `get_or_create_active_job` | Reaper re-enqueue, restore and reprocess must reuse or replace the right job; races are settled by the database |
| C9 | `mgmt_log_job.user_id` FK | `ON DELETE SET NULL` | Keep job history when a user is deleted; the job becomes a system job |
| C10 | - | **Bug fix folded into X7:** `_reap_stuck_processing` in `track_processing.py` calls `enqueue_process_track` **before** `session.commit()`. The worker can claim before the row is `pending`, skip, and the track waits for the next reaper round (`_reap_stuck_pending` already commits first). The new version also enqueues only when the track `UPDATE` matched a row (the old code enqueued unconditionally, so a track that finished in the meantime was enqueued again for nothing) | Found in the current code; X7 touches those lines anyway |
| C11 | - | `NONE_TABLES`: the VS Code agent already fixed the `profile_user_credentials` typo and added `explorer_sub_geo_record` and `explorer_sub_geo_performance`. X1 keeps all of that and only swaps the two `core_` names for `mgmt_` names and adds `mgmt_log_job` | Verified in the current `seed_entity_types.py` |
| C13 | `mark_running` for every start | A **first** task only starts a job that is `queued` (`WHERE status = 'queued'`); continuation tasks may start a `queued` or `running` job. `process_gpx` returns a plain `skipped` (job closes) when the track is archived | A duplicate delivery must not bump `attempts` or reset the stage of a run in progress, and an archived pending track must not leave its job `running` for 24 hours |
| C14 | - | Rescan routes fail a leftover active job of the same subject once the Redis lock was acquired; `scripts/reprocess_tracks.py` fails the job when the enqueue raises | An orphaned active job (hard-killed task, lost message) would otherwise block new rescans through the unique index until `jobs.stale_after_hours` |
| C12 | Pub/Sub on `/3` (v1) | Prefix `aw:` only (already corrected in v2) | Redis Pub/Sub ignores database numbers |

---

## 2. Architecture

### 2.1 Data flow (current code plus management)

```
Client --POST /tracks--> API (explorer/routes/track.py)
   INSERT gpx + track(pending) + log_created + INSERT mgmt_log_job(queued, id = new uuid) -> COMMIT
   enqueue_process_track(track.id, job_id)  ->  send_task("tracks.process_gpx", task_id = job_id)
   publish job.update(queued) to aw:user:{uid}, aw:job:{job_id}
   <-- 202 {id, name, processing_status, created_at, duplicate_of_track_id, job_id}   Location: /api/v1/jobs/{job_id}

Worker: tracks.process_gpx (base = TrackedTask)
   before_start      -> job running (attempts+1, stage "parsing")      -> COMMIT -> publish
   ... existing claim / parse / persist ...
   report_progress   -> job.progress (Redis only, rate limited); stage changes also written to the DB
   return {"status": "ready", "job": "continue", "stage": "detecting_pois"} after enqueue_detect_pois(track_id, job_id=<job id>)
Worker: tracks.detect_pois (base = TrackedTask, kwargs job_id)
   before_start      -> job running (stage "detecting_pois", no attempt increment)
   return {"status": "ok", ...}  -> on_success -> job succeeded (result: counts) -> COMMIT -> publish

Failure paths: mark_failed() also fails the active job in the same transaction; reaper does the same;
               unhandled exception -> TrackedTask.on_failure -> job failed (safe text).
```

### 2.2 Job status lifecycle

- `queued -> running`: `TrackedTask.before_start`.
- `running -> succeeded`: `on_success` when the task result is not `keep` or `continue`.
- `running -> failed`: domain helper (`mark_failed`, reaper), `on_failure`, or `on_success` with `status == "failed"`.
- `running -> queued`: `on_retry`, or the track reaper re-queues a stuck run (same job id).
- `queued/running -> failed`: `mgmt.reap_stale_jobs` after `jobs.stale_after_hours`.
- `cancelled`: reserved for the postponed cancel endpoint (allowed by the CHECK, never set in v1).
- Terminal states are final: every transition is a single guarded `UPDATE ... WHERE status IN ('queued','running')`.

### 2.3 Task result contract (new, small)

Tracked tasks keep returning a dict. `TrackedTask.on_success` reads two optional keys:

| Returned | Job effect |
|---|---|
| `{"job": "keep"}` | job untouched (another execution owns it, for example `process_gpx` lost the claim) |
| `{"job": "continue", "stage": "x"}` | job stays `running`, `stage` updated (the chain goes on in another task) |
| `{"status": "failed", "message": "..."}` | job `failed` with that text (generic text if absent). A no-op if the domain code already failed it |
| anything else (including `status: "skipped"`, `"ready"`, `"ok"`) | job `succeeded`, `result` = the dict without the reserved keys (`job`, `stage`, `message`), capped at 2 KB |

### 2.4 Redis channels and keys (all prefixed `aw:`)

| Name | Type | Content |
|---|---|---|
| `aw:all` | channel | `system.notice` for every connected socket |
| `aw:user:{user_id}` | channel | `job.update`, `job.progress` of my jobs |
| `aw:job:{job_id}` | channel | same events, one job |
| `aw:ctl:{user_id}` | channel | `control` (close sockets of this user) |
| `aw:ticket:{ticket}` | string, TTL `ws.ticket_ttl_s` | value = user id; read once with `GETDEL` |
| `aw:conns:{user_id}` | sorted set | open sockets (member = connection id, score = expiry time); crash-safe counter |
| `aw:celery:status`, `aw:celery:workers`, `aw:celery:registered`, `aw:celery:live` | string, TTL `celery.status_cache_s` | cached Celery answers (JSON) |

---

## 3. File inventory

### 3.1 New files

| Path | Milestone |
|---|---|
| `scripts/sql/management_x1_move.sql` | X1 |
| `scripts/sql/management_x2_settings.sql` | X2 |
| `scripts/sql/management_x3_jobs.sql` | X3 |
| `app/management/__init__.py` (empty) | X1 |
| `app/management/models/__init__.py`, `entity_type.py`, `event_log.py` | X1 |
| `app/management/models/settings.py` | X2 |
| `app/management/models/job.py` | X3 |
| `app/management/schemas/__init__.py` (empty), `event_log.py` | X1 |
| `app/management/schemas/settings.py` | X2 |
| `app/management/schemas/job.py` | X3 |
| `app/management/schemas/ws.py`, `broadcast.py` | X4 |
| `app/management/schemas/celery.py` | X5 |
| `app/management/utils/__init__.py` (empty), `event_logger.py`, `seed_entity_types.py` | X1 |
| `app/management/runtime_settings/__init__.py`, `registry.py`, `service.py`, `seed.py` | X2 |
| `app/management/jobs/__init__.py`, `kinds.py`, `outcome.py`, `service.py`, `events.py`, `tracked_task.py` | X3 |
| `app/management/routes/__init__.py`, `event_log.py` | X1 |
| `app/management/routes/settings.py` | X2 |
| `app/management/routes/jobs.py`, `admin_jobs.py` | X3 |
| `app/management/routes/ws.py`, `broadcast.py` | X4 |
| `app/management/routes/celery.py`, `app/management/celery_info.py` | X5 |
| `app/worker/tasks/management.py` (`mgmt.demo_job`, `mgmt.cleanup_retention`, `mgmt.reap_stale_jobs`) | X3 (demo), X6 |
| `scripts/demo_job.py` | X3 |
| `scripts/ws_check.py` | X4 |
| `tests/test_runtime_settings.py`, `test_job_outcome.py`, `test_job_payload.py`, `test_ws_messages.py`, `test_celery_info.py` | X2 to X5 |

### 3.2 Moved (X1)

| From | To |
|---|---|
| `app/core/models/event_log.py` | `app/management/models/event_log.py` |
| `app/core/models/entity_type.py` | `app/management/models/entity_type.py` |
| `app/core/routes/event_log.py` | `app/management/routes/event_log.py` |
| `app/core/schemas/event_log.py` | `app/management/schemas/event_log.py` |
| `app/core/utils/event_logger.py` | `app/management/utils/event_logger.py` |
| `app/core/utils/seed_entity_types.py` | `app/management/utils/seed_entity_types.py` |

### 3.3 Changed files

| Path | Change | M |
|---|---|---|
| `app/core/models/__init__.py` | remove `CoreRefEntityType`, `CoreLogEvent` | X1 |
| `app/core/routes/__init__.py` | remove event log import and `event_log_api_router` | X1 |
| `app/main.py` | imports, router, lifespan (seed settings), later nothing else | X1, X2 |
| `app/database.py` | `import app.management.models` in `create_tables` | X1 |
| `app/worker/model_registry.py` | `import app.management.models` | X1 |
| 12 route files | import path `app.core.utils.event_logger` becomes `app.management.utils.event_logger` (list in X1.3) | X1 |
| `app/redis.py` | add `get_sync_redis()` | X3 |
| `app/worker/celery_app.py` | `include` gets `app.worker.tasks.management`; beat gets two entries | X3, X6 |
| `requirements.txt` | `redis>=5.0.1` | X4 |
| `app/profile/routes/logout.py`, `admin.py` | publish control message | X4 |
| `app/explorer/services/dispatch.py` | optional `job_id` parameter on every `enqueue_*` | X7 |
| `app/worker/tasks/track_processing.py`, `track_detection.py` | `base=TrackedTask`, return contract, reaper commit order | X7 |
| `app/explorer/services/track_persist.py` | `mark_failed` also fails the job | X7 |
| `app/explorer/routes/track.py`, `app/compendium/routes/poi.py`, `card.py` | create job, `job_id` and `Location` in responses | X7 |
| `app/explorer/schemas/track.py` | `task_id` becomes `job_id` | X7 |
| `scripts/reprocess_tracks.py`, `scripts/smoke_tracks.sh` | create job / read `job_id` | X7 |
| `README.md`, `designe/explorer_track_flow.svg` | structure, endpoints, names | X1, X7 |

---

## 4. Milestones

### X0. Pre-flight and backup (you run, nothing is changed)

Run on the host and paste everything back.

```bash
cd ~/jrdurt
P="sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege"
$P -c "SELECT version();"
$P -c "SELECT count(*) AS events, max(seq) AS max_seq FROM core_log_event;"
$P -c "\d core_log_event"
$P -c "\d core_ref_entity_type"
$P -c "SELECT key, module, display_name, tracking_mode FROM core_ref_entity_type WHERE key IN ('core_log_event','core_ref_entity_type') OR key LIKE 'mgmt%' OR key LIKE 'profile_%cred%';"
$P -c "SELECT sequencename FROM pg_sequences WHERE sequencename LIKE 'core\_log\_event%';"
$P -c "SELECT to_regclass('public.mgmt_log_event') AS a, to_regclass('public.mgmt_settings') AS b, to_regclass('public.mgmt_log_job') AS c, to_regclass('public.mgmt_ref_entity_type') AS d;"
sudo docker exec alpen-redis redis-server --version
sudo docker exec alpen-api python -c "import redis, celery, websockets; print(redis.__version__, celery.__version__, websockets.__version__)"
```

Expected: PostgreSQL 15, the four `to_regclass` values all empty, Redis 6.2 or newer (needed for `GETDEL`), `redis` 5.x, `celery` 5.4 or newer, `websockets` installed. If any `mgmt_*` table already exists (for example because code was deployed too early), tell me before continuing.

Backup (small tables, a few seconds):

```bash
sudo docker exec alpen-postgres pg_dump -U alpenwege -d alpenwege -Fc -t core_log_event -t core_ref_entity_type > ~/backup_event_log_$(date +%F).dump
ls -l ~/backup_event_log_*.dump
```

Also tell me whether the `?expand=` plan (`get_expand_implementation_plan.md`) is already merged or still in progress. X1 moves three files that plan edits (section 5.2 has the path mapping).

**Done when:** outputs pasted, dump file exists, expected values confirmed.

---

### X1. Move event log and entity types to `management`

Goal: `core_log_event` becomes `mgmt_log_event` and `core_ref_entity_type` becomes `mgmt_ref_entity_type` **in place** (history and `seq` kept), the code lives in `app/management`, and the event-log URL becomes `/api/v1/management/event-log`.

#### X1.1 DDL: `scripts/sql/management_x1_move.sql`

Idempotent, one transaction. It renames tables, constraints, indexes and the identity sequence by pattern (so it does not depend on the exact names in your database), renames the two entity type rows, adds an index for retention, and **verifies** row count and highest `seq` before it commits (otherwise it rolls back).

```sql
-- Management move (X1): core_log_event -> mgmt_log_event, core_ref_entity_type -> mgmt_ref_entity_type.
-- Idempotent, one transaction. Run with api and worker STOPPED:
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/management_x1_move.sql
\set ON_ERROR_STOP on
BEGIN;

-- 0. Remember row count and highest seq of the event log (checked at the end)
CREATE TEMP TABLE _x1_before (n bigint, max_seq bigint) ON COMMIT DROP;
DO $$
BEGIN
    IF to_regclass('public.core_log_event') IS NOT NULL THEN
        INSERT INTO _x1_before SELECT count(*), coalesce(max(seq), 0) FROM core_log_event;
    ELSIF to_regclass('public.mgmt_log_event') IS NOT NULL THEN
        INSERT INTO _x1_before SELECT count(*), coalesce(max(seq), 0) FROM mgmt_log_event;
    ELSE
        RAISE EXCEPTION 'Neither core_log_event nor mgmt_log_event exists';
    END IF;
END $$;

-- 1. Rename the tables
DO $$
BEGIN
    IF to_regclass('public.core_ref_entity_type') IS NOT NULL THEN
        IF to_regclass('public.mgmt_ref_entity_type') IS NOT NULL THEN
            RAISE EXCEPTION 'Both core_ref_entity_type and mgmt_ref_entity_type exist; drop the empty mgmt table first';
        END IF;
        ALTER TABLE core_ref_entity_type RENAME TO mgmt_ref_entity_type;
    END IF;
    IF to_regclass('public.core_log_event') IS NOT NULL THEN
        IF to_regclass('public.mgmt_log_event') IS NOT NULL THEN
            RAISE EXCEPTION 'Both core_log_event and mgmt_log_event exist; drop the empty mgmt table first';
        END IF;
        ALTER TABLE core_log_event RENAME TO mgmt_log_event;
    END IF;
END $$;

-- 2. Rename constraints (this also renames the index behind a primary key or unique constraint)
DO $$
DECLARE r record; new_name text;
BEGIN
    FOR r IN
        SELECT c.conrelid::regclass::text AS tbl, c.conname
          FROM pg_constraint c
         WHERE c.conrelid IN ('public.mgmt_log_event'::regclass, 'public.mgmt_ref_entity_type'::regclass)
           AND c.conname ~ 'core_(log_event|ref_entity_type)'
    LOOP
        new_name := regexp_replace(r.conname, 'core_(log_event|ref_entity_type)', 'mgmt_\1');
        EXECUTE format('ALTER TABLE %s RENAME CONSTRAINT %I TO %I', r.tbl, r.conname, new_name);
        RAISE NOTICE 'constraint % -> %', r.conname, new_name;
    END LOOP;
END $$;

-- 3. Rename the remaining indexes
DO $$
DECLARE r record; new_name text;
BEGIN
    FOR r IN
        SELECT i.indexname
          FROM pg_indexes i
         WHERE i.schemaname = 'public'
           AND i.tablename IN ('mgmt_log_event', 'mgmt_ref_entity_type')
           AND i.indexname ~ 'core_(log_event|ref_entity_type)'
    LOOP
        new_name := regexp_replace(r.indexname, 'core_(log_event|ref_entity_type)', 'mgmt_\1');
        EXECUTE format('ALTER INDEX public.%I RENAME TO %I', r.indexname, new_name);
        RAISE NOTICE 'index % -> %', r.indexname, new_name;
    END LOOP;
END $$;

-- 4. Rename the identity sequence of mgmt_log_event.seq (cosmetic: a failure only prints a notice)
DO $$
DECLARE r record; new_name text;
BEGIN
    FOR r IN
        SELECT sequencename FROM pg_sequences
         WHERE schemaname = 'public' AND sequencename ~ '^core_log_event'
    LOOP
        new_name := regexp_replace(r.sequencename, '^core_log_event', 'mgmt_log_event');
        BEGIN
            EXECUTE format('ALTER SEQUENCE public.%I RENAME TO %I', r.sequencename, new_name);
            RAISE NOTICE 'sequence % -> %', r.sequencename, new_name;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'sequence % not renamed: %', r.sequencename, SQLERRM;
        END;
    END LOOP;
END $$;

-- 5. The entity type rows follow their tables (the seed does not update key, module or display_name)
UPDATE mgmt_ref_entity_type
   SET key = 'mgmt_log_event', module = 'mgmt', display_name = 'Event'
 WHERE key = 'core_log_event'
   AND NOT EXISTS (SELECT 1 FROM mgmt_ref_entity_type WHERE key = 'mgmt_log_event');
UPDATE mgmt_ref_entity_type
   SET key = 'mgmt_ref_entity_type', module = 'mgmt', display_name = 'Entity Type'
 WHERE key = 'core_ref_entity_type'
   AND NOT EXISTS (SELECT 1 FROM mgmt_ref_entity_type WHERE key = 'mgmt_ref_entity_type');

-- 6. Index for the retention job (X6)
CREATE INDEX IF NOT EXISTS ix_mgmt_log_event_changed_at ON mgmt_log_event (changed_at);

-- 7. Verification: nothing lost, nothing left behind
DO $$
DECLARE b record; a record; left_over int;
BEGIN
    SELECT * INTO b FROM _x1_before;
    SELECT count(*) AS n, coalesce(max(seq), 0) AS max_seq INTO a FROM mgmt_log_event;
    IF a.n <> b.n OR a.max_seq <> b.max_seq THEN
        RAISE EXCEPTION 'Event log changed: before % rows / max seq %, after % rows / max seq %',
            b.n, b.max_seq, a.n, a.max_seq;
    END IF;
    SELECT count(*) INTO left_over FROM pg_class
     WHERE relname ~ 'core_(log_event|ref_entity_type)' AND relkind <> 'S';
    IF left_over > 0 THEN
        RAISE EXCEPTION '% objects are still named core_log_event / core_ref_entity_type', left_over;
    END IF;
    RAISE NOTICE 'OK: % events, max seq %', a.n, a.max_seq;
END $$;

COMMIT;
```

If the script stops with "Both ... exist": an earlier API start created empty `mgmt_*` tables (code deployed too early). Check they are empty (`SELECT count(*) FROM mgmt_log_event;`), drop the empty ones (`DROP TABLE mgmt_log_event; DROP TABLE mgmt_ref_entity_type;`, log first), and run again.

#### X1.2 New files

`app/management/__init__.py`, `app/management/schemas/__init__.py`, `app/management/utils/__init__.py`: empty files (like `app/core/utils/__init__.py`).

`app/management/models/entity_type.py`: copy of `app/core/models/entity_type.py` with only these changes:

```python
class MgmtRefEntityType(Base, TimestampMixin):
    __tablename__ = "mgmt_ref_entity_type"
    # __table_args__ (CheckConstraint "ck_entity_type_tracking_mode") and all columns unchanged
```

`app/management/models/event_log.py`: copy of `app/core/models/event_log.py` with only these changes:

```python
class MgmtLogEvent(Base):
    __tablename__ = "mgmt_log_event"
    # ...
    entity_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("mgmt_ref_entity_type.id"),
        nullable=False,
        index=True,
    )
    # ...
    entity_type = relationship("MgmtRefEntityType", lazy="joined")
```

`app/management/models/__init__.py`:

```python
# Local application
from .entity_type import MgmtRefEntityType
from .event_log import MgmtLogEvent

__all__ = ["MgmtRefEntityType", "MgmtLogEvent"]
```

`app/management/schemas/event_log.py`: copy of `app/core/schemas/event_log.py`, unchanged.

`app/management/utils/event_logger.py`: copy of `app/core/utils/event_logger.py`, then search and replace in the copy: `CoreRefEntityType` to `MgmtRefEntityType`, `CoreLogEvent` to `MgmtLogEvent`, `app.core.models.entity_type` to `app.management.models.entity_type`, `app.core.models.event_log` to `app.management.models.event_log`. Nothing else changes (`from app.core.base import Base` and `request_id_ctx` stay).

`app/management/utils/seed_entity_types.py`: copy of `app/core/utils/seed_entity_types.py`, then replace `CoreRefEntityType` with `MgmtRefEntityType`, `app.core.models.entity_type` with `app.management.models.entity_type`, and set:

```python
NONE_TABLES = frozenset({
    "mgmt_ref_entity_type",
    "mgmt_log_event",
    "mgmt_log_job",
    "profile_user_credentials",
    "explorer_sub_geo_record",
    "explorer_sub_geo_performance",
    "spatial_ref_sys",
})
```

(Only the first two entries change from the current file, which lists `core_ref_entity_type` and `core_log_event`; keep the other entries exactly as they are, including the two `explorer_sub_geo_*` tables and the already corrected `profile_user_credentials`. `mgmt_log_job` is listed now so X3 needs no edit. `mgmt_settings` stays tracked on purpose.)

`app/management/routes/event_log.py`: copy of `app/core/routes/event_log.py`, then replace `CoreRefEntityType` with `MgmtRefEntityType`, `CoreLogEvent` with `MgmtLogEvent`, `app.core.models.entity_type` with `app.management.models.entity_type`, `app.core.models.event_log` with `app.management.models.event_log`, `app.core.schemas.event_log` with `app.management.schemas.event_log`, and the router line with:

```python
router = APIRouter(prefix="/event-log", tags=["Management - Event Log"])
```

(The router prefix stays `/event-log`; the `/management` part comes from the parent router below. Every route keeps `require_groups("administrator")`.)

`app/management/routes/__init__.py`:

```python
# Third-party
from fastapi import APIRouter

# Local application
from .event_log import router as event_log_router

# Administrator-only routes live under /management; user routes (jobs, WebSocket)
# are added to `router` directly in later milestones.
admin_router = APIRouter(prefix="/management")
admin_router.include_router(event_log_router)

router = APIRouter()
router.include_router(admin_router)
```

#### X1.3 Edits to existing files

1. `app/core/models/__init__.py`: remove the two imports (`CoreRefEntityType`, `CoreLogEvent`) and their two `__all__` entries.
2. `app/core/routes/__init__.py` becomes:

```python
from fastapi import APIRouter

from .ref import routers as ref_routers

router = APIRouter(prefix="/ref")
for r in ref_routers:
    router.include_router(r)
```

3. Delete the six moved files from `app/core` (section 3.2) after the copies exist.
4. `app/main.py`:
   - remove `from app.core.routes import event_log_api_router`
   - `from app.core.utils.event_logger import load_entity_type_cache` becomes `from app.management.utils.event_logger import load_entity_type_cache`
   - `from app.core.utils.seed_entity_types import seed_entity_types` becomes `from app.management.utils.seed_entity_types import seed_entity_types`
   - add `from app.management.routes import router as management_router`
   - replace `app.include_router(event_log_api_router, prefix=api_v1_prefix)` with `app.include_router(management_router, prefix=api_v1_prefix)`
5. `app/database.py`, function `create_tables`: add `import app.management.models  # noqa: F401` after the `app.core.models` import.
6. `app/worker/model_registry.py`: add `import app.management.models  # noqa: F401`.
7. Import path in 12 route files: `from app.core.utils.event_logger import ...` becomes `from app.management.utils.event_logger import ...` in
   `app/compendium/routes/` `card.py`, `country.py`, `poi.py`, `poi_region.py`, `post.py`, `region.py`;
   `app/explorer/routes/` `gear.py`, `track.py`;
   `app/profile/routes/` `access_policy.py`, `admin.py`, `me.py`;
   `app/core/routes/ref.py`.
   Check with a search that no `app.core.utils.event_logger`, `CoreLogEvent` or `CoreRefEntityType` remains anywhere under `app/`, `scripts/`, `tests/`.
8. `designe/explorer_track_flow.svg`: the text labels `core_log_event` (line 120 and 126), `core_ref_entity_type` (line 124) and `API: /event-log` (line 129) become `mgmt_log_event`, `mgmt_ref_entity_type`, `API: /management/event-log`.

#### X1.4 Deploy and checks

Use the deploy sequence in 0.3 with `management_x1_move.sql`. Then:

```bash
P="sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege"
sudo docker logs --tail 40 alpen-api       # started, no traceback
sudo docker logs --tail 40 alpen-celery    # no ImportError
$P -c "SELECT count(*) AS events, max(seq) AS max_seq FROM mgmt_log_event;"      # same as X0
$P -c "\dt core_log*" -c "\dt mgmt_*"                                              # no core_log_*; mgmt_log_event and mgmt_ref_entity_type
$P -c "SELECT relname, relkind FROM pg_class WHERE relname ~ 'core_(log_event|ref_entity_type)';"   # 0 rows, or only sequences
$P -c "SELECT key, module, display_name, tracking_mode FROM mgmt_ref_entity_type WHERE module='mgmt' OR key LIKE 'profile_%cred%';"
$P -c "SELECT key, count(*) FROM mgmt_ref_entity_type GROUP BY key HAVING count(*) > 1;"            # 0 rows
```

Expected for the key query: `mgmt_log_event` and `mgmt_ref_entity_type` (module `mgmt`, `tracking_mode = none`) and `profile_user_credentials` with `tracking_mode = none`; `mgmt_log_job` appears after X3.

API checks (with an administrator `$TOKEN`):

```bash
H="Authorization: Bearer $TOKEN"; API=http://localhost:8000/api/v1
curl -s "$API/management/event-log?limit=3" -H "$H" | python3 -m json.tool | head -40   # newest entries
curl -s -o /dev/null -w "%{http_code}\n" "$API/event-log" -H "$H"                        # 404 (old URL gone)
curl -s "$API/management/event-log/entity-types?module=mgmt" -H "$H" | python3 -m json.tool
curl -s http://localhost:8000/openapi.json | python3 -c "import sys,json; print(sorted(p for p in json.load(sys.stdin)['paths'] if 'event-log' in p))"
```

Make one event-logged change (for example `PATCH $API/gear/<id>` with a new name, or `PATCH $API/users/me`) and check:

```bash
$P -c "SELECT seq, action, request_id, changed_at FROM mgmt_log_event ORDER BY seq DESC LIMIT 3;"   # new row, seq greater than before, request_id set
```

Restart idempotency: `sudo docker restart alpen-api alpen-celery`, repeat the duplicate-key query (still 0 rows). Run the pytest line from 0.4 (still green).

**Done when:** row count and max seq equal X0 (the script already verified this), a new change appears in `mgmt_log_event` with a `request_id`, `/management/event-log` works and `/event-log` returns 404, no duplicate or stale entity type rows, no import error in either container.

**Rollback:** stop both containers, restore the old code, run the inverse renames (I write them on request; the X0 dump is the safety net).

---

### X2. Runtime settings (`mgmt_settings`)

Goal: global application settings that an administrator can change through the API without a deployment. Keys, types, ranges and defaults are fixed **in code**; values are stored in the table; readers use a 30 second cache. Used from X3 onward (WebSocket limits, retention, progress rate).

#### X2.1 DDL: `scripts/sql/management_x2_settings.sql`

```sql
-- Runtime settings table (X2). Idempotent, one transaction.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/management_x2_settings.sql
\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS moddatetime;

CREATE TABLE IF NOT EXISTS mgmt_settings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key              varchar(128) NOT NULL UNIQUE,
    value            jsonb        NOT NULL,
    value_type       varchar(16)  NOT NULL,
    default_value    jsonb        NOT NULL,
    min_value        numeric,
    max_value        numeric,
    category         varchar(32)  NOT NULL,
    description      text         NOT NULL,
    requires_restart boolean      NOT NULL DEFAULT false,
    updated_by       uuid REFERENCES profile_usr_user (id) ON DELETE SET NULL,
    created_at       timestamptz  NOT NULL DEFAULT now(),
    updated_at       timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT ck_mgmt_settings_value_type CHECK (value_type IN ('int', 'float', 'bool', 'string'))
);

DROP TRIGGER IF EXISTS trg_set_updated_at ON mgmt_settings;
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON mgmt_settings
    FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');

COMMIT;
```

#### X2.2 New files

`app/management/models/settings.py`:

```python
# Standard library
import uuid

# Third-party
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin


class MgmtSettings(Base, TimestampMixin):
    __tablename__ = "mgmt_settings"
    __table_args__ = (
        CheckConstraint(
            "value_type IN ('int', 'float', 'bool', 'string')",
            name="ck_mgmt_settings_value_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Primary key UUID, generated by the database.",
    )
    key: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        comment="Setting key such as 'jobs.retention_days'. Must exist in the registry in code.",
    )
    value: Mapped[object] = mapped_column(
        JSONB,
        nullable=False,
        comment="Current value as JSON (number, boolean or string, matching value_type).",
    )
    value_type: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        comment="One of 'int', 'float', 'bool', 'string'. Copied from the registry at startup.",
    )
    default_value: Mapped[object] = mapped_column(
        JSONB,
        nullable=False,
        comment="Default from the registry in code, used by the reset endpoint.",
    )
    min_value: Mapped[float | None] = mapped_column(
        Numeric(asdecimal=False),
        nullable=True,
        comment="Smallest allowed value for numeric settings, NULL if unbounded.",
    )
    max_value: Mapped[float | None] = mapped_column(
        Numeric(asdecimal=False),
        nullable=True,
        comment="Largest allowed value for numeric settings, NULL if unbounded.",
    )
    category: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="Group for display: jobs, events, ws, celery.",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="One sentence for the administrator screen. Copied from the registry at startup.",
    )
    requires_restart: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default="false",
        comment="True if a change only applies after a restart of the service.",
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profile_usr_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="User who last changed the value through the API, NULL if never changed.",
    )
```

`app/management/models/__init__.py`: add `from .settings import MgmtSettings` and `"MgmtSettings"` in `__all__`.

`app/management/runtime_settings/__init__.py`: empty file. (Callers import from the submodules, so `import ...registry` in tests does not pull in the database engine.)

`app/management/runtime_settings/registry.py`:

```python
# Standard library
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: str  # 'int' | 'float' | 'bool' | 'string'
    default: Any
    category: str
    description: str
    min: float | None = None
    max: float | None = None
    requires_restart: bool = False


REGISTRY_LIST: tuple[SettingDef, ...] = (
    SettingDef("jobs.retention_days", "int", 30, "jobs",
               "Delete finished jobs older than this many days. 0 keeps them forever.", 0, 3650),
    SettingDef("jobs.stale_after_hours", "int", 24, "jobs",
               "Fail queued or running jobs that did not change for this many hours. 0 switches the check off.", 0, 720),
    SettingDef("jobs.progress_min_interval_ms", "int", 1000, "jobs",
               "Minimum time between two progress messages of one job.", 100, 60000),
    SettingDef("jobs.recent_finished_minutes", "int", 10, "jobs",
               "Jobs finished within this many minutes are included in the sync message of a WebSocket.", 0, 1440),
    SettingDef("events.retention_days", "int", 30, "events",
               "Delete event log entries older than this many days. 0 keeps them forever.", 0, 3650),
    SettingDef("ws.ticket_ttl_s", "int", 30, "ws",
               "Lifetime of a one-time WebSocket ticket in seconds.", 5, 300),
    SettingDef("ws.max_connections_per_user", "int", 5, "ws",
               "Open WebSockets allowed per user. Applies to new connections.", 1, 50),
    SettingDef("ws.max_lifetime_s", "int", 3600, "ws",
               "A WebSocket is closed after this many seconds and the client reconnects. Applies to new connections.", 60, 86400),
    SettingDef("celery.status_cache_s", "int", 5, "celery",
               "How long the Celery status answer is cached, in seconds. 0 switches the cache off.", 0, 60),
)

REGISTRY: dict[str, SettingDef] = {d.key: d for d in REGISTRY_LIST}


def validate_value(definition: SettingDef, value: Any) -> Any:
    # Check a value against the type and range of a setting.
    # Params:
    #   definition: the registry entry.
    #   value: the JSON value sent by the client or read from the database.
    # Returns: the normalised value.
    # Raises: ValueError with a short message for the client.
    if definition.type == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    if definition.type == "string":
        if not isinstance(value, str):
            raise ValueError("must be text")
        if len(value) > 1000:
            raise ValueError("must be at most 1000 characters")
        return value
    if definition.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("must be a whole number")
    elif definition.type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        value = float(value)
    else:
        raise ValueError(f"unknown setting type {definition.type}")
    if definition.min is not None and value < definition.min:
        raise ValueError(f"must be at least {definition.min:g}")
    if definition.max is not None and value > definition.max:
        raise ValueError(f"must be at most {definition.max:g}")
    return value
```

`app/management/runtime_settings/service.py`:

```python
# Standard library
import logging
import time
from typing import Any

# Third-party
from sqlalchemy import select

# Local application
from app.database import AsyncSessionLocal, SyncSessionLocal
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY, validate_value

logger = logging.getLogger(__name__)

# Values are cached per process. A change applies in the process that handled the
# PATCH at once (invalidate) and in every other process within this many seconds.
CACHE_TTL_S = 30.0

_values: dict[str, Any] = {}
_loaded_at: float | None = None


def _stale() -> bool:
    return _loaded_at is None or (time.monotonic() - _loaded_at) > CACHE_TTL_S


def _store(rows) -> None:
    global _values, _loaded_at
    _values = {key: value for key, value in rows}
    _loaded_at = time.monotonic()


def _backoff() -> None:
    # The table could not be read: keep what we have (or the defaults) and retry after the TTL.
    global _loaded_at
    _loaded_at = time.monotonic()


def invalidate() -> None:
    # Drop the cache so the next read loads from the database.
    global _loaded_at
    _loaded_at = None


def _typed(key: str) -> Any:
    definition = REGISTRY[key]  # unknown key = programming error, raise KeyError
    raw = _values.get(key, definition.default)
    try:
        return validate_value(definition, raw)
    except ValueError:
        logger.warning("Setting %s has an invalid stored value %r, using the default", key, raw)
        return definition.default


def get_setting_sync(key: str) -> Any:
    # Read one setting from a synchronous context (Celery worker, scripts).
    # Params: key: a key from the registry.
    # Returns: the value, or the registry default if the database cannot be read.
    if _stale():
        try:
            with SyncSessionLocal() as session:
                rows = session.execute(select(MgmtSettings.key, MgmtSettings.value)).all()
            _store(rows)
        except Exception:
            logger.warning("Could not read mgmt_settings, using cached or default values", exc_info=True)
            _backoff()
    return _typed(key)


async def get_setting(key: str) -> Any:
    # Read one setting from async code (API routes, WebSocket).
    # Params: key: a key from the registry.
    # Returns: the value, or the registry default if the database cannot be read.
    if _stale():
        try:
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(select(MgmtSettings.key, MgmtSettings.value))).all()
            _store(rows)
        except Exception:
            logger.warning("Could not read mgmt_settings, using cached or default values", exc_info=True)
            _backoff()
    return _typed(key)
```

`app/management/runtime_settings/seed.py`:

```python
# Standard library
import logging

# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY, REGISTRY_LIST, validate_value
from app.management.runtime_settings.service import invalidate

logger = logging.getLogger(__name__)


async def seed_settings(session: AsyncSession) -> None:
    # Insert missing settings with their default and refresh type, range, description and
    # default of existing ones. NEVER overwrites `value`.
    result = await session.execute(select(MgmtSettings))
    existing = {row.key: row for row in result.scalars().all()}
    dirty = False

    for d in REGISTRY_LIST:
        row = existing.get(d.key)
        if row is None:
            session.add(MgmtSettings(
                key=d.key, value=d.default, value_type=d.type, default_value=d.default,
                min_value=d.min, max_value=d.max, category=d.category,
                description=d.description, requires_restart=d.requires_restart,
            ))
            dirty = True
            continue
        for attr, new in (
            ("value_type", d.type), ("default_value", d.default),
            ("min_value", d.min), ("max_value", d.max), ("category", d.category),
            ("description", d.description), ("requires_restart", d.requires_restart),
        ):
            if getattr(row, attr) != new:
                setattr(row, attr, new)
                dirty = True
        try:
            validate_value(d, row.value)
        except ValueError as exc:
            logger.warning("Setting %s has an invalid value %r (%s); readers fall back to the default", d.key, row.value, exc)

    for key in set(existing) - set(REGISTRY):
        logger.warning("mgmt_settings row %s is not in the registry; kept but unused", key)

    if dirty:
        await session.commit()
    invalidate()
```

`app/management/schemas/settings.py`:

```python
# Standard library
from datetime import datetime
from typing import Any
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict


class SettingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    value: Any
    value_type: str
    default_value: Any
    min_value: float | None = None
    max_value: float | None = None
    category: str
    description: str
    requires_restart: bool
    updated_at: datetime
    updated_by: UUID | None = None


class SettingUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: Any
```

`app/management/routes/settings.py`:

```python
# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY, validate_value
from app.management.runtime_settings.service import invalidate
from app.management.schemas.settings import SettingRead, SettingUpdate
from app.management.utils.event_logger import log_updated
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups

router = APIRouter(prefix="/settings", tags=["Management - Settings"])
admin_only = require_groups("administrator")


async def _get_row(db: AsyncSession, key: str) -> MgmtSettings:
    definition = REGISTRY.get(key)
    row = (await db.execute(select(MgmtSettings).where(MgmtSettings.key == key))).scalar_one_or_none()
    if definition is None or row is None:
        raise AppError(404, "Not found", error_message="No setting exists with this key.")
    return row


async def _apply(db: AsyncSession, row: MgmtSettings, value, admin: ProfileUsrUser) -> MgmtSettings:
    old_values = {"value": row.value}
    row.value = value
    row.updated_by = admin.id
    log_updated(db, row, old_values, {"value": value}, admin.id)
    await db.commit()
    await db.refresh(row)
    invalidate()
    return row


@router.get("", response_model=ApiResponse[list[SettingRead]])
async def list_settings(
    category: str | None = None,
    _user: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MgmtSettings).order_by(MgmtSettings.category, MgmtSettings.key)
    if category is not None:
        stmt = stmt.where(MgmtSettings.category == category)
    return ok((await db.execute(stmt)).scalars().all())


@router.get("/{key}", response_model=ApiResponse[SettingRead])
async def get_setting_route(
    key: str,
    _user: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return ok(await _get_row(db, key))


@router.patch("/{key}", response_model=ApiResponse[SettingRead])
async def update_setting(
    key: str,
    body: SettingUpdate,
    admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(db, key)
    try:
        value = validate_value(REGISTRY[key], body.value)
    except ValueError as exc:
        raise AppError(
            422, "Validation failed",
            error_message=f"{key}: {exc}",
            error_errors=[{"field": "value", "code": "invalid_value", "message": str(exc)}],
        )
    return ok(await _apply(db, row, value, admin), message="Updated")


@router.post("/{key}/reset", response_model=ApiResponse[SettingRead])
async def reset_setting(
    key: str,
    admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(db, key)
    return ok(await _apply(db, row, REGISTRY[key].default, admin), message="Reset to default")
```

#### X2.3 Edits to existing files

1. `app/management/routes/__init__.py`: add `from .settings import router as settings_router` and `admin_router.include_router(settings_router)`.
2. `app/main.py`, function `lifespan`: after `await load_entity_type_cache(session)` (inside the same `async with`) add

```python
        from app.management.runtime_settings.seed import seed_settings
        await seed_settings(session)
```

(The order matters: `seed_entity_types` must have registered `mgmt_settings` and `load_entity_type_cache` must have loaded it before the first `PATCH`, otherwise `log_updated` finds no entity type and silently logs nothing.)

#### X2.4 Tests: `tests/test_runtime_settings.py` (pure, no database)

```python
# Local application
from app.management.runtime_settings.registry import REGISTRY, REGISTRY_LIST, validate_value
import pytest


def test_keys_are_unique_and_prefix_matches_category():
    assert len(REGISTRY) == len(REGISTRY_LIST)
    for d in REGISTRY_LIST:
        assert d.key.split(".")[0] == d.category


def test_every_default_is_valid_and_inside_its_range():
    for d in REGISTRY_LIST:
        assert validate_value(d, d.default) == d.default
        if d.min is not None and d.max is not None:
            assert d.min <= d.default <= d.max


@pytest.mark.parametrize("value", [True, 3.5, "5", None])
def test_int_setting_rejects_wrong_types(value):
    with pytest.raises(ValueError):
        validate_value(REGISTRY["jobs.retention_days"], value)


def test_range_is_enforced():
    d = REGISTRY["ws.max_connections_per_user"]
    with pytest.raises(ValueError):
        validate_value(d, 0)
    with pytest.raises(ValueError):
        validate_value(d, 51)
    assert validate_value(d, 5) == 5
```

#### X2.5 Deploy and checks

Deploy with 0.3 and `management_x2_settings.sql`. Then (admin `$TOKEN`, non-admin `$TOKEN_EDITOR`):

```bash
$P -c "SELECT key, value, value_type, min_value, max_value, category FROM mgmt_settings ORDER BY category, key;"   # 9 rows
curl -s "$API/management/settings" -H "$H" | python3 -c "import sys,json; print(len(json.load(sys.stdin)['response_data']))"   # 9
J='Content-Type: application/json'
curl -s -X PATCH "$API/management/settings/jobs.retention_days" -H "$H" -H "$J" -d '{"value": 45}'    # 200, value 45
curl -s -X PATCH "$API/management/settings/jobs.retention_days" -H "$H" -H "$J" -d '{"value": -1}'    # 422
curl -s -X PATCH "$API/management/settings/jobs.retention_days" -H "$H" -H "$J" -d '{"value": 3.5}'   # 422
curl -s -X PATCH "$API/management/settings/jobs.retention_days" -H "$H" -H "$J" -d '{"value": true}'  # 422
curl -s -X PATCH "$API/management/settings/nope.nope" -H "$H" -H "$J" -d '{"value": 1}'               # 404
curl -s -X PATCH "$API/management/settings/jobs.retention_days" -H "$H" -H "$J" -d '{"value": 1, "x": 2}'   # 422 (extra field)
curl -s -X POST  "$API/management/settings/jobs.retention_days/reset" -H "$H"                          # value 30 again
curl -s -o /dev/null -w "%{http_code}\n" "$API/management/settings" -H "Authorization: Bearer $TOKEN_EDITOR"   # 403
curl -s -o /dev/null -w "%{http_code}\n" -X PATCH "$API/management/settings/jobs.retention_days" -H "Authorization: Bearer $TOKEN_EDITOR" -H "$J" -d '{"value": 5}'   # 403
$P -c "SELECT e.seq, e.action, e.snapshot FROM mgmt_log_event e JOIN mgmt_ref_entity_type t ON t.id = e.entity_type_id WHERE t.key = 'mgmt_settings' ORDER BY e.seq DESC LIMIT 3;"   # old and new value
sudo docker restart alpen-api
$P -c "SELECT key, count(*) FROM mgmt_settings GROUP BY key HAVING count(*) > 1;"      # 0 rows
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python -c "from app.management.runtime_settings.service import get_setting_sync as g; print(g('jobs.retention_days'), g('ws.ticket_ttl_s'))"   # 30 30
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

**Done when:** nine rows exist, all PATCH checks give the stated codes, a change shows `old`/`new` in the event log, restart keeps values and creates no duplicates, the sync reader prints the stored values, pytest passes.

---

### X3. Jobs core: table, service, `TrackedTask`, publisher, `/jobs`, demo task

Goal: the generic job mechanism, proven with a throw-away demo task before any GPX code is touched. After X3 a job can be created, run by a worker, followed through REST, and its events are visible on Redis (the WebSocket in X4 only forwards them).

#### X3.1 DDL: `scripts/sql/management_x3_jobs.sql`

```sql
-- Job log table (X3). Idempotent, one transaction.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/management_x3_jobs.sql
\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS moddatetime;

CREATE TABLE IF NOT EXISTS mgmt_log_job (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- the app always supplies it (= Celery task id)
    user_id         uuid REFERENCES profile_usr_user (id) ON DELETE SET NULL,
    kind            varchar(64)  NOT NULL,
    task_name       varchar(128) NOT NULL,
    status          varchar(16)  NOT NULL DEFAULT 'queued',
    stage           varchar(64),
    progress        smallint,
    subject_type    varchar(64),
    subject_id      uuid,
    result          jsonb,
    error_message   text,
    attempts        smallint     NOT NULL DEFAULT 0,
    worker_hostname varchar(128),
    request_id      text,
    created_at      timestamptz  NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    updated_at      timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT ck_mgmt_log_job_status
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT ck_mgmt_log_job_progress
        CHECK (progress IS NULL OR progress BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_user_created ON mgmt_log_job (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_subject ON mgmt_log_job (subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_finished ON mgmt_log_job (finished_at) WHERE finished_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_active ON mgmt_log_job (updated_at) WHERE status IN ('queued', 'running');
-- one active job per (kind, subject): reaper, restore and reprocess reuse it, races are settled here
CREATE UNIQUE INDEX IF NOT EXISTS ux_mgmt_log_job_active_subject
    ON mgmt_log_job (kind, subject_type, subject_id)
    WHERE status IN ('queued', 'running') AND subject_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_set_updated_at ON mgmt_log_job;
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON mgmt_log_job
    FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');

COMMIT;
```

#### X3.2 Model and schemas

`app/management/models/job.py`:

```python
# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, SmallInteger, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

# Local application
from app.core.base import Base, TimestampMixin


class MgmtLogJob(Base, TimestampMixin):
    __tablename__ = "mgmt_log_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_mgmt_log_job_status",
        ),
        CheckConstraint(
            "progress IS NULL OR progress BETWEEN 0 AND 100",
            name="ck_mgmt_log_job_progress",
        ),
        Index("ix_mgmt_log_job_user_created", "user_id", text("created_at DESC")),
        Index("ix_mgmt_log_job_subject", "subject_type", "subject_id"),
        Index("ix_mgmt_log_job_finished", "finished_at", postgresql_where=text("finished_at IS NOT NULL")),
        Index("ix_mgmt_log_job_active", "updated_at", postgresql_where=text("status IN ('queued', 'running')")),
        Index(
            "ux_mgmt_log_job_active_subject", "kind", "subject_type", "subject_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND subject_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Job id. Also the Celery task id of the first task of the job (supplied by the application).",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profile_usr_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Owner. NULL for system or admin-script jobs, which only the management API shows.",
    )
    kind: Mapped[str] = mapped_column(String(64), nullable=False, comment="What the job does, for example 'track.process'.")
    task_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="Celery task name of the first task.")
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="queued",
        comment="queued, running, succeeded, failed or cancelled. Terminal states are final.",
    )
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Machine name of the current step.")
    progress: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True, comment="0 to 100, written when the stage or status changes (finer values only go through Redis).",
    )
    subject_type: Mapped[str | None] = mapped_column(String(64), nullable=True, comment="Type of the object the job is about, for example 'track'.")
    subject_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, comment="Id of the object the job is about.")
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True, comment="Small summary for the client. Never large data.")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Safe text for the user. Technical details are only in the worker log.")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0", comment="Number of times the first task started.")
    worker_hostname: Mapped[str | None] = mapped_column(String(128), nullable=True, comment="Worker that ran the job last.")
    request_id: Mapped[str | None] = mapped_column(Text, nullable=True, comment="HTTP request id that started the job (same value as mgmt_log_event.request_id).")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="First start of a worker.")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, comment="When the job reached a terminal state.")
```

`app/management/models/__init__.py`: add `from .job import MgmtLogJob` and `"MgmtLogJob"`.

`app/management/schemas/job.py` (pure pydantic, no database imports):

```python
# Standard library
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict, model_validator


class JobSubject(BaseModel):
    type: str
    id: UUID


class JobRead(BaseModel):
    # One shape for REST and WebSocket. Accepts an ORM object or a row mapping.
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    stage: str | None = None
    progress: int | None = None
    subject: JobSubject | None = None
    result: dict | None = None
    error_message: str | None = None
    attempts: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _build(cls, value):
        if isinstance(value, Mapping):
            get = value.get
        else:
            def get(name, default=None):
                return getattr(value, name, default)
        data = {name: get(name) for name in cls.model_fields if name != "subject"}
        subject_type, subject_id = get("subject_type"), get("subject_id")
        data["subject"] = {"type": subject_type, "id": subject_id} if subject_type and subject_id else None
        return data


class JobAdminRead(JobRead):
    user_id: UUID | None = None
    task_name: str
    worker_hostname: str | None = None
    request_id: str | None = None


class JobAccepted(BaseModel):
    job_id: UUID


class JobStats(BaseModel):
    by_status: dict[str, int]
    by_kind: dict[str, dict[str, int]]
    failed_last_24h: int
    oldest_queued_at: datetime | None = None
    avg_duration_s_by_kind: dict[str, float]
```

#### X3.3 Job modules

`app/management/jobs/__init__.py`: empty.

`app/management/jobs/kinds.py`:

```python
class JobKind:
    TRACK_PROCESS = "track.process"
    TRACK_REPROCESS = "track.reprocess"
    POI_RESCAN = "poi.rescan"
    CARD_RESCAN = "card.rescan"
    DEMO = "demo"


# Celery task that starts a job of each kind (used when a job row is created)
TASK_NAME = {
    JobKind.TRACK_PROCESS: "tracks.process_gpx",
    JobKind.TRACK_REPROCESS: "tracks.reprocess",
    JobKind.POI_RESCAN: "tracks.rescan_poi",
    JobKind.CARD_RESCAN: "tracks.rescan_card",
    JobKind.DEMO: "mgmt.demo_job",
}

# Task name -> job kind, for the Celery API ("is this task tracked?")
TRACKED_TASKS = {name: kind for kind, name in TASK_NAME.items()}
# Tasks that continue an existing job (they receive job_id as a keyword argument)
CHAIN_TASKS = frozenset({"tracks.detect_pois"})
```

`app/management/jobs/outcome.py` (pure, no database imports; this is what the unit test imports):

```python
# Standard library
import json
from typing import Any

GENERIC_FAILURE = "The task failed. Please try again or contact support."
TIMEOUT_FAILURE = "The task took too long. Please try again or contact support."
_RESERVED = {"job", "stage", "message"}
_MAX_RESULT_BYTES = 2048


def public_result(retval: dict) -> dict | None:
    # The part of a task result that is stored on the job and shown to the client.
    out = {k: v for k, v in retval.items() if k not in _RESERVED}
    try:
        text = json.dumps(out, default=str)
    except (TypeError, ValueError):
        return None
    if len(text) > _MAX_RESULT_BYTES:
        return {"status": out.get("status")} if "status" in out else None
    return json.loads(text)


def interpret_result(retval: Any) -> tuple[str, dict]:
    # Decide what a returned task result means for the job.
    # Returns: (action, info) with action one of 'keep', 'continue', 'failed', 'succeeded'.
    if not isinstance(retval, dict):
        return "succeeded", {"result": None}
    job = retval.get("job")
    if job == "keep":
        return "keep", {}
    if job == "continue":
        return "continue", {"stage": retval.get("stage")}
    if retval.get("status") == "failed":
        return "failed", {"message": retval.get("message") or GENERIC_FAILURE}
    return "succeeded", {"result": public_result(retval)}
```

`app/redis.py`: add

```python
# Third-party (add next to the existing import)
import redis as sync_redis

# Module-level synchronous client for Celery workers and scripts (created on first use).
_sync_redis: sync_redis.Redis | None = None


def get_sync_redis() -> sync_redis.Redis:
    # Accessor for a synchronous Redis client (the async pool cannot be used in a worker).
    # Params: none.
    # Returns: a client for REDIS_URL with decoded (str) responses.
    global _sync_redis
    if _sync_redis is None:
        _sync_redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _sync_redis
```

`app/management/jobs/service.py`:

```python
# Standard library
import uuid
from typing import Any

# Third-party
from sqlalchemy import func, null, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Local application
from app.core.utils.responses import request_id_ctx
from app.management.models.job import MgmtLogJob

ACTIVE = ("queued", "running")
_T = MgmtLogJob.__table__


def _first(result) -> dict | None:
    row = result.mappings().first()
    return dict(row) if row is not None else None


def _insert(user_id, kind, task_name, subject_type, subject_id):
    return pg_insert(_T).values(
        id=uuid.uuid4(), user_id=user_id, kind=kind, task_name=task_name, status="queued",
        subject_type=subject_type, subject_id=subject_id,
        request_id=request_id_ctx.get("") or None,
    )


def _insert_if_free(user_id, kind, task_name, subject_type, subject_id):
    # ON CONFLICT DO NOTHING without a target: the only unique rule that can fire here is
    # ux_mgmt_log_job_active_subject (the primary key is a fresh uuid). No predicate to keep in sync.
    return _insert(user_id, kind, task_name, subject_type, subject_id).on_conflict_do_nothing().returning(*_T.c)


def _active_for(kind, subject_type, subject_id):
    return select(_T).where(
        _T.c.kind == kind, _T.c.subject_type == subject_type,
        _T.c.subject_id == subject_id, _T.c.status.in_(ACTIVE),
    )


def _active_update(job_id):
    return update(_T).where(_T.c.id == job_id, _T.c.status.in_(ACTIVE))


# ---------------------------------------------------------------- async (API routes)

async def create_job(db, *, user_id, kind, task_name, subject_type=None, subject_id=None) -> dict:
    # Insert a queued job (flush only; the caller commits). Returns the row as a dict.
    # Raises IntegrityError if an active job already exists for the same (kind, subject).
    result = await db.execute(_insert(user_id, kind, task_name, subject_type, subject_id).returning(*_T.c))
    return dict(result.mappings().one())


async def get_or_create_active_job(db, *, user_id, kind, task_name, subject_type, subject_id) -> tuple[dict, bool]:
    # Return (job, created). Reuses the queued or running job of this (kind, subject).
    for _ in range(3):
        row = _first(await db.execute(_insert_if_free(user_id, kind, task_name, subject_type, subject_id)))
        if row is not None:
            return row, True
        existing = _first(await db.execute(_active_for(kind, subject_type, subject_id)))
        if existing is not None:
            return existing, False
    raise RuntimeError("Could not create or find an active job")


async def fail_job(db, job_id, message: str) -> dict | None:
    # For routes that could not enqueue the task: the job must not hang in 'queued'.
    # Flush only; the caller commits (and publishes the returned row). None if it was not active.
    result = await db.execute(
        update(_T).where(_T.c.id == job_id, _T.c.status.in_(ACTIVE)).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    )
    return _first(result)


async def fail_active_jobs_for_subject(db, *, kind, subject_type, subject_id, message: str) -> list[dict]:
    # Fail every queued or running job of this (kind, subject). Used by routes that hold a lock
    # proving no run can be in progress (rescan), so a leftover job cannot block the new one.
    # Flush only; the caller commits and publishes the returned rows.
    result = await db.execute(
        update(_T).where(
            _T.c.kind == kind, _T.c.subject_type == subject_type,
            _T.c.subject_id == subject_id, _T.c.status.in_(ACTIVE),
        ).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    )
    return [dict(r) for r in result.mappings().all()]


# ---------------------------------------------------------------- sync (worker, reaper, scripts)

def create_job_sync(session, *, user_id, kind, task_name, subject_type=None, subject_id=None) -> dict:
    result = session.execute(_insert(user_id, kind, task_name, subject_type, subject_id).returning(*_T.c))
    return dict(result.mappings().one())


def get_or_create_active_job_sync(session, *, user_id, kind, task_name, subject_type, subject_id) -> tuple[dict, bool]:
    for _ in range(3):
        row = _first(session.execute(_insert_if_free(user_id, kind, task_name, subject_type, subject_id)))
        if row is not None:
            return row, True
        existing = _first(session.execute(_active_for(kind, subject_type, subject_id)))
        if existing is not None:
            return existing, False
    raise RuntimeError("Could not create or find an active job")


def requeue_or_create_job_sync(session, *, user_id, kind, task_name, subject_type, subject_id) -> tuple[dict, bool]:
    # For the reaper: reuse the active job of the subject (a running one goes back to queued)
    # or create a new one. Returns (job, changed); changed is True if the job was created or
    # moved back to queued (publish an event only then). The caller enqueues with task_id = job["id"].
    job, created = get_or_create_active_job_sync(
        session, user_id=user_id, kind=kind, task_name=task_name,
        subject_type=subject_type, subject_id=subject_id,
    )
    if created:
        return job, True
    if job["status"] == "running":
        requeued = mark_queued_again(session, job["id"], stage="requeued")
        return (requeued or job), requeued is not None
    return job, False


def mark_running(
    session, job_id, *, hostname: str | None = None, stage: str | None = None, first_task: bool = True,
) -> dict | None:
    # first_task=True : the first task of a job. Only a *queued* job is started, so a duplicate
    #                   delivery (or a skipped run) cannot bump `attempts` or reset the stage of a
    #                   run in progress. Retries and the reaper move the job back to queued first.
    # first_task=False: a continuation task (detect_pois): the job is running, keep it running.
    values: dict[str, Any] = {
        "status": "running",
        "started_at": func.coalesce(_T.c.started_at, func.now()),
    }
    if first_task:
        values["attempts"] = _T.c.attempts + 1
    if hostname:
        values["worker_hostname"] = hostname[:128]
    if stage:
        values["stage"] = stage
    if first_task:
        stmt = update(_T).where(_T.c.id == job_id, _T.c.status == "queued")
    else:
        stmt = _active_update(job_id)
    return _first(session.execute(stmt.values(**values).returning(*_T.c)))


def mark_progress(session, job_id, *, stage: str | None, progress: int | None) -> dict | None:
    values: dict[str, Any] = {}
    if stage is not None:
        values["stage"] = stage
    if progress is not None:
        values["progress"] = max(0, min(100, int(progress)))
    if not values:
        return None
    return _first(session.execute(_active_update(job_id).values(**values).returning(*_T.c)))


def mark_succeeded(session, job_id, result: dict | None) -> dict | None:
    return _first(session.execute(
        _active_update(job_id).values(
            status="succeeded", progress=100, stage="done",
            result=result if result is not None else null(),  # SQL NULL, not JSON null
            error_message=None, finished_at=func.now(),
        ).returning(*_T.c)
    ))


def mark_failed(session, job_id, message: str) -> dict | None:
    return _first(session.execute(
        _active_update(job_id).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    ))


def mark_queued_again(session, job_id, *, stage: str | None = None) -> dict | None:
    values: dict[str, Any] = {"status": "queued"}
    if stage:
        values["stage"] = stage
    return _first(session.execute(_active_update(job_id).values(**values).returning(*_T.c)))


def fail_active_job_for_subject(session, *, kind, subject_type, subject_id, message: str) -> dict | None:
    # Used by domain code that fails the subject itself (mark_failed, reaper) so the job follows.
    return _first(session.execute(
        update(_T).where(
            _T.c.kind == kind, _T.c.subject_type == subject_type,
            _T.c.subject_id == subject_id, _T.c.status.in_(ACTIVE),
        ).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    ))


def fail_stale_jobs(session, hours: int) -> list[dict]:
    result = session.execute(
        update(_T).where(
            _T.c.status.in_(ACTIVE),
            _T.c.updated_at < func.now() - func.make_interval(0, 0, 0, 0, hours),
        ).values(
            status="failed", error_message="The job did not finish in time.", finished_at=func.now(),
        ).returning(*_T.c)
    )
    return [dict(r) for r in result.mappings().all()]
```

`func.make_interval(0, 0, 0, 0, hours)` = `make_interval(years, months, weeks, days, hours)`: five positional args → hours ✓.

`app/management/jobs/events.py`:

```python
# Standard library
import json
import logging
from datetime import datetime
from typing import Any

# Local application
from app.management.schemas.job import JobRead
from app.redis import get_redis_pool, get_sync_redis

logger = logging.getLogger(__name__)

CH_ALL = "aw:all"
TICKET_PREFIX = "aw:ticket:"
CONN_PREFIX = "aw:conns:"


def ch_user(user_id) -> str:
    return f"aw:user:{user_id}"


def ch_job(job_id) -> str:
    return f"aw:job:{job_id}"


def ch_ctl(user_id) -> str:
    return f"aw:ctl:{user_id}"


def job_event(row) -> dict:
    return {"type": "job.update", "job": JobRead.model_validate(row).model_dump(mode="json")}


def progress_event(job_id, stage: str | None, progress: int | None) -> dict:
    return {"type": "job.progress", "job_id": str(job_id), "stage": stage, "progress": progress}


def control_event(action: str, reason: str) -> dict:
    return {"type": "control", "action": action, "reason": reason}


def notice_event(level: str, text: str, expires_at: datetime | None = None) -> dict:
    return {
        "type": "system.notice", "level": level, "text": text,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


def _targets(row_or_ids: dict) -> list[str]:
    channels = [ch_job(row_or_ids["id"])]
    if row_or_ids.get("user_id"):
        channels.append(ch_user(row_or_ids["user_id"]))
    return channels


def publish_job_event(row: dict) -> None:
    # Synchronous (worker, reaper, scripts). Never raises: the database state is already correct.
    try:
        payload = json.dumps(job_event(row))
        client = get_sync_redis()
        for channel in _targets(row):
            client.publish(channel, payload)
    except Exception:
        logger.warning("Could not publish job event for %s", row.get("id"), exc_info=True)


def publish_progress(user_id, job_id, stage: str | None, progress: int | None) -> None:
    try:
        payload = json.dumps(progress_event(job_id, stage, progress))
        client = get_sync_redis()
        client.publish(ch_job(job_id), payload)
        if user_id:
            client.publish(ch_user(user_id), payload)
    except Exception:
        logger.warning("Could not publish progress for %s", job_id, exc_info=True)


async def publish_job_event_async(row: dict) -> None:
    # Async variant for API routes (job created). Never raises.
    try:
        payload = json.dumps(job_event(row))
        client = get_redis_pool()
        for channel in _targets(row):
            await client.publish(channel, payload)
    except Exception:
        logger.warning("Could not publish job event for %s", row.get("id"), exc_info=True)
```

(X4 adds `publish_control` and `publish_notice`.)

`app/management/jobs/tracked_task.py`:

```python
# Standard library
import logging
import time
import uuid

# Third-party
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

# Local application
from app.database import SyncSessionLocal
from app.management.jobs import service
from app.management.jobs.events import publish_job_event, publish_progress
from app.management.jobs.outcome import GENERIC_FAILURE, TIMEOUT_FAILURE, interpret_result
from app.management.runtime_settings.service import get_setting_sync

logger = logging.getLogger(__name__)

_last_progress_sent: dict[str, float] = {}


def _to_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _run(fn) -> dict | None:
    # Run one job update in its own transaction, publish after the commit, never raise.
    try:
        with SyncSessionLocal() as session:
            row = fn(session)
            session.commit()
        if row is not None:
            publish_job_event(row)
        return row
    except Exception:
        logger.warning("Job update failed", exc_info=True)
        return None


class TrackedTask(Task):
    # Celery base class that keeps a mgmt_log_job row in step with the task. A task without a
    # job row (the UPDATEs match nothing) behaves exactly as before.
    #
    # job id = the keyword argument "job_id" (continuation tasks) or the task id (first task).
    job_stage: str | None = None  # stage set when this task starts (set through the task options)

    def _job_id(self, task_id, kwargs) -> uuid.UUID | None:
        return _to_uuid((kwargs or {}).get("job_id") or task_id)

    def before_start(self, task_id, args, kwargs):
        job_id = self._job_id(task_id, kwargs)
        if job_id is None:
            return
        first = str(job_id) == str(task_id)  # False for a continuation task (job_id in kwargs)
        row = _run(lambda s: service.mark_running(
            s, job_id, hostname=getattr(self.request, "hostname", None),
            stage=self.job_stage, first_task=first,
        ))
        if row is not None:
            self.request.job_id = str(job_id)
            self.request.job_user_id = row.get("user_id")

    def on_success(self, retval, task_id, args, kwargs):
        job_id = self._job_id(task_id, kwargs)
        if job_id is None:
            return
        action, info = interpret_result(retval)
        if action == "keep":
            return
        if action == "continue":
            if info.get("stage"):
                _run(lambda s: service.mark_progress(s, job_id, stage=info["stage"], progress=None))
            return
        _last_progress_sent.pop(str(job_id), None)
        if action == "failed":
            _run(lambda s: service.mark_failed(s, job_id, info["message"]))
        else:
            _run(lambda s: service.mark_succeeded(s, job_id, info["result"]))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        job_id = self._job_id(task_id, kwargs)
        if job_id is not None:
            _run(lambda s: service.mark_queued_again(s, job_id, stage="retrying"))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = self._job_id(task_id, kwargs)
        if job_id is None:
            return
        _last_progress_sent.pop(str(job_id), None)
        message = TIMEOUT_FAILURE if isinstance(exc, SoftTimeLimitExceeded) else GENERIC_FAILURE
        _run(lambda s: service.mark_failed(s, job_id, message))


def report_progress(task, percent: int, stage: str | None = None, *, persist: bool = False) -> None:
    # Report progress from inside a tracked task (call as report_progress(self, 40, "parsing")).
    # persist=False: publish only, at most once per jobs.progress_min_interval_ms.
    # persist=True : also write stage and percent to the job row and publish the full job
    #                (use when the stage changes; a few times per job).
    # Never raises.
    job_id = getattr(task.request, "job_id", None)
    if not job_id:
        return
    try:
        if persist:
            parsed = uuid.UUID(job_id)
            _run(lambda s: service.mark_progress(s, parsed, stage=stage, progress=percent))
            return
        interval = get_setting_sync("jobs.progress_min_interval_ms") / 1000.0
        now = time.monotonic()
        if now - _last_progress_sent.get(job_id, 0.0) < interval:
            return
        _last_progress_sent[job_id] = now
        publish_progress(getattr(task.request, "job_user_id", None), job_id, stage, percent)
    except Exception:
        logger.warning("Could not report progress for job %s", job_id, exc_info=True)
```

Important points for the implementer:
- `before_start` runs after Celery has pushed the request, so `self.request` is the live context and `self.request.job_id` is visible later in the same execution (including inside the task body).
- Hooks run in the worker child process. They must never raise (a raising `before_start` would fail the task); `_run` guarantees this.
- Hard kills (`time_limit` exceeded, OOM) may skip `on_failure`; the reaper (X6 for generic jobs, existing track reaper plus X7 for GPX) recovers those.
- If `mark_running` matches nothing (a duplicate delivery while the job is already running, or the job is already terminal), `self.request.job_id` is **not** set, so `report_progress` does nothing for that execution and cannot disturb the run that owns the job. `on_success` still interprets the returned dict; a duplicate that returns `{"job": "keep"}` changes nothing.

#### X3.4 Routes

`app/management/routes/jobs.py` (user routes, own jobs only):

```python
# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.management.models.job import MgmtLogJob
from app.management.schemas.job import JobRead
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser

router = APIRouter(prefix="/jobs", tags=["Management - Jobs"])

JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")


@router.get("", response_model=ApiResponse[list[JobRead]])
async def list_my_jobs(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    kind: str | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    active: bool = False,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    if status is not None and status not in JOB_STATUSES:
        raise AppError(422, f"Invalid status: {status}")

    base = select(MgmtLogJob).where(MgmtLogJob.user_id == user.id)
    if status:
        base = base.where(MgmtLogJob.status == status)
    if active:
        base = base.where(MgmtLogJob.status.in_(("queued", "running")))
    if kind:
        base = base.where(MgmtLogJob.kind == kind)
    if subject_type:
        base = base.where(MgmtLogJob.subject_type == subject_type)
    if subject_id:
        base = base.where(MgmtLogJob.subject_id == subject_id)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(MgmtLogJob.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return ok_list(rows, total=total, limit=limit, offset=offset)


@router.get("/{job_id}", response_model=ApiResponse[JobRead])
async def get_my_job(
    job_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(MgmtLogJob, job_id)
    if job is None or job.user_id != user.id:
        # Same answer for "not found" and "not yours"
        raise AppError(404, "Not found", error_message="The job does not exist or you do not have access to it.")
    return ok(job)
```

`app/management/routes/admin_jobs.py` (administrator, all users). Declare `/stats` **before** `/{job_id}`:

```python
# Standard library
from datetime import datetime, timedelta, timezone
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.management.models.job import MgmtLogJob
from app.management.routes.jobs import JOB_STATUSES
from app.management.schemas.job import JobAdminRead, JobStats
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups

router = APIRouter(prefix="/jobs", tags=["Management - Jobs"])
admin_only = require_groups("administrator")
T = MgmtLogJob


@router.get("", response_model=ApiResponse[list[JobAdminRead]])
async def list_all_jobs(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    kind: str | None = None,
    user_id: UUID | None = None,
    task_name: str | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    active: bool = False,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    if status is not None and status not in JOB_STATUSES:
        raise AppError(422, f"Invalid status: {status}")
    base = select(T)
    for condition, value in (
        (T.status == status, status), (T.kind == kind, kind), (T.user_id == user_id, user_id),
        (T.task_name == task_name, task_name), (T.subject_type == subject_type, subject_type),
        (T.subject_id == subject_id, subject_id), (T.created_at >= created_from, created_from),
        (T.created_at < created_to, created_to),
    ):
        if value is not None:
            base = base.where(condition)
    if active:
        base = base.where(T.status.in_(("queued", "running")))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(T.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return ok_list(rows, total=total, limit=limit, offset=offset)


@router.get("/stats", response_model=ApiResponse[JobStats])
async def job_stats(
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    by_status: dict[str, int] = {}
    by_kind: dict[str, dict[str, int]] = {}
    for kind, status, n in (await db.execute(select(T.kind, T.status, func.count()).group_by(T.kind, T.status))).all():
        by_status[status] = by_status.get(status, 0) + n
        by_kind.setdefault(kind, {})[status] = n
    failed_24h = (await db.execute(
        select(func.count()).where(T.status == "failed", T.finished_at > now - timedelta(hours=24))
    )).scalar_one()
    oldest = (await db.execute(select(func.min(T.created_at)).where(T.status == "queued"))).scalar_one()
    avg_rows = (await db.execute(
        select(T.kind, func.avg(func.extract("epoch", T.finished_at - T.started_at)))
        .where(T.status == "succeeded", T.started_at.isnot(None), T.finished_at > now - timedelta(days=7))
        .group_by(T.kind)
    )).all()
    return ok(JobStats(
        by_status=by_status, by_kind=by_kind, failed_last_24h=failed_24h, oldest_queued_at=oldest,
        avg_duration_s_by_kind={k: round(float(v), 2) for k, v in avg_rows if v is not None},
    ))


@router.get("/{job_id}", response_model=ApiResponse[JobAdminRead])
async def get_any_job(
    job_id: UUID,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(T, job_id)
    if job is None:
        raise AppError(404, "Not found", error_message="No job exists with this id.")
    return ok(job)
```

Edit `app/management/routes/__init__.py` to:

```python
# Third-party
from fastapi import APIRouter

# Local application
from .admin_jobs import router as admin_jobs_router
from .event_log import router as event_log_router
from .jobs import router as jobs_router
from .settings import router as settings_router

admin_router = APIRouter(prefix="/management")
admin_router.include_router(event_log_router)
admin_router.include_router(settings_router)
admin_router.include_router(admin_jobs_router)

router = APIRouter()
router.include_router(jobs_router)
router.include_router(admin_router)
```

#### X3.5 Worker wiring, demo task and script

`app/worker/celery_app.py`: add `"app.worker.tasks.management"` to the `include=[...]` list.

`app/worker/tasks/management.py` (X6 adds the two beat tasks to this file):

```python
# Standard library
import logging
import time

# Third-party
from celery import shared_task

# Local application
from app.worker import model_registry  # noqa: F401
from app.management.jobs.tracked_task import TrackedTask, report_progress

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    base=TrackedTask,
    name="mgmt.demo_job",
    job_stage="working",
    acks_late=True,
    soft_time_limit=300,
    time_limit=330,
)
def demo_job(self, seconds: int = 10, fail: bool = False):
    # Throw-away task to try jobs, progress and the WebSocket without any GPX file.
    seconds = max(1, min(int(seconds), 120))
    for i in range(seconds):
        time.sleep(1)
        report_progress(self, int((i + 1) * 100 / seconds), "working")
        if i + 1 == seconds // 2:
            report_progress(self, 50, "halfway", persist=True)
    if fail:
        raise RuntimeError("demo failure (this text must never reach the client)")
    return {"status": "ok", "seconds": seconds}
```

`scripts/demo_job.py`:

```python
#!/usr/bin/env python
"""Start a demo job (a worker task that sleeps and reports progress).

Usage (inside the api container):
    python scripts/demo_job.py --user-id <uuid> --seconds 8          # job of a user
    python scripts/demo_job.py --seconds 8 --fail                    # system job, task fails
"""
import argparse
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SyncSessionLocal  # noqa: E402
from app.management.jobs.events import publish_job_event  # noqa: E402
from app.management.jobs.kinds import JobKind, TASK_NAME  # noqa: E402
from app.management.jobs.service import create_job_sync  # noqa: E402
from app.worker import model_registry  # noqa: E402,F401
from app.worker.celery_app import celery_app  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Start a demo job")
    parser.add_argument("--user-id", help="owner of the job (omit for a system job)")
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()

    with SyncSessionLocal() as session:
        job = create_job_sync(
            session,
            user_id=UUID(args.user_id) if args.user_id else None,
            kind=JobKind.DEMO,
            task_name=TASK_NAME[JobKind.DEMO],
        )
        session.commit()
    publish_job_event(job)
    celery_app.send_task(
        TASK_NAME[JobKind.DEMO], args=[args.seconds, args.fail],
        task_id=str(job["id"]), ignore_result=True,
    )
    print(job["id"])


if __name__ == "__main__":
    main()
```

#### X3.6 Tests (pure)

`tests/test_job_outcome.py`:

```python
# Local application
from app.management.jobs.outcome import GENERIC_FAILURE, interpret_result


def test_keep_and_continue():
    assert interpret_result({"status": "skipped", "job": "keep"}) == ("keep", {})
    assert interpret_result({"status": "ready", "job": "continue", "stage": "detecting_pois"}) == (
        "continue", {"stage": "detecting_pois"})


def test_failed_uses_message_or_generic_text():
    assert interpret_result({"status": "failed", "message": "Bad file"}) == ("failed", {"message": "Bad file"})
    assert interpret_result({"status": "failed", "error": "internal_error"}) == ("failed", {"message": GENERIC_FAILURE})


def test_anything_else_succeeds_and_hides_reserved_keys():
    action, info = interpret_result({"status": "skipped", "track_id": "t", "stage": "x", "message": "m"})
    assert action == "succeeded"
    assert info["result"] == {"status": "skipped", "track_id": "t"}


def test_non_dict_and_large_results():
    assert interpret_result(None) == ("succeeded", {"result": None})
    action, info = interpret_result({"status": "ok", "blob": "x" * 5000})
    assert action == "succeeded" and info["result"] == {"status": "ok"}
```

`tests/test_job_payload.py`:

```python
# Standard library
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

# Local application
from app.management.schemas.job import JobAdminRead, JobRead

NOW = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)


def _row(**extra):
    base = dict(
        id=uuid.uuid4(), kind="track.process", status="running", stage="parsing", progress=None,
        subject_type="track", subject_id=uuid.uuid4(), result=None, error_message=None, attempts=1,
        created_at=NOW, started_at=NOW, finished_at=None, updated_at=NOW,
        user_id=uuid.uuid4(), task_name="tracks.process_gpx", worker_hostname="w1", request_id="r",
    )
    base.update(extra)
    return base


def test_from_mapping_builds_subject_and_hides_internal_fields():
    job = JobRead.model_validate(_row())
    dumped = job.model_dump(mode="json")
    assert dumped["subject"]["type"] == "track"
    assert "user_id" not in dumped and "task_name" not in dumped


def test_from_object_and_no_subject():
    job = JobRead.model_validate(SimpleNamespace(**_row(subject_type=None, subject_id=None)))
    assert job.subject is None


def test_admin_shape_has_extra_fields():
    job = JobAdminRead.model_validate(_row())
    assert job.task_name == "tracks.process_gpx" and job.worker_hostname == "w1"
```

#### X3.7 Deploy and checks

Deploy with 0.3 and `management_x3_jobs.sql`. Then:

```bash
P="sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege"
$P -c "\d mgmt_log_job"                                   # columns, 6 indexes including the primary key (one unique partial), trigger trg_set_updated_at, 2 CHECKs
$P -c "SELECT key, tracking_mode FROM mgmt_ref_entity_type WHERE key = 'mgmt_log_job';"   # none
sudo docker exec alpen-celery celery -A app.worker.celery_app inspect registered | grep -E "mgmt.demo_job|tracks\."   # demo job and the track tasks are registered
```

Run the demo while watching Redis in a second terminal:

```bash
# terminal 2: every event on every aw: channel (Pub/Sub ignores the database number)
sudo docker exec -it alpen-redis redis-cli PSUBSCRIBE 'aw:*'

# terminal 1: your own user id comes from GET $API/users/me
JOB=$(sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/demo_job.py --user-id <MY_USER_ID> --seconds 8)
echo $JOB
for i in 1 2 3 4 5 6 7 8 9 10; do curl -s "$API/jobs/$JOB" -H "$H" | python3 -c "import sys,json; j=json.load(sys.stdin)['response_data']; print(j['status'], j['stage'], j['progress'], j['attempts'])"; sleep 1.5; done
```

Expected: `queued` (or straight to) `running working None 1`, then stage `halfway` with progress 50, finally `succeeded done 100 1` with `result = {"status": "ok", "seconds": 8}`. In terminal 2: one `job.update` (queued), `job.update` (running), up to one `job.progress` per second on both `aw:user:<id>` and `aw:job:<id>`, `job.update` for `halfway`, and a final `job.update` (succeeded).

More checks:

```bash
# failing task: the client text is generic, the secret text only in the worker log
JOB2=$(sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/demo_job.py --user-id <MY_USER_ID> --seconds 2 --fail)
sleep 5; curl -s "$API/jobs/$JOB2" -H "$H" | python3 -m json.tool        # status failed, error_message = generic text, no "demo failure"
sudo docker logs --tail 30 alpen-celery | grep -n "demo failure"           # traceback is here

# another user cannot see it; unknown id; list; filters
curl -s -o /dev/null -w "%{http_code}\n" "$API/jobs/$JOB" -H "Authorization: Bearer $TOKEN_EDITOR"   # 404
curl -s -o /dev/null -w "%{http_code}\n" "$API/jobs/$(python3 -c 'import uuid;print(uuid.uuid4())')" -H "$H"   # 404
curl -s "$API/jobs?status=failed&limit=5" -H "$H" | python3 -m json.tool | head -30
curl -s -o /dev/null -w "%{http_code}\n" "$API/jobs?status=bogus" -H "$H"                              # 422

# system job (no owner): invisible in /jobs, visible in /management/jobs
JOB3=$(sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/demo_job.py --seconds 2)
curl -s -o /dev/null -w "%{http_code}\n" "$API/jobs/$JOB3" -H "$H"                                     # 404
curl -s "$API/management/jobs/$JOB3" -H "$H" | python3 -m json.tool                                    # user_id null, task_name mgmt.demo_job, worker_hostname set, request_id null
curl -s "$API/management/jobs?kind=demo" -H "$H" | python3 -m json.tool | head -40
curl -s "$API/management/jobs/stats" -H "$H" | python3 -m json.tool
curl -s -o /dev/null -w "%{http_code}\n" "$API/management/jobs" -H "Authorization: Bearer $TOKEN_EDITOR"   # 403
```

Terminal states are final because every transition is a single `UPDATE ... WHERE status IN ('queued','running')`. The failing demo task already exercises this: `on_failure` runs after the job could have been closed and changes nothing a second time (the job row keeps `attempts = 1` and one `finished_at`).

Unique active-subject index check (psql, then clean up):

```bash
$P -c "INSERT INTO mgmt_log_job (kind, task_name, subject_type, subject_id) VALUES ('demo','mgmt.demo_job','demo','00000000-0000-0000-0000-000000000001');"   # INSERT 0 1
$P -c "INSERT INTO mgmt_log_job (kind, task_name, subject_type, subject_id) VALUES ('demo','mgmt.demo_job','demo','00000000-0000-0000-0000-000000000001');"   # ERROR duplicate key ux_mgmt_log_job_active_subject
$P -c "DELETE FROM mgmt_log_job WHERE subject_id = '00000000-0000-0000-0000-000000000001';"
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

**Done when:** the demo job runs through `queued`, `running`, `succeeded` with the stages above, Redis shows the events with at most one `job.progress` per second, a failing task shows only the generic text to the client, another user gets 404, a system job is invisible in `/jobs` and visible in `/management/jobs`, the unique index refuses a second active job for one subject, pytest passes.

---

### X4. WebSocket: ticket, general and dedicated socket, broadcast, control

Goal: clients follow their jobs live. One socket per client (`/api/v1/ws`) receives broadcast notices and the events of all the user's jobs; an optional socket per job (`/api/v1/ws/jobs/{job_id}`) follows one job and closes when it ends. Login by one-time ticket. No DDL.

#### X4.1 New and changed code

`requirements.txt`: change `redis>=5.0.0` to `redis>=5.0.1` (`PubSub.aclose()` exists from 5.0.1). The rebuild in the deploy sequence installs it.

Add to `app/management/jobs/events.py` (keep what is there; no new imports are needed, `json`, `logging`, `datetime`, `get_redis_pool` and `CH_ALL` are already imported or defined there):

```python
async def publish_control(user_id, action: str, reason: str) -> None:
    # Tell every socket of this user to close (logout, deactivation). Never raises.
    try:
        await get_redis_pool().publish(ch_ctl(user_id), json.dumps(control_event(action, reason)))
    except Exception:
        logger.warning("Could not publish control message for %s", user_id, exc_info=True)


async def publish_notice(level: str, text: str, expires_at: datetime | None = None) -> int:
    # Broadcast to every connected socket. Returns the number of sockets that received it.
    return int(await get_redis_pool().publish(CH_ALL, json.dumps(notice_event(level, text, expires_at))))
```

`app/management/schemas/ws.py`:

```python
# Third-party
from pydantic import BaseModel


class WsTicket(BaseModel):
    ticket: str
    expires_in: int
```

`app/management/schemas/broadcast.py`:

```python
# Standard library
from datetime import datetime
from typing import Literal

# Third-party
from pydantic import BaseModel, ConfigDict, Field


class BroadcastCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: Literal["info", "warning", "critical"] = "info"
    text: str = Field(min_length=1, max_length=500)
    expires_at: datetime | None = None


class BroadcastResult(BaseModel):
    delivered_to: int
```

`app/management/routes/broadcast.py`:

```python
# Standard library
import logging
from datetime import datetime, timezone

# Third-party
from fastapi import APIRouter, Depends

# Local application
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.jobs.events import publish_notice
from app.management.schemas.broadcast import BroadcastCreate, BroadcastResult
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/broadcast", tags=["Management - Broadcast"])
admin_only = require_groups("administrator")


@router.post("", response_model=ApiResponse[BroadcastResult])
async def send_broadcast(body: BroadcastCreate, admin: ProfileUsrUser = Depends(admin_only)):
    expires_at = body.expires_at
    if expires_at is not None:
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise AppError(422, "Validation failed", error_message="expires_at must be in the future.")
    delivered = await publish_notice(body.level, body.text, expires_at)
    logger.info("Broadcast by %s (%s) to %d sockets", admin.id, body.level, delivered)
    return ok(BroadcastResult(delivered_to=delivered), message="Broadcast sent")
```

`app/management/routes/ws.py`:

```python
# Standard library
import asyncio
import json
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

# Third-party
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy import or_, select
from starlette.websockets import WebSocketState

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.database import AsyncSessionLocal
from app.management.jobs.events import (
    CH_ALL, CONN_PREFIX, TICKET_PREFIX, ch_ctl, ch_job, ch_user,
)
from app.management.models.job import MgmtLogJob
from app.management.runtime_settings.service import get_setting
from app.management.schemas.job import JobRead
from app.management.schemas.ws import WsTicket
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser
from app.redis import get_redis_pool

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Management - WebSocket"])

# Close codes (4000 to 4999 are free for applications)
CLOSE_UNAUTHORIZED = 4401   # bad ticket, or logout
CLOSE_FORBIDDEN = 4403      # account deactivated
CLOSE_NOT_FOUND = 4404      # dedicated socket: not your job, or no such job
CLOSE_RECONNECT = 4408      # maximum lifetime reached: get a new ticket and reconnect
CLOSE_TOO_MANY = 4429       # too many open sockets for this user
MAX_CLIENT_MESSAGE_CHARS = 1024
TERMINAL = ("succeeded", "failed", "cancelled")


@router.post("/ws/ticket", response_model=ApiResponse[WsTicket])
async def create_ws_ticket(user: ProfileUsrUser = Depends(get_current_active_user)):
    # A bearer token cannot be sent on a browser WebSocket, and tokens here rotate.
    # So: exchange the token for a short-lived, single-use ticket that goes in the URL.
    ttl = await get_setting("ws.ticket_ttl_s")
    ticket = secrets.token_urlsafe(32)
    await get_redis_pool().set(f"{TICKET_PREFIX}{ticket}", str(user.id), ex=ttl)
    return ok(WsTicket(ticket=ticket, expires_in=ttl))


async def _consume_ticket(ticket: str) -> uuid.UUID | None:
    raw = await get_redis_pool().getdel(f"{TICKET_PREFIX}{ticket}")  # works once
    try:
        return uuid.UUID(raw) if raw else None
    except ValueError:
        return None


async def _register_connection(user_id, conn_id: str, max_conns: int, lifetime: int) -> bool:
    # Sorted set of open sockets; the score is an expiry time, so a crashed process cannot
    # leave a permanent count behind.
    redis = get_redis_pool()
    key = f"{CONN_PREFIX}{user_id}"
    now = time.time()
    pipe = redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", now)
    pipe.zadd(key, {conn_id: now + lifetime + 30})
    pipe.zcard(key)
    pipe.expire(key, lifetime + 60)
    _, _, count, _ = await pipe.execute()
    if count > max_conns:
        await redis.zrem(key, conn_id)
        return False
    return True


def _dump(job) -> dict:
    return JobRead.model_validate(job).model_dump(mode="json")


async def _general_snapshot(user_id: uuid.UUID) -> dict:
    minutes = await get_setting("jobs.recent_finished_minutes")
    now = datetime.now(timezone.utc)
    since = now - timedelta(minutes=minutes)
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(
            select(MgmtLogJob)
            .where(
                MgmtLogJob.user_id == user_id,
                or_(MgmtLogJob.status.in_(("queued", "running")), MgmtLogJob.finished_at > since),
            )
            .order_by(MgmtLogJob.created_at.desc())
            .limit(200)
        )).scalars().all()
    return {"type": "sync", "jobs": [_dump(r) for r in rows], "server_time": now.isoformat()}


async def _job_snapshot(user_id: uuid.UUID, job_id: uuid.UUID) -> dict | None:
    async with AsyncSessionLocal() as session:
        job = (await session.execute(
            select(MgmtLogJob).where(MgmtLogJob.id == job_id, MgmtLogJob.user_id == user_id)
        )).scalar_one_or_none()
    if job is None:
        return None
    return {"type": "sync", "jobs": [_dump(job)], "server_time": datetime.now(timezone.utc).isoformat()}


def _close_code_for(reason: str | None) -> int:
    return CLOSE_FORBIDDEN if reason == "deactivated" else CLOSE_UNAUTHORIZED


def _parse(data: str) -> dict:
    try:
        parsed = json.loads(data)
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


async def _serve(websocket: WebSocket, user_id: uuid.UUID, channels: list[str], snapshot, *, close_on_terminal: bool) -> None:
    redis = get_redis_pool()
    max_conns = await get_setting("ws.max_connections_per_user")
    lifetime = await get_setting("ws.max_lifetime_s")
    conn_id = uuid.uuid4().hex

    if not await _register_connection(user_id, conn_id, max_conns, lifetime):
        await websocket.close(code=CLOSE_TOO_MANY)
        return

    pubsub = redis.pubsub()
    try:
        # Subscribe first, then read the snapshot, so no event can fall into a gap.
        await pubsub.subscribe(*channels)
        first = await snapshot()
        await websocket.send_text(json.dumps(first))
        jobs = first.get("jobs", [])
        if close_on_terminal and jobs and jobs[0]["status"] in TERMINAL:
            await websocket.close(code=1000)
            return

        async def forward():
            async for message in pubsub.listen():
                if message.get("type") != "message":
                    continue
                data = message["data"]
                await websocket.send_text(data)
                event = _parse(data)
                if event.get("type") == "control" and event.get("action") == "close":
                    await websocket.close(code=_close_code_for(event.get("reason")))
                    return
                if (
                    close_on_terminal and event.get("type") == "job.update"
                    and event.get("job", {}).get("status") in TERMINAL
                ):
                    await websocket.close(code=1000)
                    return

        async def receive():
            # The client sends nothing we need; reading detects a closed connection.
            try:
                while True:
                    text = await websocket.receive_text()
                    if len(text) > MAX_CLIENT_MESSAGE_CHARS:
                        await websocket.close(code=1009)
                        return
            except Exception:
                return

        async def lifetime_timer():
            await asyncio.sleep(lifetime)
            await websocket.close(code=CLOSE_RECONNECT)

        tasks = [asyncio.create_task(c()) for c in (forward, receive, lifetime_timer)]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, (WebSocketDisconnect, RuntimeError)):
                logger.warning("WebSocket task failed", exc_info=exc)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await pubsub.unsubscribe(*channels)
            try:
                await pubsub.aclose()
            except AttributeError:
                await pubsub.close()
        except Exception:
            pass
        try:
            await redis.zrem(f"{CONN_PREFIX}{user_id}", conn_id)
        except Exception:
            pass
        if websocket.application_state != WebSocketState.DISCONNECTED:
            try:
                await websocket.close(code=1011)
            except Exception:
                pass


@router.websocket("/ws")
async def ws_general(websocket: WebSocket, ticket: str = Query(...)):
    # General socket: broadcast notices, all my job events, control messages.
    await websocket.accept()
    user_id = await _consume_ticket(ticket)
    if user_id is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    await _serve(
        websocket, user_id, [CH_ALL, ch_user(user_id), ch_ctl(user_id)],
        lambda: _general_snapshot(user_id), close_on_terminal=False,
    )


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(websocket: WebSocket, job_id: uuid.UUID, ticket: str = Query(...)):
    # Dedicated socket: one job, closes when the job ends. Same answer for "not found" and "not yours".
    await websocket.accept()
    user_id = await _consume_ticket(ticket)
    if user_id is None:
        await websocket.close(code=CLOSE_UNAUTHORIZED)
        return
    if await _job_snapshot(user_id, job_id) is None:
        await websocket.close(code=CLOSE_NOT_FOUND)
        return

    async def snapshot():
        return await _job_snapshot(user_id, job_id) or {"type": "sync", "jobs": []}

    await _serve(websocket, user_id, [ch_job(job_id), ch_ctl(user_id)], snapshot, close_on_terminal=True)
```

Notes for the implementer:

- The ticket is in the URL, so uvicorn and any proxy log it. That is acceptable only because it works **once** and lives 30 seconds. Never put a bearer token in a WebSocket URL.
- `accept()` comes first and errors are sent as close codes, so a client can tell "bad ticket" (4401) from "network down".
- A missing `ticket` parameter is rejected by FastAPI before the handler runs (close code 1008).
- One Redis connection per open socket (`pubsub`); fine for the expected number of users. Redis fan-out also makes several API processes work without any change.
- `app/redis.py` pool uses `decode_responses=True`, so `message["data"]` is already a `str`.

Edit `app/management/routes/__init__.py`: add `from .broadcast import router as broadcast_router` and `from .ws import router as ws_router`; then `admin_router.include_router(broadcast_router)` and `router.include_router(ws_router)` (before `router.include_router(admin_router)`).

#### X4.2 Control messages on logout and deactivation

Reason (C1): sockets must close when the user logs out or is deactivated, but a token id check cannot tell logout from normal token rotation.

`app/profile/routes/logout.py`: add the import `from app.management.jobs.events import publish_control` and, after the `blacklist_token` block, before `return`:

```python
    await publish_control(_current_user.id, "close", "logout")
```

(This closes **all** sockets of that user, including those of other devices. They reconnect with a new ticket; a device whose token is revoked cannot get one. This is intended and documented.)

`app/profile/routes/admin.py`, function `deactivate_user`: add the same import and replace the last two lines with:

```python
    log_updated(db, user, old_values, {"is_active": False}, admin.id)
    await db.commit()
    await publish_control(user_id, "close", "deactivated")
    return ok(_user_to_read(user), message="User deactivated")
```

(The explicit commit makes the deactivation visible before the client can reconnect and ask for a new ticket.)

#### X4.3 Client check script: `scripts/ws_check.py`

```python
#!/usr/bin/env python
"""Open the job WebSocket like a client and print every message.

Usage (inside the api container; TOKEN is a login access token):
    python scripts/ws_check.py --token "$TOKEN"                       # general socket
    python scripts/ws_check.py --token "$TOKEN" --job <job_id>        # dedicated socket
    python scripts/ws_check.py --ticket <ticket>                      # reuse a ticket (it works once)
Options: --host http://localhost:8000   --seconds 60
"""
import argparse
import asyncio
import json
import time
import urllib.request

import websockets


def get_ticket(host: str, token: str) -> str:
    request = urllib.request.Request(
        f"{host}/api/v1/ws/ticket", method="POST", headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)["response_data"]["ticket"]


def close_info(exc) -> str:
    rcvd = getattr(exc, "rcvd", None)
    code, reason = (rcvd.code, rcvd.reason) if rcvd else (getattr(exc, "code", None), getattr(exc, "reason", None))
    return f"CLOSED code={code} reason={reason!r}"


async def run(args) -> None:
    ticket = args.ticket or get_ticket(args.host, args.token)
    ws_host = args.host.replace("https://", "wss://").replace("http://", "ws://")
    path = f"/api/v1/ws/jobs/{args.job}" if args.job else "/api/v1/ws"
    end = time.time() + args.seconds
    try:
        async with websockets.connect(f"{ws_host}{path}?ticket={ticket}") as ws:
            while True:
                remaining = end - time.time()
                if remaining <= 0:
                    print("STOPPED (time is up)")
                    return
                try:
                    print(await asyncio.wait_for(ws.recv(), remaining), flush=True)
                except asyncio.TimeoutError:
                    print("STOPPED (time is up)")
                    return
    except websockets.ConnectionClosed as exc:
        print(close_info(exc))
    except websockets.InvalidStatus as exc:
        print(f"REJECTED http status {exc.response.status_code}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Print job WebSocket messages")
    parser.add_argument("--token")
    parser.add_argument("--ticket")
    parser.add_argument("--job")
    parser.add_argument("--host", default="http://localhost:8000")
    parser.add_argument("--seconds", type=int, default=60)
    asyncio.run(run(parser.parse_args()))
```

(`websockets.InvalidStatus` exists from websockets 11; with an older version the rejected-handshake branch raises a different exception name, which is only cosmetic. The X0 check printed the installed version.)

#### X4.4 Tests (pure): `tests/test_ws_messages.py`

```python
# Local application
from app.management.jobs.events import (
    CH_ALL, ch_ctl, ch_job, ch_user, control_event, notice_event, progress_event,
)


def test_channel_names_share_the_prefix():
    assert CH_ALL == "aw:all"
    assert ch_user("u1") == "aw:user:u1"
    assert ch_job("j1") == "aw:job:j1"
    assert ch_ctl("u1") == "aw:ctl:u1"


def test_message_shapes():
    assert control_event("close", "logout") == {"type": "control", "action": "close", "reason": "logout"}
    assert progress_event("j1", "parsing", 40) == {"type": "job.progress", "job_id": "j1", "stage": "parsing", "progress": 40}
    notice = notice_event("warning", "Maintenance", None)
    assert notice["type"] == "system.notice" and notice["level"] == "warning" and notice["expires_at"] is None
```

#### X4.5 Deploy and checks

Deploy with 0.3 (no DDL, rebuild installs `redis>=5.0.1`). Two terminals. Stop the `PSUBSCRIBE` monitor from X3 first: it would count as a receiver and make `delivered_to` one too high. `TOKEN`, `TOKEN_EDITOR`, `API`, `H` as before; also define `J='Content-Type: application/json'` and `WS="sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/ws_check.py"`.

1. Ticket: `curl -s -X POST "$API/ws/ticket" -H "$H"` returns `ticket` and `expires_in: 30`; without a token: 401.
2. General socket sees a job live. Terminal A: `$WS --token "$TOKEN" --seconds 60`. First line is `sync`. Terminal B: `python scripts/demo_job.py --user-id <MY_USER_ID> --seconds 8`. Terminal A prints `job.update` (queued, running), `job.progress` (at most one per second), `job.update` (halfway), `job.update` (succeeded).
3. Dedicated socket: start a 10 s demo job, then `$WS --token "$TOKEN" --job $JOB`: `sync`, updates, final `succeeded`, then `CLOSED code=1000`. Run it again after the job finished: `sync` with `succeeded`, then `CLOSED code=1000` at once.
4. Ticket rules: `T=$(curl -s -X POST "$API/ws/ticket" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['response_data']['ticket'])")`; `$WS --ticket $T --seconds 3` works, the same `$WS --ticket $T` again prints `CLOSED code=4401`. A ticket older than 30 seconds: 4401. A made-up ticket: 4401. No ticket parameter: rejected at the handshake (the script prints `REJECTED http status 403`; a browser sees close code 1006 or 1008).
5. Isolation: listen with `$WS --token "$TOKEN_EDITOR"` while you run a demo job for **your** user id: the editor only gets its own (empty) `sync` and nothing else. `$WS --token "$TOKEN_EDITOR" --job $JOB` (your job): `CLOSED code=4404`. Same code for a random job id.
6. Limit: `PATCH $API/management/settings/ws.max_connections_per_user` to 2, then start three `$WS --token "$TOKEN" --seconds 20 &`: the third prints `CLOSED code=4429`. Reset the setting afterwards (`POST .../reset`).
7. Broadcast: one socket as admin, one as editor; `curl -s -X POST "$API/management/broadcast" -H "$H" -H "$J" -d '{"level":"info","text":"Test notice"}'` returns `delivered_to: 2` and both sockets print `system.notice`. Editor token: 403. `{"text":""}`: 422. `expires_at` in the past: 422. With no socket open: `delivered_to: 0`.
8. Logout: open a socket, call `POST $API/auth/logout` with the same token: the socket prints a `control` message and `CLOSED code=4401`. A new ticket request with the logged-out token: 401.
9. Deactivation: open a socket as a test user, then as admin `PUT $API/users/<test user id>/deactivate`: the socket prints `control` and `CLOSED code=4403`; that user's `POST /ws/ticket` now returns 403. Reactivate the user afterwards.
10. Maximum lifetime: set `ws.max_lifetime_s` to 60, open a socket: after about 60 seconds `CLOSED code=4408`. Reset the setting.
11. **Token rotation does not close the socket** (this proves decision C1): the token lifetime is 5 minutes (`.env`), rotation starts at half of it. Open `$WS --token "$TOKEN" --seconds 420`, and meanwhile call `GET $API/users/me` every 30 seconds for 7 minutes, replacing `TOKEN` with the `X-Access-Token` header whenever the response has one (use `curl -si`). The socket must still be open at the end.
12. Cleanup: after all sockets are closed, `sudo docker exec alpen-redis redis-cli -n 2 ZRANGE aw:conns:<MY_USER_ID> 0 -1` is empty.
13. `pytest` passes.

**Done when:** checks 2 to 12 behave as stated (especially 4, 5, 8, 9 and 11), no traceback in `alpen-api` logs, pytest passes.

---

### X5. Celery API (read-only, administrator only)

Goal: see the state of Celery and of its tasks from the API. No DDL. All calls are for administrators; no task arguments, keyword arguments or results are ever returned.

Facts from the current code that shape this milestone:

- Every task is sent with `ignore_result=True`, so the result backend holds nothing. `AsyncResult.state` would always say `PENDING`. The task detail therefore comes from the **job row** plus a **live location** from `inspect` (decision C5).
- `inspect()` is a broadcast: without a known destination it waits the full timeout for replies. So the code pings first (about one second), then asks the workers that answered with `destination=` and `limit=`, which returns as soon as they have replied. Everything runs in a threadpool and is cached in Redis for `celery.status_cache_s` seconds (default 5).
- "No worker online" is a normal state (`state: "no_workers"`), never a 500.
- Chain tasks (`tracks.detect_pois`) have their own random task id, so they appear in the live list without a job. The job of a chain is found through the first task's id.

#### X5.1 New files

`app/management/celery_info.py` (blocking collectors plus **pure** shaping functions that the tests use):

```python
# Standard library
import logging
from datetime import datetime, timezone

# Third-party
import redis as sync_redis

# Local application
from app.config import get_settings
from app.management.jobs.kinds import CHAIN_TASKS, TRACKED_TASKS
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _epoch_to_iso(value) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


# ------------------------------------------------------------------ pure shaping (tested)

def shape_workers(stats: dict | None, queues: dict | None, registered: dict | None) -> list[dict]:
    stats, queues, registered = stats or {}, queues or {}, registered or {}
    out = []
    for name in sorted(set(stats) | set(queues) | set(registered)):
        s = stats.get(name) or {}
        pool = s.get("pool") or {}
        out.append({
            "hostname": name,
            "pid": s.get("pid"),
            "uptime_s": s.get("uptime"),
            "concurrency": pool.get("max-concurrency"),
            "queues": sorted(q["name"] for q in (queues.get(name) or []) if q.get("name")),
            "tasks_executed": dict(s.get("total") or {}),
            "registered_tasks": len(registered.get(name) or []),
        })
    return out


def shape_live(active: dict | None, reserved: dict | None, scheduled: dict | None) -> list[dict]:
    # Task arguments are deliberately dropped here.
    items = []
    for state, data in (("active", active), ("reserved", reserved), ("scheduled", scheduled)):
        for worker, tasks in (data or {}).items():
            for task in tasks or []:
                request = (task.get("request") if state == "scheduled" else task) or {}
                if not request.get("id"):
                    continue
                items.append({
                    "task_id": request["id"],
                    "name": request.get("name"),
                    "worker": worker,
                    "state": state,
                    "started_at": _epoch_to_iso(request.get("time_start")) if state == "active" else None,
                    "eta": task.get("eta") if state == "scheduled" else None,
                })
    return items


def shape_registered(registered: dict | None) -> list[dict]:
    names = sorted({n for tasks in (registered or {}).values() for n in (tasks or []) if not n.startswith("celery.")})
    return [
        {"name": n, "tracked": n in TRACKED_TASKS or n in CHAIN_TASKS, "job_kind": TRACKED_TASKS.get(n)}
        for n in names
    ]


def overall_state(broker_ok: bool, workers_online: int) -> str:
    if not broker_ok:
        return "down"
    return "ok" if workers_online > 0 else "no_workers"


# ------------------------------------------------------------------ blocking collectors

def _redis_ok(url: str) -> bool:
    client = None
    try:
        client = sync_redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        return bool(client.ping())
    except Exception:
        return False
    finally:
        if client is not None:
            client.close()


def _queue_length() -> int | None:
    client = None
    try:
        client = sync_redis.from_url(get_settings().CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        return int(client.llen(celery_app.conf.task_default_queue or "celery"))
    except Exception:
        return None
    finally:
        if client is not None:
            client.close()


def _online_workers(timeout: float) -> list[str]:
    try:
        return sorted((celery_app.control.inspect(timeout=timeout).ping() or {}).keys())
    except Exception:
        logger.warning("Celery ping failed", exc_info=True)
        return []


def _inspector(workers: list[str], timeout: float):
    return celery_app.control.inspect(destination=workers, timeout=timeout, limit=len(workers))


def collect_status(timeout: float = 1.0) -> dict:
    settings = get_settings()
    broker_ok = _redis_ok(settings.CELERY_BROKER_URL)
    backend_ok = _redis_ok(settings.CELERY_RESULT_BACKEND)
    workers = _online_workers(timeout) if broker_ok else []
    active = reserved = scheduled = 0
    if workers:
        insp = _inspector(workers, timeout)
        active = sum(len(v) for v in (insp.active() or {}).values())
        reserved = sum(len(v) for v in (insp.reserved() or {}).values())
        scheduled = sum(len(v) for v in (insp.scheduled() or {}).values())
    return {
        "state": overall_state(broker_ok, len(workers)),
        "broker_reachable": broker_ok,
        "result_backend_reachable": backend_ok,
        "workers_online": len(workers),
        "workers": workers,
        "queue_length": _queue_length() if broker_ok else None,
        "active_tasks": active,
        "reserved_tasks": reserved,
        "scheduled_tasks": scheduled,
        "beat_entries": len(celery_app.conf.beat_schedule or {}),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_workers(timeout: float = 1.0) -> list[dict]:
    workers = _online_workers(timeout)
    if not workers:
        return []
    insp = _inspector(workers, timeout)
    return shape_workers(insp.stats(), insp.active_queues(), insp.registered())


def collect_registered(timeout: float = 1.0) -> list[dict]:
    workers = _online_workers(timeout)
    if not workers:
        return []
    return shape_registered(_inspector(workers, timeout).registered())


def collect_live(timeout: float = 1.0) -> list[dict]:
    workers = _online_workers(timeout)
    if not workers:
        return []
    insp = _inspector(workers, timeout)
    return shape_live(insp.active(), insp.reserved(), insp.scheduled())


def collect_beat() -> list[dict]:
    now = datetime.now(timezone.utc)
    entries = []
    for name, entry in sorted((celery_app.conf.beat_schedule or {}).items()):
        schedule = entry.get("schedule")
        try:
            next_run = (now + schedule.remaining_estimate(now)).isoformat()
        except Exception:
            next_run = None
        entries.append({
            "name": name,
            "task": entry.get("task"),
            "schedule": getattr(schedule, "human_readable", None) or str(schedule),
            "next_run_at": next_run,
        })
    return entries
```

`app/management/schemas/celery.py`:

```python
# Standard library
from datetime import datetime

# Third-party
from pydantic import BaseModel

# Local application
from app.management.schemas.job import JobAdminRead


class CeleryStatus(BaseModel):
    state: str  # ok | no_workers | down
    broker_reachable: bool
    result_backend_reachable: bool
    workers_online: int
    workers: list[str]
    queue_length: int | None = None
    active_tasks: int
    reserved_tasks: int
    scheduled_tasks: int
    beat_entries: int
    checked_at: datetime


class WorkerInfo(BaseModel):
    hostname: str
    pid: int | None = None
    uptime_s: int | None = None
    concurrency: int | None = None
    queues: list[str]
    tasks_executed: dict[str, int]
    registered_tasks: int


class RegisteredTask(BaseModel):
    name: str
    tracked: bool
    job_kind: str | None = None


class LiveTask(BaseModel):
    task_id: str
    name: str | None = None
    worker: str
    state: str  # active | reserved | scheduled
    started_at: datetime | None = None
    eta: str | None = None
    job: JobAdminRead | None = None


class TaskDetail(BaseModel):
    task_id: str
    job: JobAdminRead | None = None
    live_state: str  # active | reserved | scheduled | unknown (not on any worker right now)
    worker: str | None = None
    started_at: datetime | None = None


class BeatEntry(BaseModel):
    name: str
    task: str | None = None
    schedule: str
    next_run_at: datetime | None = None
```

`app/management/routes/celery.py`:

```python
# Standard library
import json
import uuid

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management import celery_info
from app.management.models.job import MgmtLogJob
from app.management.runtime_settings.service import get_setting
from app.management.schemas.celery import (
    BeatEntry, CeleryStatus, LiveTask, RegisteredTask, TaskDetail, WorkerInfo,
)
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups
from app.redis import get_redis_pool

router = APIRouter(prefix="/celery", tags=["Management - Celery"])
admin_only = require_groups("administrator")


async def _cached(key: str, collector):
    # Run a blocking collector in a threadpool; cache the JSON answer in Redis.
    ttl = await get_setting("celery.status_cache_s")
    redis = get_redis_pool()
    if ttl > 0:
        raw = await redis.get(f"aw:celery:{key}")
        if raw:
            return json.loads(raw)
    data = await run_in_threadpool(collector)
    if ttl > 0:
        await redis.set(f"aw:celery:{key}", json.dumps(data), ex=ttl)
    return data


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def _jobs_by_task_id(db: AsyncSession, task_ids: list[str]) -> dict[str, MgmtLogJob]:
    ids = [u for u in (_uuid_or_none(t) for t in task_ids) if u]
    if not ids:
        return {}
    rows = (await db.execute(select(MgmtLogJob).where(MgmtLogJob.id.in_(ids)))).scalars().all()
    return {str(r.id): r for r in rows}


@router.get("/status", response_model=ApiResponse[CeleryStatus])
async def celery_status(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await _cached("status", celery_info.collect_status))


@router.get("/workers", response_model=ApiResponse[list[WorkerInfo]])
async def celery_workers(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await _cached("workers", celery_info.collect_workers))


@router.get("/tasks/registered", response_model=ApiResponse[list[RegisteredTask]])
async def celery_registered(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await _cached("registered", celery_info.collect_registered))


@router.get("/tasks/active", response_model=ApiResponse[list[LiveTask]])
async def celery_live_tasks(
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    live = await _cached("live", celery_info.collect_live)
    jobs = await _jobs_by_task_id(db, [t["task_id"] for t in live])
    return ok([{**t, "job": jobs.get(t["task_id"])} for t in live])


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskDetail])
async def celery_task_detail(
    task_id: str,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    live = {t["task_id"]: t for t in await _cached("live", celery_info.collect_live)}.get(task_id)
    job = (await _jobs_by_task_id(db, [task_id])).get(task_id)
    if live is None and job is None:
        raise AppError(404, "Not found", error_message="No job and no live task with this id.")
    return ok({
        "task_id": task_id,
        "job": job,
        "live_state": live["state"] if live else "unknown",
        "worker": live["worker"] if live else None,
        "started_at": live["started_at"] if live else None,
    })


@router.get("/beat", response_model=ApiResponse[list[BeatEntry]])
async def celery_beat(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(celery_info.collect_beat())
```

(`/tasks/registered` and `/tasks/active` are declared before `/tasks/{task_id}` on purpose.)

Edit `app/management/routes/__init__.py`: add `from .celery import router as celery_router` and `admin_router.include_router(celery_router)`.

#### X5.2 Tests (pure): `tests/test_celery_info.py`

```python
# Local application
from app.management.celery_info import overall_state, shape_live, shape_registered, shape_workers


def test_shape_live_drops_arguments_and_handles_scheduled():
    active = {"w1": [{"id": "a", "name": "mgmt.demo_job", "args": "(8,)", "kwargs": "{}", "time_start": 1790000000.0}]}
    scheduled = {"w1": [{"eta": "2026-10-23T08:00:00+00:00", "request": {"id": "s", "name": "stats.recompute_user", "args": "('u',)"}}]}
    items = shape_live(active, None, scheduled)
    assert [i["task_id"] for i in items] == ["a", "s"]
    assert all("args" not in i and "kwargs" not in i for i in items)
    assert items[0]["state"] == "active" and items[0]["started_at"] is not None
    assert items[1]["state"] == "scheduled" and items[1]["eta"] is not None


def test_shape_workers_and_registered():
    workers = shape_workers(
        {"w1": {"pid": 7, "uptime": 120, "pool": {"max-concurrency": 4}, "total": {"mgmt.demo_job": 2}}},
        {"w1": [{"name": "celery"}]},
        {"w1": ["tracks.process_gpx", "celery.ping"]},
    )
    assert workers[0]["concurrency"] == 4 and workers[0]["queues"] == ["celery"] and workers[0]["registered_tasks"] == 2
    names = {t["name"]: t for t in shape_registered({"w1": ["tracks.process_gpx", "stats.recompute_user", "celery.ping"]})}
    assert "celery.ping" not in names
    assert names["tracks.process_gpx"]["tracked"] is True and names["tracks.process_gpx"]["job_kind"] == "track.process"
    assert names["stats.recompute_user"]["tracked"] is False


def test_overall_state():
    assert overall_state(False, 3) == "down"
    assert overall_state(True, 0) == "no_workers"
    assert overall_state(True, 1) == "ok"
```

#### X5.3 Deploy and checks

Deploy with 0.3 (no DDL; rebuild so the worker image has the same code). `C="$API/management/celery"`.

```bash
# worker stopped: a clear answer, not an error
sudo docker stop alpen-celery
time curl -s "$C/status" -H "$H" | python3 -m json.tool     # state no_workers, workers_online 0, broker_reachable true, queue_length a number; takes about 1 to 2 s
curl -s "$C/workers" -H "$H"; curl -s "$C/tasks/active" -H "$H"; curl -s "$C/tasks/registered" -H "$H"   # empty lists, HTTP 200
curl -s "$C/beat" -H "$H" | python3 -m json.tool             # the beat entries still show (they come from the configuration), next_run_at in the future; a crontab schedule prints like "<crontab: 30 3 * * * (m/h/dM/MY/d)>"
sudo docker start alpen-celery; sleep 8

# worker running
curl -s "$C/status" -H "$H" | python3 -m json.tool           # state ok, workers_online 1, queue_length 0
curl -s "$C/workers" -H "$H" | python3 -m json.tool          # hostname celery@..., concurrency, queues ["celery"], tasks_executed
curl -s "$C/tasks/registered" -H "$H" | python3 -m json.tool # tracks.process_gpx tracked true job_kind track.process; tracks.detect_pois tracked true; stats.recompute_user tracked false; no celery.* names

# a live task and its job (30 s demo job)
JOB=$(sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/demo_job.py --user-id <MY_USER_ID> --seconds 30)
sleep 3
curl -s "$C/tasks/active" -H "$H" | python3 -m json.tool     # mgmt.demo_job, state active, started_at set, job filled (kind demo, status running)
curl -s "$C/tasks/$JOB" -H "$H" | python3 -m json.tool       # live_state active, worker, job
sleep 35
curl -s "$C/tasks/$JOB" -H "$H" | python3 -m json.tool       # live_state unknown, job succeeded
curl -s -o /dev/null -w "%{http_code}\n" "$C/tasks/$(python3 -c 'import uuid;print(uuid.uuid4())')" -H "$H"   # 404

# privacy and access
for p in status workers tasks/registered tasks/active beat; do curl -s "$C/$p" -H "$H" | grep -c '"args"\|"kwargs"'; done   # all 0
for p in status workers tasks/registered tasks/active beat "tasks/$JOB"; do curl -s -o /dev/null -w "%{http_code} " "$C/$p" -H "Authorization: Bearer $TOKEN_EDITOR"; done; echo   # 403 for each

# cache: two calls within 5 s return the same checked_at; with celery.status_cache_s = 0 they differ
curl -s "$C/status" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['response_data']['checked_at'])"
curl -s "$C/status" -H "$H" | python3 -c "import sys,json;print(json.load(sys.stdin)['response_data']['checked_at'])"
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

**Done when:** every answer above matches (especially `no_workers` without an error, no `args`/`kwargs` anywhere, 403 for non-admins), pytest passes.

---

### X6. Retention and stale-job reaper

Goal: two beat tasks that use the runtime settings. `mgmt.cleanup_retention` deletes finished jobs and old event log entries (`0` = keep forever). `mgmt.reap_stale_jobs` fails jobs that stopped changing (a hard-killed worker, a dropped message). No DDL (the index on `mgmt_log_event.changed_at` came with X1, the ones on `mgmt_log_job` with X3).

#### X6.1 Tasks: append to `app/worker/tasks/management.py`

Add these imports at the top of the file (next to the existing ones):

```python
# Third-party
from sqlalchemy import text

# Local application
from app.database import SyncSessionLocal
from app.management.jobs import service
from app.management.jobs.events import publish_job_event
from app.management.runtime_settings.service import get_setting_sync
```

Then add:

```python
BATCH_SIZE = 5000
MAX_BATCHES = 1000  # safety stop: at most 5 million rows per run and table


def _delete_in_batches(sql: str, params: dict) -> int:
    # Delete in small transactions so no long lock is held on a large table.
    total = 0
    for _ in range(MAX_BATCHES):
        with SyncSessionLocal() as session:
            deleted = session.execute(text(sql), {**params, "batch": BATCH_SIZE}).rowcount
            session.commit()
        total += deleted
        if deleted < BATCH_SIZE:
            break
    return total


@shared_task(name="mgmt.cleanup_retention")
def cleanup_retention():
    # Not a job (nobody follows it). Queued and running jobs are never deleted.
    jobs_days = get_setting_sync("jobs.retention_days")
    events_days = get_setting_sync("events.retention_days")
    jobs_deleted = events_deleted = 0

    if jobs_days > 0:
        jobs_deleted = _delete_in_batches(
            "DELETE FROM mgmt_log_job WHERE id IN ("
            "  SELECT id FROM mgmt_log_job"
            "   WHERE status IN ('succeeded', 'failed', 'cancelled')"
            "     AND finished_at < now() - make_interval(days => :days)"
            "   LIMIT :batch)",
            {"days": jobs_days},
        )
    if events_days > 0:
        events_deleted = _delete_in_batches(
            "DELETE FROM mgmt_log_event WHERE id IN ("
            "  SELECT id FROM mgmt_log_event"
            "   WHERE changed_at < now() - make_interval(days => :days)"
            "   LIMIT :batch)",
            {"days": events_days},
        )

    logger.info(
        "Retention: deleted %d job(s) older than %s day(s) and %d event(s) older than %s day(s)",
        jobs_deleted, jobs_days or "forever", events_deleted, events_days or "forever",
    )
    return {"status": "done", "jobs_deleted": jobs_deleted, "events_deleted": events_deleted}


@shared_task(name="mgmt.reap_stale_jobs")
def reap_stale_jobs():
    hours = get_setting_sync("jobs.stale_after_hours")
    if hours <= 0:
        return {"status": "disabled"}
    with SyncSessionLocal() as session:
        rows = service.fail_stale_jobs(session, hours)
        session.commit()
    for row in rows:
        publish_job_event(row)
    if rows:
        logger.warning("Failed %d stale job(s): %s", len(rows), [str(r["id"]) for r in rows])
    return {"status": "done", "failed": len(rows)}
```

`app/worker/celery_app.py`, `beat_schedule`: add two entries (the module is already in `include` since X3):

```python
        "mgmt-cleanup-retention-daily": {
            "task": "mgmt.cleanup_retention",
            "schedule": crontab(hour=3, minute=30),
        },
        "mgmt-reap-stale-jobs": {
            "task": "mgmt.reap_stale_jobs",
            "schedule": crontab(minute="*/15"),
        },
```

Behaviour to know:

- A worker reads the settings through a 30 second cache. After changing a setting through the API, wait 31 seconds before you trigger the task by hand.
- `mgmt_log_job.updated_at` is kept current by the `moddatetime` trigger, so every stage or status change resets the "stale" clock. A job that is legitimately long (a rescan can take 30 minutes) is nowhere near the default 24 hours.
- A task killed by the hard time limit or by the operating system may not call `on_failure`. For GPX the existing track reaper recovers the track and, after X7, requeues or fails the matching job. For every other job `mgmt.reap_stale_jobs` is the safety net.

#### X6.2 Deploy and checks

Deploy with 0.3 (no DDL). Define `P="sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege"` and `RUN="sudo docker exec alpen-celery celery -A app.worker.celery_app call"`; `API`, `H` as before.

```bash
# 1. both beat entries are known
curl -s "$API/management/celery/beat" -H "$H" | python3 -m json.tool | grep -E "mgmt-"

# 2. retention with 1 day
J='Content-Type: application/json'
for k in jobs.retention_days events.retention_days; do
  curl -s -X PATCH "$API/management/settings/$k" -H "$H" -H "$J" -d '{"value": 1}' > /dev/null
done
$P -c "INSERT INTO mgmt_log_job (kind, task_name, status, created_at, started_at, finished_at, updated_at) VALUES
  ('demo','mgmt.demo_job','succeeded', now()-interval '3 days', now()-interval '3 days', now()-interval '3 days', now()-interval '3 days'),
  ('demo','mgmt.demo_job','failed',    now()-interval '3 days', now()-interval '3 days', now()-interval '3 days', now()-interval '3 days'),
  ('demo','mgmt.demo_job','queued',    now()-interval '3 days', NULL, NULL, now()-interval '3 days'),
  ('demo','mgmt.demo_job','succeeded', now(), now(), now(), now());"
$P -c "INSERT INTO mgmt_log_event (entity_type_id, entity_id, action, snapshot, changed_by, changed_at)
  SELECT t.id, gen_random_uuid(), 'created', '{\"retention_test\": true}', (SELECT id FROM profile_usr_user LIMIT 1), now() - interval '5 days'
  FROM mgmt_ref_entity_type t WHERE t.key = 'mgmt_settings';"
sleep 31
$RUN mgmt.cleanup_retention
sleep 3
sudo docker logs --tail 5 alpen-celery | grep -i retention                    # deleted 2 job(s) ... 1 event(s) (at least)
$P -c "SELECT status, count(*) FROM mgmt_log_job WHERE kind='demo' AND created_at < now()-interval '2 days' GROUP BY status;"   # only the old 'queued' row remains
$P -c "SELECT count(*) AS old_test_events FROM mgmt_log_event WHERE snapshot ? 'retention_test';"                              # 0
$P -c "SELECT count(*) AS recent_events FROM mgmt_log_event WHERE changed_at > now() - interval '1 day';"                      # unchanged, greater than 0

# 3. 0 keeps everything
for k in jobs.retention_days events.retention_days; do
  curl -s -X PATCH "$API/management/settings/$k" -H "$H" -H "$J" -d '{"value": 0}' > /dev/null
done
$P -c "INSERT INTO mgmt_log_job (kind, task_name, status, created_at, finished_at, updated_at) VALUES ('demo','mgmt.demo_job','succeeded', now()-interval '400 days', now()-interval '400 days', now()-interval '400 days');"
sleep 31; $RUN mgmt.cleanup_retention; sleep 3
$P -c "SELECT count(*) FROM mgmt_log_job WHERE finished_at < now() - interval '300 days';"                                      # 1 (kept)

# 4. batches: 12000 old rows go in three transactions
curl -s -X PATCH "$API/management/settings/jobs.retention_days" -H "$H" -H "$J" -d '{"value": 1}' > /dev/null
$P -c "INSERT INTO mgmt_log_job (kind, task_name, status, created_at, finished_at, updated_at)
  SELECT 'demo','mgmt.demo_job','succeeded', now()-interval '9 days', now()-interval '9 days', now()-interval '9 days' FROM generate_series(1, 12000);"
sleep 31; $RUN mgmt.cleanup_retention; sleep 5
$P -c "SELECT count(*) FROM mgmt_log_job WHERE finished_at < now() - interval '2 days';"                                        # 0

# 5. stale reaper
curl -s -X PATCH "$API/management/settings/jobs.stale_after_hours" -H "$H" -H "$J" -d '{"value": 1}' > /dev/null
$P -c "INSERT INTO mgmt_log_job (kind, task_name, status, created_at, updated_at) VALUES ('demo','mgmt.demo_job','running', now()-interval '3 days', now()-interval '3 days') RETURNING id;"
sleep 31; $RUN mgmt.reap_stale_jobs; sleep 3
$P -c "SELECT status, error_message, finished_at IS NOT NULL AS finished FROM mgmt_log_job WHERE kind='demo' AND created_at < now() - interval '2 days' AND status='failed';"   # 2 rows: the new running one and the old queued one from step 2 (both 3 days without change), 'The job did not finish in time.'
curl -s -X PATCH "$API/management/settings/jobs.stale_after_hours" -H "$H" -H "$J" -d '{"value": 0}' > /dev/null
sleep 31; $RUN mgmt.reap_stale_jobs; sleep 3
sudo docker logs --tail 5 alpen-celery | grep -i "reap_stale"                 # result {'status': 'disabled'}

# 6. clean up and restore defaults
$P -c "DELETE FROM mgmt_log_job WHERE kind='demo' AND created_at < now() - interval '2 days';"
curl -s -X POST "$API/management/settings/jobs.retention_days/reset" -H "$H" > /dev/null
curl -s -X POST "$API/management/settings/events.retention_days/reset" -H "$H" > /dev/null
curl -s -X POST "$API/management/settings/jobs.stale_after_hours/reset" -H "$H" > /dev/null
```

**Done when:** step 2 deletes only finished old jobs and old events (the old `queued` row and recent events stay), step 3 keeps everything at `0`, step 4 clears 12000 rows without error, step 5 fails the stale job with the stated text and `disabled` at `0`, the settings are back to 30, 30 and 24.

---

### X7. Plug into GPX, reprocess and rescan; documentation

Goal: the real work becomes visible as jobs. `POST /tracks`, `POST /tracks/{id}/reprocess`, `POST /pois/{id}/rescan` and `POST /cards/{id}/rescan` create a job and return `job_id` plus `Location`; the processing and detection tasks keep the job in step; the reaper and `mark_failed` follow the job; the admin script creates system jobs. No DDL.

Rules this milestone keeps:

- The job row is **committed before** the task is enqueued (otherwise a fast worker finds no row and the job never moves).
- Job id = Celery task id for the first task (`task_id=str(job_id)` in `send_task`). The continuation task `tracks.detect_pois` gets `job_id` as a keyword argument.
- The track's `processing_status` stays the domain truth (reaper and atomic claim depend on it). Wherever the code fails or requeues a track, the same transaction fails or requeues the job.
- `request_stats_recompute` and `tracks.detect_pois` started by `restore` (a ready track) stay untracked: nobody follows them.

#### X7.1 `app/explorer/services/dispatch.py`

Replace the five `enqueue_*` functions (keep `_get_sync_redis` and `request_stats_recompute` unchanged):

```python
def enqueue_process_track(track_id: UUID, job_id: UUID | None = None) -> str | None:
    result = celery_app.send_task(
        "tracks.process_gpx",
        args=[str(track_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )
    return result.id if result else None


def enqueue_detect_pois(track_id: UUID, job_id: UUID | str | None = None) -> None:
    celery_app.send_task(
        "tracks.detect_pois",
        args=[str(track_id)],
        kwargs={"job_id": str(job_id)} if job_id else None,
        ignore_result=True,
    )


def enqueue_reprocess_track(track_id: UUID, job_id: UUID | None = None) -> None:
    celery_app.send_task(
        "tracks.reprocess",
        args=[str(track_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )


def enqueue_rescan_poi(poi_id: UUID, job_id: UUID | None = None) -> None:
    celery_app.send_task(
        "tracks.rescan_poi",
        args=[str(poi_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )


def enqueue_rescan_card(card_id: UUID, job_id: UUID | None = None) -> None:
    celery_app.send_task(
        "tracks.rescan_card",
        args=[str(card_id)],
        task_id=str(job_id) if job_id else None,
        ignore_result=True,
    )
```

(`task_id=None` makes Celery generate one, so callers without a job behave as before.)

#### X7.2 `app/explorer/services/track_persist.py`: `mark_failed` also fails the job

Add the imports:

```python
from app.management.jobs.events import publish_job_event
from app.management.jobs.kinds import JobKind
from app.management.jobs.service import fail_active_job_for_subject
```

Replace `mark_failed`:

```python
def mark_failed(session: Session, track_id: UUID, message: str) -> None:
    result = session.execute(
        update(ExplorerAggTrack)
        .where(
            ExplorerAggTrack.id == track_id,
            ExplorerAggTrack.processing_status == "processing",
        )
        .values(
            processing_status="failed",
            processing_error=message,
            processing_started_at=None,
            updated_at=func.now(),
        )
    )
    job = None
    if result.rowcount:
        # same transaction: the job text equals the track's processing_error
        job = fail_active_job_for_subject(
            session, kind=JobKind.TRACK_PROCESS, subject_type="track",
            subject_id=track_id, message=message,
        )
    session.commit()
    if job is not None:
        publish_job_event(job)
```

#### X7.3 `app/worker/tasks/track_processing.py`

Add the imports:

```python
from app.management.jobs import service as job_service
from app.management.jobs.events import publish_job_event
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.tracked_task import TrackedTask, report_progress
```

**`process_track_gpx`**: decorator gets `base=TrackedTask` and `job_stage="parsing"`; both "skipped" returns get `"job": "keep"`; one `report_progress` call before saving; the final part hands the job to `detect_pois`. Replace the whole function:

```python
@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.process_gpx",
    job_stage="parsing",
    acks_late=True,
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
)
def process_track_gpx(self, track_id: str):
    track_id = UUID(track_id)

    with SyncSessionLocal() as session:
        result = session.execute(
            text(
                "UPDATE explorer_agg_track "
                "SET processing_status = 'processing', processing_error = NULL, "
                "    processing_started_at = now(), updated_at = now() "
                "WHERE id = :id AND processing_status = 'pending' "
                "  AND archived_at IS NULL "
                "RETURNING gpx_id"
            ),
            {"id": str(track_id)},
        )
        row = result.fetchone()
        session.commit()

    if row is None:
        with SyncSessionLocal() as session:
            archived = session.execute(
                text("SELECT archived_at IS NOT NULL FROM explorer_agg_track WHERE id = :id"),
                {"id": str(track_id)},
            ).scalar()
        if archived:
            # nothing to process while archived (restore enqueues again with a new job): close this job
            return {"track_id": str(track_id), "status": "skipped", "reason": "archived"}
        # another execution owns the track (or it is already done): leave the job alone
        return {"track_id": str(track_id), "status": "skipped", "job": "keep"}

    gpx_id = row[0]

    with SyncSessionLocal() as session:
        gpx = session.get(AssetAggGpx, gpx_id)
        if not gpx:
            mark_failed(session, track_id, "GPX asset record not found.")
            return {"track_id": str(track_id), "status": "failed"}
        gpx_path = str(resolve_path(gpx.path))

    try:
        processed = process_gpx_file(gpx_path)
    except GpxProcessingError as exc:
        with SyncSessionLocal() as session:
            mark_failed(session, track_id, exc.user_message)
        if exc.code == "file_missing":
            logger.error("GPX file missing for track %s: %s", track_id, gpx_path)
        return {"track_id": str(track_id), "status": "failed", "error": exc.code}
    except SoftTimeLimitExceeded:
        with SyncSessionLocal() as session:
            mark_failed(
                session, track_id,
                "Processing took too long. Please try a smaller file or contact support.",
            )
        return {"track_id": str(track_id), "status": "failed", "error": "timeout"}
    except Exception as exc:
        logger.exception("Unexpected error processing track %s", track_id)
        with SyncSessionLocal() as session:
            mark_failed(
                session, track_id,
                "Processing failed. Please try again or contact support.",
            )
        return {"track_id": str(track_id), "status": "failed", "error": "internal_error"}

    report_progress(self, 60, "saving", persist=True)

    try:
        with SyncSessionLocal() as session:
            track = session.execute(
                select(ExplorerAggTrack)
                .where(ExplorerAggTrack.id == track_id)
                .with_for_update()
            ).scalar_one_or_none()

            if not track or track.processing_status != "processing":
                return {"track_id": str(track_id), "status": "skipped", "job": "keep"}

            persist_processed_track(session, track, processed)
            owner_id = track.created_by
            session.commit()
    except Exception as exc:
        logger.exception("DB error persisting track %s", track_id)
        try:
            with SyncSessionLocal() as session:
                session.execute(
                    update(ExplorerAggTrack)
                    .where(ExplorerAggTrack.id == track_id)
                    .values(processing_status="pending", processing_started_at=None)
                )
                session.commit()
            self.retry(countdown=30 * 2 ** self.request.retries, max_retries=3)
        except self.MaxRetriesExceededError:
            with SyncSessionLocal() as session:
                mark_failed(
                    session, track_id,
                    "Processing failed after multiple attempts. Please contact support.",
                )
            return {"track_id": str(track_id), "status": "failed", "error": "max_retries"}
        raise

    # hand the job to detect_pois (same job id as keyword argument); if that fails the job ends here
    continued = False
    try:
        enqueue_detect_pois(track_id, job_id=self.request.id)
        continued = True
    except Exception:
        logger.warning("Failed to enqueue detect_pois for track %s", track_id)

    try:
        request_stats_recompute(owner_id)
    except Exception:
        logger.warning("Failed to request stats recompute for user %s", owner_id)

    result = {
        "track_id": str(track_id),
        "status": "ready",
        "warnings": processed.warnings,
    }
    if continued:
        result.update({"job": "continue", "stage": "detecting_pois"})
    return result
```

(Only these parts differ from the current function: `base` and `job_stage` in the decorator, the new archived check in the first `row is None` branch (it replaces the single `skipped` return there), the `"job": "keep"` on the second `skipped` return, the `report_progress` call, and the `continued` block at the end.)

**`_reap_stuck_processing`**: select the owner too, and enqueue **after** the commit (fixes C10). Replace the function:

```python
def _reap_stuck_processing():
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT id, created_by FROM explorer_agg_track "
                "WHERE processing_status = 'processing' "
                "  AND processing_started_at < now() - make_interval(mins => :mins)"
            ),
            {"mins": settings.STUCK_PROCESSING_MINUTES},
        ).fetchall()

    if not rows:
        return

    try:
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        r = None

    for tid, owner_id in rows:
        attempts = 0
        if r:
            try:
                key = f"track:attempts:{tid}"
                attempts = r.incr(key)
                r.expire(key, 86400)
            except Exception:
                pass

        job_event = None
        enqueue_job_id = None
        with SyncSessionLocal() as session:
            if attempts >= settings.STUCK_MAX_ATTEMPTS:
                message = "Processing was interrupted repeatedly. Please try again or contact support."
                updated = session.execute(
                    text(
                        "UPDATE explorer_agg_track "
                        "SET processing_status = 'failed', "
                        "    processing_error = :msg, "
                        "    processing_started_at = NULL, updated_at = now() "
                        "WHERE id = :id AND processing_status = 'processing' "
                        "  AND processing_started_at < now() - make_interval(mins => :mins)"
                    ),
                    {"id": str(tid), "msg": message, "mins": settings.STUCK_PROCESSING_MINUTES},
                )
                if updated.rowcount:
                    job_event = job_service.fail_active_job_for_subject(
                        session, kind=JobKind.TRACK_PROCESS, subject_type="track",
                        subject_id=tid, message=message,
                    )
                logger.warning("Track %s failed after %d stuck attempts", tid, attempts)
            else:
                updated = session.execute(
                    text(
                        "UPDATE explorer_agg_track "
                        "SET processing_status = 'pending', "
                        "    processing_started_at = NULL, updated_at = now() "
                        "WHERE id = :id AND processing_status = 'processing' "
                        "  AND processing_started_at < now() - make_interval(mins => :mins)"
                    ),
                    {"id": str(tid), "mins": settings.STUCK_PROCESSING_MINUTES},
                )
                if updated.rowcount:
                    job, changed = job_service.requeue_or_create_job_sync(
                        session, user_id=owner_id, kind=JobKind.TRACK_PROCESS,
                        task_name=TASK_NAME[JobKind.TRACK_PROCESS],
                        subject_type="track", subject_id=tid,
                    )
                    enqueue_job_id = job["id"]
                    job_event = job if changed else None
            session.commit()

        # after the commit: publish and enqueue (the worker must see the track as pending)
        if job_event is not None:
            publish_job_event(job_event)
        if enqueue_job_id is not None:
            try:
                enqueue_process_track(tid, enqueue_job_id)
            except Exception:
                logger.warning("Failed to re-enqueue stuck track %s", tid)
```

**`_reap_stuck_pending`**: select the owner, reuse or create the job, enqueue with the job id. Replace the function:

```python
def _reap_stuck_pending():
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                "WITH due AS ("
                "  SELECT id FROM explorer_agg_track"
                "  WHERE processing_status = 'pending' AND archived_at IS NULL"
                "    AND updated_at < now() - make_interval(mins => :mins)"
                "  FOR UPDATE SKIP LOCKED"
                ") "
                "UPDATE explorer_agg_track t SET updated_at = now() "
                "FROM due WHERE t.id = due.id "
                "RETURNING t.id, t.created_by"
            ),
            {"mins": settings.STUCK_PENDING_MINUTES},
        ).fetchall()
        session.commit()

    for tid, owner_id in rows:
        try:
            with SyncSessionLocal() as session:
                job, changed = job_service.requeue_or_create_job_sync(
                    session, user_id=owner_id, kind=JobKind.TRACK_PROCESS,
                    task_name=TASK_NAME[JobKind.TRACK_PROCESS],
                    subject_type="track", subject_id=tid,
                )
                session.commit()
            if changed:
                publish_job_event(job)
            enqueue_process_track(tid, job["id"])
        except Exception:
            logger.warning("Failed to re-enqueue pending track %s", tid)
```

**`reprocess_track`** (task `tracks.reprocess`, admin script, ready track): decorator gets `base=TrackedTask` and `job_stage="reprocessing"`; the failure return carries the user message; the end hands over to `detect_pois`. Make exactly these changes:

```python
@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.reprocess",
    job_stage="reprocessing",
    acks_late=True,
    soft_time_limit=600,
    time_limit=660,
)
def reprocess_track(self, track_id: str):
    ...  # body unchanged except the three points below
```

1. In `except GpxProcessingError as exc:` the return becomes
   `return {"track_id": str(track_id), "status": "failed", "error": exc.code, "message": exc.user_message}`.
2. The "skipped" return (track not ready) stays as it is: a skipped reprocess closes its job as `succeeded` with `result.status == "skipped"`.
3. Replace the block after the `with` (from `try: enqueue_detect_pois(track_id)` to the final `return`) with:

```python
    continued = False
    try:
        enqueue_detect_pois(track_id, job_id=self.request.id)
        continued = True
    except Exception:
        logger.warning("Failed to enqueue detect_pois after reprocess for track %s", track_id)

    try:
        request_stats_recompute(owner_id)
    except Exception:
        logger.warning("Failed to request stats recompute after reprocess for user %s", owner_id)

    logger.info("Reprocessed track %s", track_id)
    result = {"track_id": str(track_id), "status": "ready"}
    if continued:
        result.update({"job": "continue", "stage": "detecting_pois"})
    return result
```

#### X7.4 `app/worker/tasks/track_detection.py`

Add the import `from app.management.jobs.tracked_task import TrackedTask`. Then:

1. `detect_pois`: decorator gets `base=TrackedTask` and `job_stage="detecting_pois"`; the function accepts the keyword argument (the base class reads it from `kwargs`, the body does not need it):

```python
@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.detect_pois",
    job_stage="detecting_pois",
    acks_late=True,
    soft_time_limit=300,
    time_limit=330,
)
def detect_pois(self, track_id: str, job_id: str | None = None):
    ...  # body and return unchanged: {"track_id", "status": report.status, "visits_added", "cards_added"}
```

2. `rescan_poi` and `rescan_card`: decorators get `base=TrackedTask` plus `job_stage="scanning"`; add `"status": "done"` to the returned dict (it becomes part of the job `result`):

```python
        return {
            "status": "done",
            "poi_id": poi_id,
            "tracks_scanned": total_tracks,
            "visits_added": total_visits,
            "cards_added": total_cards,
        }
```
and
```python
        return {
            "status": "done",
            "card_id": card_id,
            "cards_granted": report.cards_granted,
        }
```

#### X7.5 Routes and schema

`app/explorer/schemas/track.py`: in `TrackCreated` replace `task_id: str | None = None` by `job_id: UUID | None = None`.

`app/explorer/routes/track.py`:

Imports: add `Response` to the `fastapi` import, and

```python
from app.management.jobs.events import publish_job_event_async
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.service import create_job, get_or_create_active_job
from app.management.schemas.job import JobAccepted
```

`create_track`: add the parameter `response: Response,` as the **first** parameter, before `name` (a parameter without a default must not follow the `Form(...)`, `File(...)` and `Depends(...)` parameters; FastAPI injects it by type), and replace everything from `track = ExplorerAggTrack(` to the end of the function with:

```python
        track = ExplorerAggTrack(
            name=name,
            summary=summary or None,
            description=description or None,
            is_public=is_public,
            gpx_id=gpx.id,
            processing_status="pending",
            created_by=access.user.id,
        )
        db.add(track)
        await db.flush()
        log_created(db, track, access.user.id)
        job = await create_job(
            db, user_id=access.user.id, kind=JobKind.TRACK_PROCESS,
            task_name=TASK_NAME[JobKind.TRACK_PROCESS],
            subject_type="track", subject_id=track.id,
        )
        await db.commit()
    except Exception:
        await run_in_threadpool(delete_quietly, relative_path)
        raise

    await publish_job_event_async(job)
    try:
        await run_in_threadpool(enqueue_process_track, track.id, job["id"])
    except Exception:
        # the track stays pending and its job queued; the reaper enqueues it again
        logger.warning("Failed to enqueue processing for track %s", track.id)

    response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
    result = TrackCreated(
        id=track.id,
        name=track.name,
        processing_status=track.processing_status,
        created_at=track.created_at,
        duplicate_of_track_id=duplicate_of,
        job_id=job["id"],
    )
    return ok(result, code=202, message="Accepted")
```

`restore_track`: replace the `if track.processing_status == "pending":` branch (the `ready` branch stays) with:

```python
        if track.processing_status == "pending":
            try:
                job, created = await get_or_create_active_job(
                    db, user_id=track.created_by, kind=JobKind.TRACK_PROCESS,
                    task_name=TASK_NAME[JobKind.TRACK_PROCESS],
                    subject_type="track", subject_id=track.id,
                )
                await db.commit()
                if created:
                    await publish_job_event_async(job)
                await run_in_threadpool(enqueue_process_track, track.id, job["id"])
            except Exception:
                logger.warning("Failed to enqueue processing after restore of track %s", track.id)
```

`reprocess_track` (the route): change the decorator to `response_model=ApiResponse[JobAccepted]`, add the parameter `response: Response,` and replace the body after the 409 check with:

```python
    track.processing_status = "pending"
    track.processing_error = None
    track.processing_started_at = None
    # the failed attempt's job is terminal, so this creates a new job and keeps the old one as history
    job, created = await get_or_create_active_job(
        db, user_id=track.created_by, kind=JobKind.TRACK_PROCESS,
        task_name=TASK_NAME[JobKind.TRACK_PROCESS],
        subject_type="track", subject_id=track.id,
    )
    await db.commit()
    if created:
        await publish_job_event_async(job)

    try:
        await run_in_threadpool(enqueue_process_track, track.id, job["id"])
    except Exception:
        logger.warning("Failed to enqueue reprocess for track %s", track.id)

    if track.created_by == access.user.id:
        response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
    return ok(JobAccepted(job_id=job["id"]), code=202, message="Reprocessing queued")
```

(The job belongs to the track owner, and `GET /jobs/{id}` is owner-only. So `Location` is only set when the caller is the owner. If an administrator reprocesses someone else's track, the body still carries `job_id`, the administrator reads the job through `/management/jobs/{id}`, and the track's `processing_status` is visible as before.)

`app/compendium/routes/poi.py`: add the same job imports (`create_job`, `fail_job`, `fail_active_jobs_for_subject` from `app.management.jobs.service`; `publish_job_event_async`; `JobKind`, `TASK_NAME`; `JobAccepted`) and `Response` to the `fastapi` import. Replace the whole `rescan_poi` route:

```python
@router.post(
    "/{poi_id}/rescan",
    response_model=ApiResponse[JobAccepted],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rescan_poi(
    poi_id: UUID,
    response: Response,
    access: AccessContext = Depends(resource_access("poi", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPoi, poi_id)
    check_object_access(access, obj, not_found_msg="POI not found")

    from app.config import get_settings
    settings = get_settings()

    redis = get_redis_pool()
    lock_key = f"rescan:poi:{poi_id}"
    locked = await redis.set(lock_key, "1", nx=True, ex=settings.RESCAN_LOCK_SECONDS)
    if not locked:
        raise AppError(409, "Rescan already queued.")

    try:
        # We hold the lock, so no rescan of this POI can be running: a leftover active job
        # (hard-killed task, lost message) must not block this one through the unique index.
        leftovers = await fail_active_jobs_for_subject(
            db, kind=JobKind.POI_RESCAN, subject_type="poi", subject_id=poi_id,
            message="The rescan did not finish.",
        )
        job = await create_job(
            db, user_id=access.user.id, kind=JobKind.POI_RESCAN,
            task_name=TASK_NAME[JobKind.POI_RESCAN],
            subject_type="poi", subject_id=poi_id,
        )
        await db.commit()
    except Exception:
        await redis.delete(lock_key)
        raise AppError(503, "Failed to create the rescan job.")

    for leftover in leftovers:
        await publish_job_event_async(leftover)
    await publish_job_event_async(job)
    try:
        await run_in_threadpool(enqueue_rescan_poi, poi_id, job["id"])
    except Exception:
        await redis.delete(lock_key)
        failed = await fail_job(db, job["id"], "The rescan could not be queued.")
        await db.commit()
        if failed is not None:
            await publish_job_event_async(failed)
        raise AppError(503, "Failed to enqueue rescan.")

    response.headers["Location"] = f"/api/v1/jobs/{job['id']}"
    return ok(JobAccepted(job_id=job["id"]), code=202, message="Rescan queued")
```

`app/compendium/routes/card.py`: the same change for `rescan_card` (including the leftover handling and publishing the failed row): `CompendiumCatCard`, `resource_access("card", "update")`, `lock_key = f"rescan:card:{card_id}"`, `JobKind.CARD_RESCAN`, `subject_type="card"`, `enqueue_rescan_card`, messages "Card not found".

#### X7.6 Scripts

`scripts/reprocess_tracks.py`: add `import uuid` is not needed; replace the final enqueue block (from `from app.explorer.services.dispatch import enqueue_reprocess_track` to the last `logger.info`) with:

```python
    from uuid import UUID  # noqa: E402
    from app.explorer.services.dispatch import enqueue_reprocess_track  # noqa: E402
    from app.management.jobs import service as job_service  # noqa: E402
    from app.management.jobs.events import publish_job_event  # noqa: E402
    from app.management.jobs.kinds import JobKind, TASK_NAME  # noqa: E402
    from app.worker import model_registry  # noqa: E402,F401

    enqueued = 0
    for tid in track_ids:
        job = None
        try:
            with SyncSessionLocal() as session:
                job, created = job_service.get_or_create_active_job_sync(
                    session, user_id=None,  # system job: visible through /management/jobs only
                    kind=JobKind.TRACK_REPROCESS,
                    task_name=TASK_NAME[JobKind.TRACK_REPROCESS],
                    subject_type="track", subject_id=UUID(str(tid)),
                )
                session.commit()
            if not created:
                logger.info("Track %s already has an active reprocess job %s, skipped", tid, job["id"])
                continue
            publish_job_event(job)
            enqueue_reprocess_track(tid, job["id"])
            enqueued += 1
        except Exception:
            logger.warning("Failed to enqueue reprocess for track %s", tid)
            if job is not None:
                # do not leave a queued job behind: the next run would skip the track as "already active"
                with SyncSessionLocal() as session:
                    failed = job_service.mark_failed(session, job["id"], "The reprocess could not be queued.")
                    session.commit()
                if failed is not None:
                    publish_job_event(failed)

    logger.info("Enqueued %d / %d tracks", enqueued, len(track_ids))
```

`scripts/smoke_tracks.sh`: the API envelope uses `response_data` and `response_message`, but the script reads `.data.` and `.message`. Replace every `.data.` by `.response_data.` (login token, upload id, status, details), `.data[]` by `.response_data[]`, and `.message` (the two archive and restore lines) by `.response_message`. Then add job checks: after the upload (`TID=...`) also read `JID=$(echo "$BODY" | jq -r '.response_data.job_id // empty')`, store it in an array `JOB_IDS[$v]`, and in the polling loop, after the status is `ready` or `failed`, print `curl -sf "$API/jobs/${JOB_IDS[$v]}" -H "Authorization: Bearer $TOKEN" | jq -c '.response_data | {status, stage, progress, attempts, result}'`. For `ready` tracks the job must be `succeeded` shortly after (detection runs after `ready`), so poll the job for up to 20 more seconds until it is terminal.

#### X7.7 Tests (pure): extend `tests/test_job_outcome.py`

```python
def test_gpx_chain_results():
    handed_over = {"track_id": "t", "status": "ready", "warnings": [], "job": "continue", "stage": "detecting_pois"}
    assert interpret_result(handed_over) == ("continue", {"stage": "detecting_pois"})
    action, info = interpret_result({"track_id": "t", "status": "ok", "visits_added": 2, "cards_added": 1})
    assert action == "succeeded" and info["result"]["visits_added"] == 2
    assert interpret_result({"track_id": "t", "status": "skipped", "job": "keep"}) == ("keep", {})
    action, info = interpret_result({"track_id": "t", "status": "skipped", "reason": "archived"})
    assert action == "succeeded" and info["result"]["reason"] == "archived"
```

#### X7.8 Deploy and checks

Deploy with 0.3 (no DDL; the worker **must** be rebuilt). Variables as before; `GPX` files from `scripts/make_sample_gpx.py` (see `smoke_tracks.sh`). Terminal A runs `ws_check.py --token "$TOKEN" --seconds 120` during checks 1 to 3.

1. **Upload, happy path.** `curl -si -X POST "$API/tracks" -H "$H" -F "name=job test" -F "gpx_file=@/tmp/full.gpx;type=application/gpx+xml"`: HTTP 202, header `Location: /api/v1/jobs/<id>`, body has `response_data.job_id` and no `task_id`. Terminal A shows `job.update` queued, running (stage `parsing`), `saving`, `detecting_pois`, then `succeeded` with `result` containing `visits_added` and `cards_added`. `GET $API/jobs/<job_id>` ends as `succeeded`, `progress 100`, `attempts 1`. The track is `ready`.
   ```bash
   $P -c "SELECT id, kind, status, stage, attempts, user_id IS NOT NULL AS owned, request_id IS NOT NULL AS has_request FROM mgmt_log_job WHERE subject_id = '<TRACK_ID>';"   # one row
   ```
2. **Failure text matches.** Upload a GPX file with only one `<trkpt>` (take `full.gpx` and delete all but one point). The track becomes `failed`; the job becomes `failed`. Both texts are identical:
   ```bash
   $P -c "SELECT t.processing_error = j.error_message AS same_text, j.status FROM explorer_agg_track t JOIN mgmt_log_job j ON j.subject_id = t.id WHERE t.id = '<TRACK_ID>';"   # t | failed
   ```
3. **Reprocess.** `POST $API/tracks/<failed id>/reprocess`: 202, `Location`, `response_data.job_id` is **new**; `GET $API/jobs?subject_id=<TRACK_ID>` lists two jobs (old `failed`, new one running or failed again for the same bad file). `POST` again while the track is not `failed`: 409.
4. **Reaper keeps one job per track.** Upload a file with the worker stopped: `sudo docker stop alpen-celery`, upload, then `sudo docker exec alpen-redis redis-cli -n 0 DEL celery` (drops the queued message), `sudo docker start alpen-celery`. After at most 5 minutes plus one 2-minute reaper tick the pending reaper re-enqueues with the **same** job id; the job finishes `succeeded`:
   ```bash
   $P -c "SELECT count(*) FROM mgmt_log_job WHERE subject_id = '<TRACK_ID>';"   # 1
   ```
5. **Stuck `processing` is requeued, then failed for good.** Upload a file and wait until the track is `ready` and its job `succeeded`. Then fake a worker that died in the middle of processing (two statements, `<TRACK_ID>` is that track):
   ```bash
   $P -c "UPDATE explorer_agg_track SET processing_status = 'processing', processing_started_at = now() - interval '40 minutes' WHERE id = '<TRACK_ID>';"
   $P -c "UPDATE mgmt_log_job SET status = 'running', finished_at = NULL, result = NULL WHERE subject_id = '<TRACK_ID>' AND status = 'succeeded';"
   ```
   (The unique index allows the second statement because no other active job exists for that track.) Within about 2 minutes the reaper sets the track `pending` and the job `queued` (stage `requeued`), enqueues with the same job id, and the run completes: job `succeeded`, `attempts = 2`, still exactly one job row for the track. For the permanent failure: `sudo docker exec alpen-redis redis-cli -n 2 SET track:attempts:<TRACK_ID> 2`, then fake the stuck state again with the same two statements; the next reaper tick makes both the track and the job `failed` with the text "Processing was interrupted repeatedly. Please try again or contact support." (`processing_error = error_message`).
6. **Rescans.** `POST $API/pois/<poi id>/rescan` (editor or admin token): 202, `response_data.job_id`, `Location`. Job kind `poi.rescan`, ends `succeeded` with `result` counts (`tracks_scanned`, `visits_added`, `cards_added`). A second call while it runs: 409 and no second job row. Same for `POST $API/cards/<card id>/rescan` (kind `card.rescan`).
7. **Admin script.** `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/reprocess_tracks.py --track-id <ready track> --apply`: `GET $API/management/jobs?kind=track.reprocess` shows a job with `user_id` null that ends `succeeded` (stages `reprocessing` then `detecting_pois`). Running it again while the first is active logs "already has an active reprocess job".
8. **Untracked paths stay untracked.** Archive and restore a **ready** track: no new `mgmt_log_job` row is created (compare the row count before and after); detection still runs (the track keeps its POI links).
   **Archived while pending:** stop the worker, upload a file, archive the track (`DELETE $API/tracks/<id>`), drop the queued message (`redis-cli -n 0 DEL celery`) is **not** needed here; just start the worker. The queued task runs, finds the track archived, and the job ends `succeeded` with `result.reason = "archived"` (not `running` for 24 hours). Restore the track: a **new** job is created and the track is processed.
9. **Event log is not polluted.** `SELECT count(*) FROM mgmt_log_event e JOIN mgmt_ref_entity_type t ON t.id = e.entity_type_id WHERE t.key = 'mgmt_log_job';` returns 0, and `GET $API/management/event-log?entity_type=explorer_agg_track` still shows `created` and `updated` entries (the worker writes none).
10. **Smoke script** `scripts/smoke_tracks.sh` (after the edit in X7.6) runs through, prints a `succeeded` job per ready track.
11. `pytest` passes; `sudo docker logs --tail 100 alpen-celery` shows no traceback except the intended ones (the failed-file case).

**Done when:** checks 1 to 9 behave as stated.

#### X7.9 Documentation (part of this milestone)

- `README.md`: in "Project structure" add `management/  # event log, jobs, runtime settings, WebSocket, Celery API` and correct the outdated `worker.py` line to `worker/  # Celery app and tasks`; in "API endpoints" add the table from section 5.1 below and a short "Following a job" section: the 202 response gives `job_id` and `Location`; poll `GET /jobs/{id}` or open the WebSocket (`POST /ws/ticket`, then `wss://.../api/v1/ws?ticket=...`); on every (re)connect wait for `sync`; message types `sync`, `job.update`, `job.progress`, `system.notice`, `control`; close codes 4401, 4403, 4404, 4408, 4429.
- The other documents: section 5.2.

---

## 5. API summary, other documents, security tests

### 5.1 API surface after X7

| Method and path | Who | Milestone |
|---|---|---|
| `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}` | any active user, own jobs only | X3 |
| `POST /api/v1/ws/ticket` | any active user | X4 |
| `WS /api/v1/ws?ticket=...` (general), `WS /api/v1/ws/jobs/{job_id}?ticket=...` (dedicated) | ticket holder | X4 |
| `GET /api/v1/management/jobs`, `/jobs/stats`, `/jobs/{id}` | administrator | X3 |
| `GET /api/v1/management/event-log`, `/event-log/entity-types`, `/event-log/{id}`, `/event-log/{id_1}/compare/{id_2}` | administrator (moved from `/event-log`) | X1 |
| `GET /api/v1/management/settings`, `/settings/{key}`; `PATCH /settings/{key}`; `POST /settings/{key}/reset` | administrator | X2 |
| `POST /api/v1/management/broadcast` | administrator | X4 |
| `GET /api/v1/management/celery/status`, `/workers`, `/tasks/registered`, `/tasks/active`, `/tasks/{task_id}`, `/beat` | administrator | X5 |
| Changed: `POST /tracks`, `POST /tracks/{id}/reprocess`, `POST /pois/{id}/rescan`, `POST /cards/{id}/rescan` now return `job_id` and a `Location` header (`TrackCreated.task_id` is replaced by `job_id`) | as before | X7 |
| Removed: `GET /api/v1/event-log...` (moved, no alias) | | X1 |

### 5.2 Other documents that mention things this plan changes

Update them in the milestone shown; none of these edits is code.

| Document | Change | M |
|---|---|---|
| `designe/explorer_track_flow.svg` | labels `core_log_event`, `core_ref_entity_type`, `API: /event-log` | X1 |
| `track_pipeline_implementation_plan.md` | line 46: `app.core.utils.event_logger` becomes `app.management.utils.event_logger`; lines 1010 and 1250: `/api/v1/event-log` becomes `/api/v1/management/event-log`; sections 2.1 and 10.3: `POST /tracks` also creates a job and returns `job_id`; add one line at the top: "Jobs, WebSocket and management: `management_implementation_plan.md`" | X1, X7 |
| `get_expand_implementation_plan.md`, `get_expand_decisions.md` | path mapping in 5.3 | X1 |
| `test_scenarios_security_proposal.md` | AUTHZ-05: `event-log` becomes `management/event-log`; add the rows of 5.4 when that proposal is finalised | X1, X7 |
| `api_routes_structure_proposal.md` | lines 33 and 34 (the `event_log_api_router` finding) and line 175 (step M1 "remove the `event_log_api_router` line from `main.py`") are done by X1; lines 122 and 123 (`core/routes/__init__.py` "includes ref and event_log") become "includes ref"; add a row for the `management` module (flat files per resource: `jobs.py`, `admin_jobs.py`, `event_log.py`, `settings.py`, `celery.py`, `broadcast.py`, `ws.py`) | X1 |
| `management_app_and_job_tracking_proposal.md` | header: "Accepted. Implemented according to `management_implementation_plan.md`" | X1 |
| `README.md` | see X7.9 | X7 |

### 5.3 Path mapping for the `?expand=` plan (VS Code agent)

X1 moves files that plan edits. If that plan is **not merged yet**, do X1 first and read its paths through this table. If it is **in progress**, merge it first; X1 then moves the already-edited files (the moves are copy plus search and replace, so its changes travel along).

| `get_expand_implementation_plan.md` says | After X1 |
|---|---|
| `app/core/models/event_log.py`, class `CoreLogEvent` | `app/management/models/event_log.py`, class `MgmtLogEvent` |
| `app/core/schemas/event_log.py` | `app/management/schemas/event_log.py` |
| `app/core/routes/event_log.py` | `app/management/routes/event_log.py` |
| `app/core/utils/expand.py` (new there) | stays in `app/core/utils/` (shared by all modules) |
| `GET /event-log/{id}`, `/event-log/{id_1}/compare/{id_2}`, `/event-log?...` (also in its curl examples, smoke script `tests/smoke_expand.py` and README text) | `GET /management/event-log/{id}` and so on |
| `/event-log/entity-types` ("not in scope") | `/management/event-log/entity-types` (still not in scope) |
| `joinedload(CoreLogEvent.entity_type)` | `joinedload(MgmtLogEvent.entity_type)` |

### 5.4 Security tests to add (merge into the security test proposal when it is final)

| ID | Test | Expected |
|---|---|---|
| JOBS-01 | user B reads `GET /jobs/{id}` of user A | 404, identical to an unknown id |
| JOBS-02 | `GET /jobs` as user A | only A's jobs; system jobs (no owner) are not listed |
| JOBS-03 | editor, viewer and guest call every `/management/*` endpoint (jobs, event-log, settings, broadcast, celery) | 403 for all three groups |
| JOBS-04 | any REST endpoint of this plan without a token | 401 |
| WS-01 | ticket: used twice, expired, made up, missing | 4401 for each (missing: rejected) |
| WS-02 | `POST /ws/ticket` with a revoked token, and as a deactivated user | 401, and 403 |
| WS-03 | general socket of user B while a job of user A runs | B receives nothing of A |
| WS-04 | dedicated socket for a job of another user, and for a random id | 4404 for both |
| WS-05 | logout while a socket is open; deactivate a user while their socket is open | 4401 after a `control` message; 4403 after a `control` message |
| WS-06 | sixth socket of one user; maximum lifetime; client message larger than 1 KB | 4429; 4408; 1009 |
| WS-07 | token rotation (7 minutes of normal requests) while a socket is open | socket stays open |
| WS-08 | `POST /management/broadcast` as non-admin; with empty text; with `expires_at` in the past | 403; 422; 422 |
| SET-01 | `PATCH /management/settings/{key}`: unknown key; out of range; wrong type (float for int, bool for int); extra field | 404; 422; 422; 422 |
| SET-02 | every successful change | one `updated` entry (old and new value) in `mgmt_log_event` |
| CEL-01 | all Celery answers as administrator | no `args` or `kwargs` keys anywhere; with the worker stopped: 200 and `state: no_workers`, never 500 |
| MOVE-01 | `GET /event-log` | 404 (moved); history before the move is still readable under `/management/event-log` |

---

## 6. Risks, assumptions to verify, troubleshooting, rollback

### 6.1 Things I could not run, and which check proves them

| Assumption | Proven by |
|---|---|
| `TrackedTask.before_start` runs after Celery pushed the request, so `self.request.job_id` can be set (Celery 5.4) | X3 demo run: `attempts = 1`, stage `working`, progress messages appear |
| Hard time limits or an OOM kill may skip `on_failure` | not asserted; recovered by the reapers (X6, X7 check 5) |
| `select(MgmtSettings.key, MgmtSettings.value)` returns decoded JSON on both drivers (asyncpg and psycopg2) | X2: the sync one-liner prints `30 30`; X4 check 6 uses the async reader |
| `BaseHTTPMiddleware` lets WebSocket scopes pass | X4 check 2 |
| `ON CONFLICT DO NOTHING` without a target fires on `ux_mgmt_log_job_active_subject` | X3 unique-index check, X7 checks 3 to 5 |
| `inspect(destination=..., limit=...)` returns as soon as the named workers answered | X5: the uncached call with the worker running takes about 1 second, not 4 |
| `crontab.remaining_estimate(now)` works with an aware UTC datetime | X5 `beat` check (otherwise `next_run_at` is `null`, nothing breaks) |
| `websockets.InvalidStatus` exists in the installed version | X0 prints the version; only the script's message for a rejected handshake depends on it |

### 6.2 Troubleshooting

| Symptom | Likely cause |
|---|---|
| Jobs stay `queued` after an upload; the track still gets processed | The worker image is old (no rebuild). `sudo docker compose up -d --build celery-worker` |
| Worker exits at start with `ImportError` about `app.management` | Same: the worker has no bind mount; rebuild |
| API start fails with "relation mgmt_... does not exist" or creates empty tables | Code deployed before the DDL. Stop both, run the script (X1: see the "Both ... exist" note), start again |
| `PATCH` on a setting works but the event log has no entry | `seed_entity_types` / `load_entity_type_cache` did not register `mgmt_settings` before the request (check the lifespan order in X2.3) |
| WebSocket closes at once with 4401 | Ticket reused, expired, or created by a different Redis (check `REDIS_URL` of the api container) |
| WebSocket fine in tests, closed after about 60 s in production | A reverse proxy read timeout; raise it above 60 s and pass `Upgrade` and `Connection` headers. Use `wss://` |
| No `job.progress` messages | `jobs.progress_min_interval_ms` too high, or the task never calls `report_progress` (only the demo task does) |

### 6.3 Rollback

- X1: stop both containers, restore the old code, run the inverse renames (I write the script on request), start. The X0 dump is the safety net.
- X2, X3: revert the code; `DROP TABLE mgmt_settings;` and `DROP TABLE mgmt_log_job;` remove the tables (jobs are history only; nothing else depends on them).
- X4, X5, X6: revert the code; no data is involved.
- X7: revert the changed files. Jobs already created stay as history; leftover active jobs fail by themselves after `jobs.stale_after_hours`.

### 6.4 Known limits (by decision)

- Broadcast messages are not stored: a user who is offline at that moment never sees them.
- A logout closes **all** sockets of that user (they reconnect; a device with a revoked token cannot).
- The event log is also an audit trail; the default of 30 days removes older `created` snapshots and makes `compare` fail for older entries. `events.retention_days = 0` keeps everything.
- Chain tasks (`tracks.detect_pois`) show in the Celery live list without a job (their task id is not the job id).
- A WebSocket ticket is created by an active user, but `is_active` is not re-checked when the socket connects (at most the 30 second ticket lifetime). Deactivation closes open sockets through the control message.
- An archived pending track whose queued task runs closes its job as `succeeded` with `result.reason = "archived"` (nothing to do); `restore` then creates a new job.
- Not in v1: push messages for a closed app, cancel endpoint, Celery actions (revoke, purge, pool control), GPX constants as runtime settings.

---

## 7. Final verification and summary

### 7.1 End-to-end run after X7 (you run, paste the results)

1. Open a general socket (`ws_check.py`), upload a valid GPX: see `queued`, `running`/`parsing`, `saving`, `detecting_pois`, `succeeded` with counts; `Location` header and `job_id` in the 202.
2. Upload a broken GPX: track and job both `failed` with the same text.
3. Reprocess it: new job id, old job kept.
4. Change `jobs.retention_days` through the API, wait 31 seconds, run `mgmt.cleanup_retention` by hand.
5. `GET /management/celery/status` shows `ok`; stop the worker and see `no_workers`; start it again.
6. Log out on the socket's token: `control` message and close code 4401.
7. `pytest` is green; `\dt mgmt_*` shows `mgmt_log_event`, `mgmt_ref_entity_type`, `mgmt_settings`, `mgmt_log_job`; no `core_log_event` remains.

### 7.2 Milestone summary

| M | Size | You run | Needs your pasted output |
|---|---|---|---|
| X0 | XS | 9 read-only commands, one dump | yes |
| X1 | M | DDL, deploy, 8 checks | yes |
| X2 | M | DDL, deploy, about 15 checks, pytest | yes |
| X3 | L | DDL, deploy, demo job with Redis monitor, pytest | yes |
| X4 | L | deploy, 13 checks (two terminals) | yes |
| X5 | M | deploy, checks with the worker stopped and running | yes |
| X6 | S | deploy, retention and reaper checks | yes |
| X7 | L | deploy, 11 checks including reaper simulation (waiting about 7 minutes in check 4) | yes |

Nothing is built before you say "start X0".
