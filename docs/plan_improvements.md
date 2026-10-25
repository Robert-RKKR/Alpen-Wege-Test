# Category 2: Improvements to Current Code — Implementation Plan

## Overview

This document covers improvements to existing implemented features. These are
not new features but refinements: better patterns, missing edges, performance,
and correctness fixes. Organized by priority.

---

## 1. Social Module: Build the Missing Router Layer

**Current state:** Models exist (`SocialM2mFollow`, `SocialSubComment`,
`SocialSubRating`) but no routes, schemas, or services. The social router
is not registered in `main.py`. The `social/__init__.py` is empty — no
routes directory exists at all.

**What needs to happen:**

### Follow system

```
POST   /social/follow/{user_id}           — follow a user
DELETE /social/follow/{user_id}           — unfollow
GET    /social/me/followers               — list followers
GET    /social/me/following               — list following
GET    /social/users/{id}/followers       — list user's followers (public)
```

- Self-follow blocked by DB constraint (`ck_social_m2m_follow_no_self`)
- Idempotent follow/unfollow (ON CONFLICT DO NOTHING / DELETE if exists)
- Follower/following counts can be stored on the user model or computed

### Comment system

```
POST   /social/{entity_type}/{entity_id}/comments   — add comment
GET    /social/{entity_type}/{entity_id}/comments   — list comments (threaded)
PATCH  /social/comments/{id}                         — edit own comment
DELETE /social/comments/{id}                         — delete own comment
```

- `entity_type` validated by DB constraint: route, journey, segment, track, trip, post
- Thread support via `parent_id` (self-referencing FK)
- List endpoint returns flat list with `parent_id`; GUI builds tree client-side
- Edit/delete restricted to comment owner (via `UserScopedMixin.user_id`)

### Rating system

```
PUT    /social/{entity_type}/{entity_id}/rating      — rate (upsert)
DELETE /social/{entity_type}/{entity_id}/rating      — remove rating
GET    /social/{entity_type}/{entity_id}/ratings     — list ratings
```

- `entity_type` constrained to route, journey, segment
- `score` 1-5, enforced by DB constraint
- PUT is an upsert (ON CONFLICT update score)
- After rating change: update `rating_avg` and `rating_count` on the entity
  (route/segment/journey already have these columns)

### Rating aggregation

When a rating is created/updated/deleted, recompute the entity's `rating_avg`
and `rating_count`:

```sql
UPDATE explorer_agg_route SET
  rating_avg = (SELECT AVG(score) FROM social_sub_rating
                WHERE entity_type = 'route' AND entity_id = :id),
  rating_count = (SELECT COUNT(*) FROM social_sub_rating
                  WHERE entity_type = 'route' AND entity_id = :id)
WHERE id = :id
```

---

## 2. Orphan Cleanup: Expand and Harden

**Current state:** `cleanup_orphaned_comments()` in `cleanup.py` only handles
track and route comments. Uses `NOT IN (SELECT id ...)` which is slow on large
tables.

**Improvements:**

### Expand coverage

Add cleanup for all entity types:
- journey, segment, trip, post comments
- Orphaned ratings (route/journey/segment deleted)
- Orphaned `explorer_m2m_track_poi` rows (track deleted but M2M survived)
- Orphaned geo_records not linked to any track or segment
- Orphaned GPX files on disk with no matching `asset_agg_gpx` row

### Performance

Replace `NOT IN` with `LEFT JOIN ... WHERE ... IS NULL`:

```sql
DELETE FROM social_sub_comment c
USING (
    SELECT c2.id FROM social_sub_comment c2
    LEFT JOIN explorer_agg_track t ON c2.entity_id = t.id
    WHERE c2.entity_type = 'track' AND t.id IS NULL
) orphan
WHERE c.id = orphan.id
```

### Batch processing

For large tables, process in batches with `LIMIT` and loop until no more
rows are deleted. This prevents long-running transactions and lock contention.

### Scheduling

Run as a periodic Celery beat task (e.g. daily at 03:00 UTC). Currently
the task exists but there's no evidence it's scheduled in the beat config.

---

## 3. Settings Singleton: Cache Once, Not Per-Call

**Current state:** `get_settings()` in `config.py` creates a new `Settings()`
instance every call. This re-reads environment variables and .env each time.
Many modules call `get_settings()` at module level (`settings = get_settings()`),
but some call it per-request.

**Improvement:**

```python
from functools import lru_cache

@lru_cache
def get_settings() -> Settings:
    return Settings()
```

This is the standard Pydantic/FastAPI pattern. The settings object is
created once and cached. If hot-reload is needed, `get_settings.cache_clear()`
can be called.

---

## 4. Track Processing: Better Error Granularity

**Current state:** Track processing catches all exceptions and writes a
generic error to `processing_error`. The user sees "Processing failed" with
no actionable information.

**Improvements:**

- Parse common GPX issues and return specific messages:
  - "GPX file contains no track points" (empty file)
  - "GPX file has no valid GPS coordinates" (all points filtered)
  - "Track is too short (X meters, minimum Y meters)"
  - "GPX file is malformed: [parser error]"
- Store error code alongside message (e.g. `processing_error_code` column or
  structured JSON in `processing_error`)
- This helps the user decide: retry with a different file, or contact support

---

## 5. Cleanup: Archived Track Handling

**Current state:** Tracks can be archived (`archived_at IS NOT NULL`) but
the archival flow is incomplete:

- Processing skips archived tracks (good)
- POI detection skips archived tracks (good)
- Statistics recomputation includes all tracks — needs filter on archived_at
- No API endpoint to archive/unarchive tracks
- No periodic cleanup of long-archived tracks (if desired)

**Improvements:**

### Archive endpoints

```
POST   /explorer/tracks/{id}/archive      — archive track
POST   /explorer/tracks/{id}/unarchive    — restore track
```

Both trigger stats recomputation for the owner.

### Stats filter

In `recompute_user_statistics()`, add `AND t.archived_at IS NULL` to the
track aggregation query. Currently the raw SQL CTEs do not check this.

### Optional: hard delete after retention period

Configurable: tracks archived for > N days are permanently deleted (including
GPX file on disk). This should be a separate periodic task, not automatic.

---

## 6. GPX Processing: Processor Version Tracking

**Current state:** `PROCESSOR_VERSION = 1` exists but isn't used for anything
beyond storing it on the processed result. There's no mechanism to identify
tracks processed with an older version or batch-reprocess them.

**Improvements:**

- Store `processor_version` on the track model (column already exists: check schema)
- Add a management endpoint or Celery task to reprocess all tracks with
  version < current:

```
POST /management/reprocess-outdated       — enqueue reprocessing for old-version tracks
```

- The existing `reprocess_track` task handles the actual reprocessing
- Just need the trigger: query tracks where `processor_version < CURRENT`,
  enqueue each for reprocessing

---

## 7. Event Logger: Add Missing Entity Types

**Current state:** `log_created`, `log_updated`, `log_deleted` work for any
entity but are only called from gear and user routes. As new CRUD routes
are added (segments, routes, journeys, trips, etc.), event logging must be
consistently applied.

**Improvement:**

Establish a convention: every CRUD endpoint calls the appropriate log function.
The gear router is the reference pattern. Create a checklist for new routers:

```
CREATE → log_created(db, entity, user_id)
UPDATE → log_updated(db, entity, old_values, changes, user_id)
DELETE → log_deleted(db, entity, user_id)
```

Consider a decorator or middleware to automate this, but the explicit approach
is clearer and already working.

---

## 8. Permission System: Fine-Grained Access Policies

**Current state:** `resource_access` and `check_object_access` handle basic
ownership checks. But access policies for new entities (routes, segments,
journeys) need:

- Public vs. private visibility (routes can be public; segments within a
  public route should be readable even if the segment creator differs)
- Follower-only visibility
- Access to entities within a shared journey/route

**Improvements:**

- Add resource_type registrations for: segment, route, journey, trip, waypoint,
  schedule, body_metric, pace_curve
- Define access policies:
  - `segment`: owner can CRUD; public segments readable by all
  - `route`: owner can CRUD; public routes readable by all; segments within
    public routes readable via route context
  - `trip`: owner can CRUD; public trips readable by followers or all
- Wire `PublicMixin.is_public` into `check_object_access` for read operations

---

## 9. API Response Consistency

**Current state:** All endpoints use `ok()` / `ok_list()` wrappers returning
`ApiResponse[T]`. This is good and consistent.

**Improvements:**

- Standardize error responses: currently some errors return raw HTTPException,
  others return structured errors. Define a consistent error schema:
  ```json
  { "status": "error", "code": "not_found", "message": "Route not found" }
  ```
- Add request-ID to error responses (the middleware adds it to headers but
  not the body)
- Standardize pagination: `ok_list` returns `total`, `limit`, `offset` but
  some endpoints may need cursor-based pagination for large datasets (e.g.
  points transaction history)

---

## 10. Database: Missing Indexes

**Current state:** The schema has indexes on primary keys and unique
constraints, but may be missing indexes needed for common query patterns.

**Recommendation:** Add indexes for:

```sql
-- Fast lookup of user's tracks by date
CREATE INDEX IF NOT EXISTS ix_explorer_agg_track_user_date
ON explorer_agg_track (created_by, recorded_at DESC)
WHERE archived_at IS NULL;

-- Fast lookup of user's statistics
CREATE INDEX IF NOT EXISTS ix_profile_sub_statistic_user_scope
ON profile_sub_statistic (user_id, scope, scope_year, scope_month);

-- Comment lookup by entity
CREATE INDEX IF NOT EXISTS ix_social_sub_comment_entity
ON social_sub_comment (entity_type, entity_id);

-- Rating lookup by entity
CREATE INDEX IF NOT EXISTS ix_social_sub_rating_entity
ON social_sub_rating (entity_type, entity_id);

-- POI detection: spatial index on route column (should already exist via PostGIS)
-- Verify with: SELECT * FROM pg_indexes WHERE tablename = 'explorer_sub_geo_record';
```

Run `EXPLAIN ANALYZE` on common queries to identify actual bottlenecks
before adding indexes blindly.

---

## 11. WebSocket: Job Status for New Features

**Current state:** WebSocket support exists for job status notifications
(track processing). As new background jobs are added (predictions, pace
curve recomputation, achievement evaluation), they need to publish events.

**Improvement:**

The `TrackedTask` base class and `publish_job_event` function already handle
this. New tasks just need to:
1. Use `TrackedTask` as their base class
2. Register a `JobKind` for the new task type
3. The job system handles the rest (progress, completion, failure events)

This is not a code change — it's a convention to follow when implementing
new Celery tasks.

---

## 12. Test Coverage

**Current state:** Limited test infrastructure visible. GPX processing
pipeline has complex logic that would benefit from unit tests.

**Priority test areas:**

1. **GPX metrics:** geometry_metrics and performance_metrics with known inputs
   - Edge cases: single-point tracks, no elevation, no timestamps, gaps
2. **POI detection:** detect_for_track with mock data
   - Test radius matching, visit deduplication, card granting
3. **Stats recomputation:** recompute_user_statistics with known track data
   - Test all scope levels, sport_type breakdowns, streak calculation
4. **Route continuity validation:** (when implemented)
   - Adjacent segment matching, alt-group handling, reversed segments
5. **Permission system:** check_object_access with various access policies

---

## Implementation Priority

| Priority | Area | Effort | Impact |
|----------|------|--------|--------|
| **P0** | Social module (routes + schemas) | Medium | Blocks likes, ratings, comments |
| **P0** | Permission system for new entities | Medium | Blocks public routes/journeys |
| **P1** | Settings singleton | Trivial | Performance, correctness |
| **P1** | Stats: filter archived tracks | Small | Data correctness |
| **P1** | Event logger in new routes | Small (per route) | Audit completeness |
| **P2** | Orphan cleanup expansion | Small | Data hygiene |
| **P2** | Track processing error messages | Small | User experience |
| **P2** | Missing indexes | Small | Performance |
| **P2** | WebSocket for new jobs | Small (per task) | User experience |
| **P3** | API response consistency | Medium | Developer experience |
| **P3** | Processor version tracking | Small | Future-proofing |
| **P3** | Test coverage | Large | Confidence |
| **P3** | Archived track handling | Medium | Feature completeness |
