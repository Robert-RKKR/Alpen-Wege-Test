# Track pipeline: agreed changes to the original plan (v2)

> Superseded by `track_pipeline_implementation_plan.md` (v3), which is authoritative. This file is kept as the record of the review decisions. Differences: statistic columns are named `total_moving_time_s` and `total_elevation_loss_m`, and 16 (not 12) transport types are set non-collectable.

Base document: the original task file ("Task: track creation and GPX processing pipeline").
This file lists only what differs from it. Everything not mentioned stays as in the original.

## Global decisions

| Topic | Decision |
|---|---|
| Event log | Object changes only (track create/edit via API routes, explicit `log_created` / `log_updated`). No logging for visits, statistics or worker writes. `geo_record` and `geo_performance` go to `NONE_TABLES` as a safeguard |
| Overrides | Dropped. No `*_override` columns, no effective columns, no `is_adjusted`, no `OVERRIDE_*` settings, no 409 rule, no `original`/`effective` blocks |
| Metrics source | Read from `geo_record` / `geo_performance` (join). Nothing copied onto the track |
| Incomplete GPX (battery died) | Out of scope. Later via "replace GPX" (ACT-05) |
| Visits | `profile_m2m_user_poi` becomes an append-only visit log. One row per (user, POI, track). No overwrite logic |
| Cards | One row per (user, card). `compendium_cat_card.poi_id` becomes NOT NULL (0 cards exist today) |
| Statistics | Extend the existing table with a sport dimension and new metrics. Recompute per user from scratch after commit |
| Rescan | Celery tasks plus API endpoints, no hourly sweep |
| Start/end POI | Closest POI of any type within `POI_COLLECT_RADIUS_M`, set only if NULL, editable by the user |

## Phase 0: answers to the open items (2.3)

1. `geo_record.elevation` = start altitude (rounded, from filtered series). `track_types` = NULL (no GPX source). `avg_grade` = distance-weighted mean of absolute grade, `highest_grade` = maximum uphill grade. `heart_graph`, `speed_pattern` and `elevation_graph` all use distance on the x-axis. Update the column comments accordingly.
2. Already nullable: `track.geo_record_id`, `recorded_at`, `sport_type_id`, `geo_record.gpx_id`, `geo_performance_id`. `user_poi.collected_at` and `user_card.collected_at` are NOT NULL (always supplied).
3. Statistic bucket key: today `(user_id, scope, scope_year, scope_month)`, plain unique (confirmed on the live DB, NULLs are distinct). Changed below.
4. Existing: unique `(user_id, poi_id)` on `user_poi` (to be replaced), unique `(user_id, card_id)` on `user_card`. Missing: unique `(track_id, poi_id)` on `track_poi`.
5. Seeded sports: Hiking, Trail Running, Fastpacking, Scrambling, Cycling, Road Cycling, Gravel Cycling, Mountain Biking, Enduro MTB, Downhill MTB, Ski Touring, Backcountry Skiing, Cross-Country Skiing, Splitboarding, Snowshoeing, Winter Hiking, Via Ferrata, Rock Climbing, Bouldering, Ice Climbing, Alpine Mountaineering, Ski Mountaineering, Canyoning. No plain Running or Walking.
6. Compose services: `postgres`, `redis`, `api` (bind-mounts code, `--reload`), `celery-worker` (no code mount, beat embedded via `--beat`). No separate beat service needed. Both api and worker run as root, so a named volume is writable.
7. FastAPI is unpinned (`>=0.111`). Use plain `Form()` parameters.
8. `compendium_cat_poi.location` is `Geometry(Point, 4326)`, so queries cast to geography and the expression index is needed.
9. `python-multipart` is installed.

Other findings that shape the work:
- `autodiscover_tasks(["app.worker.tasks"])` registers nothing (it looks for `app.worker.tasks.tasks`). Fix with `include=[...]` and import all model packages in the worker.
- No `moddatetime` trigger exists on any table. Add one for `explorer_agg_track` and also set `updated_at` explicitly in claim/touch statements.
- `aggregate_user_statistics` is unused and broken (NULL conflict key). It is replaced.

## Phase 1: config, dependencies, storage

- Remove `OVERRIDE_MAX_FACTOR`. Other settings as in the original. Add `GPX_TIMESTAMP_MIN_YEAR` (default 2000) and `GPX_TIMESTAMP_MAX_FUTURE_DAYS` (default 1).
- Volume `gpx_data` mounted at `GPX_STORAGE_DIR` in `api` and `celery-worker` only.
- `celery_app.py`: add `include=[...]` for the new task modules, add the reaper to `beat_schedule`. Existing task bodies stay untouched.

## Phase 2: models and DDL (`scripts/sql/track_pipeline_ddl.sql`, run it BEFORE rebuilding images)

`ExplorerAggTrack`: `processing_status` (+ CHECK `ck_track_processing_status`), `processing_error`, `processing_warnings` (JSONB), `processing_started_at`, `processed_at`, `archived_at`, `gpx_id` (FK to `asset_agg_gpx`). Remove from the original: all four effective and all four override columns. Keep the partial index `ix_track_active_owner` and the `processing_status` index. Add `moddatetime` trigger (`DROP TRIGGER IF EXISTS` then `CREATE`).

`AssetAggGpx`: `sha256` (indexed, not unique), `size_bytes`.

`ExplorerSubGeoRecord`: `route` Geography MULTILINESTRING with an explicitly named GIST index, `processor_version`.

`CoreRefCompendiumType`: `is_collectable` (default true). The DDL sets it to false for 16 transport and parking types (the exact list is in section 7.1 of the implementation plan). Move `compendium-types` out of `_FACTOR_TABLES` and register it with its own create/update/read schemas.

`CompendiumCatCard`: `poi_id` NOT NULL. Required in `CardCreate`.

`ProfileM2mUserPoi`: drop `profile_m2m_user_poi_user_id_poi_id_key`, add unique `(user_id, poi_id, track_id)`. Update column comments to "one row per visit".

`ExplorerM2mTrackPoi`: add unique `(track_id, poi_id)`.

`ProfileSubStatistic`:
- add `sport_type_id` (uuid, NULL = all sports, FK to `core_ref_sport_type`, ON DELETE CASCADE)
- add `total_moving_time_s`, `total_elevation_loss_m`, `active_days`, `max_elevation_m`, `longest_track_m`, `longest_track_id` (FK to track, ON DELETE SET NULL)
- drop `profile_sub_statistic_user_id_scope_scope_year_scope_month_key`
- add `UNIQUE NULLS NOT DISTINCT (user_id, sport_type_id, scope, scope_year, scope_month)`; model uses `postgresql_nulls_not_distinct=True`

Index: `ix_poi_location_geog` on `(location::geography)`. Existing FK `ON DELETE SET NULL` on the four Tier 3 tables and the `track` resource type with policies already exist, so they are only verified, not recreated.

## Phase 3: GPX library

As in the original, plus: timestamps before `GPX_TIMESTAMP_MIN_YEAR` or more than `GPX_TIMESTAMP_MAX_FUTURE_DAYS` ahead are treated as missing, with warning `implausible_timestamps`. Simplification test compares in the same local projection used for simplifying.

## Phase 4: services

Remove `track_metrics.py`. Keep `sport_inference.py` (alias map onto the seeded names above, underscores and spaces normalised, unmatched types logged at INFO) and `dispatch.py` as specified.

## Phase 5: Celery processing

As in the original. The claim sets `processing_started_at = now()` and `updated_at = now()`. The reaper uses `processing_started_at` for stuck `processing` rows and `updated_at` for stuck `pending` rows, and sets `updated_at = now()` explicitly when touching rows.

## Phase 6: API

- `PATCH` allows: name, summary, description (all languages), `is_public`, `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id`, `start_poi_id`, `end_poi_id`. All referenced ids are validated.
- Create and edit call `log_created` / `log_updated` explicitly. Create passes the log call after `flush`.
- `TrackRead`: base fields, status fields, ids, plus a light `metrics` block (distance, gain, loss, highest elevation, total/moving time) joined from Tier 1. No `original`/`effective`, no `is_adjusted`.
- Other users never see archived tracks. The owner can.
- Statistics are recomputed after create, archive, restore, reprocess and a `sport_type_id` change.

## Phase 7: statistics (`recompute_user_statistics`)

- One transaction per user, guarded by `pg_advisory_xact_lock(hashtextextended(user_id::text, 0))`. First step deletes the Redis debounce key.
- Source: tracks where `created_by = user`, `archived_at IS NULL`, `processing_status = 'ready'`, joined to `geo_record` and `geo_performance`.
- Three `INSERT ... ON CONFLICT DO UPDATE` statements (scope `all`, `year`, `month`), each with `GROUPING SETS ((), (sport_type_id))`.
- Tracks with NULL `sport_type_id` count only in the all-sports rows. Tracks with NULL `recorded_at` count only in the `all` scope.
- Computed columns only: distance, gain, loss, highest elevation, longest track, activity count, active days, moving and elapsed time. `unique_pois_count` from distinct visited POIs by visit date (all-sports rows only). Plans, streaks, points, regions and graphs are left untouched.
- Buckets with no tracks left: computed columns are set to zero.
- Averages are never stored.

## Phase 8: POI and card detection, rescan

- `detect_track_pois` as specified, but visits go into `profile_m2m_user_poi` with `ON CONFLICT (user_id, poi_id, track_id) DO NOTHING` (no earliest-wins update). Cards: `ON CONFLICT (user_id, card_id) DO NOTHING`, using the earliest visit time. `track_poi.distance_m` is filled with the cumulative distance at the nearest point.
- Tasks `tracks.rescan_poi(poi_id)` and `tracks.rescan_card(card_id)`.
- Endpoints `POST /pois/{id}/rescan` and `POST /cards/{id}/rescan`, 202, permission `update` on `poi` / `card`, Redis lock per id.
- `scripts/rescan_pois.py` stays for dry runs and `--all`.

## Phase 9: admin reprocess, docs

As in the original. Also update: ACT-05 and ACT-06 in `api_actions_executed_activities.md` (archive, not hard delete; no override), the SVG event-logger box (explicit calls instead of `after_flush`), and the README project structure.

## Not in this task

Achievement evaluation, points ledger, waypoints, photos, gear, conditions, trips, segment rankings, pace curves, calories, steps, streaks, regions, time zones, hard delete, frontend, overrides.
