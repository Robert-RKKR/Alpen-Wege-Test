# Management app, job tracking, settings and Celery API - proposal v2

Date: 2026-10-23. Status: proposal, no code written. Supersedes `job_tracking_websocket_proposal.md` (v1). Decisions are in section 13.

## 0. What changed since v1

You confirmed the v1 decisions (own job id in Postgres, general and dedicated channel, Pub/Sub plus snapshot, only user-started work is a job, GPX job covers POI detection, progress in Redis only, 30 days retention, postpone push and cancel). You added:

1. A new app **`management`** (like `core`) that holds `mgmt_log_job`, `mgmt_log_event` (moved from `core_log_event`) and a new `mgmt_settings` table with global application settings.
2. An **API for Celery**: information about tasks and about the state of Celery itself.
3. Retention for **events** next to jobs, both as global settings.
4. A question about the WebSocket: one connection with a general channel for all and a dedicated channel per user.

**Correction to v1:** I wrote that Pub/Sub should use a separate Redis database number (`/3`). That does nothing: Redis Pub/Sub ignores database numbers. Isolation is done by a **channel prefix** (`aw:`), and `REDIS_URL` (db 2) is used as it is.

## 1. The new app `management`

Naming follows the existing pattern (`asset_` tables live in `app/assets`, `core_` in `app/core`): folder `app/management`, table prefix `mgmt_`, module key `mgmt` (the seed derives the module from the prefix before the first underscore), API prefix `/api/v1/management`.

```
app/management/
  models/      job.py  event_log.py  entity_type.py  settings.py
  schemas/     job.py  event_log.py  entity_type.py  settings.py  celery.py  ws.py
  routes/      jobs.py  event_log.py  settings.py  celery.py  broadcast.py  ws.py
  jobs/        service.py  events.py  tracked_task.py        (create_job, publish, TrackedTask)
  settings/    registry.py  service.py                       (known keys, get_setting)
  utils/       event_logger.py                               (moved from core/utils)
```

(If the routes-layout proposal in `api_routes_structure_proposal.md` is decided differently, the route files follow that layout. The rest does not depend on it.)

### 1.1 What moves from `core` to `management`

| Today | After | Note |
|---|---|---|
| `core_log_event` / `CoreLogEvent` | `mgmt_log_event` / `MgmtLogEvent` | **renamed in place**, no data copy, `seq` continues |
| `core_ref_entity_type` / `CoreRefEntityType` | `mgmt_ref_entity_type` / `MgmtRefEntityType` | the event log depends on it (FK `entity_type_id`), decision D3 |
| `app/core/utils/event_logger.py` | `app/management/utils/event_logger.py` | imported by about 12 files (compendium routes: card, country, poi, poi_region, post, region; explorer `gear`; profile `admin`, `access_policy`, `me`; core `ref`; `main.py`) |
| `app/core/routes/event_log.py` | `app/management/routes/event_log.py` | path `/event-log` becomes `/management/event-log` (decision D4) |
| `app/core/schemas/event_log.py` | `app/management/schemas/event_log.py` | |
| `app/core/utils/seed_entity_types.py` | `app/management/utils/seed_entity_types.py` | `NONE_TABLES` updated (see below) |

Stays in `core`: all `core_ref_*` lookup tables including `core_ref_resource_type` (access policy), `responses.py`, `base.py`, geo and pagination schemas.

### 1.2 Things that are easy to miss in the move

1. **`create_all` does not rename.** On startup `Base.metadata.create_all` would create an empty `mgmt_log_event` and leave the old table (and all history) orphaned. So the `ALTER TABLE ... RENAME` runs **first**, then the code is copied (same rule as in the GPX plan: the api container bind-mounts the repo with `--reload`).
2. **Constraint, index and sequence names keep the old names** after a rename (`core_log_event_pkey`, `ix_core_log_event_*`, the identity sequence of `seq`). They work, but should be renamed for a clean schema. Exact statements need your `\d` output (milestone X0).
3. **`seed_entity_types` registers every table automatically with `tracking_mode = 'all'`** unless it is in `NONE_TABLES`. After the move: `NONE_TABLES` must contain `mgmt_log_event`, `mgmt_log_job`, `mgmt_ref_entity_type` (the worker writes jobs; logging changes of the log itself makes no sense). `mgmt_settings` stays **tracked**, so every setting change can be written to the event log. The old rows `core_log_event` and `core_ref_entity_type` in the entity type table must be **renamed** by the same DDL (key and module), otherwise a stale row stays and a new row appears. While there: the existing typo `profile_usr_credentials` in `NONE_TABLES` (real table `profile_user_credentials`) should be fixed in the same edit.
4. `app/database.py` needs `import app.management.models`, and `app/core/models/__init__.py` loses two entries.
5. `designe/explorer_track_flow.svg`, `README.md`, the GPX plan v3 (6 mentions), `get_expand_implementation_plan.md` (13 mentions) and the security test proposal mention the old names or import path. They are updated after your answers.
6. **Coordination:** the move touches about 12 route files. If another session (for example the VS Code work on `?expand=`) edits routes at the same time, do the move when those changes are merged.

## 2. Tables

### 2.1 `mgmt_log_job` (was `core_log_job` in v1, plus three columns)

| Column | Type | Meaning |
|---|---|---|
| `id` | uuid PK | job id = Celery `task_id` |
| `user_id` | uuid FK `profile_usr_user`, **NULL allowed** | owner. NULL = system or admin-script job (visible only through the management API), decision D7 |
| `kind` | varchar(64) NOT NULL | `track.process`, `poi.rescan`, `card.rescan`, later `export.gpx` ... |
| `task_name` | varchar(128) NOT NULL | Celery task name of the first task, for example `tracks.process_gpx` |
| `status` | varchar(16) NOT NULL | `queued`, `running`, `succeeded`, `failed`, `cancelled` (CHECK) |
| `stage` | varchar(64) NULL | machine name of the current step |
| `progress` | smallint NULL | 0 to 100, written at status changes only |
| `subject_type`, `subject_id` | varchar(64), uuid NULL | what it is about, for example `track` and the track id |
| `result` | jsonb NULL | small summary for the client. Never large data |
| `error_message` | text NULL | safe text for the user. Technical details only in the worker log |
| `attempts` | smallint NOT NULL DEFAULT 0 | number of starts |
| `worker_hostname` | varchar(128) NULL | which worker ran it (admin view) |
| `request_id` | text NULL | the HTTP request id that started it, the same value as `mgmt_log_event.request_id` and `X-Request-ID`, so a job can be matched with the object changes of the same request |
| `created_at`, `started_at`, `finished_at`, `updated_at` | timestamptz | `updated_at` with the same `moddatetime` trigger as the other tables |

Indexes: `(user_id, created_at desc)`, `(subject_type, subject_id)`, `(finished_at)` for retention, partial index on `status IN ('queued','running')`.

The relation to the GPX plan is unchanged: `explorer_agg_track.processing_status` stays (reaper, atomic claim). The job is the generic user-facing view of the same work, both are updated in one transaction, and the track state wins if they ever disagree.

### 2.2 `mgmt_log_event`

The existing `core_log_event` table, same columns. Only name, class name and location change.

### 2.3 `mgmt_settings` (global application settings)

Short version: the **allowed keys, types, ranges and defaults live in code** (a registry); the **values live in the table** and can be changed by an administrator without a deployment.

| Column | Type | Meaning |
|---|---|---|
| `id` | uuid PK | project standard |
| `key` | varchar(128) UNIQUE NOT NULL | for example `jobs.retention_days` |
| `value` | jsonb NOT NULL | current value |
| `value_type` | varchar(16) NOT NULL | `int`, `float`, `bool`, `string` (CHECK) |
| `default_value` | jsonb NOT NULL | from the registry, used by "reset" |
| `min_value`, `max_value` | numeric NULL | range for numbers |
| `category` | varchar(32) NOT NULL | `jobs`, `events`, `ws`, `celery` (grouping in the UI) |
| `description` | text NOT NULL | one sentence for the admin screen |
| `requires_restart` | boolean NOT NULL DEFAULT false | shown to the admin; the value only applies after a restart |
| `created_at`, `updated_at` | timestamptz | `moddatetime` trigger |
| `updated_by` | uuid FK user NULL | last editor |

How it works:

- A registry in code (`SettingDef(key, type, default, min, max, category, description, requires_restart)`) lists every key. On startup a seed (same idea as `seed_entity_types`) inserts **missing keys with the default**, and refreshes type, range, description and default of existing keys. It **never overwrites `value`**.
- `PATCH /management/settings/{key}` accepts only keys that exist and validates type and range (422 otherwise). New keys cannot be created through the API, so typos cannot create junk. Adding a setting later = one line in the registry, no migration.
- Every change calls `log_updated`, so who changed which setting and when is in `mgmt_log_event` (the table is tracked, see 1.2).
- Reading: `get_setting(key)` (async for the API, synchronous for Celery workers) with an in-process cache of **30 seconds**. A change applies in the API process that received it immediately, in the others and in the worker within 30 seconds. If the table cannot be read, the registry default is used.
- **Infrastructure stays in `.env`**: database and Redis URLs, Celery URLs, `JWT_SECRET_KEY`, algorithm and expiry. Secrets never go into this table.

Settings in v1:

| Key | Default | Meaning |
|---|---|---|
| `jobs.retention_days` | 30 | delete finished jobs older than this; **0 = keep forever** |
| `events.retention_days` | 30 | delete event log entries older than this; **0 = keep forever** |
| `jobs.progress_min_interval_ms` | 1000 | minimum time between progress messages of one job |
| `jobs.recent_finished_minutes` | 10 | finished jobs included in the `sync` message |
| `ws.ticket_ttl_s` | 30 | lifetime of the one-time ticket |
| `ws.max_connections_per_user` | 5 | open sockets per user |
| `ws.max_lifetime_s` | 3600 | a socket is closed after this time, the client reconnects |
| `ws.ping_interval_s` / `ws.pong_timeout_s` | 25 / 10 | keep-alive |
| `ws.token_check_interval_s` | 60 | how often the server re-checks that the login is still valid |
| `celery.status_cache_s` | 5 | cache of the Celery status calls (section 6) |

WebSocket limits apply to **new** connections. Later candidates (not now): the GPX constants of plan v3 (upload size, reaper minutes, stuck attempts). They can be added as registry lines when you want them.

**A note on events:** the event log is also your audit trail ("who changed what"). With 30 days, the `created` snapshots disappear, and `compare` no longer works for older entries. You decided 30, so 30 is the default. Because it is a setting (0 = forever) you can change it at any time without code.

## 3. Message flow (as in v1)

```
Client --POST /tracks--> API
   API: INSERT track + INSERT mgmt_log_job (queued) -> COMMIT -> send_task(task_id = job.id)
   <-- 202 {id, ..., job_id}   Location: /api/v1/jobs/{job_id}

Worker (TrackedTask base class)
   before_start -> job running   -> UPDATE -> COMMIT -> publish
   report_progress(40, "detecting_pois") -> publish only, rate limited
   on_success   -> job succeeded -> UPDATE -> COMMIT -> publish
   on_failure   -> job failed    -> UPDATE -> COMMIT -> publish
```

Rules: Postgres is the truth and the WebSocket is a hint; commit first, publish second; terminal states are final; only user-started work is a job (beat tasks and the debounced statistics recompute are not).

Worker side: `TrackedTask` (`before_start`, `on_success`, `on_failure`, `on_retry`) as in v1, with `close_job_on_success = False` for the first task of a chain. The worker uses a small **synchronous** Redis helper (`app/redis.py` has only an async client). `publish_job_event` is the only function that knows about Redis, so a push sink can be added there later.

## 4. WebSocket: one connection, three levels

Your question was whether one connection can carry a **general channel for all** and a **dedicated channel per user**. Yes, and I propose exactly that, on **one socket per client**:

| Channel | Who receives it | What is sent | Who publishes |
|---|---|---|---|
| `aw:all` | every connected user | `system.notice` (maintenance, announcements) | administrator, `POST /management/broadcast` |
| `aw:user:{user_id}` | all sockets of that user | `job.update` for all my jobs, later `notification` | the worker |
| `aw:job:{job_id}` | the owner, on the dedicated URL only | `job.update` of one job | the worker |

- `/api/v1/ws?ticket=...` is the normal connection. The server **subscribes it automatically** to `aw:all` and `aw:user:{id}`. The user id comes from the ticket, never from the client.
- `/api/v1/ws/jobs/{job_id}?ticket=...` is the optional dedicated one for a screen that watches exactly one job. It checks that the job belongs to the user (4404 otherwise), sends the job, and closes when the job is finished.
- The worker publishes each job event to `aw:user:{id}` **and** `aw:job:{id}`. The mobile app normally uses only the first URL.
- Broadcast messages are not stored in v1. A user who is offline at that moment does not get them. The administrator publishes with `POST /management/broadcast` `{level: info|warning|critical, text, expires_at?}`.

Everything else from v1 stays: login by **one-time ticket** (`POST /api/v1/ws/ticket`, random, single use through `GETDEL`, bound to user id and token id), first message `sync`, ping every 25 s, hard lifetime 1 hour, logout detected through the token blacklist every 60 s, max 5 sockets per user, 1 KB message limit, same answer for "not yours" and "not found". The limits now come from `mgmt_settings` (section 2.3).

Messages:

```json
{"type":"sync","jobs":[{job}],"server_time":"..."}
{"type":"job.update","job":{"id":"...","kind":"track.process","status":"running","stage":"detecting_pois","progress":70,"subject":{"type":"track","id":"..."},"result":null,"error_message":null,"updated_at":"..."}}
{"type":"system.notice","level":"warning","text":"Maintenance in 10 minutes","expires_at":"..."}
{"type":"ping","t":1790000000}
```

Client rule: on every (re)connect wait for `sync`, replace the local state, then apply updates. Terminal job states are never overwritten. Production needs `wss://` and a reverse proxy that passes `Upgrade`/`Connection` and has a read timeout above 60 s.

## 5. REST API

### 5.1 For every user (own jobs)

| Method and path | Purpose |
|---|---|
| `GET /api/v1/jobs` | my jobs, newest first. Filters: `status`, `kind`, `subject_type`, `subject_id`, `active=true`, `limit`, `offset` |
| `GET /api/v1/jobs/{id}` | one job; 404 if it is not mine |
| `POST /api/v1/ws/ticket` | one-time WebSocket ticket |

Every route that starts work returns `job_id` in the 202 body and `Location: /api/v1/jobs/{job_id}`: `POST /tracks`, `/tracks/{id}/reprocess`, `/pois/{id}/rescan`, `/cards/{id}/rescan`.

### 5.2 Management (administrator only, `require_groups("administrator")`, like the current event log)

| Method and path | Purpose |
|---|---|
| `GET /management/jobs` | all jobs of all users. Filters as above plus `user_id`, `task_name`, `created_from`, `created_to` |
| `GET /management/jobs/{id}` | one job with owner, worker, attempts |
| `GET /management/jobs/stats` | counts per status and kind, failed in the last 24 h, average duration per kind, oldest queued job |
| `GET /management/event-log`, `/entity-types`, `/{id}`, `/{id_1}/compare/{id_2}` | the existing event log API, moved |
| `GET /management/settings` | all settings, grouped by category |
| `GET /management/settings/{key}` | one setting |
| `PATCH /management/settings/{key}` | change the value (validated, logged) |
| `POST /management/settings/{key}/reset` | back to the default |
| `POST /management/broadcast` | publish a `system.notice` to all connected users |
| `GET /management/celery/...` | the Celery API, section 6 |

## 6. Celery API (read-only in v1)

Celery can be asked through `celery_app.control.inspect(timeout=1.0)` (ping, stats, active, reserved, scheduled, registered, active_queues) and through the result backend (`AsyncResult`). These calls are broadcast requests that **wait up to the timeout** and return nothing when no worker answers. So: they run in a threadpool (not in the event loop), the answers are cached for `celery.status_cache_s` seconds, and "no worker online" is a normal, clearly reported state, not a 500.

| Path | Content |
|---|---|
| `GET /management/celery/status` | **the one-glance health view**: broker reachable, result backend reachable, workers online (count and names), queue length of the default queue (`LLEN` on the broker database), counts of active / reserved / scheduled tasks, number of beat entries, `checked_at` |
| `GET /management/celery/workers` | per worker: hostname, pid, uptime, concurrency, queues it consumes, total tasks executed per task name, number of registered tasks |
| `GET /management/celery/tasks/registered` | registered task names; each marked tracked (job `kind`) or untracked |
| `GET /management/celery/tasks/active` | active, reserved and scheduled tasks: task id, task name, worker, start time, ETA. If the task id is a job id the matching job (`kind`, owner, subject) is joined in |
| `GET /management/celery/tasks/{task_id}` | Celery state (`PENDING`, `STARTED`, `SUCCESS`, `FAILURE`, `RETRY`, `REVOKED`) and, for failures, the exception text and traceback, plus the job row. Note: Celery removes results after one day (`result_expires`), the job row stays for the retention period |
| `GET /management/celery/beat` | the periodic schedule from `beat_schedule`: name, task, schedule text, and the next run time computed from the schedule |

Deliberate limits:

- **No task arguments, keyword arguments or results** in these answers (they can contain ids and user data). Only the job `result` summary is visible.
- Read-only. No revoke, purge, shutdown or pool control in v1 (decision D6). Cancel stays in the postponed list.
- Why not Flower? Flower is a ready dashboard, but it is a separate service with its own login, it does not know your users, jobs or access rules, and it would need its own protection. This API reuses your admin check and the job table.

## 7. Retention

A beat task `mgmt.cleanup_retention` runs daily (03:30, after the existing 03:00 cleanup). It reads `jobs.retention_days` and `events.retention_days` from `mgmt_settings`, and for each value greater than 0 deletes finished jobs (`finished_at`) or events (`changed_at`) older than that, in **batches of 5000** so it does not hold a long lock, and logs the counts. Running or queued jobs are never deleted. The task is not a job itself.

## 8. Security summary

- Management endpoints: administrator only. Own-scope jobs: `job.user_id = current user`; not mine and not found give the same 404.
- WebSocket: one-time ticket, user channel name from the server, limits, hard lifetime, blacklist check, no sensitive data in messages. `aw:all` carries only text that an administrator wrote.
- Celery API: no arguments or results, errors shown only to administrators.
- Settings: only registered keys, validated, every change in the event log; no secrets in the table.
- The new resource keys (`jobs`, `mgmt_jobs`, `mgmt_settings`, `mgmt_celery`, `mgmt_event_log`, `ws`) go into the security test proposal.

## 9. How the GPX plan changes

1. Event logging import path: `app.core.utils.event_logger` becomes `app.management.utils.event_logger` (plan v3 sections 10.3 and others).
2. `POST /tracks`: insert the job in the same transaction (`kind=track.process`, `task_name=tracks.process_gpx`, `subject_type=track`, `subject_id`, `request_id`), `send_task(..., task_id=str(job.id))`, return `job_id` and `Location`.
3. `tracks.process_gpx` and `tracks.detect_pois` use `TrackedTask`. One job for the whole chain; `process_gpx` has `close_job_on_success = False`; `detect_pois` closes it with `{"pois_found": n, "cards_found": m}`. Stages: `queued, parsing, saving, detecting_pois, done`.
4. Reaper: re-enqueue with the same job id and set the job back to `queued`; a permanent failure fails the job too. `/reprocess` creates a **new** job.
5. `TrackCreated` gets `job_id`.

## 10. Milestones (each small, each with a check you run)

| M | Content | Check |
|---|---|---|
| X0 | Pre-flight: you paste `\d core_log_event`, `\d core_ref_entity_type`, `SELECT count(*), max(seq) FROM core_log_event;`, `SELECT key, module, tracking_mode FROM core_ref_entity_type WHERE key IN ('core_log_event','core_ref_entity_type');` | I write the exact DDL |
| X1 | **Move**: DDL rename (tables, indexes, constraints, identity sequence, entity type rows), then code move, import path changes, router path, `NONE_TABLES`, docs | row count and max `seq` unchanged; a gear update creates a new entry with the next `seq` and the right `request_id`; `/management/event-log` works; no duplicate or stale entity type rows; app starts without creating an empty table |
| X2 | `mgmt_settings`: model, registry, seed, `get_setting` (async and sync), cache, routes, event log for changes | 422 out of range, 404 unknown key, 403 non-admin, change visible in the event log, value change effective within 30 s |
| X3 | `mgmt_log_job`, `/jobs`, `/management/jobs`, `TrackedTask`, publisher, demo task (sleeps and reports progress), `include=[...]` fix for task registration | demo job goes queued, running, succeeded; progress rate limited; failure sets `failed` with a safe message |
| X4 | WebSocket: ticket, general socket with `aw:all` and `aw:user`, dedicated socket, `sync`, limits from settings, broadcast endpoint | tests in section 11 |
| X5 | Celery API (read-only) | status with no worker running, with worker, `active` shows the demo job |
| X6 | `mgmt.cleanup_retention` | retention 0 deletes nothing; 1 day deletes old rows in batches |
| X7 | Plug into the GPX plan (section 9) and update plan v3 and the other documents | GPX end-to-end test |

X1 and X2 come before the GPX milestones that write events (the import path changes); X3 and later can run in parallel with the GPX plan once its Celery registration milestone is done.

## 11. Tests (added to the security test list)

- **Move:** old entries still readable after the rename, `seq` continues, new events written, `compare` still works, seed makes no duplicates, orphan table check.
- **Settings:** admin only; type and range validation; reset; unknown key; change is logged; cache behaviour; table unreadable gives defaults.
- **Jobs and WebSocket:** all v1 tests (ticket once, expired, no bearer; isolation between users on REST and sockets; logout closes the socket within 60 s; 6th socket refused; reconnect after finish gives final state in `sync`; terminal state not overwritten; worker kill and reaper) plus: broadcast reaches all connected users and no one else; a user never receives another user's `aw:user` message; the dedicated socket closes after the final state.
- **Celery API:** 403 for editor and viewer; no worker gives a clear "no workers online"; no arguments or results in any answer; results older than one day return the job row only.
- **Retention:** 0 keeps everything; running and queued jobs never deleted; batch deletion on a large table.
- **Middleware:** a WebSocket request passes `RequestIdMiddleware` and `TokenRefreshMiddleware`.

## 12. Findings in the repo that matter

1. `celery_app.py` has no task time limit, no `task_acks_late` and no `worker_prefetch_multiplier`. A hanging task keeps a job `running`. A global `task_time_limit` / `task_soft_time_limit` belongs in `.env`/`config.py` (they are worker start-up options, so not in `mgmt_settings`).
2. `autodiscover_tasks(["app.worker.tasks"])` registers nothing (known); fix with `include=[...]` in X3 or the GPX Celery milestone, whichever comes first. It makes the existing beat jobs run for the first time.
3. The worker container runs `celery ... worker --beat` (beat embedded in the worker). If that container stops, beat stops too. The status endpoint will show beat entries but cannot tell whether beat is alive; fine for now.
4. `seed_entity_types` treats every new table as tracked unless listed in `NONE_TABLES` (see 1.2).
5. `JWT_EXPIRE_MINUTES` is 5 in `.env` but 999 in `config.py`; the ticket design does not depend on it. `/auth/refresh` does not revoke the old token (finding F6), so the 1 hour socket lifetime limits that.
6. `app/redis.py` has only an async client; the worker needs a synchronous helper.

## 13. Decisions (answer briefly; "accept all" is allowed)

**D1. One socket with broadcast plus user channel (my reading of your question).** I understood: one connection per client that carries a channel for all users and a channel for the user, with the per-job socket kept as an option. Options: (a) as in section 4 (recommended); (b) only per-user channel, no broadcast; (c) subscribe to jobs by message over the one socket instead of a second URL (more protocol, one URL less). **Recommendation: (a).** Please tell me if you meant something different.

**D2. Names.** Folder `app/management`, table prefix `mgmt_`, module key `mgmt`, API prefix `/api/v1/management`. Alternative: `/mgmt`. **Recommendation: as written** (the folder and the API path use the full word, the table prefix is short).

**D3. Move `core_ref_entity_type` too (to `mgmt_ref_entity_type`).** It exists only for the event log (FK from the log). Options: (a) move it (recommended); (b) leave it in core. **Recommendation: (a)** so the whole log lives in one place.

**D4. Move by rename, and the event-log path becomes `/management/event-log`.** Rename keeps all history and `seq`. The path change breaks any client that calls `/event-log`; the plan says there is no frontend yet. Options: (a) new path only (recommended); (b) keep `/event-log` as a second route for a while. **Recommendation: (a).**

**D5. Settings design.** Keys, types and ranges fixed in code; values in `mgmt_settings`; 30 s cache; infrastructure and secrets stay in `.env`; changes written to the event log; `0 = keep forever` for both retention values (default 30, as you decided). **Recommendation: yes.**

**D6. Celery API is read-only in v1, administrator only, without task arguments and results.** Revoke, purge and pool control come later together with cancel. **Recommendation: yes.**

**D7. `user_id` of a job may be NULL (system or admin-script job), and administrators get `/management/jobs` for all users.** Needed for `scripts/reprocess_tracks.py`. **Recommendation: yes.**

**D8. Broadcast (`POST /management/broadcast` plus `aw:all`) in v1, not stored for offline users.** It is small once the socket exists. Options: (a) include now (recommended); (b) later. **Recommendation: (a).**

Order of work: **X0 first** (you paste the four outputs), then X1 to X7 as in section 10. Nothing is built before your answers.
