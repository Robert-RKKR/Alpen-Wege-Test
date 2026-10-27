# Explorer planned hierarchy: implementation plan v2

Replaces the open issues and phases of `plan_explorer_hierarchy.md` (v1). The concept, the data model and user flows 1 to 9 of v1 stay valid, with the changes listed here. Decisions and open checks: `plan_explorer_hierarchy_decisions.md` (D1 to D9, C1 to C9).

```
Journey (multi-day plan)  -> days, each one Route
  Route (one-day outing)  -> ordered slots, each slot has 1 default Segment and optional alternatives
    Segment (trail stretch) -> one geo_record (geometry and metrics, no time data)
```

Segments never change their geometry. A "changed" segment is a new segment placed in the same slot.

## 1. What exists in the repo today (checked 2026-10-26)

- Models and link tables exist: `ExplorerAggSegment`, `ExplorerAggRoute`, `ExplorerAggJourney`, `ExplorerM2mSegmentRoute`, `ExplorerM2mRouteJourney`, `ExplorerM2mSegmentPoi`, `ExplorerM2mSegmentPhoto`.
- No routes, schemas or services for them. `explorer/routes/__init__.py` mounts only `gear` and `track`.
- Permission keys `segment`, `route`, `journey` are seeded with the four actions create, read, update, delete. `PUT .../segments` therefore uses `("route", "update")`.
- The GPX pipeline works without timestamps (`performance=None`). `process_gpx_file(path)` only accepts a file path; there is no entry point for already parsed points (see 3.2).
- `core/utils/listing.py`, `core/utils/expand.py` and `core/utils/scope.py` (`apply_scope`) are the standard way for lists and detail views. New resources must use them.
- The rank table seed data lives in `push_data/core_ref_*.csv`.

## 2. Step 0: `rank` on four reference tables

Tables: `difficulty_level`, `difficulty_sport`, `rarity`, `visibility` (C1). Meaning: higher number = harder / rarer / worse.

| Table | Seed values |
|---|---|
| `difficulty_level` | Very Easy 1, Easy 2, Moderate 3, Difficult 4, Very Difficult 5, Expert 6, Extreme 7 |
| `rarity` | Common 1, Uncommon 2, Rare 3, Epic 4, Legendary 5, Mythic 6 |
| `visibility` | Excellent 1, Very Good 2, Good 3, Moderate 4, Poor 5, Low 6, Very Low 7, Whiteout 8 |
| `difficulty_sport` | per `sport_type_id`: dense order of `point_factor` (ties keep the same rank). `point_factor` is already increasing inside every grading system. UIAA and French share the climbing sport type, so their mix (for example UIAA V next to French 6a) needs your review. |

Changes:

1. `core/base.py`: new `ReferenceWithRankMixin(ReferenceWithFactorMixin)` with `rank: Mapped[int]` (SmallInteger, NOT NULL, comment says "higher = ..."). The 4 models use it.
2. `core/schemas/ref.py`: `RefRankedCreate/Update/Read/Detail`. `DifficultySport*` derive from them.
3. In the four folders `core/routes/ref/<table>/`: `create.py`, `update.py`, `get_one.py` use the ranked schemas; `get_many.py` adds `"rank"` to `SORT` and gets `rank_min`/`rank_max` filters. `upload_csv.py` needs no change if `import_csv` reads the model columns (to be checked in the sandbox).
4. `push_data/core_ref_<table>.csv` for the four tables get a `rank` column.
5. Tests: `tests/test_list_routes.py` (sort fields), a test that `rank` is required on create, a test that CSV import loads it. Postman collection regenerated.
6. Test database (one script): `ALTER TABLE ... ADD COLUMN rank smallint NOT NULL DEFAULT 0;` for the four tables, then `UPDATE` with the seed values (CASE by `icon`; `difficulty_sport` with `dense_rank() OVER (PARTITION BY sport_type_id ORDER BY point_factor)`). The script is run on a copy in the sandbox before it is handed over.

## 3. Schema changes (test database, all in one script)

| Table | Change |
|---|---|
| `explorer_agg_route` | `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id` become nullable (D1) |
| `explorer_m2m_segment_route` | FK `segment_id`: `ON DELETE CASCADE` becomes `RESTRICT` (D4); unique `(route_id, slot_position, segment_id)`; partial unique index on `(route_id, alt_group) WHERE is_default` (at most one default per group; "exactly one" is checked in code); index on `segment_id` |
| `explorer_m2m_route_journey` | FK `route_id`: CASCADE becomes `RESTRICT` (C5); unique `(journey_id, slot_position)`; index on `route_id` |
| four reference tables | `rank` (section 2) |

The models are changed first so a fresh `create_all` builds the same schema; the script is only for the existing test database.

## 4. Rules

### 4.1 Visibility and delete protection (D4, D7, C5, C6)

- A user may reference only segments they own or public ones (scope `all` sees everything). Anything else answers 404, so existence is not leaked. Same for routes in journeys.
- `DELETE /segments/{id}`: 409 when any `segment_route` row exists. The body has the count and only the routes the caller may see. Same for `DELETE /routes/{id}` with `route_journey`.
- A segment cannot be set private while a route of another user or a public route uses it (409). Same for routes and journeys.
- Publishing a route (`is_public` true) publishes its own segments in the same transaction. A segment owned by someone else must already be public, otherwise 422.
- New standalone segments (`POST /segments`, `/from-coordinates`, `/from-track`) start private unless the body says `is_public`. Inline segments take the route's `is_public` at creation.
- Lists and single reads of segments, routes and journeys use `apply_scope` and `check_object_access` like gear. Tests cover each combination.

### 4.2 Segment creation (D5, D7, D8, C8, C9)

| Endpoint | Input | Processing |
|---|---|---|
| `POST /explorer/segments` | multipart GPX + metadata | threadpool, file limit `SEGMENT_GPX_MAX_UPLOAD_MB` (proposal 2). Times, heart rate and cadence of all points are dropped before processing. The file is deleted afterwards; `gpx_id` stays NULL |
| `POST /explorer/segments/from-coordinates` | JSON `[[lon, lat, ele?], ...]` + metadata | same processing; caps below |
| `POST /explorer/segments/from-track` | `track_id`, `start_distance_m`, `end_distance_m` + metadata | only the track owner (scope `all` may do it for others). Loads the stored GPX, parses and cleans it, cuts by distance, drops times and heart rate, processes |

Inline segments in `PUT /routes/{id}/segments` use the same builder as `/from-coordinates` and `/from-track`. An inline GPX is not supported: upload it first with `POST /segments`.

Caps (settings, with these proposed defaults): `SEGMENT_DRAW_MAX_POINTS` 5,000 per segment; `ROUTE_SAVE_MAX_POINTS` 20,000 per save; `ROUTE_MAX_SEGMENTS` 50 per route; at least 2 points; latitude and longitude ranges checked. Over a cap: 422.

Each creation: build the geo record (no performance row), set `start_location`, `end_location`, `route`, then run the existing start/end POI detection against the start and end points. Segment POIs along the trail and photos are a later step (v1 Issue 4); they are not needed to build routes.

### 4.3 Continuity (replaces the v1 algorithm)

Effective start and end of a segment: its start and end, swapped when `is_reversed`.
Two points are connected when their POI ids are equal or their distance is at most `CONTINUITY_THRESHOLD_M` (proposal 50). A different POI does not fail by itself; the distance decides.

1. Structure: slots are 0 to n-1 without gaps; `alt_group` equals `slot_position` (v1 rule kept: multi-slot alternatives are not supported); every slot has exactly one default.
2. Alternatives: every alternative's effective start and end are connected to the default's effective start and end of the same slot.
3. Chain: for each pair of neighbour slots, effective end of the default in slot N is connected to effective start of the default in slot N+1.

Rules 2 and 3 together prove every path A, D, C, so the v1 "every combination" check is dropped.

Result: `is_valid`, `errors` (missing geometry or location), `warnings` (slot, kind, distance_m). `validation: "strict"` (default for save) answers 422 on any error or warning; `"warn"` saves and returns the warnings. Journeys: gaps between days only give warnings (`JOURNEY_GAP_WARN_M` proposal 500); the day's `poi_id` is the real link.

### 4.4 Aggregates and classification (D1, D2, D6, C2, C4, C7)

Route aggregates come from the default segments only: distance and elevation gain and loss summed (gain and loss swapped for a reversed segment), highest point = max, lowest = min, `agg_duration_s` NULL (filled by Prediction later). A route without segments: all aggregates NULL.

Classification on save, only when the field is empty:
- `sport_type_id`: the sport with the most distance among the default segments.
- `difficulty_level_id`: the level with the highest `rank` among the default segments' levels.
- `difficulty_sport_id`: among the default segments of the route's primary sport, the grade with the highest `rank`.
- Segments without a value are ignored. No value at all: the field stays NULL.

Detail responses add computed, read-only fields: `sport_types` (default segments: sport, `distance_m`, `segment_count`, ordered by distance) and `derived` (`sport_type_id`, `difficulty_level_id`, `difficulty_sport_id` as they would be computed now) with `classification_differs`. No new columns.

Journey aggregates: sums of its routes, `length_days` = number of days, `agg_duration_s` only when every route has one. Classification rule as for routes (level by `rank`; sport as most distance). After every route save, all journeys that contain the route are recomputed in the same transaction.

### 4.5 Route geometry (v1 Issue 3, option C)

`GET /routes/{id}/geometry` returns the combined geojson and elevation graph of the default segments. Each segment's graph distances (which start at 0) get the length of all segments before it as offset. For a reversed segment the coordinates are reversed, the graph is mirrored (`d` becomes `length - d`, order reversed). Alternatives are returned as separate lines with their slot, not joined into the main line.

### 4.6 Other issues of v1

| v1 issue | v2 |
|---|---|
| 5 Plan conditions | Option A kept: `plan_conditions` object inside route/journey create and update (one row per owner, created or updated in the same transaction). |
| 6 Real-time validation | `POST /routes/{id}/segments/validate` accepts `segment_id` items and `{"start": [lon, lat], "end": [lon, lat]}` items for unsaved drawings; no inline coordinates. |
| 8 Orphan segments | Option B kept: never delete automatically. `GET /segments?mine=true&unused=true` lists the user's unused segments. |
| 9 Inline ownership | `created_by` is the user who saved. |
| 10 Concurrency | Last write wins. |

## 5. Files (Phase 3 layout: one folder per resource, one file per action)

```
explorer/routes/segment/  _router.py (/segments) __init__.py get_many get_one create create_from_coordinates create_from_track update delete
explorer/routes/route/    _router.py (/routes)   __init__.py get_many get_one create update delete
                          set_segments get_segments validate_segments geometry
explorer/routes/journey/  _router.py (/journeys) __init__.py get_many get_one create update delete set_routes get_routes
explorer/schemas/         segment.py route.py journey.py  (Read, Detail with Link fields for ?expand=, Create, Update)
explorer/services/        segment_build.py  segment_persist.py  continuity.py  aggregate.py
                          classification.py  route_geometry.py  visibility.py
explorer/services/gpx/pipeline.py   new process_cleaned(cleaned, limits)
```

- `process_gpx_file` is split: the part after `clean()` becomes `process_cleaned(cleaned, limits)`; `process_gpx_file` calls it. Test: output for the 5 GPX sample variants is identical before and after.
- `routes/__init__.py` mounts the three routers. The expand and filter conventions (`get_many` with `Filters` class, `SORT`, `expand_plan(Detail)`) follow `gear` and `track`.
- The segment `PATCH` changes metadata only (name, summary, description, l18n, sport, difficulty, POIs, `is_public`). Geometry is not editable.
- Settings added to `config.py`: the caps in 4.2, `CONTINUITY_THRESHOLD_M`, `JOURNEY_GAP_WARN_M`, `SEGMENT_GPX_MAX_UPLOAD_MB`.

## 6. Phases and exit checks

Each phase: models first, then code, then checks in the sandbox; delivery as in the earlier deliveries (backup tarball, file-list hash, route map compare, Postman collection regenerated).

| Phase | Content | Exit checks |
|---|---|---|
| 0 | `rank` (section 2) and the schema script (section 3) | tests green; route map shows only the intended new fields; script run on a copy; Postman `rank` requests |
| 1 | Segments: pipeline split, builder, persist, 3 create endpoints, get, update, delete with protection | the 5 GPX samples give the same track results as before the split; segment from GPX with times has no performance and no stored file; clip removes times and heart rate; timing of the largest allowed segment GPX and a clip of a large track (C9); visibility tests; 409 tests |
| 2 | Routes: CRUD, `set_segments` with inline segments, continuity, aggregates, classification, geometry, validate | continuity unit tests (reverse, alternatives, POI match, gap, missing location); aggregates equal a hand calculation; elevation graph offset test; classification never overwrites a set value; publish/unpublish tests; atomic rollback test (a failed validation leaves no new segments) |
| 3 | Journeys: CRUD, `set_routes`, aggregates, route-save recompute (C4), route delete protection | journey recomputed after a route change; 409 on route delete; warn-only gaps |

## 7. Tests and tools

- New tests: `tests/test_segments.py`, `tests/test_routes_planned.py`, `tests/test_journeys.py`, `tests/test_continuity.py`, `tests/test_aggregate.py`; `tests/test_routes_standard.py` must stay green; list sort/filter fields added to `tests/test_list_routes.py`.
- A live check script in the style of `list_check.py` and `expand_check.py` for flows 1 to 8 of v1 (draw, mixed, variant, edit geometry, reverse, clip, multi-sport), run against Postgres, Redis, Celery and uvicorn in the sandbox.
- Mutation test of the continuity and visibility checks with deliberate mistakes on a copy (lesson of the routes migration), and an independent review pass before delivery.
- The Postman collection is regenerated for the new resources and the `rank` fields.

## 8. Not in scope

Segment POIs and photos endpoints, Prediction (see `plan_recorded_hierarchy.md`), social features (ratings feed `rating_avg`), schedule and likes (see the profile plans), multi-slot alternatives, optimistic locking, automatic orphan cleanup, and deployment to the host (the host still runs none of the delivered work; one combined runbook will cover this too).
