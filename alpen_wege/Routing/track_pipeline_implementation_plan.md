# Track creation and GPX processing pipeline: implementation plan (v3)

> Update 2026-10-23: the event log moved to the `management` app (`app.management.utils.event_logger`, URL `/api/v1/management/event-log`), and `POST /tracks` and the rescan endpoints now create jobs and return `job_id`. See `management_implementation_plan.md` and `management_deploy_runbook.md`.

Status: ready to implement. This document is authoritative. It merges the original task file, the review findings, and every decision made in the review conversation. Where it differs from `track_pipeline_plan_v2_changes.md`, this file wins (the only differences are naming, see section 1.2).

Repo root = the folder that contains `app/` and `docker-compose.yml`. Docker runs on your Linux host (`~/jrdurt` in your terminal output), so every changed file must be copied or pulled there before you run the DDL, build or tests.

---

## 0. How to read and use this plan

### 0.1 Build order versus original phase numbers

The original file numbers its phases 0 to 9. The recommended build order is slightly different, because the pure GPX library needs only the new dependencies and gives fast feedback.

| Milestone | Original phase | What | Needs |
|---|---|---|---|
| M0 | 0 | Pre-flight checks (you run SQL, paste output) | nothing |
| M1 | 1 | Dependencies, settings, volume, Celery registration | M0 |
| M2 | 3 | GPX processing library and tests (pure, no DB) | M1 |
| M3 | 2 | DDL script and model changes | M1 |
| M4 | 4 | Services: storage, sport inference, dispatch, persistence | M2, M3 |
| M5 | 5 | Celery processing task and reaper | M4 |
| M6 | 6 | Track API | M4, M5 |
| M7 | 7 | Statistics recompute | M5 |
| M8 | 8 | POI and card detection, rescan tasks and endpoints | M5 |
| M9 | 9 | Reprocess, docs, README, smoke test | M6, M7, M8 |
| M10 | - | Final verification and report | all |

Dependency sketch: `M1 -> M2`, `M1 -> M3`, `{M2, M3} -> M4 -> M5 -> {M6, M7}`, `{M5, M7} -> M8` (detection requests a statistics recompute), `{M6, M7, M8} -> M9 -> M10`. M2 and M3 can be built in parallel. Until M7 and M8 exist, the worker discards the `stats.recompute_user` and `tracks.detect_pois` messages that M5 sends (Celery logs "unregistered task"); that is expected and harmless.

### 0.2 Working protocol (one milestone at a time)

1. Read the files a milestone touches (listed per milestone) and copy their patterns.
2. Make the changes.
3. You run the checks listed for that milestone and paste the output back. (My shell is currently unavailable, so I cannot run `pytest`, SQL or Docker myself. If it comes back I run the checks and tell you.)
4. I summarise the result in a few lines and move to the next milestone.

### 0.3 Code conventions (verified in the repo)

- Import order with the three comment headers `# Standard library`, `# Third-party`, `# Local application` (see `config.py`, `database.py`, `celery_app.py`, `track.py` model).
- `Mapped[...]` typing with `mapped_column(..., comment=...)`. Every new column gets a `comment` in the same style as its neighbours.
- Function-leading comment blocks (`# What it does`, `# Params:`, `# Returns:`) in infrastructure modules such as `database.py` and `current_user.py`. Route modules like `gear.py` have none; follow the neighbours of whatever file you edit.
- Responses: `ok`, `ok_list`, `fail`, `AppError` from `app.core.utils.responses`. `ok(data, code=202, message="Accepted")` sets the envelope code, so the route also needs `status_code=202`.
- `get_db` commits after the route function returns. Where ordering matters (before enqueueing a task), commit explicitly.
- Permissions: `resource_access(key, action)` returns `AccessContext(user, scope)`; `check_object_access(access, obj)` returns 404 for objects outside the scope; lists use a local `_apply_scope()` helper.
- Event logging is explicit: `log_created`, `log_updated`, `log_deleted` from `app.management.utils.event_logger`, called after `flush` and before `commit`. It is API-only by design. The worker never calls it.
- No secrets in code. Settings only through `app/config.py`.
- Code, comments and commit messages in English.
- Database changes go only through `scripts/sql/track_pipeline_ddl.sql`, which you run. No SQL is ever run against the database by me.
- Scripts under `scripts/` that import `app` start with `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))` and are run as `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/<name>.py <args>`. (`python scripts/x.py` puts only `scripts/` on the path, and the Dockerfile sets no `PYTHONPATH`; the existing seed scripts work only because they import nothing from `app`.)

---

## 1. Decisions

### 1.1 Final decisions (all confirmed by you)

| Topic | Decision |
|---|---|
| Create form | `name` (required), `summary`, `description`, `is_public` (default false), `gpx_file` (required). Nothing else |
| Processing | Celery. `processing_status`: `pending` -> `processing` -> `ready` or `failed` |
| GPX tolerance | Only the path is required. Time, elevation, heart rate optional. Missing data leaves fields NULL. Warnings are stored on the track |
| Tier 1 | `asset_agg_gpx`, `explorer_sub_geo_record`, `explorer_sub_geo_performance` are not user-editable. The original file stays on disk |
| Archive | `archived_at` (NULL = active). Delete means archive. No hard delete |
| File link | `explorer_agg_track.gpx_id` from the moment of upload |
| Overrides | Dropped. No override columns, no effective columns, no `is_adjusted`. Incomplete GPX is handled later by "replace GPX" |
| Metrics source | Read from `geo_record` and `geo_performance` by join. Nothing is copied onto the track |
| Duplicates | Not blocked. SHA-256 stored. Create response carries `duplicate_of_track_id`. Duplicates count twice in statistics |
| Sport type | Inferred from GPX `<type>` through an alias map, otherwise NULL until edited |
| Visits | `profile_m2m_user_poi` becomes an append-only visit log. One row per (user, POI, track). No overwrite logic |
| Cards | One row per (user, card). `compendium_cat_card.poi_id` becomes NOT NULL |
| Collectable types | `core_ref_compendium_type.is_collectable` (default true). Transport and parking types are set to false in the DDL |
| Start and end POI | Closest POI of any type within `POI_COLLECT_RADIUS_M`. Set only if NULL. Editable by the user |
| Statistics | Existing `profile_sub_statistic` is extended with a sport dimension and extra metrics. Recomputed per user from scratch after commit, debounced |
| Rescan | Celery tasks plus API endpoints `POST /pois/{id}/rescan` and `POST /cards/{id}/rescan`. No hourly sweep |
| Event log | Object changes only, written explicitly in API routes. `geo_record` and `geo_performance` go to `NONE_TABLES` as a safeguard |
| Time zones | Deferred. Year and month buckets use UTC |

### 1.2 Naming refinement against the v2 changes file

New statistic columns follow the existing `total_*` pattern: `total_moving_time_s` and `total_elevation_loss_m` (v2 said `moving_time_s` and `elevation_loss_m`). Extremes keep plain names: `active_days`, `max_elevation_m`, `longest_track_m`, `longest_track_id`.

### 1.3 Defaults I chose where you did not decide (confirm or change)

| # | Assumption (default) | If you disagree |
|---|---|---|
| A1 | Cards use `ON CONFLICT (user_id, card_id) DO NOTHING`. The card's `collected_at` is the earliest visit time within the run that creates it | Use "earliest wins" update instead (rewrites a Tier 3 row) |
| A2 | Start and end POI are set for every `ready` track, even without timestamps. Visits and cards still require timestamps | Skip all detection without timestamps |
| A3 | Interval grade for ascent and descent speeds uses the 50 m windowed grade at the interval start (smoother than point-to-point) | Use raw interval grade |
| A4 | The stored `asset_agg_gpx` row is private (`is_public = false`) even when the track is public | Mirror the track flag |
| A5 | `unique_pois_count` is computed on the all-sports rows only (not per sport) | Add per-sport counts later |
| A6 | `worker_prefetch_multiplier = 1` (long tasks do not hog prefetched messages) and `worker_max_tasks_per_child = 50` (numpy memory) | Keep the Celery defaults |
| A7 | Early 413 for oversized uploads is done by a small ASGI middleware on `POST /api/v1/tracks` (FastAPI parses the body before route code) | Rely on a reverse proxy limit plus the in-route byte counter |
| A8 | Rescan endpoints take a Redis lock per POI or card and return 409 while queued. The task releases the lock when it finishes; the `RESCAN_LOCK_SECONDS` default of 1860 s is only a safety net above the 1800 s task limit | No lock |
| A9 | Archive and restore are logged with `log_updated` on `archived_at` | Do not log |
| A10 | Statistics are recomputed again at the end of `detect_pois` and the rescan tasks (visits change `unique_pois_count`) | Only after processing |
| A11 | The reaper marks a track `failed` when its interrupted-attempt counter reaches `STUCK_MAX_ATTEMPTS` (3; counter in Redis, no schema change) | Retry forever |
| A12 | Field limits: `summary` at most 1000 characters, `description` at most 10000 | Other limits |
| A13 | Fix the typo in `NONE_TABLES` while adding the two geo tables: `profile_usr_credentials` becomes `profile_user_credentials` (the real table name). Today the credentials table is not excluded from event logging | Leave the typo |
| A14 | `push_data/seed.py` marks the 16 transport and parking types non-collectable after loading, so a freshly seeded database matches the migrated one | Edit the CSV instead |
| A15 | The `start_poi_id` and `end_poi_id` foreign keys become `ON DELETE SET NULL`. Otherwise deleting a POI that a track uses as start or end returns 500, which becomes likely once we fill them automatically | Keep RESTRICT |
| A16 | `app/profile/models/__init__.py` also imports `models_cat`, `models_m2m` and `models_sub`. Today nothing imports the Tier 3 and statistics models, so a fresh `create_all` would not create those tables and the worker could not map them | Import them only in the worker registry (fresh databases then differ) |

### 1.4 Not in this task

Achievement evaluation, points ledger, waypoints, photos, gear, conditions and POI links edited by users, trip aggregates, segment rankings, pace curves, calories and steps, streaks and region counts in statistics, trimming track ends in public views, `archived_at` on POI and card, frontend, hard delete, overrides, time zones.

---

## 2. Architecture

### 2.1 Data flow

```
Client --POST /api/v1/tracks (multipart)--> API
  size guard (ASGI) -> name and extension check -> XML root pre-check (defusedxml)
  -> stream to disk + SHA-256 -> INSERT asset_agg_gpx + explorer_agg_track (pending)
  -> COMMIT -> send_task("tracks.process_gpx")
  <-- 202 {id, name, processing_status, created_at, duplicate_of_track_id}

Worker: tracks.process_gpx
  claim (pending -> processing) -> path via track.gpx_id -> gpx.pipeline.process_gpx_file()
  -> persist geo_performance (if timed), geo_record, track fields, status ready -> COMMIT
  -> send_task("tracks.detect_pois") and request_stats_recompute(owner)

Worker: tracks.detect_pois
  stored route within 50 m of collectable POIs -> nearest GPX point -> visit time
  -> track_poi, user_poi (visit log), user_card; start and end POI -> COMMIT
  -> request_stats_recompute(owner)

Worker: stats.recompute_user   (debounced)
  advisory lock -> zero computed columns -> upsert all/year/month x sport buckets -> COMMIT

Beat: tracks.reap_stuck every 2 minutes

Editors: POST /pois/{id}/rescan -> tracks.rescan_poi ; POST /cards/{id}/rescan -> tracks.rescan_card
Admin:   scripts/reprocess_tracks.py -> tracks.reprocess ; scripts/rescan_pois.py (dry run, --all)
```

### 2.2 Status lifecycle

- `pending` -> `processing`: atomic claim by the worker (`UPDATE ... WHERE processing_status = 'pending'`).
- `processing` -> `ready`: persisted in the same transaction as the derived data.
- `processing` -> `failed`: permanent error (`GpxProcessingError`, unexpected exception, timeout, too many interruptions).
- `processing` -> `pending`: transient database error (before retry) or reaper reset of a stuck job.
- `failed` -> `pending`: `POST /tracks/{id}/reprocess` (only from `failed`, otherwise 409).
- Archive (`archived_at`) is orthogonal to status.

### 2.3 What each part writes (three-tier mapping)

| Tier | Tables | Writers |
|---|---|---|
| 1 authoritative facts | `asset_agg_gpx`, `explorer_sub_geo_record`, `explorer_sub_geo_performance`, `explorer_agg_track`, `explorer_m2m_track_poi` | API (gpx, track), `tracks.process_gpx`, `tracks.reprocess`, detection tasks (track_poi, start and end POI) |
| 2 derived | `profile_sub_statistic` | `stats.recompute_user` only |
| 3 event log | `profile_m2m_user_poi`, `profile_m2m_user_card` | detection and rescan tasks, insert only. Nothing in this task deletes or updates them |

---

## 3. File inventory

### 3.1 New files

| Path | Milestone |
|---|---|
| `requirements-dev.txt`, `pytest.ini` | M1 |
| `app/explorer/services/__init__.py` (empty) | M2 |
| `app/explorer/services/gpx/__init__.py`, `errors.py`, `limits.py`, `models.py`, `xml_guard.py`, `parser.py`, `cleaning.py`, `metrics.py`, `shaping.py`, `matching.py`, `pipeline.py` | M2 |
| `tests/__init__.py`, `tests/conftest.py`, `tests/gpx_factory.py`, `tests/test_gpx_*.py`, `tests/test_matching.py`, `tests/test_xml_guard.py`, `scripts/make_sample_gpx.py` | M2 |
| `scripts/sql/track_pipeline_ddl.sql` | M3 |
| `app/explorer/services/gpx_storage.py`, `sport_inference.py`, `dispatch.py`, `track_persist.py`, `tests/test_sport_alias.py` | M4 |
| `app/worker/model_registry.py`, `app/worker/tasks/track_processing.py` | M5 |
| `app/core/utils/upload_limit.py` | M6 |
| `app/explorer/routes/track.py`, `app/explorer/schemas/track.py` | M6 |
| `app/explorer/services/track_statistics.py`, `scripts/recompute_stats.py` | M7 |
| `app/explorer/services/poi_detection.py`, `app/worker/tasks/track_detection.py`, `scripts/rescan_pois.py` | M8 |
| `scripts/reprocess_tracks.py`, `scripts/smoke_tracks.sh` | M9 |

### 3.2 Changed files

| Path | Change | Milestone |
|---|---|---|
| `requirements.txt` | add gpxpy, defusedxml, shapely, numpy | M1 |
| `app/config.py` | new settings | M1 |
| `docker-compose.yml` | `gpx_data` volume on `api` and `celery-worker` | M1 |
| `app/worker/celery_app.py` | `include=[...]`, prefetch, reaper beat entry | M1, M5 |
| `.env.example` | document `GPX_STORAGE_DIR` for local runs | M1 |
| `app/explorer/models/models_agg/track.py` | new columns, indexes, constraint, trigger on create, `ON DELETE SET NULL` on start and end POI | M3 |
| `app/assets/models/models_agg/gpx.py` | `sha256`, `size_bytes` | M3 |
| `app/explorer/models/models_sub/geo_record.py` | `route`, `processor_version` | M3 |
| `app/explorer/models/models_m2m/track_poi.py` | unique `(track_id, poi_id)` | M3 |
| `app/profile/models/models_m2m/user_poi.py` | unique swap, comments | M3 |
| `app/profile/models/models_sub/statistic.py` | sport column, new metrics, new unique key | M3 |
| `app/compendium/models/models_cat/card.py`, `app/compendium/schemas/card.py` | `poi_id` NOT NULL and required | M3 |
| `app/compendium/models/models_cat/poi.py` | expression index for `location::geography` | M3 |
| `app/core/models/models_ref/core_ref_compendium_type.py` | `is_collectable` | M3 |
| `app/core/schemas/ref.py`, `app/core/routes/ref.py` | compendium-type create, update, read schemas and special router | M3 |
| `app/core/utils/seed_entity_types.py` | `NONE_TABLES` additions and the credentials table name fix (A13) | M3 |
| `app/profile/models/__init__.py` | also import `models_cat`, `models_m2m`, `models_sub` (A16) | M3 |
| `push_data/seed.py` | after loading, set the 16 transport and parking types non-collectable (A14) | M3 |
| `app/worker/tasks/track_processing.py` | add `reprocess_track` | M9 |
| `app/worker/tasks/stats.py` | replace broken `aggregate_user_statistics` with `recompute_user_statistics` | M7 |
| `app/explorer/routes/__init__.py` | include the track router | M6 |
| `app/main.py` | register the upload size middleware | M6 |
| `app/compendium/routes/poi.py`, `card.py` | one rescan endpoint each | M8 |
| `README.md` | "Track pipeline" section, project structure fixes | M9 |
| `designe/explorer_track_flow.svg` | event logger box: explicit calls, not `after_flush` | M9 |
| `test/api_actions_executed_activities.md` | ACT-05 and ACT-06: archive instead of hard delete, no overrides | M9 |

Already present and only verified: `track` resource type and policies in `scripts/init_seed.py`; `ON DELETE SET NULL` on `track_id` of `user_poi`, `user_card`, `user_achievement`, `point`; nullable `recorded_at`, `geo_record_id`, `sport_type_id`.

---

## 4. M0: pre-flight checks (you run, paste the output)

Run on the Docker host. Each command is read-only.

```bash
# 4.1 Access policies exist for track, poi and card (needed or POST /tracks returns 403)
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "SELECT rt.key, p.user_group, p.action, p.scope FROM profile_access_policy p JOIN core_ref_resource_type rt ON rt.id = p.resource_type_id WHERE rt.key IN ('track','poi','card') ORDER BY 1,2,3;"

# 4.2 The tables touched by constraint swaps are empty
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "SELECT 'track' t, count(*) FROM explorer_agg_track UNION ALL SELECT 'geo_record', count(*) FROM explorer_sub_geo_record UNION ALL SELECT 'user_poi', count(*) FROM profile_m2m_user_poi UNION ALL SELECT 'track_poi', count(*) FROM explorer_m2m_track_poi UNION ALL SELECT 'statistic', count(*) FROM profile_sub_statistic UNION ALL SELECT 'card_without_poi', count(*) FROM compendium_cat_card WHERE poi_id IS NULL;"

# 4.3 The existing daily cleanup job will start running once Celery registration is fixed
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "\d social_sub_comment"

# 4.4 Library versions inside the api container
sudo docker exec alpen-api pip list 2>/dev/null | grep -Ei "fastapi|starlette|pydantic|sqlalchemy|geoalchemy2|celery|redis|python-multipart|shapely|numpy"

# 4.5 Real constraint names that the DDL drops (never guess them)
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "\d profile_m2m_user_poi"
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "\d profile_m2m_user_card"

# 4.6 Which Tier 3 and statistic tables exist (no current code imports their models)
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "\dt profile_*"

# 4.7 The 16 transport and parking type names exist in the live data (the DDL seeds is_collectable by name)
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "SELECT name FROM core_ref_compendium_type WHERE name IN ('Bus Stop','Train Station','Tram','Cable Car Station','Gondola Station','Chair Lift','Funicular Station','Rack Railway','Mountain Railway','Ferry Crossing','Multi transport station','Multi transport station (Bus/Cable Car)','Multi transport station (Tram/Bus)','Parking','Lake Harbor','Helipad') ORDER BY 1;"
```

What I need from the output:

- 4.1: rows for `track` for each group (viewer and editor: create own, read public, update own, delete own; administrator: all). If they are missing, tell me before running `init_seed.py`: it also recreates the four default users with the seeded password and resets their groups.
- 4.2: expected 0 everywhere. If `statistic` or `user_poi` is above 0, tell me before the DDL.
- 4.3: if the table does not exist, the cleanup job would log an error every night. Then I leave `cleanup` out of the Celery `include` list.
- 4.4: confirms the installed versions (`requirements.txt` pins SQLAlchemy at 2.0.30 or newer, which supports `postgresql_nulls_not_distinct`) and decides `Form()` handling.
- 4.5: the DDL drops `profile_m2m_user_poi_user_id_poi_id_key` (PostgreSQL's default name). If your output shows a different name, I use that one. It also confirms that `profile_m2m_user_card` has the unique `(user_id, card_id)` that `ON CONFLICT` relies on.
- 4.6: tells me which `profile_*` tables really exist. The Tier 3 and statistic models are not imported by any current code, so I need to know how those tables were created.
- 4.7: should list 16 names. Missing names simply stay collectable.

---

## 5. M1: dependencies, settings, volume, Celery registration

Goal: the stack can run new code, store files on a shared volume, and the worker actually registers tasks.

Reads first: `app/config.py`, `docker-compose.yml`, `Dockerfile`, `requirements.txt`, `app/worker/celery_app.py`, `app/worker/tasks/*.py`, `.env.example`.

### 5.1 Changes

1. `requirements.txt`: add `gpxpy>=1.6.2`, `defusedxml>=0.7.1`, `shapely>=2.0`, `numpy>=1.26`. (`shapely` already arrives through `geoalchemy2[shapely]`; listing it makes the dependency explicit.) New `requirements-dev.txt`: `-r requirements.txt` and `pytest>=8.0`. New `pytest.ini`: `testpaths = tests`, `pythonpath = .`.
2. `app/config.py`: add the settings below to `Settings`, with the same style (typed attribute, default, grouped under short comments). `PROCESSOR_VERSION = 1` is not a setting; it lives in `gpx/pipeline.py`.

| Setting | Type | Default |
|---|---|---|
| `GPX_STORAGE_DIR` | str | `/data/gpx` |
| `GPX_MAX_UPLOAD_MB` | int | 20 |
| `GPX_MAX_SPEED_MS` | float | 70.0 |
| `GPX_MAX_GAP_NO_TIME_M` | float | 5000.0 |
| `GPX_SEGMENT_GAP_S`, `GPX_SEGMENT_GAP_MIN_M` | float | 300.0, 100.0 |
| `GPX_MOVING_SPEED_MS` | float | 0.5 |
| `GPX_TIMESTAMP_MIN_YEAR` | int | 2000 |
| `GPX_TIMESTAMP_MAX_FUTURE_DAYS` | int | 1 |
| `ELEVATION_MEDIAN_WINDOW` | int (odd, at least 1) | 5 |
| `ELEVATION_THRESHOLD_M` | float | 3.0 |
| `GRADE_WINDOW_M` | float | 50.0 |
| `GEOJSON_MAX_POINTS` | int | 1000 |
| `GEOJSON_COORD_DECIMALS` | int | 5 |
| `GRAPH_MAX_POINTS` | int | 300 |
| `ROUTE_SIMPLIFY_TOLERANCE_M` | float | 5.0 |
| `POI_COLLECT_RADIUS_M` | float | 50.0 |
| `POI_DETECTION_REQUIRES_TIMESTAMPS` | bool | true |
| `RESCAN_LOCK_SECONDS` | int | 1860 |
| `STUCK_PENDING_MINUTES`, `STUCK_PROCESSING_MINUTES` | int | 5, 30 |
| `STUCK_MAX_ATTEMPTS` | int | 3 |
| `STATS_RECOMPUTE_DELAY_S` | int | 5 |

   A field validator on `ELEVATION_MEDIAN_WINDOW` rejects values below 1 and raises even values to the next odd number.
3. `docker-compose.yml`: add a named volume `gpx_data`, mount it at `/data/gpx` in `api` (next to the existing `.:/app` bind mount) and in `celery-worker` (which has no volumes today), and set `GPX_STORAGE_DIR: /data/gpx` in both `environment` blocks. Both containers run as root (the Dockerfile has no `USER`), so the volume is writable. No separate beat service is needed: the worker already runs with `--beat`.
4. `app/worker/celery_app.py`: pass `include=["app.worker.tasks.cleanup", "app.worker.tasks.stats"]` to `Celery(...)` (only modules that exist at this point; later milestones add `track_processing` and `track_detection`). Add `worker_prefetch_multiplier=1` and `worker_max_tasks_per_child=50` to `conf.update`. Leave `autodiscover_tasks` and the existing beat entries alone. Reason: `autodiscover_tasks(["app.worker.tasks"])` looks for `app.worker.tasks.tasks`, which does not exist, so no task module is registered today.
5. `.env.example`: add `GPX_STORAGE_DIR=./data/gpx` (local runs outside Docker).

Side effect to expect: once the include is in place, the two existing beat jobs run for the first time (`log_active_users` hourly, `cleanup_orphaned_comments` daily at 03:00 UTC). Both are read-mostly and safe, subject to the 4.3 check.

### 5.2 Checks (you run)

```bash
docker compose config | grep -B2 -A2 gpx_data
sudo docker compose build api celery-worker && sudo docker compose up -d
sudo docker exec alpen-celery celery -A app.worker.celery_app inspect registered
sudo docker exec alpen-api sh -c "echo hi > /data/gpx/.probe" && sudo docker exec alpen-celery cat /data/gpx/.probe
```

Done when: the volume appears on both services, `inspect registered` lists `app.worker.tasks.stats.log_active_users` and the cleanup task, and the worker can read a file the api wrote.

---

## 6. M2: GPX processing library and tests (pure, no DB, no Celery)

Goal: `process_gpx_file(path)` turns a GPX file into everything the database needs, with defined behaviour for every degraded input.

Rules for the package `app/explorer/services/gpx/`:

- No imports from `app.database`, models, Celery or Redis. Only `app.config` through `limits.py`. This keeps `pytest` runnable without a database.
- Every function takes a `GpxLimits` (default `GpxLimits.from_settings()`), so tests pass explicit limits and never depend on the environment.
- numpy for all vector math. No Python loops over points except where a result depends on the previous accepted point (outlier removal) or a running reference (elevation hysteresis).
- All times are timezone-aware UTC.

### 6.1 Modules and contracts

| Module | Public API |
|---|---|
| `errors.py` | `GpxProcessingError(code, user_message)`. Codes: `invalid_xml`, `no_usable_path`, `file_missing`, `timeout`, `internal_error` |
| `limits.py` | frozen dataclass `GpxLimits` with every limit used below; `GpxLimits.from_settings()` |
| `models.py` | dataclasses `GpxPoint(lat, lon, ele, time, hr, cad)`, `ParsedGpx`, `CleanedGpx`, `GeoMetrics`, `PerfMetrics`, `ProcessedGpx` |
| `xml_guard.py` | `check_gpx_root(source)`: defusedxml `iterparse(source, events=("start",), forbid_dtd=True)`, reads only the first start event, requires local name `gpx` (namespace stripped). Raises `GpxProcessingError("invalid_xml", ...)`. Accepts a path or a binary file object. Used by the worker and by the API pre-check |
| `parser.py` | `parse_gpx(path, limits) -> ParsedGpx` |
| `cleaning.py` | `clean(parsed, limits) -> CleanedGpx` |
| `metrics.py` | `geometry_metrics(cleaned, limits) -> GeoMetrics`, `performance_metrics(cleaned, geo, limits) -> PerfMetrics or None` |
| `shaping.py` | `build_geojson(...)`, `build_graphs(...)`, `build_route_ewkt(...)` |
| `matching.py` | `nearest_visit(cleaned, lat, lon) -> NearestVisit(distance_m, along_track_m, time)` and a vectorised `visit_times(cleaned, pois)` |
| `pipeline.py` | `PROCESSOR_VERSION = 1`, `process_gpx_file(path, limits=None) -> ProcessedGpx`, `load_clean_segments(path, limits=None) -> CleanedGpx` (parse and clean only, used by detection) |

### 6.2 Parsing

- Run `check_gpx_root` first (defence in depth: the API pre-check is not the only entry).
- Parse with gpxpy. Take points from every `<trk>/<trkseg>` in file order, one segment per `<trkseg>`. If there are no track points, use every `<rte>` (one segment per route) and add warning `route_only`.
- Naive timestamps are UTC. Aware timestamps are converted to UTC.
- Timestamp plausibility: a time before January 1 of `GPX_TIMESTAMP_MIN_YEAR` or later than now plus `GPX_TIMESTAMP_MAX_FUTURE_DAYS` is set to None for that point and adds warning `implausible_timestamps`. Many devices write 1970 or 1980 when they lack a clock.
- Sport hint: the first `<trk><type>`; also read the file `creator`.
- Heart rate and cadence: iterate the point's extension elements and their descendants and match the local tag name `hr` and `cad` (namespace ignored). Keep heart rate only between 30 and 250.
- `<wpt>` is ignored; if present add `waypoints_ignored`.
- Warnings are plain codes in a set: `route_only`, `waypoints_ignored`, `no_timestamps`, `partial_timestamps`, `no_elevation`, `outliers_removed`, `segments_split`, `isolated_points_dropped`, `implausible_timestamps`, `geometry_truncated`. Stored sorted.
- `no_timestamps` if no point has a time, `partial_timestamps` if some have, `no_elevation` if no point has elevation (evaluated after cleaning).

### 6.3 Cleaning (order matters)

1. Drop points with missing, out-of-range, NaN or (0, 0) coordinates.
2. Drop consecutive points with identical coordinates (keep the first).
3. With timestamps (previous accepted point and current point both timed): `dt = t - t_prev`, `d` = haversine. Drop the point if `dt > 0` and `d / dt > GPX_MAX_SPEED_MS`, or if `dt <= 0` and `d > 50 m`. Compare each point with the last accepted point, not the raw predecessor. Add `outliers_removed` if anything was dropped.
4. Split a segment between two consecutive points when: both timed, `dt > GPX_SEGMENT_GAP_S` and `d >= GPX_SEGMENT_GAP_MIN_M`; or one of them is untimed and `d > GPX_MAX_GAP_NO_TIME_M`. Add `segments_split`.
5. Drop segments with fewer than 2 points (`isolated_points_dropped`).
6. If no segment is left: `GpxProcessingError("no_usable_path", "No usable path found in the file.")`.

Haversine everywhere: `R = 6371008.8 m`, `a = sin^2(dphi/2) + cos(phi1) cos(phi2) sin^2(dlambda/2)`, `d = 2 R asin(sqrt(a))`. Distances are computed inside segments only; gaps between segments are never counted.

### 6.4 Metrics (processor version 1)

Per segment build arrays: `lat`, `lon`, `ele` (NaN if missing), `t` (epoch seconds, NaN if missing), `hr` (NaN if missing), `cum` (cumulative distance inside the segment, `cum[0] = 0`).

Elevation (per segment):

1. Keep the points that have elevation. If fewer than 2 remain the segment adds nothing to gain or loss (its single value still counts for highest and lowest).
2. Median filter, window `ELEVATION_MEDIAN_WINDOW`, shrinking at the ends (use `sliding_window_view` on the interior and explicit slices at the ends).
3. Hysteresis with threshold `T = ELEVATION_THRESHOLD_M`: `ref = ele[0]`; for each next value `d = e - ref`; if `d >= T` then `gain += d, ref = e`; if `d <= -T` then `loss += -d, ref = e`.
4. Sum over segments. Highest and lowest elevation come from the filtered values. `elevation` (the record column) is the filtered elevation of the first point that has one (start altitude). Elevation fields are NULL when no point has elevation.

Grade (on the filtered elevation along `cum`): for each point `i` find the first later point `j` with `cum[j] - cum[i] >= GRADE_WINDOW_M` (`np.searchsorted`), grade `= (ele[j] - ele[i]) / (cum[j] - cum[i]) * 100`, clipped to plus or minus 100. `avg_grade` is the mean of the absolute grade weighted by the step distance to the next point. `highest_grade` is `max(0, max grade)`.

Time and performance (only if at least one segment has two timed points, otherwise no `geo_performance`):

- `started_at` and `ended_at`: first and last timestamp over all points. The track's `recorded_at` equals `started_at`, or NULL.
- `total_time_s`: sum over timed segments of (last timed point minus first timed point). Recorder gaps between segments are excluded.
- Intervals are consecutive points that both have times and `dt > 0`: speed `v = d / dt`. An interval is moving if `v >= GPX_MOVING_SPEED_MS`.
- `moving_time_s` = sum of `dt` over moving intervals. `stop_time_s = max(0, total_time_s - moving_time_s)`. `moving_ratio = moving_time_s / total_time_s`.
- `avg_speed_kmh` = timed distance / `total_time_s` x 3.6. `moving_avg_speed_kmh` = moving distance / `moving_time_s` x 3.6.
- Ascent and descent: an interval is ascent if the windowed grade at its start point is above +3 percent, descent if below minus 3 percent. `ascent_avg_speed_kmh` and `descent_avg_speed_kmh` = distance / time over the moving intervals of that class (a rest stop on a slope should not drag climbing speed down). NULL if there are none.
- `max_speed_kmh`: maximum of the 3-point rolling median of interval speeds (median of the speeds, so a single GPS spike is ignored). `max_ascent_speed_kmh` and `max_descent_speed_kmh`: the same rolling-median series restricted to ascent and descent intervals.
- Heart rate: `avg_heart_rate` (mean, rounded), `max_heart_rate`, `min_heart_rate` from valid samples, NULL if none.
- `calories_burned` and `steps_count` are NULL in version 1. `track_types` is NULL.

### 6.5 Stored representations

| Column | Content | Limit |
|---|---|---|
| `geojson` | `LineString` for one segment, `MultiLineString` otherwise, `[lon, lat]` only, rounded to `GEOJSON_COORD_DECIMALS` | at most `GEOJSON_MAX_POINTS` points in total |
| `elevation_graph` | `[[distance_m, elevation_m], ...]`, 1 decimal. NULL without elevation | at most `GRAPH_MAX_POINTS` |
| `heart_graph` | `[[distance_m, bpm], ...]`, integer bpm. NULL without heart rate | at most `GRAPH_MAX_POINTS` |
| `speed_pattern` | `[[distance_m, speed_kmh], ...]` from the rolling-median interval speeds, 1 decimal. NULL without timed intervals | at most `GRAPH_MAX_POINTS` |
| `route` | EWKT `SRID=4326;MULTILINESTRING(...)`, always a multi-line, 6 decimals | simplification tolerance only, no point cap |

Graph x is the cumulative distance inside segments with gaps removed (global distance = sum of previous segment lengths + `cum`). Resample with `np.interp` on `N = min(GRAPH_MAX_POINTS, sample count)` equally spaced distances. Never emit NaN or infinity (`json.dumps(..., allow_nan=False)` must pass); a graph with fewer than 2 usable samples is NULL.

Simplification: project each segment to local metres (`x = (lon - lon0) * cos(lat0) * 111320`, `y = (lat - lat0) * 110540`, with `lon0`, `lat0` the segment means), `shapely.LineString(...).simplify(tol, preserve_topology=False)`, map back to lon and lat. Douglas-Peucker keeps the first and last point of every segment.

- `geojson`: binary search the tolerance (12 iterations between 0 and 5000 m) for the smallest tolerance that gives at most `GEOJSON_MAX_POINTS` points in total. If that is impossible (very many segments), keep the longest segments that fit and add `geometry_truncated`. Drop consecutive duplicate points created by rounding.
- `route`: fixed tolerance `ROUTE_SIMPLIFY_TOLERANCE_M`. Never simplify by degrees.
- The raw file on disk stays the full-resolution source. `geojson` is only for display and is too coarse for POI matching.

### 6.6 Matching (used by detection)

`nearest_visit(cleaned, lat, lon)`: vectorised haversine from the POI to every point of every segment, take the nearest vertex, then refine on its two adjacent edges in local metres to get the closest point on the polyline. Return the distance, the along-track distance (for `track_poi.slot_position` and `distance_m`) and the time, linearly interpolated between the edge ends when both are timed. If the neighbours have no time, take the time of the nearest timed vertex in the same segment; if there is none, return None (the caller falls back to `track.recorded_at`, then `track.created_at`).

### 6.7 Pipeline and output mapping

`process_gpx_file(path, limits=None)`: missing file -> `file_missing`; `check_gpx_root`; parse; clean; metrics; shaping; return `ProcessedGpx`. Unexpected exceptions propagate (the worker maps them to `internal_error`).

| `ProcessedGpx` field | Target | Conversion |
|---|---|---|
| geojson, elevation_graph | `geo_record.geojson`, `.elevation_graph` | JSON |
| route EWKT | `geo_record.route` | geography |
| elevation, distance_m, elevation_gain_m, elevation_loss_m, highest_elevation_m, lowest_elevation_m | same names | `int(round(x))`, NULL if undefined |
| avg_grade, highest_grade | same names | float |
| total_points | `geo_record.total_points` | points kept after cleaning |
| start and end location | `geo_record.start_location`, `.end_location` | first point of first segment, last point of last segment, `POINT(lon lat)` SRID 4326 |
| processor_version | `geo_record.processor_version` | `PROCESSOR_VERSION` |
| all time, speed, heart rate fields, heart_graph, speed_pattern | `geo_performance.*` | ints for seconds and bpm, floats for speeds and ratio |
| recorded_at | `track.recorded_at` | `started_at` or None |
| warnings | `track.processing_warnings` | sorted list of codes |
| sport_hint | input for sport inference | string or None |

### 6.8 Tests (`tests/`, pytest, no database)

`tests/gpx_factory.py` provides `make_gpx(points, *, times=None, elevations=None, hr=None, tracks=1, route_only=False, waypoints=False, creator=None, sport_type=None)` and small generators (straight line, climb with noise, random walk). Fixed RNG seeds. An empty `tests/__init__.py` makes `from tests.gpx_factory import make_gpx` work, also from `scripts/make_sample_gpx.py` (which bootstraps `sys.path` as described in 0.3).

The 13 required cases from the original plan:

1. A 1 km straight line gives 1000 m, tolerance 2 m.
2. Flat ground with plus or minus 1 m elevation noise gives a gain near 0.
3. A 100 m climb with 0.5 m noise gives a gain of 100 m, tolerance 5 m.
4. A single 5 km jump with timestamps is removed as an outlier (`outliers_removed`).
5. A 10 minute gap with a 300 m jump splits the line (`segments_split`), the gap is not in the distance or in `total_time_s`.
6. No timestamps gives no performance result and `no_timestamps`.
7. No elevation gives NULL elevation fields and `no_elevation`.
8. Several `<trk>` elements are merged in file order.
9. A file with only `<rte>` is accepted with `route_only`.
10. 50 000 input points give a `geojson` with at most 1000 points and each graph with at most 300 (also assert it finishes in a few seconds).
11. The maximum distance between the simplified `route` and the original line is at most the tolerance (measured in the same local projection, with 1 percent numeric margin).
12. Heart rate is parsed from `gpxtpx:hr`.
13. An empty or invalid file raises `GpxProcessingError`.

Additional cases:

14. A DTD or entity-expansion file raises `invalid_xml` (xml_guard).
15. A root element that is not `gpx` raises `invalid_xml`.
16. Naive timestamps are treated as UTC; a 1970 timestamp is treated as missing with `implausible_timestamps`.
17. `<wpt>` adds `waypoints_ignored`.
18. Output is JSON-safe: `json.dumps(graphs, allow_nan=False)` works for every fixture.
19. `matching`: nearest-point distance, along-track distance and time interpolation on a known line; fallback when neighbours are untimed.
20. Moved to M4: `tests/test_sport_alias.py` (normalisation and alias resolution against a fake list of sport names) needs `sport_inference.py`.

### 6.9 Checks (you run)

```bash
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"
```

Done when all tests pass and no test imports `app.database`.

---

## 7. M3: DDL script and model changes

Goal: the schema supports the pipeline, and the ORM models match the live database. `create_all` does not alter existing tables, so the DDL script is the only thing that changes the live database. Run it before starting the new application image.

Reads first: the models listed in section 3.2, `app/core/schemas/ref.py`, `app/core/routes/ref.py`, `app/core/utils/seed_entity_types.py`.

### 7.1 `scripts/sql/track_pipeline_ddl.sql`

Idempotent: every statement uses `IF NOT EXISTS`, `DROP ... IF EXISTS` or a guarded `DO` block. It runs in one transaction with `\set ON_ERROR_STOP on`, so a failure leaves nothing half-applied. Run it twice to prove idempotency.

```sql
-- Run: sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/track_pipeline_ddl.sql
\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS moddatetime;

-- 0. Preconditions
DO $$
BEGIN
    IF current_setting('server_version_num')::int < 150000 THEN
        RAISE EXCEPTION 'PostgreSQL 15 or newer is required (UNIQUE NULLS NOT DISTINCT)';
    END IF;
    IF EXISTS (SELECT 1 FROM compendium_cat_card WHERE poi_id IS NULL) THEN
        RAISE EXCEPTION 'compendium_cat_card has rows with poi_id IS NULL; fix or delete them first';
    END IF;
    IF EXISTS (SELECT 1 FROM explorer_m2m_track_poi GROUP BY track_id, poi_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'explorer_m2m_track_poi has duplicate (track_id, poi_id) pairs';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_profile_sub_statistic_bucket')
       AND EXISTS (SELECT 1 FROM profile_sub_statistic
                   GROUP BY user_id, scope, scope_year, scope_month HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'profile_sub_statistic has duplicate buckets; remove them first';
    END IF;
END $$;

-- 1. asset_agg_gpx
ALTER TABLE asset_agg_gpx ADD COLUMN IF NOT EXISTS sha256 varchar(64);
ALTER TABLE asset_agg_gpx ADD COLUMN IF NOT EXISTS size_bytes bigint;
CREATE INDEX IF NOT EXISTS ix_asset_agg_gpx_sha256 ON asset_agg_gpx (sha256);

-- 2. explorer_agg_track
ALTER TABLE explorer_agg_track
    ADD COLUMN IF NOT EXISTS processing_status varchar(16) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS processing_error text,
    ADD COLUMN IF NOT EXISTS processing_warnings jsonb,
    ADD COLUMN IF NOT EXISTS processing_started_at timestamptz,
    ADD COLUMN IF NOT EXISTS processed_at timestamptz,
    ADD COLUMN IF NOT EXISTS archived_at timestamptz,
    ADD COLUMN IF NOT EXISTS gpx_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_track_processing_status') THEN
        ALTER TABLE explorer_agg_track ADD CONSTRAINT ck_track_processing_status
            CHECK (processing_status IN ('pending', 'processing', 'ready', 'failed'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'explorer_agg_track_gpx_id_fkey') THEN
        ALTER TABLE explorer_agg_track ADD CONSTRAINT explorer_agg_track_gpx_id_fkey
            FOREIGN KEY (gpx_id) REFERENCES asset_agg_gpx (id);
    END IF;
END $$;

-- Start and end POI: deleting a POI must not fail because a track uses it (we now fill them automatically).
ALTER TABLE explorer_agg_track
    DROP CONSTRAINT IF EXISTS explorer_agg_track_start_poi_id_fkey,
    DROP CONSTRAINT IF EXISTS explorer_agg_track_end_poi_id_fkey;
ALTER TABLE explorer_agg_track
    ADD CONSTRAINT explorer_agg_track_start_poi_id_fkey
        FOREIGN KEY (start_poi_id) REFERENCES compendium_cat_poi (id) ON DELETE SET NULL,
    ADD CONSTRAINT explorer_agg_track_end_poi_id_fkey
        FOREIGN KEY (end_poi_id) REFERENCES compendium_cat_poi (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_track_active_owner
    ON explorer_agg_track (created_by, recorded_at) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_track_processing_status ON explorer_agg_track (processing_status);
CREATE INDEX IF NOT EXISTS ix_track_gpx_id ON explorer_agg_track (gpx_id);

-- updated_at trigger (missing today; the reaper and every consumer of updated_at need it)
DROP TRIGGER IF EXISTS trg_set_updated_at ON explorer_agg_track;
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_track
    FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');

-- 3. explorer_sub_geo_record
ALTER TABLE explorer_sub_geo_record
    ADD COLUMN IF NOT EXISTS route geography(MultiLineString, 4326),
    ADD COLUMN IF NOT EXISTS processor_version smallint;
CREATE INDEX IF NOT EXISTS idx_explorer_sub_geo_record_route
    ON explorer_sub_geo_record USING gist (route);

-- 4. compendium
CREATE INDEX IF NOT EXISTS ix_poi_location_geog
    ON compendium_cat_poi USING gist ((location::geography));
ALTER TABLE compendium_cat_card ALTER COLUMN poi_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_compendium_cat_card_poi_id ON compendium_cat_card (poi_id);

DO $$
DECLARE n integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = current_schema()
                     AND table_name = 'core_ref_compendium_type'
                     AND column_name = 'is_collectable') THEN
        ALTER TABLE core_ref_compendium_type
            ADD COLUMN is_collectable boolean NOT NULL DEFAULT true;
        -- Seeded once, only when the column is created, so a manual change is never overwritten.
        UPDATE core_ref_compendium_type SET is_collectable = false WHERE name IN (
            'Bus Stop', 'Train Station', 'Tram', 'Cable Car Station', 'Gondola Station',
            'Chair Lift', 'Funicular Station', 'Rack Railway', 'Mountain Railway',
            'Ferry Crossing', 'Multi transport station',
            'Multi transport station (Bus/Cable Car)', 'Multi transport station (Tram/Bus)',
            'Parking', 'Lake Harbor', 'Helipad');
        GET DIAGNOSTICS n = ROW_COUNT;
        RAISE NOTICE 'is_collectable set to false on % rows (16 names were expected)', n;
    END IF;
END $$;

-- Optional (disabled): also exclude everyday amenities. Uncomment, run once, then comment it out again.
-- UPDATE core_ref_compendium_type SET is_collectable = false WHERE name IN (
--     'Cinema', 'Library', 'School', 'Cemetery', 'Bakery', 'Restaurant', 'Bar', 'Café', 'Hotel',
--     'Hostel', 'Guesthouse', 'Bed & Breakfast', 'Tennis Court', 'Mini Golf', 'Playground',
--     'Outdoor Gym', 'Information Board', 'Picnic Table', 'Rest Bench', 'Drinking Water',
--     'Customs Post', 'Border Crossing', 'Skate Park', 'University', 'Theatre', 'Concert Hall');

-- 5. Tier 3 visit log and track-poi uniqueness
ALTER TABLE profile_m2m_user_poi
    DROP CONSTRAINT IF EXISTS profile_m2m_user_poi_user_id_poi_id_key;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_profile_m2m_user_poi_visit') THEN
        ALTER TABLE profile_m2m_user_poi ADD CONSTRAINT uq_profile_m2m_user_poi_visit
            UNIQUE (user_id, poi_id, track_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_explorer_m2m_track_poi_track_poi') THEN
        ALTER TABLE explorer_m2m_track_poi ADD CONSTRAINT uq_explorer_m2m_track_poi_track_poi
            UNIQUE (track_id, poi_id);
    END IF;
END $$;

-- 6. profile_sub_statistic
ALTER TABLE profile_sub_statistic
    ADD COLUMN IF NOT EXISTS sport_type_id uuid,
    ADD COLUMN IF NOT EXISTS total_moving_time_s bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_elevation_loss_m bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS active_days integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_elevation_m integer,
    ADD COLUMN IF NOT EXISTS longest_track_m integer,
    ADD COLUMN IF NOT EXISTS longest_track_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'profile_sub_statistic_sport_type_id_fkey') THEN
        ALTER TABLE profile_sub_statistic ADD CONSTRAINT profile_sub_statistic_sport_type_id_fkey
            FOREIGN KEY (sport_type_id) REFERENCES core_ref_sport_type (id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'profile_sub_statistic_longest_track_id_fkey') THEN
        ALTER TABLE profile_sub_statistic ADD CONSTRAINT profile_sub_statistic_longest_track_id_fkey
            FOREIGN KEY (longest_track_id) REFERENCES explorer_agg_track (id) ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE profile_sub_statistic
    DROP CONSTRAINT IF EXISTS profile_sub_statistic_user_id_scope_scope_year_scope_month_key;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_profile_sub_statistic_bucket') THEN
        ALTER TABLE profile_sub_statistic ADD CONSTRAINT uq_profile_sub_statistic_bucket
            UNIQUE NULLS NOT DISTINCT (user_id, sport_type_id, scope, scope_year, scope_month);
    END IF;
END $$;

-- 7. Fail loudly if an older unique constraint survived under an unexpected name
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
                WHERE contype = 'u'
                  AND ((conrelid = 'profile_m2m_user_poi'::regclass
                        AND conname <> 'uq_profile_m2m_user_poi_visit')
                    OR (conrelid = 'profile_sub_statistic'::regclass
                        AND conname <> 'uq_profile_sub_statistic_bucket'))) THEN
        RAISE EXCEPTION 'A stale unique constraint remains on profile_m2m_user_poi or profile_sub_statistic; drop it by its real name (see \d) and run the script again';
    END IF;
END $$;

COMMIT;
```

Notes:

- The transport and parking list is the one agreed in the review (decision 8). Everyday amenities (Cinema, Library, School, Cemetery, Bakery, Restaurant, Bar, Cafe, Hotel, Hostel, Guesthouse, Bed & Breakfast, Tennis Court, Mini Golf, Playground, Outdoor Gym, Information Board, Picnic Table, Rest Bench, Drinking Water, Customs Post, Border Crossing, Skate Park, University, Theatre, Concert Hall) stay collectable by default. The commented, disabled `UPDATE` block after the `is_collectable` section excludes them too; enable it only if you want that.
- The track resource type and policies, and `ON DELETE SET NULL` on the four Tier 3 `track_id` columns, already exist (confirmed on your live DB for the foreign keys). They are not recreated here.
- Rollback: the changes are additive except three swaps (the `user_poi` unique constraint, the statistic unique constraint, `card.poi_id` NOT NULL). To roll back, drop `uq_profile_m2m_user_poi_visit` and `uq_profile_sub_statistic_bucket`, re-add the old constraints (only possible while no duplicate rows exist), and `ALTER COLUMN poi_id DROP NOT NULL`. Dropping the new columns is destructive and not part of a normal rollback.

### 7.2 Model changes

Keep every model definition in line with the DDL names above, so a fresh database built by `create_all` and a migrated database end up identical.

`ExplorerAggTrack` (`models_agg/track.py`): new imports `CheckConstraint`, `Index`, `String`, `text` from `sqlalchemy` and `JSONB` from `sqlalchemy.dialects.postgresql`.

```python
__table_args__ = (
    CheckConstraint(
        "processing_status IN ('pending', 'processing', 'ready', 'failed')",
        name="ck_track_processing_status",
    ),
    Index("ix_track_active_owner", "created_by", "recorded_at",
          postgresql_where=text("archived_at IS NULL")),
    Index("ix_track_processing_status", "processing_status"),
    Index("ix_track_gpx_id", "gpx_id"),
)

processing_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending", comment=...)
processing_error: Mapped[str | None] = mapped_column(Text, comment=...)
processing_warnings: Mapped[list | None] = mapped_column(JSONB, comment=...)
processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment=...)
processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment=...)
archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), comment=...)
gpx_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("asset_agg_gpx.id"), comment=...)
```

Also in `track.py`: `start_poi_id` and `end_poi_id` get `ForeignKey("compendium_cat_poi.id", ondelete="SET NULL")`, and the module ends with the trigger the DDL creates, so a fresh database built by `create_all` matches (the `moddatetime` extension is created before `create_all` in `create_tables`):

```python
from sqlalchemy import DDL, event

event.listen(
    ExplorerAggTrack.__table__, "after_create",
    DDL("CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_track "
        "FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at')"),
)
```

`AssetAggGpx`: `sha256: Mapped[str | None] = mapped_column(String(64), index=True, ...)` (the default index name `ix_asset_agg_gpx_sha256` matches the DDL) and `size_bytes: Mapped[int | None] = mapped_column(BigInteger, ...)`.

`ExplorerSubGeoRecord`: `route = mapped_column(Geography(geometry_type="MULTILINESTRING", srid=4326), nullable=True, deferred=True, comment=...)` (`deferred=True` so that ORM loads of a geo record do not fetch the large geography; GeoAlchemy2 creates `idx_explorer_sub_geo_record_route` for fresh databases, the same name as in the DDL) and `processor_version: Mapped[int | None] = mapped_column(SmallInteger, ...)`. Also fix the column comments that say JSONB but declare `JSON`, and update the `avg_grade`, `elevation` and graph comments to the definitions in section 6.

`ExplorerM2mTrackPoi`: `__table_args__ = (UniqueConstraint("track_id", "poi_id", name="uq_explorer_m2m_track_poi_track_poi"),)`; clarify that `distance_m` is the along-track distance.

`ProfileM2mUserPoi`: replace `UniqueConstraint("user_id", "poi_id")` with `UniqueConstraint("user_id", "poi_id", "track_id", name="uq_profile_m2m_user_poi_visit")`; update the comments of `poi_id`, `collected_at` and `track_id` to "one row per visit".

`ProfileSubStatistic`: add `sport_type_id` (nullable UUID FK, `ondelete="CASCADE"`), `total_moving_time_s` and `total_elevation_loss_m` (BigInteger, NOT NULL, server default 0), `active_days` (Integer, NOT NULL, server default 0), `max_elevation_m`, `longest_track_m` (Integer, nullable), `longest_track_id` (UUID FK to the track, `ondelete="SET NULL"`). Replace the unique constraint with `UniqueConstraint("user_id", "sport_type_id", "scope", "scope_year", "scope_month", name="uq_profile_sub_statistic_bucket", postgresql_nulls_not_distinct=True)`. (The keyword is available in the SQLAlchemy 2.0.30 or newer that `requirements.txt` requires; confirm with the 4.4 output. The upsert depends on this being a real constraint, so no index-only fallback is planned.) Update the `scope_year`, `scope_month` and `unique_pois_count` comments (sport dimension, visit log).

`CompendiumCatCard`: `poi_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("compendium_cat_poi.id"), nullable=False, index=True, ...)`. In `schemas/card.py`: `CardCreate.poi_id: UUID` (required), `CardRead.poi_id: UUID`, and in `CardUpdate` a validator that rejects an explicit `null` for `poi_id`.

`CompendiumCatPoi`: `__table_args__ = (Index("ix_poi_location_geog", text("(location::geography)"), postgresql_using="gist"),)`.

`CoreRefCompendiumType`: `is_collectable: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true", comment=...)`. In `app/core/schemas/ref.py` add `CompendiumTypeCreate(RefWithFactorCreate)` with `is_collectable: bool = True`, `CompendiumTypeUpdate(RefWithFactorUpdate)` with `is_collectable: bool | None = None`, and `CompendiumTypeRead(RefWithFactorRead)` with `is_collectable: bool`. In `app/core/routes/ref.py` remove `(CoreRefCompendiumType, "compendium-types")` from `_FACTOR_TABLES` and register it with the three new schemas, the same way `SportTypeCreate` and `DifficultySportCreate` are registered (otherwise the routes are registered twice).

`app/core/utils/seed_entity_types.py`: add `explorer_sub_geo_record` and `explorer_sub_geo_performance` to `NONE_TABLES`. The seed function re-syncs `tracking_mode` at every startup, so the change applies on the next API start. In the same set, correct `profile_usr_credentials` to `profile_user_credentials` (A13).

`app/profile/models/__init__.py` (A16): add `from . import models_cat, models_m2m, models_sub  # noqa: F401`. All three are needed, because `ProfileM2mUserAchievement` has a foreign key to `profile_cat_achievement`, so importing `models_m2m` alone raises `NoReferencedTableError`. Effect: a fresh `create_all` builds the Tier 3 and statistic tables, the worker can map them, and on the first start `seed_entity_types` adds entity-type rows for them. Tables that already exist are left alone.

`push_data/seed.py` (A14): after the table loop, run `UPDATE core_ref_compendium_type SET is_collectable = false WHERE name IN (<the 16 names>)`. The seed inserts only CSV columns, so the new column would otherwise stay true on a fresh database.

### 7.3 Checks (you run)

```bash
# 1. DDL, twice. The second run must also finish without errors.
sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/track_pipeline_ddl.sql
sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/track_pipeline_ddl.sql

# 2. Spot checks
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "\d explorer_agg_track"          # new columns, indexes, check, trigger
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "\d profile_sub_statistic"       # new unique, sport column
sudo docker exec alpen-postgres psql -U alpenwege -d alpenwege -c "SELECT name, is_collectable FROM core_ref_compendium_type WHERE NOT is_collectable ORDER BY name;"

# 3. Application starts with the new models and create_all raises nothing
sudo docker compose up -d --build api && curl -s http://localhost:8000/health
```

Done when: both DDL runs succeed (the first prints a NOTICE with the number of types set to non-collectable), the `\d` output shows the new structure including `ON DELETE SET NULL` on the track's start and end POI keys, 16 types are non-collectable, `/health` returns ok, and `GET /api/v1/ref/compendium-types` includes `is_collectable`.

---

## 8. M4: services (storage, sport inference, dispatch, persistence)

Goal: small, synchronous, Celery-free building blocks that the API, the worker and the scripts share.

Reads first: `app/database.py`, `app/redis.py`, `app/worker/celery_app.py`, the models from M3, `app/core/utils/responses.py`.

### 8.1 `gpx_storage.py`

```python
def storage_root() -> Path                      # Path(settings.GPX_STORAGE_DIR)
def new_relative_path(now=None) -> str          # "<yyyy>/<mm>/<uuid4>.gpx"
def resolve_path(relative: str) -> Path         # joins with the root, refuses paths outside it
def save_upload(fileobj, *, max_bytes) -> StoredFile   # (relative_path, sha256, size_bytes)
def delete_quietly(relative: str) -> None
class UploadTooLarge(Exception): ...
```

- `save_upload` creates the directory, writes to `<uuid>.gpx.part` in 1 MiB chunks while counting bytes and updating the SHA-256, aborts and deletes the part file when `max_bytes` is exceeded, and renames to the final name only on success. A partial file therefore never stays on disk.
- `resolve_path` resolves symlinks and `..`, and raises `ValueError` if the result is not inside the storage root. Paths in the database are always relative; they are generated by the server, never taken from user input.
- All functions are synchronous. Routes call them through `run_in_threadpool`.

### 8.2 `sport_inference.py`

```python
def normalise(text: str) -> str                 # strip, lower-case, "_" and "-" to space, collapse spaces
def resolve_sport_id(hint: str, sports: dict[str, UUID]) -> UUID | None      # pure, unit-tested
def infer_sport_type_id(session, gpx_type: str | None) -> UUID | None        # loads sports, logs unmatched at INFO
```

Matching order: exact against the normalised `name`, `name_de` and `name_pl` of the seeded sports, then the alias map, otherwise None (INFO log with the raw value so you can extend the map). Draft alias map (normalised hint to canonical seeded name; finalised against the seed CSV when coding):

| Canonical sport | Hints |
|---|---|
| Hiking | hiking, hike, walking, walk, trekking, wandern |
| Trail Running | trail running, trailrunning, running, run, jogging |
| Cycling | cycling, biking, bike, ride, cycle |
| Road Cycling | road biking, road cycling, road bike |
| Gravel Cycling | gravel, gravel biking, gravel cycling |
| Mountain Biking | mountain biking, mountainbiking, mountain bike, mtb |
| Ski Touring | ski touring, skitouring, skinning |
| Backcountry Skiing | backcountry skiing, freeride |
| Cross-Country Skiing | cross country skiing, nordic skiing, xc skiing, langlauf |
| Snowshoeing | snowshoeing, snowshoe |
| Via Ferrata | via ferrata, klettersteig |
| Rock Climbing | rock climbing, climbing |
| Alpine Mountaineering | mountaineering, alpine mountaineering, alpinism |

The seed has no plain Running or Walking, so those map to Trail Running and Hiking. Numeric types (some Strava exports) are not interpreted.

### 8.3 `dispatch.py` (all synchronous)

```python
def enqueue_process_track(track_id) -> None          # send_task("tracks.process_gpx")
def enqueue_detect_pois(track_id) -> None            # send_task("tracks.detect_pois")
def enqueue_reprocess_track(track_id) -> None        # send_task("tracks.reprocess")
def enqueue_rescan_poi(poi_id) -> None               # send_task("tracks.rescan_poi")
def enqueue_rescan_card(card_id) -> None             # send_task("tracks.rescan_card")
def request_stats_recompute(user_id) -> bool         # debounced send_task("stats.recompute_user")
```

- Always `celery_app.send_task("<name>", args=[str(id)], ignore_result=True)` by name, so the API process never imports numpy, shapely or the task modules. Importing `celery_app` itself is cheap (it only reads settings). `ignore_result=True` matters: with a Redis result backend, a producer that does not ignore results subscribes to a result channel on every call, and nothing in the API ever reads or forgets those channels.
- `request_stats_recompute`: sync Redis client from `settings.REDIS_URL` (module-level, lazily created). `SET stats:pending:{user_id} 1 NX EX (STATS_RECOMPUTE_DELAY_S + 60)`. If it was newly set, `send_task("stats.recompute_user", args=[...], countdown=STATS_RECOMPUTE_DELAY_S)` and return True. If `send_task` fails, delete the key and re-raise so the next request can schedule again. The task deletes the key as its first step, so a request that arrives while the task runs schedules a fresh run.
- Async routes call these through `starlette.concurrency.run_in_threadpool`. In routes, an enqueue failure after a successful commit is logged and tolerated (the reaper picks up stuck `pending` tracks; statistics recover on the next trigger or with `scripts/recompute_stats.py`).

### 8.4 `track_persist.py` (no Celery imports)

```python
def persist_processed_track(session, track, processed, existing_geo_record=None) -> ExplorerSubGeoRecord
def mark_failed(session, track_id, message: str) -> None
```

`persist_processed_track` runs inside the caller's transaction and never commits:

1. Performance: create `ExplorerSubGeoPerformance` from `processed.performance` if it exists. With `existing_geo_record` update the existing row in place; if the new result has no performance data but a row exists, set its derived columns to NULL (Tier 1 rows are never deleted).
2. Record: create or update `ExplorerSubGeoRecord` (all columns of section 6.7, `gpx_id = track.gpx_id`, `geo_performance_id`, `processor_version`). Points use `WKTElement("POINT(lon lat)", srid=4326)` (the pattern already used in `csv_import.py`). `route` is assigned as the SQL expression `func.ST_GeogFromText(ewkt)`, which avoids any ambiguity in GeoAlchemy2's Geography binding. The JSON columns (`geojson`, `elevation_graph`, `heart_graph`, `speed_pattern`, `track_types`) are plain `JSON`, so assigning Python `None` would store a JSON `null` instead of SQL NULL; assign `sqlalchemy.null()` (or leave the attribute unset on create) for missing values. When an existing record or performance row is updated, set `updated_at = func.now()` explicitly (those tables have no trigger).
3. Track: set `geo_record_id`, `recorded_at`, `processing_warnings` (sorted list), `processed_at = now()`, `processing_status = 'ready'`, `processing_error = NULL`, `processing_started_at = NULL`. Set `sport_type_id` only if it is NULL and inference finds one.
4. Reprocess keeps `start_poi_id`, `end_poi_id` and every user-edited field untouched.

`mark_failed` is a single `UPDATE ... SET processing_status = 'failed', processing_error = :msg, processing_started_at = NULL, updated_at = now() WHERE id = :id AND processing_status = 'processing'`.

### 8.5 Checks

`tests/test_sport_alias.py` (pure) passes under `pytest`. The rest is verified through M5 and M6.

---

## 9. M5: Celery processing and reaper

Goal: a track in `pending` becomes `ready` or `failed` without any user waiting, and nothing stays stuck.

Reads first: `app/worker/celery_app.py`, `app/worker/tasks/stats.py`, M4 services, `app/database.py`.

### 9.1 New and changed pieces

- `app/worker/model_registry.py`: imports the same six model packages as `create_tables` (`app.core.models`, `app.assets.models`, `app.compendium.models`, `app.explorer.models`, `app.profile.models`, `app.social.models`) with `# noqa: F401` (after A16, `app.profile.models` also pulls in the Tier 3 and statistic models). Every worker task module starts with `from app.worker import model_registry  # noqa: F401`. The worker never runs `create_tables`, and models with string-based relationships fail to configure unless all packages are imported.
- `app/worker/tasks/track_processing.py`: the two tasks below.
- `celery_app.py`: add `"app.worker.tasks.track_processing"` to `include`, and the beat entry `"reap-stuck-tracks": {"task": "tracks.reap_stuck", "schedule": crontab(minute="*/2")}`.

### 9.2 `process_track_gpx(track_id)` (task name `tracks.process_gpx`)

Options: `bind=True`, `acks_late=True`, `soft_time_limit=600`, `time_limit=660`, at most 3 retries for transient errors.

1. Claim, in its own short transaction (no transaction stays open during file work):

```sql
UPDATE explorer_agg_track
   SET processing_status = 'processing', processing_error = NULL,
       processing_started_at = now(), updated_at = now()
 WHERE id = :id AND processing_status = 'pending' AND archived_at IS NULL
RETURNING gpx_id;
```

   Zero rows: return `"skipped"` (already claimed, finished, or archived).
2. Resolve the path through `track.gpx_id` and `gpx_storage.resolve_path`.
3. Call `process_gpx_file(path)` outside any transaction.
4. Persist in one transaction: open a session, `SELECT ... FOR UPDATE` the track, confirm it is still `processing`, call `persist_processed_track`, commit.
5. After the commit: `enqueue_detect_pois(track_id)` and `request_stats_recompute(track.created_by)`.

Failure handling:

| Failure | Result |
|---|---|
| `GpxProcessingError` (`invalid_xml`, `no_usable_path`, `file_missing`) | `mark_failed` with the user-safe message, commit, no retry. `file_missing` is logged at ERROR |
| `SoftTimeLimitExceeded` | `mark_failed` ("Processing took too long. Please try a smaller file or contact support."), no retry |
| `sqlalchemy.exc.OperationalError` (transient database error) | set the track back to `pending`, then `self.retry(countdown=30 * 2**retries, max_retries=3)`. After the last retry `mark_failed` |
| any other exception | log with traceback, `mark_failed` ("Processing failed. Please try again or contact support."), commit |

The task returns a small status dict for the result backend (`{"track_id": ..., "status": "ready", "warnings": [...]}`).

### 9.3 `reap_stuck_tracks` (task name `tracks.reap_stuck`)

Runs every 2 minutes from the existing embedded beat.

1. Stuck `processing`:

```sql
SELECT id FROM explorer_agg_track
 WHERE processing_status = 'processing'
   AND processing_started_at < now() - make_interval(mins => :processing_minutes);
```

   For each id increment a Redis counter `track:attempts:{id}` (expiry one day). When the counter reaches `STUCK_MAX_ATTEMPTS`: `UPDATE ... SET processing_status = 'failed', processing_error = 'Processing was interrupted repeatedly. Please try again or contact support.', processing_started_at = NULL, updated_at = now()`. Otherwise `UPDATE ... SET processing_status = 'pending', processing_started_at = NULL, updated_at = now()` and call `enqueue_process_track(id)` straight away, so recovery does not wait for the pending rule below. Both updates end with `WHERE id = :id AND processing_status = 'processing' AND processing_started_at < now() - make_interval(mins => :processing_minutes)`, so a track that finished in the meantime is never flipped back. If Redis is unavailable skip the counter (never block recovery). This stops a poison file that kills the worker (for example out of memory) from looping forever.
2. Stuck `pending`: select and touch in one statement, then enqueue each id.

```sql
WITH due AS (
    SELECT id FROM explorer_agg_track
     WHERE processing_status = 'pending' AND archived_at IS NULL
       AND updated_at < now() - make_interval(mins => :pending_minutes)
     FOR UPDATE SKIP LOCKED
)
UPDATE explorer_agg_track t SET updated_at = now()
  FROM due WHERE t.id = due.id
RETURNING t.id;
```

   Touching `updated_at` stops every reaper run from enqueueing the same tracks again during a long queue backlog. Duplicate messages are harmless anyway because the claim is atomic.

### 9.4 Manual check before the API exists (you run)

```bash
# 1. sample file from the test factory, written straight into the shared volume
sudo docker exec alpen-api mkdir -p /data/gpx/test
sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/make_sample_gpx.py --out /data/gpx/test/sample.gpx

# 2. two rows (replace <admin uuid> with a real profile_usr_user id)
INSERT INTO asset_agg_gpx (name, path, created_by) VALUES ('sample.gpx', 'test/sample.gpx', '<admin uuid>') RETURNING id;
INSERT INTO explorer_agg_track (name, created_by, gpx_id) VALUES ('M5 test', '<admin uuid>', '<gpx id>') RETURNING id;

# 3. run and watch
sudo docker exec alpen-celery celery -A app.worker.celery_app call tracks.process_gpx --args='["<track id>"]'
sudo docker logs --tail 50 alpen-celery
SELECT processing_status, processing_warnings, processed_at FROM explorer_agg_track WHERE id = '<track id>';
```

Reaper test: insert another track, set `processing_status = 'processing'` and `processing_started_at = now() - interval '1 hour'`, wait up to 2 minutes, confirm it returns to `pending` and then to `ready`. Kill test: `sudo docker kill alpen-celery` during a task, restart, confirm the reaper re-runs it after the thresholds.

Done when: `pending -> processing -> ready` is observed, a corrupt file ends as `failed` with a readable message, and the reaper recovers a stuck row (the reset track is re-enqueued immediately, so "wait up to 2 minutes" is enough). The worker log will show "unregistered task" for the `tracks.detect_pois` and `stats.recompute_user` messages sent at the end of a successful run; they are discarded until M7 and M8 exist, which is expected.

---

## 10. M6: track API

Goal: the user-facing endpoints, with the same patterns as `gear.py`.

Reads first: `app/explorer/routes/gear.py`, `app/explorer/schemas/gear.py`, `app/profile/permissions/resource_access.py`, `app/core/utils/responses.py`, `app/main.py`, `app/core/schemas/geo.py` (reuse its GeoJSON helper for point output), `app/compendium/schemas/poi.py`.

### 10.1 Files

- `app/explorer/routes/track.py`: router `prefix="/tracks"`, `tags=["Explorer - Track"]`, resource key `track`. Include it in `app/explorer/routes/__init__.py` the way `gear_router` is included.
- `app/explorer/schemas/track.py`: all request and response models.
- `app/core/utils/upload_limit.py`: pure ASGI middleware. If the request is `POST /api/v1/tracks` and `Content-Length` exceeds `(GPX_MAX_UPLOAD_MB + 1) MiB`, answer 413 with the standard `fail(...)` envelope before the body is read (FastAPI parses multipart forms before route code runs, so a route-level check alone cannot reject early). Register it in `create_app()` in `app/main.py` with one `add_middleware` line, after the existing ones, so it is the outermost middleware and a 413 skips token rotation (that response then carries no `X-Request-ID` header, which is acceptable). Requests without `Content-Length` are still limited by the byte counter in `save_upload`. A reverse proxy limit (for example nginx `client_max_body_size`) is recommended in production.

### 10.2 Endpoints

| Endpoint | Action | Success | Errors |
|---|---|---|---|
| `POST /tracks` | `create` | 202 | 400 invalid GPX or extension, 413, 422 |
| `GET /tracks` | `read` | 200 list | 403 |
| `GET /tracks/{id}` | `read` | 200 | 404 |
| `GET /tracks/{id}/geometry` | `read` | 200 | 404 until `ready` |
| `GET /tracks/{id}/performance` | `read` | 200 | 404 if none |
| `PATCH /tracks/{id}` | `update` | 200 | 404, 422 |
| `DELETE /tracks/{id}` | `delete` | 200 (archive, idempotent) | 404 |
| `POST /tracks/{id}/restore` | `update` | 200 | 404 |
| `POST /tracks/{id}/reprocess` | `update` | 202 | 404, 409 unless `failed` |

Visibility rules (applied by one helper `_apply_visibility(stmt, access, archived)` in addition to `_apply_scope`):

- Scope `own`: own tracks. Scope `public`: own tracks plus other users' public tracks. Scope `all`: everything.
- Other users see only tracks that are `ready` and not archived. The owner and scope `all` see their tracks in every status, including archived ones.
- `archived=false` (default) returns only active tracks. `archived=true` returns archived tracks the caller may see (owner's own, or all for scope `all`).
- Every single-object endpoint (`GET /tracks/{id}`, `/geometry`, `/performance`, and the write endpoints) calls `check_object_access` and then `_ensure_visible(access, track)`: `if access.scope != "all" and track.created_by != access.user.id and (track.processing_status != "ready" or track.archived_at is not None): raise AppError(404, "Not found")`. `check_object_access` alone would let another user read a pending or failed public track (including `processing_error` and warnings), because it only knows `is_public`. The owner and scope `all` can read their archived tracks.

List: query `limit` (default 100, max 500), `offset`, `archived`, `processing_status` (validated against the four values), `sport_type_id`. Order by `coalesce(recorded_at, created_at) desc`. The query outer-joins `geo_record` and `geo_performance` for the light metric columns only. No `geojson` or graphs in a list.

### 10.3 `POST /tracks`

Form fields: `name` (1 to 255 characters), `summary` (at most 1000), `description` (at most 10000), `is_public` (default false), `gpx_file`. Plain `Form()` and `File()` parameters; a dedicated signature, not `TrackUpdate`. Empty strings are stored as NULL.

1. `(gpx_file.filename or "")` must end with `.gpx` (case-insensitive), otherwise 400 `Only .gpx files are accepted.`
2. Pre-check in `run_in_threadpool`: `check_gpx_root(gpx_file.file)` (defusedxml, first start event only, DTD forbidden), then `seek(0)`. Failure gives 400 `Not a valid GPX file.` Full well-formedness is checked by the worker.
3. `save_upload(...)` in `run_in_threadpool` with `max_bytes = GPX_MAX_UPLOAD_MB * 1024 * 1024`. `UploadTooLarge` gives 413 `File too large (maximum N MB).`
4. Duplicate lookup: an active track of the same owner whose linked gpx has the same `sha256`:

```sql
SELECT t.id FROM explorer_agg_track t JOIN asset_agg_gpx g ON g.id = t.gpx_id
 WHERE t.created_by = :uid AND t.archived_at IS NULL AND g.sha256 = :sha
 ORDER BY t.created_at DESC LIMIT 1;
```

   The result is `duplicate_of_track_id`. It never blocks.
5. In one transaction insert `AssetAggGpx` (`name` = original file name truncated to 255, `path`, `sha256`, `size_bytes`, `created_by`, `is_public = false`) and `ExplorerAggTrack` (`gpx_id`, `processing_status = 'pending'`, `created_by`, base fields). `flush` the gpx row first (the track needs `gpx.id`), then flush the track and call `log_created(db, track, user.id)`.
6. `await db.commit()` explicitly (`get_db` commits only after the route returns, so enqueueing earlier would let the worker run before the row is visible), then `await run_in_threadpool(enqueue_process_track, track.id)`. An enqueue error is logged and tolerated; the reaper recovers the track.
7. If anything fails before the commit, delete the stored file (`delete_quietly`) and re-raise.
8. Return `ok({...}, code=202, message="Accepted")` with route `status_code=202`. Body: `id`, `name`, `processing_status`, `created_at`, `duplicate_of_track_id`.

### 10.4 `PATCH /tracks/{id}`

`TrackUpdate` uses `ConfigDict(extra="forbid")` so an attempt to send `recorded_at` or any other non-editable field returns a clear 422. Allowed: `name` (not null), `name_de`, `name_pl`, `summary`, `summary_de`, `summary_pl`, `description`, `description_de`, `description_pl`, `is_public`, `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id`, `start_poi_id`, `end_poi_id`.

- `changes = body.model_dump(exclude_unset=True)`. An explicit null clears an optional field. `name` and `is_public` are NOT NULL columns, so a `field_validator("name", "is_public")` on `TrackUpdate` rejects an explicit null with 422 (otherwise the database error would surface as a 500).
- Every referenced id is checked for existence (sport type, difficulty level, difficulty sport, both POIs); a missing one gives 422 naming the field.
- `old_values`, `setattr`, `log_updated(db, track, old_values, changes, user.id)`, `await db.commit()`, `await db.refresh(track)` as in `gear.py`.
- If `sport_type_id` actually changed, call `request_stats_recompute(track.created_by)` after the commit (statistics are per sport).
- No metric, geometry or status field is editable here. Photos, gear, POI links and conditions come in a later task.

### 10.5 Archive, restore, reprocess, geometry, performance

- `DELETE`: if `archived_at` is NULL set it to `now()` and `log_updated` the change; commit; `request_stats_recompute`. Calling it again changes nothing. Tier 3 rows are not touched.
- `POST /restore`: clear `archived_at`, `log_updated`, commit, `request_stats_recompute`. If the track is still `pending`, enqueue processing too; if it is `ready`, enqueue `tracks.detect_pois` (idempotent), because detection is skipped while a track is archived.
- `POST /reprocess`: only when `processing_status = 'failed'` (else 409). Set `pending`, clear `processing_error` and `processing_started_at`, commit, enqueue. Return 202.
- `GET /geometry`: 404 until `ready`. Returns `geojson`, `elevation_graph`, `heart_graph`, `speed_pattern`, `start_location`, `end_location` (GeoJSON points via `ST_AsGeoJSON` or the existing helper).
- `GET /performance`: the `geo_performance` summary without `heart_graph` and `speed_pattern`; 404 if there is no performance row.

### 10.6 Read schemas

- `TrackCreated`: `id`, `name`, `processing_status`, `created_at`, `duplicate_of_track_id`.
- `TrackMetrics`: `distance_m`, `elevation_gain_m`, `elevation_loss_m`, `highest_elevation_m`, `lowest_elevation_m`, `total_time_s`, `moving_time_s` (all nullable).
- `TrackListItem`: `id`, `name`, `summary`, `is_public`, `sport_type_id`, `recorded_at`, `created_at`, `processing_status`, `archived_at`, `created_by`, and the light `metrics`.
- `TrackRead`: base fields in all languages, `is_public`, `processing_status`, `processing_error`, `processing_warnings`, `processed_at`, `recorded_at`, `archived_at`, `sport_type_id`, difficulty ids, `start_poi_id`, `end_poi_id`, `geo_record_id`, `created_at`, `updated_at`, `created_by`, `metrics`.

### 10.7 Checks (you run; `$HOST` and `$TOKEN` from a normal login)

```bash
curl -s -X POST $HOST/api/v1/tracks -H "Authorization: Bearer $TOKEN" -F name=Test -F gpx_file=@sample.gpx
curl -s $HOST/api/v1/tracks/<id> -H "Authorization: Bearer $TOKEN"
```

- Create returns 202 with `pending`, and the track becomes `ready` after the worker ran.
- A broken file ends as `failed` with a readable `processing_error`; `POST /tracks/{id}/reprocess` re-queues it; the same call on a `ready` track returns 409.
- `PATCH` with `recorded_at` returns 422; `PATCH` with a valid sport changes it.
- Another user with only `read public` access gets 404 for a private track; the list for them shows only ready, active, public tracks.
- No `MissingGreenlet` in the API log on create. If it appears, add `__mapper_args__ = {"eager_defaults": True}` to `ExplorerAggTrack`.
- `GET /api/v1/management/event-log?entity_type=explorer_agg_track` shows `created` and `updated` entries with small snapshots.

---

## 11. M7: statistics recompute

Goal: `profile_sub_statistic` follows the user's tracks, per sport and per period, and can always be rebuilt from scratch (Tier 2).

Reads first: `app/profile/models/models_sub/statistic.py` (after M3), `app/worker/tasks/stats.py`, `app/explorer/services/dispatch.py`.

### 11.1 Pieces

- `app/explorer/services/track_statistics.py`: `recompute_user_statistics(session, user_id) -> dict` containing all SQL. No Celery, no Redis.
- `app/worker/tasks/stats.py`: replace the unused, broken `aggregate_user_statistics` with a task `recompute_user_statistics(user_id)` (task name `stats.recompute_user`). Import the service function under an alias (for example `from app.explorer.services.track_statistics import recompute_user_statistics as _recompute`) so the task does not shadow it. `log_active_users` stays unchanged. The task: delete the Redis key `stats:pending:{user_id}` as its first step, open a `SyncSessionLocal` transaction, call the service, commit, log the counts.
- `scripts/recompute_stats.py` (`--user-id <uuid>` or `--all`): runs the service directly. This is the "full recompute fixes everything" tool after any algorithm change.

### 11.2 Algorithm (one transaction per user)

1. `SELECT pg_advisory_xact_lock(hashtextextended(:uid_text, 0))`. Two workers can never recompute the same user at once.
2. Zero the computed columns on all existing rows of this user, so buckets that lost their tracks fall back to zero: `total_activities`, `total_distance_m`, `total_elevation_m`, `total_elevation_loss_m`, `total_time_s`, `total_moving_time_s`, `active_days`, `unique_pois_count` set to 0; `max_elevation_m`, `longest_track_m`, `longest_track_id` set to NULL. Columns this task does not compute (plans, streaks, points, regions, graphs) are never touched. The same statement sets `updated_at = now()`; this table has no trigger, so every `DO UPDATE SET` below sets it as well. Readers see the old committed rows until the commit, so there is no flicker.
3. Upsert from this source, three statements (scope `all`, `year`, `month`):

```sql
WITH src AS (
    SELECT t.id, t.sport_type_id,
           gr.distance_m, gr.elevation_gain_m, gr.elevation_loss_m, gr.highest_elevation_m,
           gp.total_time_s, gp.moving_time_s,
           (t.recorded_at AT TIME ZONE 'UTC')                                  AS rec_utc,
           EXTRACT(YEAR  FROM t.recorded_at AT TIME ZONE 'UTC')::int           AS y,
           EXTRACT(MONTH FROM t.recorded_at AT TIME ZONE 'UTC')::int           AS m
      FROM explorer_agg_track t
      JOIN explorer_sub_geo_record gr ON gr.id = t.geo_record_id
      LEFT JOIN explorer_sub_geo_performance gp ON gp.id = gr.geo_performance_id
     WHERE t.created_by = :uid AND t.archived_at IS NULL AND t.processing_status = 'ready'
)
INSERT INTO profile_sub_statistic
    (user_id, sport_type_id, scope, scope_year, scope_month,
     total_activities, total_distance_m, total_elevation_m, total_elevation_loss_m,
     total_time_s, total_moving_time_s, active_days,
     max_elevation_m, longest_track_m, longest_track_id)
SELECT :uid, sport_type_id, 'all', NULL, NULL,
       count(*),
       coalesce(sum(distance_m), 0), coalesce(sum(elevation_gain_m), 0),
       coalesce(sum(elevation_loss_m), 0),
       coalesce(sum(total_time_s), 0), coalesce(sum(moving_time_s), 0),
       count(DISTINCT rec_utc::date),
       max(highest_elevation_m), max(distance_m),
       (array_agg(id ORDER BY distance_m DESC NULLS LAST))[1]
  FROM src
 GROUP BY GROUPING SETS ((), (sport_type_id))
HAVING GROUPING(sport_type_id) = 1 OR sport_type_id IS NOT NULL
ON CONFLICT ON CONSTRAINT uq_profile_sub_statistic_bucket DO UPDATE SET
    total_activities = EXCLUDED.total_activities, total_distance_m = EXCLUDED.total_distance_m,
    total_elevation_m = EXCLUDED.total_elevation_m, total_elevation_loss_m = EXCLUDED.total_elevation_loss_m,
    total_time_s = EXCLUDED.total_time_s, total_moving_time_s = EXCLUDED.total_moving_time_s,
    active_days = EXCLUDED.active_days, max_elevation_m = EXCLUDED.max_elevation_m,
    longest_track_m = EXCLUDED.longest_track_m, longest_track_id = EXCLUDED.longest_track_id,
    updated_at = now();
```

   The `year` statement selects `'year', y, NULL`, filters `WHERE rec_utc IS NOT NULL` and groups by `GROUPING SETS ((y), (y, sport_type_id))`. The `month` statement selects `'month', y, m` and groups by `GROUPING SETS ((y, m), (y, m, sport_type_id))`. All three share the `HAVING` rule and the `ON CONFLICT` clause (the SQL string is built once in Python and reused).

   Rules that this encodes:
   - `sport_type_id` NULL means "all sports". Tracks whose sport is unknown count only in the all-sports rows (the `HAVING` removes the per-sport group for NULL, which would otherwise collide with the all-sports row).
   - Tracks without `recorded_at` count only in scope `all`.
   - The empty grouping set `()` returns a row even when there are no tracks, so the user's `all` row always exists and is zero after the last track is archived.
   - Averages are never stored; compute `distance_m / moving_time_s` on read.
   - Year and month use UTC.
4. `unique_pois_count` from the visit log (all-sports rows only), counting distinct POIs, including visits from archived tracks (earned is earned):

```sql
UPDATE profile_sub_statistic s SET unique_pois_count = v.n
  FROM (SELECT count(DISTINCT poi_id) AS n FROM profile_m2m_user_poi WHERE user_id = :uid) v
 WHERE s.user_id = :uid AND s.scope = 'all' AND s.sport_type_id IS NULL;
-- year and month: same with GROUP BY EXTRACT(YEAR/MONTH FROM collected_at AT TIME ZONE 'UTC'),
-- joined on s.scope_year (and s.scope_month), s.sport_type_id IS NULL
```

   Year and month rows that exist because of tracks get their POI counts; a bucket with visits but no tracks has no row and is not counted (documented limitation).
5. Commit. Running the task twice gives identical rows.

### 11.3 Checks (you run, with a `ready` track from M6)

```sql
SELECT scope, scope_year, scope_month, sport_type_id, total_activities, total_distance_m,
       total_elevation_m, total_time_s, active_days, unique_pois_count
  FROM profile_sub_statistic WHERE user_id = '<uid>'
 ORDER BY scope, scope_year, scope_month, sport_type_id NULLS FIRST;
```

- After a track becomes `ready`: an `all` row, a `year` row and a `month` row for the all-sports series; plus per-sport rows if the sport was inferred.
- `DELETE /tracks/{id}` (archive): totals drop to zero; `POST /restore`: totals return.
- A track with no sport: present in the all-sports rows only. A track without `recorded_at`: counted only in `all`.
- Run `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/recompute_stats.py --user-id <uid>` twice: the rows do not change.

Done when all five checks hold.

---

## 12. M8: POI and card detection, rescan

Goal: visits and cards follow the tracks, and editors can pull new POIs and cards into old tracks.

Reads first: M3 models, `app/compendium/routes/poi.py` and `card.py`, `app/redis.py`.

### 12.1 `app/explorer/services/poi_detection.py` (sync, shared by tasks and scripts)

```python
def detect_for_track(session, track_id, *, radius_m, require_timestamps) -> DetectionReport
def rescan_poi_batch(session, poi_id, *, radius_m, require_timestamps, after_track_id, batch_size=200) -> RescanBatch
def rescan_card(session, card_id) -> RescanReport
```

Transaction rule: the services never commit and never enqueue. They return counts and `affected_user_ids`. The caller (task or script) owns the transaction. Tasks commit after each unit of work and then call `request_stats_recompute` for the affected users. A dry run keeps one transaction, never commits, enqueues nothing, and ends with `session.rollback()`, so a dry run is a real rollback of the real code path. `rescan_poi_batch` pages by track id (`WHERE t.id > :after_track_id ORDER BY t.id LIMIT :batch_size`) and returns `last_track_id` (None when finished).

`detect_for_track`:

1. Load the track. Return a "skipped" report if it is archived or not `ready`.
2. Start and end POI (for every `ready` track, even without timestamps): only if currently NULL, the closest POI of any type within `radius_m` of the stored start or end location:

```sql
UPDATE explorer_agg_track t
   SET start_poi_id = (
       SELECT poi.id FROM compendium_cat_poi poi
        WHERE ST_DWithin(poi.location::geography, g.start_location::geography, :r)
        ORDER BY ST_Distance(poi.location::geography, g.start_location::geography) LIMIT 1)
  FROM explorer_sub_geo_record g
 WHERE t.id = :tid AND g.id = t.geo_record_id AND t.start_poi_id IS NULL;
-- end_poi_id: same with end_location
```

3. If `require_timestamps` and `recorded_at IS NULL`: stop here. A planned route is not proof of a visit.
4. Hits (collectable types only), measured against the stored route, so sparse recording does not miss a POI. The stored route is simplified by up to `ROUTE_SIMPLIFY_TOLERANCE_M`, so this prefilter is widened by that tolerance and step 5 applies the exact radius to the original points:

```sql
SELECT poi.id, ST_X(poi.location) AS lon, ST_Y(poi.location) AS lat
  FROM explorer_sub_geo_record g
  JOIN compendium_cat_poi poi ON ST_DWithin(poi.location::geography, g.route, :radius_m + :tolerance_m)
  JOIN core_ref_compendium_type t ON t.id = poi.compendium_type_id AND t.is_collectable
 WHERE g.id = :geo_record_id;
```

5. Re-read the original GPX (`load_clean_segments`) and run `matching.nearest_visit` for every hit. Keep a hit only if `nearest_visit.distance_m <= radius_m`. The stored `route` is simplified and cannot give a time. Visit time = interpolated time, else `track.recorded_at`, else `track.created_at`. Sort hits by along-track distance.
6. Writes (core `insert()` from `sqlalchemy.dialects.postgresql`; ids and timestamps come from server defaults):
   - `explorer_m2m_track_poi`: `slot_position` 0 to n-1 by order along the track, `distance_m` = along-track distance, `created_by` = track owner; `ON CONFLICT (track_id, poi_id) DO NOTHING`. Existing rows (possibly linked manually) are never deleted.
   - `profile_m2m_user_poi`: one visit row per hit with `track_id` and `collected_at`; `ON CONFLICT ON CONSTRAINT uq_profile_m2m_user_poi_visit DO NOTHING`. Re-running detection for the same track adds nothing; a different track through the same POI adds a new visit (that is the visit log).
   - `profile_m2m_user_card`: for every card whose `poi_id` is among the hits, `(user_id, card_id, collected_at, track_id)` with `ON CONFLICT (user_id, card_id) DO NOTHING`.
7. Return the report with `affected_user_ids`. The task commits and then calls `request_stats_recompute(owner)` if any visit row was added (A10). An early return (steps 1 or 3) leaves the step 2 updates to the caller's commit.

`rescan_poi`: skip with a clear report if the POI's type is not collectable. Find active, `ready` tracks near the POI using the route index, then re-read only those GPX files:

```sql
SELECT t.id AS track_id, t.created_by, t.recorded_at, t.created_at, gpx.path
  FROM compendium_cat_poi poi
  JOIN explorer_sub_geo_record g ON ST_DWithin(g.route, poi.location::geography, :radius_m + :tolerance_m)
  JOIN explorer_agg_track t ON t.geo_record_id = g.id
  JOIN asset_agg_gpx gpx ON gpx.id = t.gpx_id
 WHERE poi.id = :poi_id AND t.archived_at IS NULL AND t.processing_status = 'ready'
   AND (t.recorded_at IS NOT NULL OR NOT :require_timestamps)
   AND t.id > :after_track_id
 ORDER BY t.id LIMIT :batch_size;
```

For each track: nearest visit (keep it only if `distance_m <= radius_m`), insert the visit row and the `track_poi` row (`slot_position` = current maximum plus one for that track, `ON CONFLICT DO NOTHING`), and the cards of that POI for that user. The task loops over batches of 200 tracks, commits after each batch, and then requests a statistics recompute for the affected users (debounced).

`rescan_card`:

```sql
INSERT INTO profile_m2m_user_card (user_id, card_id, collected_at, track_id)
SELECT DISTINCT ON (v.user_id) v.user_id, c.id, v.collected_at, v.track_id
  FROM compendium_cat_card c
  JOIN compendium_cat_poi p ON p.id = c.poi_id
  JOIN core_ref_compendium_type t ON t.id = p.compendium_type_id AND t.is_collectable
  JOIN profile_m2m_user_poi v ON v.poi_id = c.poi_id
 WHERE c.id = :card_id
 ORDER BY v.user_id, v.collected_at ASC
ON CONFLICT (user_id, card_id) DO NOTHING
RETURNING user_id;
```

Granted visits and cards are never deleted by anything in this task. Archiving a track does not touch them.

### 12.2 Tasks (`app/worker/tasks/track_detection.py`, add to `include`)

| Task name | Behaviour |
|---|---|
| `tracks.detect_pois(track_id)` | `detect_for_track` with settings, then commit, then enqueue the statistics recompute; `acks_late`, soft limit 300 s |
| `tracks.rescan_poi(poi_id)` | loops `rescan_poi_batch`, commits after each batch, then requests recomputes for the affected users; soft limit 1800 s; always deletes the Redis lock `rescan:poi:{poi_id}` in `finally` |
| `tracks.rescan_card(card_id)` | `rescan_card`; deletes `rescan:card:{card_id}` in `finally` |

### 12.3 API endpoints (one each, in the existing route modules)

- `POST /pois/{poi_id}/rescan` in `app/compendium/routes/poi.py`, and `POST /cards/{card_id}/rescan` in `card.py`. Resource action `update` on `poi` or `card`, then `check_object_access`, so editors can rescan only their own and administrators any.
- Lock: `SET rescan:poi:{id} 1 NX EX RESCAN_LOCK_SECONDS` with the async Redis client; if it already exists return 409 `Rescan already queued.`
- Enqueue through `run_in_threadpool(enqueue_rescan_poi, id)`; on failure delete the lock and return 503. Success returns 202 `{"poi_id": ..., "status": "queued"}`.

### 12.4 `scripts/rescan_pois.py`

`argparse` flags: `--poi-id`, `--card-id`, `--all`, `--apply`, `--radius`, `--batch-size`. Default is dry run: it runs the real service code in one transaction, never commits, never enqueues anything, and ends with a rollback, then prints "would add N visits and M cards to K users across T tracks". `--apply` commits. `--all` loops every collectable POI in batches. Nothing is ever revoked.

### 12.5 Checks (you run)

- A track through a seeded POI that has a card: after processing there is one visit row, one `user_card` row, one `track_poi` row.
- Re-run `tracks.detect_pois` for that track: all counts unchanged. Upload a second track through the same POI: one more visit row (the log), still one card row.
- Create a new POI on the path of an old track, call `POST /pois/{id}/rescan`: the visit appears; calling it again immediately returns 409; after the task finished a second call adds nothing.
- `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/rescan_pois.py --poi-id <id>` (dry run) reports 0 new after the rescan; the same command with `--apply` on a fresh POI adds rows.
- Index use: `EXPLAIN SELECT poi.id FROM compendium_cat_poi poi, explorer_sub_geo_record g WHERE g.id = '<id>' AND ST_DWithin(poi.location::geography, g.route, 50);` shows `ix_poi_location_geog` once there are enough POIs (a tiny table may legitimately use a sequential scan).

---

## 13. M9: admin reprocess, documentation, smoke test

### 13.1 Reprocess

- Task `reprocess_track(track_id)` (name `tracks.reprocess`) in `track_processing.py`. For a `ready` track only: take a per-track advisory lock, re-read the GPX from disk, run `process_gpx_file`, call `persist_processed_track(..., existing_geo_record=...)` to overwrite the derived columns of `geo_record` and `geo_performance` in place and bump `processor_version`. If processing fails, log at ERROR and leave the existing data and status untouched (Tier 1 data is never lost to a failed reprocess). On success: `enqueue_detect_pois` (idempotent) and `request_stats_recompute`. It never deletes or updates Tier 3 rows. `failed` tracks use the API reprocess endpoint instead.
- `scripts/reprocess_tracks.py`: `--track-id <uuid>` or `--below-version N` (tracks whose `processor_version` is NULL or lower than N), optional `--limit`; dry run by default (prints how many tracks and which ids); `--apply` enqueues `tracks.reprocess` for each.

### 13.2 Sample files and smoke script

- `scripts/make_sample_gpx.py` (built in M2, reusing `tests/gpx_factory.py`): `--variant full|no-time|no-ele|two-trk|route-only|broken`, `--out <file>`.
- `scripts/smoke_tracks.sh` (curl and jq; `HOST`, `EMAIL`, `PASSWORD` come from the environment, nothing hard-coded): generates the variants (`sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/make_sample_gpx.py --variant <v> --out /tmp/<v>.gpx`, copied out with `docker cp`), logs in, uploads every variant, polls until `ready` or `failed`, prints status, warnings and metrics, archives and restores one track, and prints the statistics rows through the API-visible fields.

### 13.3 Documentation

- `README.md`: add a "Track pipeline" section (volume and storage layout, new settings, the DDL script and its run command, the scripts and their flags, the status lifecycle, the new endpoints, troubleshooting: stuck `pending` means check the worker and the reaper, `failed` means read `processing_error`). Fix the stale project structure block (it still lists `auth/`, `users/`, `worker.py`).
- `designe/explorer_track_flow.svg`: change the event logger box `after_flush auto-capture` to "explicit log_* calls (API only)".
- `test/api_actions_executed_activities.md`: ACT-05 and ACT-06 now archive instead of hard delete and drop the points-revocation text that depends on it; remove the override idea; ACT-02 becomes asynchronous with optional sport type.
- Update `track_pipeline_plan_v2_changes.md` to point to this file.

---

## 14. M10: final verification and report

### 14.1 End-to-end test (dev stack)

1. Upload a full sample: 202 with `pending`. Poll `GET /api/v1/tracks/{id}` until `ready`; check `metrics`, `processing_warnings` and `sport_type_id`.
2. `GET /api/v1/tracks/{id}/geometry`: `geojson` has at most 1000 points; each graph at most 300.
3. `PATCH` the name and the sport type: both change; `PATCH` with `recorded_at` returns 422.
4. Upload the variants: no time, no elevation, two `<trk>`, route-only, broken. Each behaves as in section 6 (warnings, NULL fields, `failed` with a readable message, reprocess re-queues and returns 409 on a `ready` track).
5. `DELETE` the track: statistics drop, the track is absent from the default list and present with `?archived=true`. `POST /restore` brings both back.
6. Event log: `GET /api/v1/management/event-log?entity_type=explorer_agg_track` shows `created` and `updated`; there are no entries for `explorer_sub_geo_record` or `explorer_sub_geo_performance`, and none written by the worker.
7. Reaper: kill the worker mid-task and confirm recovery.
8. POI and card detection and rescan as in 12.5.
9. SQL spot checks:

```sql
SELECT id, processing_status, processing_warnings, archived_at FROM explorer_agg_track;
SELECT id, total_points, distance_m, processor_version, ST_NPoints(route::geometry) FROM explorer_sub_geo_record;
SELECT * FROM profile_sub_statistic;
SELECT user_id, poi_id, track_id, collected_at FROM profile_m2m_user_poi ORDER BY collected_at;
```

### 14.2 Review pass

Before the report, one independent review of the full diff against this document (a second reader that did not write the code), focused on: SQL correctness, transaction boundaries (commit before enqueue), idempotency of every task, and that no Tier 3 row is ever updated or deleted.

### 14.3 Final report format

1. Created and changed files, grouped by milestone.
2. The exact DDL command and the rebuild command:
   `sudo docker compose build api celery-worker && sudo docker compose up -d`
3. Answers found for each item of the original 2.3, and which definitions came from code, docs or this plan.
4. Deviations from the original task file (section 17) and why.
5. Open questions.

---

## 15. Runbook (commands in the order you run them)

0. Copy files to the Docker host checkout (`~/jrdurt`) in the right order. For M3 copy only `scripts/sql/track_pipeline_ddl.sql` first, run it (7.3), and only then copy the rest (for example by `git pull`). Reason: the running `api` container bind-mounts the repo and reloads on every file change, so new model files copied before the DDL would load models that select columns the old schema does not have. The additive DDL is safe for the old code.
1. M0: run the section 4 commands and paste the output.
2. After M1: `sudo docker compose build api celery-worker && sudo docker compose up -d`, then the M1 checks.
3. After M2: `sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q"`.
4. After M3: run the DDL twice (7.3), then `sudo docker compose up -d --build api`.
5. After M4 to M9: rebuild both services (`sudo docker compose build api celery-worker && sudo docker compose up -d`) because the worker has no code mount. The `api` service has a bind mount and `--reload`, but it still needs the rebuild whenever dependencies change.
6. If section 4.1 showed no `track` policies, tell me before running `init_seed.py`: it rebuilds the policy matrix, but it also recreates the four default users with the seeded password and resets their groups.
7. Re-run the checks of each milestone as it lands and paste anything unexpected.
8. Scripts that import `app` always run as `sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/<name>.py <args>`.

Deploy order matters: DDL first, then new application code. `create_all` does not alter existing tables, so new code against an old schema fails on the first track query.

---

## 16. Risks and mitigations

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| R1 | Registration fix starts the two existing beat jobs for the first time | Nightly cleanup deletes orphaned comments; hourly active-user count | Both are safe; check 4.3 first. If `social_sub_comment` is missing, leave `cleanup` out of `include` and delete its beat entry, otherwise Celery logs an unregistered-task error every night |
| R2 | Oversized upload is buffered before the route sees it | Disk and memory pressure | ASGI `Content-Length` guard, byte counter in `save_upload`, proxy limit in production |
| R3 | A malformed GPX kills the worker (memory) and loops through the reaper | Endless retries | `STUCK_MAX_ATTEMPTS` counter, time limits, 20 MB cap, prefetch 1 and `worker_max_tasks_per_child = 50` |
| R4 | Partial DDL failure | Inconsistent schema | One transaction, `ON_ERROR_STOP`, preconditions, idempotent statements |
| R5 | GeoAlchemy2 Geography binding surprises (no shell to try it here) | Persist fails | `route` assigned through `func.ST_GeogFromText(ewkt)`; points use the pattern already proven in `csv_import.py` |
| R6 | The `::geography` expression index is not used | Slow detection | Expression index in DDL and model; `EXPLAIN` check in 12.5 |
| R7 | NULL-distinct unique key in statistics | Duplicate rows | `NULLS NOT DISTINCT` plus `ON CONFLICT ON CONSTRAINT` |
| R8 | Statistics recompute runs before detection finishes | Stale `unique_pois_count` | Recompute is requested again at the end of detection and rescans (A10) |
| R9 | `updated_at` has no trigger today | Reaper misjudges stuck jobs | Trigger on the track table in the DDL, plus explicit `updated_at` and `processing_started_at` |
| R10 | My shell is unavailable, so I cannot run tests | Errors found late | Small milestones, you run checks after each, pure library first |
| R11 | `requirements.txt` is unpinned | A rebuild can pull new major versions | Minimum versions for new libraries; consider a lock file later |
| R12 | Public tracks expose full geometry and start and end points | Privacy | Out of scope (trimming ends is listed as not in this task); the raw GPX stays private (A4) |
| R13 | Duplicate uploads count twice | Inflated totals | Warning field `duplicate_of_track_id`; accepted by decision |
| R14 | Deleting a POI cascades into `user_poi` (Tier 3) and is blocked while a card references it | Visits disappear | Outside this task; recommend a separate ticket (`ON DELETE` policy for POI). The track's start and end POI keys become `SET NULL` here (A15) |
| R15 | Files authored in OneDrive, Docker runs on another host | Old code runs | Runbook step 0 |
| R16 | Scripts cannot import `app` when run as `python scripts/x.py` | `ModuleNotFoundError` | `sys.path` bootstrap in every script and the `docker exec -w /app -e PYTHONPATH=/app` pattern (0.3) |
| R17 | The Tier 3 and statistics models are imported nowhere today | Fresh databases lack those tables; worker mapping errors | A16: import the three profile subpackages; the worker registry imports them through `app.profile.models` |

---

## 17. Deviations from the original task file

1. Overrides removed: no override or effective columns, no `track_metrics.py`, no 409 rule, no `original` and `effective` blocks (original sections 1, 4, 6, 8.3, 8.4, 9).
2. Visits are an append-only log instead of an earliest-wins upsert (original 10.1).
3. `profile_sub_statistic` is extended (sport dimension, new metrics, new unique key) instead of only upserting existing columns (original 9).
4. The event logger is described as explicit calls, not listeners (original 2.2 and 8.3).
5. Celery registration is fixed with `include`, plus prefetch 1 (not in the original).
6. No separate beat service was needed (original: "add one if needed").
7. `card.poi_id` NOT NULL, and transport and parking types seeded as non-collectable in the DDL (original had only the column).
8. Resource type, policies, `SET NULL` foreign keys and the two Tier 3 uniques already existed, so they are only verified (original 4).
9. Added: `processing_started_at`, Redis attempt counter in the reaper, timestamp plausibility, start and end POI independent of timestamps, statistics recompute after detection, ASGI upload guard, rescan endpoints, `scripts/recompute_stats.py`, filled `track_poi.distance_m`, and the moving-only and windowed-grade refinement for ascent and descent speeds.
10. The original check "upload the same track again and no duplicates appear" becomes: re-running detection for the same track adds nothing, while a second upload is a second visit by design.
11. The `start_poi_id` and `end_poi_id` foreign keys become `ON DELETE SET NULL` (A15).
12. `app/profile/models/__init__.py` imports the Tier 3 and statistics model packages (A16); `push_data/seed.py` marks the transport types non-collectable (A14); the credentials table name in `NONE_TABLES` is corrected (A13).
13. The detection and rescan services never commit or enqueue; tasks and scripts own the transaction, so dry runs are real rollbacks.
14. Detection prefilters with the route simplification tolerance and then enforces the exact radius on the original points.
15. The reaper re-enqueues a reset track immediately, and the DDL fails loudly on a stale unique constraint.

---

## 18. Definition of done (mapped to checks)

| Done item | Verified by |
|---|---|
| `pytest` passes | M2 check 6.9 |
| App starts, DDL runs twice without errors | M3 check 7.3 |
| Create, read, patch, archive, restore, reprocess work | M6 checks 10.7, M10 end-to-end 1 to 5 |
| Worker: valid file to `ready`, broken file to `failed`, reaper recovers a stuck job | M5 checks 9.4, M10 step 7 |
| Statistics follow create, archive and restore | M7 checks 11.3 |
| POI and card detection works, is idempotent, visits are logged | M8 checks 12.5 |
| Event log has no entries from the worker and none for `geo_record` or `geo_performance` | M10 step 6 |
| README updated | M9 13.3 |

---

## 19. Effort and sequencing

| Milestone | Size | Your touchpoints |
|---|---|---|
| M0 | S | run 6 read-only commands |
| M1 | S | rebuild, 3 checks |
| M2 | L (algorithms and tests) | run `pytest`, paste failures |
| M3 | M | run DDL twice, 3 checks |
| M4 | S | none beyond `pytest` |
| M5 | M | manual worker check, reaper and kill test |
| M6 | L | curl checks, event log check |
| M7 | M | SQL checks |
| M8 | L | detection, rescan and `EXPLAIN` checks |
| M9 | S | smoke script, README review |
| M10 | S | full end-to-end, final report |

Recommended pacing: M0 to M2 first (no database risk, quick feedback), then M3 and M4 together, then M5, M6, M7, M8 in that order, and M9 and M10 last. M2 and M3 can run in parallel if two people work on it.

