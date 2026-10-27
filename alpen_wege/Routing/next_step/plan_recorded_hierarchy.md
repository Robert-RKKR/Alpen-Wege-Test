# Explorer Recorded Hierarchy: Implementation Plan

## Overview

The recorded hierarchy captures **actual activities** — what the user did, as opposed
to what they planned. It mirrors the planned hierarchy but is anchored to GPS tracks.

```
Trip (multi-day recorded adventure)
  └── Track (one GPS-recorded activity)
        ├── Waypoint (notable stop along the track)
        ├── Photo (attached images)
        └── POI visit (auto-detected or manual)

Prediction (estimated completion time for a planned route)
  └── based on user's pace_curve + route geometry
```

The **Track** already exists and is fully implemented (upload, GPX processing,
persist, POI detection, stats recompute). This plan covers Trip, Waypoint, and
Prediction — the three missing pieces.

---

## Core Design Decisions

### Trips group tracks into multi-day adventures

A trip is a user-created grouping of tracks. Unlike a journey (which groups
planned routes), a trip groups *recorded* tracks. Each track in the trip gets
a slot_position and day label via `explorer_m2m_track_trip`.

A trip does not own any geometry. Its map view is a composite of its tracks'
geo_records. Aggregate stats (total distance, total elevation) are computed
from the member tracks at read time — not stored.

### Waypoints are standalone entities linked to tracks

A waypoint (`explorer_sub_waypoint`) is a named stop with location, altitude,
and timing. Waypoints are created by the user — they are not auto-detected
like POIs.

Waypoints link to tracks via `explorer_m2m_track_waypoint` with slot_position
for ordering along the track. A waypoint can optionally reference a compendium
POI (via `poi_id`) but stands on its own even without one.

### Waypoints can also attach to trip-track slots

The `explorer_m2m_track_trip` table has a nullable `waypoint_id`. This lets
a specific track-in-trip slot reference a waypoint (e.g. "Day 2 started at
the mountain hut"). This is a convenience link, not a requirement.

### Predictions are read-only computed estimates

A prediction estimates how long a user will take to complete a planned route,
based on their pace curve and the route's geometry. Predictions are:

- Created by a background service (not direct user input)
- Immutable once created (new prediction = new row with new model_version)
- Scoped to one user + one route
- Stored with their input snapshot (`inputs` JSONB) for reproducibility

---

## Models (existing)

| Model | Table | Key columns |
|-------|-------|-------------|
| `ExplorerAggTrip` | `explorer_agg_trip` | name (NOT NULL), length_days, first_day, last_day, sport_type_id |
| `ExplorerSubWaypoint` | `explorer_sub_waypoint` | name, summary, description, location (Point), altitude_m, arrived_at, departed_at, duration_min, poi_id |
| `ExplorerSubPrediction` | `explorer_sub_prediction` | route_id (NOT NULL, CASCADE), predicted_s (NOT NULL), predicted_moving_s, model_version (NOT NULL), inputs (JSONB), track_id (optional) |
| `ExplorerM2mTrackTrip` | `explorer_m2m_track_trip` | track_id, trip_id, waypoint_id, slot_position, day_name (NOT NULL), day_summary, day_description |
| `ExplorerM2mTrackWaypoint` | `explorer_m2m_track_waypoint` | track_id, waypoint_id, slot_position |

Mixins: Trip has `IdentificationL18nMixin` (l18n fields), `CreatorMixin`, `PublicMixin`, `TimestampMixin`.
Waypoint and Prediction have `TimestampMixin`; Prediction also has `CreatorMixin`.

---

## API Endpoints

### Trip CRUD

```
GET    /explorer/trips                    — list user's trips (paginated, scope filter)
POST   /explorer/trips                    — create empty trip
GET    /explorer/trips/{id}               — get trip with tracks + waypoints
PATCH  /explorer/trips/{id}               — update trip metadata
DELETE /explorer/trips/{id}               — delete trip (CASCADE removes M2M links)
```

### Trip ↔ Track management

```
PUT    /explorer/trips/{id}/tracks        — set the ordered list of tracks in the trip
GET    /explorer/trips/{id}/tracks        — get tracks in order with day labels
```

The PUT payload is the full ordered list (replace semantics, same pattern as
route segments):

```json
{
  "tracks": [
    {
      "track_id": "uuid",
      "day_name": "Day 1: Approach",
      "day_summary": "Easy hike to base camp",
      "day_description": "...",
      "waypoint_id": null
    },
    {
      "track_id": "uuid",
      "day_name": "Day 2: Summit",
      "waypoint_id": "uuid"
    }
  ]
}
```

Server:
1. Validate all track_ids belong to the current user (or are public)
2. Delete existing `explorer_m2m_track_trip` rows for this trip
3. Insert new rows with auto-assigned slot_position (from array order)
4. Recompute trip aggregates (length_days, first_day, last_day from track dates)
5. Optionally derive sport_type_id from tracks (same logic as route: most distance wins)

### Waypoint CRUD

```
GET    /explorer/waypoints                — list user's waypoints
POST   /explorer/waypoints                — create waypoint
GET    /explorer/waypoints/{id}           — get waypoint detail
PATCH  /explorer/waypoints/{id}           — update waypoint
DELETE /explorer/waypoints/{id}           — delete waypoint (CASCADE removes M2M)
```

Waypoints can also be created inline when managing a track's waypoints:

```
PUT    /explorer/tracks/{id}/waypoints    — set waypoints along a track
GET    /explorer/tracks/{id}/waypoints    — get waypoints for a track
```

The PUT payload supports both existing references and inline creation:

```json
{
  "waypoints": [
    { "waypoint_id": "uuid" },
    {
      "inline": {
        "name": "Lunch spot",
        "location": { "lat": 47.12, "lon": 11.45 },
        "altitude_m": 2150,
        "arrived_at": "2025-07-15T12:00:00Z",
        "departed_at": "2025-07-15T12:45:00Z"
      }
    }
  ]
}
```

This follows the same inline pattern established for segments in routes.

### Prediction endpoints

Predictions are read-only for the user. They are generated by the system.

```
GET    /explorer/routes/{id}/prediction   — get latest prediction for current user + route
POST   /explorer/routes/{id}/prediction   — request a new prediction (triggers background job)
GET    /explorer/predictions              — list user's recent predictions
```

POST `/routes/{id}/prediction`:
1. Validates the route exists and has geometry (at least one segment with geo_record)
2. Checks the user has a pace curve for the route's sport_type
3. Enqueues a Celery task to compute the prediction
4. Returns `202 Accepted` with job reference

The prediction task:
1. Loads route geometry (all default segments' geo_records)
2. Loads user's pace curve for the relevant sport_type(s)
3. For each segment: compute estimated time from distance + elevation profile + pace curve
4. Sum segment times, add estimated stop time
5. Insert `ExplorerSubPrediction` row with model_version and inputs snapshot
6. Notify via WebSocket (job completion)

---

## User Flows

### Flow 1: Create a trip from existing tracks

```
GUI                                   API
──────────────────────────────────────────────────

User opens "My Trips" ──────────── GET /explorer/trips
User clicks "New Trip" ─────────── POST /explorer/trips
                                    { "name": "Stubai Haute Route" }
                                    → 201: { trip }

Trip editor shows user's tracks ─── GET /explorer/tracks?scope=me

User drags tracks into order,
fills day labels ────────────────── PUT /explorer/trips/{id}/tracks
                                    { "tracks": [...] }
                                    → 200: { trip with tracks }
```

### Flow 2: Add waypoints to a track

```
GUI                                   API
──────────────────────────────────────────────────

User opens track detail ─────────── GET /explorer/tracks/{id}
User clicks map to add waypoint ─── (GUI collects name, location from click)

User saves waypoints ────────────── PUT /explorer/tracks/{id}/waypoints
                                    { "waypoints": [
                                        { "inline": { "name": "Summit", "location": {...} } },
                                        { "inline": { "name": "Hut", "poi_id": "uuid" } }
                                    ]}
                                    → 200: { waypoints with IDs }
```

### Flow 3: Request a route prediction

```
GUI                                   API
──────────────────────────────────────────────────

User views route detail ─────────── GET /explorer/routes/{id}
                                    GET /explorer/routes/{id}/prediction
                                    → 200: { prediction } or 404

User clicks "Estimate my time" ──── POST /explorer/routes/{id}/prediction
                                    → 202: { job_id }

WebSocket delivers result ───────── WS: { job completed }
GUI refreshes prediction ────────── GET /explorer/routes/{id}/prediction
                                    → 200: { predicted_s, predicted_moving_s, inputs }
```

### Flow 4: View trip on map

```
GUI                                   API
──────────────────────────────────────────────────

User opens trip detail ──────────── GET /explorer/trips/{id}
                                    → 200: { trip + tracks with geo_records }

GUI renders composite map:
  - Each track's geojson in a different color
  - Waypoints as markers
  - Day labels as annotations
```

---

## Schemas

### Trip

```
TripCreate:
  name: str (required)
  summary, description, name_de, name_pl, summary_de, ... : str | None
  sport_type_id: UUID | None
  is_public: bool = false

TripUpdate (all optional):
  name, summary, description, l18n fields
  sport_type_id, is_public

TripRead:
  id, name, summary, description, l18n fields
  sport_type_id, sport_type (nested read)
  length_days, first_day, last_day
  is_public, created_at, updated_at
  tracks: list[TripTrackRead] (when expanded)

TripTrackRead:
  slot_position, day_name, day_summary, day_description
  track: TrackRead (nested)
  waypoint: WaypointRead | None
```

### Waypoint

```
WaypointCreate:
  name: str | None
  summary, description: str | None
  location: PointInput (lat, lon) | None
  altitude_m: int | None
  arrived_at, departed_at: datetime | None
  poi_id: UUID | None

WaypointUpdate: same fields, all optional

WaypointRead:
  id, name, summary, description
  location: PointRead | None
  altitude_m, arrived_at, departed_at, duration_min
  poi: PoiRead | None (when poi_id set)
  created_at, updated_at
```

### Prediction

```
PredictionRead:
  id, route_id
  predicted_s, predicted_moving_s
  model_version
  inputs: dict | None (input snapshot)
  track_id: UUID | None (calibration track)
  created_at
```

---

## Services

### trip_service.py

```python
async def create_trip(session, data, user_id) -> ExplorerAggTrip
async def update_trip(session, trip, changes) -> ExplorerAggTrip
async def delete_trip(session, trip) -> None
async def set_trip_tracks(session, trip_id, tracks_payload, user_id) -> list
async def recompute_trip_aggregates(session, trip) -> None
```

`recompute_trip_aggregates`:
- Query all tracks in the trip (via M2M), ordered by slot_position
- `length_days` = count distinct dates from track recorded_at values
- `first_day` = min recorded_at date
- `last_day` = max recorded_at date
- `sport_type_id` = most-distance sport from tracks (same logic as route)

### waypoint_service.py

```python
async def create_waypoint(session, data, user_id) -> ExplorerSubWaypoint
async def update_waypoint(session, waypoint, changes) -> ExplorerSubWaypoint
async def delete_waypoint(session, waypoint) -> None
async def set_track_waypoints(session, track_id, payload, user_id) -> list
```

`set_track_waypoints`:
- Accept mixed list of `{ waypoint_id }` references and `{ inline: {...} }` blocks
- Create inline waypoints, then insert all M2M rows with slot_position
- If inline waypoint has `poi_id`, validate POI exists
- Compute `duration_min` from arrived_at / departed_at if both present

### prediction_service.py

```python
def compute_prediction(session, user_id, route_id) -> ExplorerSubPrediction
```

This runs in a Celery task (sync):
1. Load route's default segments with geo_records
2. Load user's pace_curve rows for relevant sport_type(s)
3. For each segment:
   - Sample elevation profile from geo_record's elevation_graph
   - For each sub-section, look up pace from the matching gradient_bin
   - Accumulate predicted time
4. Add stop time estimate (configurable ratio, e.g. 20% of moving time)
5. Insert prediction row with inputs snapshot:
   `{ pace_curve_ids, segment_ids, stop_ratio, model_version }`

---

## Celery Tasks

### predict_route_time (new)

```python
@shared_task(name="routes.predict_time", base=TrackedTask, ...)
def predict_route_time(user_id: str, route_id: str):
    with SyncSessionLocal() as session:
        prediction = compute_prediction(session, UUID(user_id), UUID(route_id))
        session.commit()
    return {"prediction_id": str(prediction.id), "predicted_s": prediction.predicted_s}
```

### Existing tasks that interact with the recorded hierarchy

- `process_track_gpx` → already implemented, creates geo_record
- `detect_pois` → already implemented, links POIs to tracks
- `recompute_user_statistics` → already implemented, aggregates from tracks

New trigger: after a trip is created/modified, request stats recompute
(trips affect `total_plans_created/completed` counts).

---

## Open Issues

### 1. Trip aggregate storage vs. computation

**Question:** Should trip aggregates (total_distance, total_elevation, total_time)
be stored on the trip row or computed at read time?

**Recommendation:** Compute at read time. Trips are small (typically 2-14 tracks),
so the join cost is negligible. Storing aggregates creates a sync problem when
tracks are reprocessed or removed.

### 2. Waypoint location: manual vs. snapped to track

**Question:** When a user clicks the map to place a waypoint, should the location
be the raw click point or snapped to the nearest track point?

**Recommendation:** Offer both. Default to snap-to-track with an option to
place freely. Snapping uses the same `nearest_visit()` logic from poi_detection.

### 3. Prediction model versioning

**Question:** How to handle invalidation when the user's pace curve changes or
the route's segments change?

**Recommendation:** Don't invalidate. Each prediction stores its inputs snapshot.
The GUI shows the prediction date and offers "Re-estimate" if the prediction is
older than the last route edit or pace curve update. Old predictions remain for
comparison.

### 4. Track-to-trip auto-suggestion

**Question:** Should the system suggest grouping consecutive-day tracks into a trip?

**Recommendation:** Yes, as a background task. After track processing, check if
the user has other tracks within ±1 day of the new track's date. If so, suggest
a trip grouping via notification. Do not auto-create.

### 5. Waypoint photos

**Question:** Can waypoints have photos?

**Recommendation:** Not directly. Photos attach to tracks (via `explorer_m2m_track_photo`).
A waypoint references a point along the track — the GUI can show nearby photos
by matching slot_positions. Adding a separate waypoint-photo M2M would add
complexity without clear benefit.

---

## Implementation Phases

### Phase 1: Trip CRUD + Track management
- Trip router with standard CRUD
- PUT /trips/{id}/tracks endpoint
- Trip schemas (create, update, read)
- Trip service with aggregate recomputation
- Register trip router in explorer.__init__

### Phase 2: Waypoints
- Waypoint router with standard CRUD
- PUT /tracks/{id}/waypoints with inline creation
- Waypoint schemas
- Waypoint service
- Register waypoint router

### Phase 3: Predictions
- Prediction service (core computation logic)
- Celery task for background prediction
- GET/POST prediction endpoints on route router
- Prediction schema
- Integration with job system (TrackedTask)

### Phase 4: Integration
- Trip auto-suggestion background task
- Waypoint snap-to-track logic
- Prediction re-estimation triggers
- WebSocket notifications for prediction completion
