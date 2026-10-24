# Job tracking and WebSocket notifications - proposal v1

Date: 2026-10-23. Status: **SUPERSEDED by `management_app_and_job_tracking_proposal.md` (v2)**. Kept only as a record of the v1 decisions. Do not use this file for implementation.

## 1. What you asked for (my reading)

You want one general way to follow **any** Celery task that a user starts (GPX processing now, other work later):

- Every started task gives the client a **job id** (UUID).
- The client can follow progress over **WebSocket**.
- Two kinds of channel: one **general** channel (all my jobs and later other notifications) and one **dedicated** channel per job.

This also replaces my earlier answer. For one GPX task the track `id` was enough. For many task types a stable job id of our own is the right tool. It is **not** the raw Celery id. We generate the UUID ourselves, store it in Postgres, and give the same value to Celery as `task_id`. So there is one id everywhere, and it stays the same when the reaper or `/reprocess` enqueues the work again.

## 2. Design in one picture

```
Client --POST /tracks--> API
   API: INSERT track + INSERT job (queued) -> COMMIT -> send_task(task_id = job.id)
   <-- 202 {id, ..., job_id}   Location: /api/v1/jobs/{job_id}

Worker (TrackedTask base class)
   before_start  -> job running   -> DB update -> COMMIT -> publish
   job.progress(40, "detecting_pois") -> publish only (no DB write, max 1 per second)
   on_success    -> job succeeded -> DB update -> COMMIT -> publish
   on_failure    -> job failed    -> DB update -> COMMIT -> publish

Redis Pub/Sub:  ws:user:{user_id}      (general)
                ws:job:{job_id}        (dedicated)

Client <--WebSocket-- API   /api/v1/ws                 general: all my jobs
Client <--WebSocket-- API   /api/v1/ws/jobs/{job_id}   dedicated: one job, closes when finished
```

Rules that make it robust:

1. **Postgres is the truth, WebSocket is only a hint.** Redis Pub/Sub does not store messages. If the client was offline, it misses events. So every connection starts with a snapshot from the database, and `GET /jobs/{id}` always works.
2. **Commit first, publish second.** The worker publishes only after the database commit, so a client that reacts to an event and calls the API always sees the new state.
3. **Terminal states are final.** `succeeded`, `failed`, `cancelled` are never overwritten by a late progress message. The client ignores anything after them.
4. **Not every Celery task is a job.** Only work a user started and wants to follow. Beat jobs, the debounced statistics recompute and internal retries are not jobs.

## 3. The job record

New table `core_log_job` (naming follows `core_log_event`: module, kind, name). Hand-written DDL first, then the model, as in the other milestones.

| Column | Type | Meaning |
|---|---|---|
| `id` | uuid PK | job id = Celery `task_id` |
| `user_id` | uuid FK `profile_usr_user` NOT NULL | owner; only the owner can see it |
| `kind` | varchar(64) NOT NULL | `track.process`, `poi.rescan`, `card.rescan`, later `export.gpx` ... |
| `status` | varchar(16) NOT NULL | `queued`, `running`, `succeeded`, `failed`, `cancelled` (CHECK) |
| `stage` | varchar(64) NULL | short machine name of the current step, for example `parsing`, `detecting_pois` |
| `progress` | smallint NULL | 0 to 100, last known value written at status changes only |
| `subject_type` | varchar(64) NULL | what the job is about, for example `track` |
| `subject_id` | uuid NULL | for example the track id |
| `result` | jsonb NULL | small summary for the client (counts, ids). Never large data |
| `error_message` | text NULL | safe text for the user. Technical details only in the worker log |
| `attempts` | smallint NOT NULL DEFAULT 0 | how many times it started |
| `created_at`, `started_at`, `finished_at` | timestamptz | |
| `updated_at` | timestamptz | with the same `moddatetime` trigger as the other tables |

Indexes: `(user_id, created_at desc)`, `(subject_type, subject_id)`, partial index on `status IN ('queued','running')` for the reaper and the "active jobs" snapshot.

Relation to the GPX plan: `explorer_agg_track.processing_status` **stays** (the reaper and the atomic claim depend on it, and it is the domain state). The job is the generic, user-facing view of the same work. The worker updates both in the same transaction. If they ever disagree, the track state wins and the reaper fixes the job.

## 4. Worker side

One base class, so a task becomes trackable with one line and no copy-paste:

```python
# app/core/jobs/tracked_task.py (sketch)
class TrackedTask(celery_app.Task):
    close_job_on_success = True          # a chain sets this to False on all but the last task

    def before_start(self, task_id, args, kwargs):   # Celery >= 5.2, we have >= 5.4
        mark_running(job_id=task_id)                 # DB update, commit, publish

    def on_success(self, retval, task_id, args, kwargs):
        if self.close_job_on_success:
            mark_succeeded(task_id, result=retval)   # retval must be a small dict

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        mark_failed(task_id, safe_message_for(exc))  # no stack trace to the client

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        mark_queued_again(task_id)

@celery_app.task(base=TrackedTask, bind=True, name="tracks.process_gpx")
def process_gpx(self, track_id): 
    report_progress(self, 30, "parsing")             # publish only
    ...
```

- The API creates the job row **before** `send_task` and passes `task_id=str(job.id)`. The task needs no `job_id` argument.
- `report_progress` publishes through a **synchronous** Redis client (the worker is synchronous) and drops messages that come faster than once per second.
- The worker never raises because of a notification problem. A failed publish is logged and ignored (the DB state is already correct).
- A single `publish_job_event(job)` function is the only place that knows about Redis. Later a push sink (FCM/APNs for a closed app) or e-mail can be added there without touching tasks.

## 5. REST endpoints

| Method and path | Purpose |
|---|---|
| `GET /api/v1/jobs` | my jobs, newest first. Filters: `status`, `kind`, `subject_type`, `subject_id`, `limit`, `offset`. Also `?active=true` for queued and running |
| `GET /api/v1/jobs/{id}` | one job. 404 if it is not mine (same answer as "does not exist", so ids cannot be probed) |
| `POST /api/v1/ws/ticket` | returns a one-time ticket for the WebSocket (section 7) |

Later, not in v1: `POST /jobs/{id}/cancel` (revoke while queued, cooperative stop while running).

Every route that starts work returns `job_id` in its 202 body and a `Location: /api/v1/jobs/{job_id}` header: `POST /tracks`, `POST /tracks/{id}/reprocess`, `POST /pois/{id}/rescan`, `POST /cards/{id}/rescan`. The GPX body becomes `id, name, processing_status, created_at, duplicate_of_track_id, job_id`.

## 6. Message format (WebSocket, JSON, server to client)

```json
{"type":"sync","jobs":[ {job}, {job} ],"server_time":"2026-10-23T08:13:26Z"}
{"type":"job.update","job":{ "id":"...","kind":"track.process","status":"running",
   "stage":"detecting_pois","progress":70,
   "subject":{"type":"track","id":"..."},
   "result":null,"error_message":null,"updated_at":"..." }}
{"type":"ping","t":1790000000}
```

- `sync` is the first message after connecting. General socket: all queued and running jobs plus jobs finished in the last 10 minutes. Dedicated socket: the one job; if it is already finished the server sends it and closes with code 1000.
- `job.update` is the same object the REST API returns, so the client needs one parser.
- Later message types on the general socket (for example `notification` for "3 new POIs discovered") reuse the same channel. That is why the field is `type`.
- The client sends nothing except a `pong`. Anything else is ignored. No commands over the socket in v1.

## 7. WebSocket details

### 7.1 Endpoints

- General: `/api/v1/ws` subscribes to `ws:user:{user_id}`.
- Dedicated: `/api/v1/ws/jobs/{job_id}` subscribes to `ws:job:{job_id}`. The server first checks that the job belongs to the user (otherwise closes with 4404).
- The worker publishes each event to **both** channels. One mobile client should normally use only the general socket (one connection, less battery). The dedicated one is handy for an upload screen that wants exactly one job.

### 7.2 Authentication: one-time ticket (important)

Browsers cannot send an `Authorization` header on a WebSocket, and the access token here is rotated (`X-Access-Token`) and lives only minutes. Putting the token in the URL would leak it into logs. So:

1. Client calls `POST /api/v1/ws/ticket` with the normal bearer token (goes through `get_current_active_user`, so revoked tokens and deactivated users are refused).
2. Server creates 32 random bytes, stores `ws_ticket:{ticket}` in Redis with `{user_id, jti}` and a **30 second** expiry, returns it.
3. Client opens `/api/v1/ws?ticket=...`. Server reads and deletes it in one step (`GETDEL`), so it works **once**.

This also blocks cross-site WebSocket hijacking: another web page cannot call the ticket endpoint because it cannot set the bearer header.

### 7.3 Connection lifetime

- Server pings every 25 s and closes the socket if no pong arrives within 10 s.
- Every 60 s the server checks `is_token_blacklisted(jti)` (a Redis lookup). After logout the socket is closed with code 4401.
- Hard maximum lifetime **1 hour**, then close with 4408 "reconnect". The client asks for a new ticket, which re-checks that the user is still active. This covers deactivated accounts without a database query every minute.
- Maximum **5 sockets per user** (Redis counter); the 6th is refused with 4429.
- Incoming messages larger than 1 KB close the socket.

### 7.4 No lost events (the reconnect rule)

The client rule is simple: **on every (re)connect, wait for `sync`, replace local state with it, then apply `job.update` messages.** The server avoids a gap by subscribing to Redis **first**, then reading the snapshot from the database, then forwarding queued events. A repeated or old event is harmless because terminal states are final.

### 7.5 Where it runs

- WebSocket support is already there (`uvicorn[standard]` installs `websockets`). The two `BaseHTTPMiddleware` classes (request id, token refresh) only handle HTTP and let WebSocket scopes pass, but this must be confirmed by a test (section 10).
- In production use `wss://`, and the reverse proxy needs `Upgrade`/`Connection` headers and a read timeout above 60 s.
- Redis: use a separate database number for Pub/Sub (for example `/3`), so it stays apart from broker (0), results (1) and the app (2).

## 8. Security summary

- A user only ever receives events of their own jobs. The channel name comes from the server (ticket user id), never from the client. The dedicated socket checks ownership.
- Ticket: random, 30 s, single use, bound to a user and token id.
- No sensitive data in messages: no file paths, no stack traces, no other users' ids. `result` holds only small summaries.
- Limits on connections, message size and lifetime (section 7.3).
- Same answer for "not yours" and "not found" (REST 404, socket close 4404).

## 9. How the GPX plan changes (small)

1. `POST /tracks` (plan 10.3, step 5): in the same transaction also insert the job (`kind=track.process`, `subject_type=track`, `subject_id=track.id`, `status=queued`). Step 6: `send_task("tracks.process_gpx", args=[track.id], task_id=str(job.id))`. Step 8: add `job_id` to the body and the `Location` header.
2. `tracks.process_gpx` and `tracks.detect_pois` use `TrackedTask`. The job covers the whole chain: `process_gpx` has `close_job_on_success = False` and hands over the same job id (as a normal argument) to `detect_pois`, which closes the job with `result = {"pois_found": n, "cards_found": m}`. Stages: `queued -> parsing -> saving -> detecting_pois -> done`.
3. Reaper (plan 9.3): when it re-enqueues a track it uses the **same** job id as `task_id` and sets the job back to `queued`; when it fails a track permanently it also fails the job. `/reprocess` creates a **new** job for the new attempt (history stays readable).
4. `TrackCreated` schema gets `job_id`.
5. Task name registration: the existing `autodiscover_tasks` finding stays (use `include=[...]`).

Nothing else in the plan changes. The statistics recompute stays a plain, untracked task.

## 10. Files, milestones, tests

New files:

| Path | Content |
|---|---|
| `app/core/models/job.py` | `CoreLogJob` |
| `app/core/schemas/job.py` | `JobRead`, `JobEvent`, `WsTicket` |
| `app/core/jobs/service.py` | `create_job`, `enqueue_job` (job row + `send_task`) |
| `app/core/jobs/events.py` | `publish_job_event` (sync for worker, async for API), channel names |
| `app/core/jobs/tracked_task.py` | `TrackedTask`, `report_progress` |
| `app/core/routes/jobs.py` | `GET /jobs`, `GET /jobs/{id}` |
| `app/core/routes/ws.py` | ticket endpoint, general and dedicated socket |
| `app/worker/tasks/cleanup.py` | add `cleanup_old_jobs` (delete finished jobs older than 30 days, daily beat) |
| `app/config.py` | `JOB_RETENTION_DAYS=30`, `WS_TICKET_TTL_S=30`, `WS_MAX_CONN_PER_USER=5`, `WS_MAX_LIFETIME_S=3600`, `REDIS_PUBSUB_URL` |

Milestones (each small, each with a check you run):

| M | Content |
|---|---|
| J1 | DDL + model + `GET /jobs`, `GET /jobs/{id}` + `create_job` |
| J2 | `TrackedTask` + publisher + a throw-away demo task (sleeps, reports progress) to prove the chain without GPX |
| J3 | WebSocket: ticket, general socket, dedicated socket, sync, ping, limits |
| J4 | Plug into the GPX plan (section 9) when plan M-milestones reach the API route |
| J5 | Retention cleanup, docs in README |

Tests (added to the security test list as a new resource key `jobs`):

- Ticket: works once, second use refused, expired refused, wrong user cannot reuse, no bearer token gives 401.
- Isolation: user B cannot read user A's job (404) and does not receive A's events on the general socket; dedicated socket for A's job closes with 4404 for B.
- Logout closes the socket within 60 s; deactivated user cannot get a ticket.
- Limits: 6th socket refused; oversized message closes the socket.
- Reconnect: finish a job while the client is disconnected, reconnect, `sync` contains the final state.
- Order: terminal state is not overwritten by a late progress event.
- Worker crash (`docker kill alpen-celery`): job returns to `queued`, then finishes after the reaper.
- Middleware: a WebSocket request passes `RequestIdMiddleware` and `TokenRefreshMiddleware` without error.
- Demo task: progress messages arrive in order and at most about one per second.

## 11. Findings in the current repo that matter here

1. `celery_app.py` has no task time limit, no `task_acks_late` and no `worker_prefetch_multiplier`. A task that hangs would keep a job `running` forever. A global `task_time_limit` (for example 10 minutes) and `task_soft_time_limit` should be added (the GPX plan already names a timeout; this makes it global).
2. `autodiscover_tasks(["app.worker.tasks"])` registers nothing (already in plan v3). The new `TrackedTask` tasks need the `include=[...]` fix first.
3. The access token lifetime is `5` in `.env` but `999` as the default in `config.py`. The ticket design does not depend on either.
4. `/auth/refresh` does not revoke the old token (finding F6 in the security proposal). A socket opened with an old token is therefore only closed on logout of **that** token. The 1 hour maximum lifetime limits this.
5. `app/redis.py` has only an async client. The worker needs a small synchronous Redis helper (the `redis` package already provides it).

## 12. Decisions (please answer; "accept all" is allowed)

**D1. Own job id in Postgres, used as Celery task_id.** Why: the id stays the same across retries, reaper and restarts, and the client can ask the API for the state at any time. Options: (a) own id (recommended), (b) raw Celery id without a table (state lost when Redis results expire, no history), (c) only track id for GPX and nothing generic. **Recommendation: (a).**

**D2. Channels: general and dedicated.** Options: (a) both, built on the same code (recommended); (b) general only, client filters by `job.id`; (c) dedicated only. **Recommendation: (a).** The dedicated socket costs about 20 extra lines and is useful for an upload screen. The mobile app normally uses only the general one.

**D3. WebSocket login by one-time ticket.** Options: (a) ticket (recommended), (b) token in the URL (simple, but leaks into logs and does not fit rotating tokens), (c) token as first message after connect (works, but the open socket exists before login). **Recommendation: (a).**

**D4. Event delivery: Redis Pub/Sub plus database snapshot on connect.** Options: (a) Pub/Sub + snapshot (recommended, simple, no replay needed), (b) Redis Streams with replay by last id (exact replay, more code and cleanup), (c) polling only (no WebSocket). **Recommendation: (a).**

**D5. What counts as a job.** Options: (a) only user-started work: GPX processing, POI and card rescan, later exports (recommended); (b) every Celery task. **Recommendation: (a).** Beat tasks and the debounced statistics recompute are not jobs; they would only create noise.

**D6. GPX job ends when POI detection ends (whole chain is one job).** Options: (a) one job for process + detection (recommended: the user waits for POIs and cards anyway); (b) job ends when the track is `ready`, detection is a separate untracked task. **Recommendation: (a).**

**D7. Progress is sent through Redis only, at most once per second; the database is written only on status changes.** Why: a database write on every progress step would slow the worker and add load for no benefit. **Recommendation: yes.**

**D8. Retention: finished jobs are deleted after 30 days by the daily beat task.** Options: 7, 30 or 90 days. **Recommendation: 30.**

**D9. Push messages when the app is closed (FCM/APNs) and cancel endpoint: not in v1.** The `publish_job_event` function is the single place where a push sink can be added later. **Recommendation: agree to postpone.**
