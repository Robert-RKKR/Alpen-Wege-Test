# Profile: User-Editable Content — Implementation Plan

## Overview

User-editable profile data is content the user creates and manages directly.
Full CRUD: create, read, update, delete. Four areas:

```
Profile (User-Editable)
  ├── Schedule (planned activities with status tracking)
  ├── Body Metrics (daily weight log)
  ├── Pace Curves (speed vs gradient, per sport type)
  └── Likes (bookmarked routes and journeys)
```

All of these are **user-scoped** (via `UserScopedMixin`), meaning each row
belongs to exactly one user. The user sees only their own data.

---

## Core Design Decisions

### Schedule entries are user-managed, status is tracked

A schedule entry links a user to a planned route or journey with a target date.
The user creates and manages these. Status transitions are:

```
planned → in_progress → completed
planned → skipped
planned → cancelled
```

Status is driven by `status_id` (FK to `core_ref_schedule_status`). When the
user records a track that matches the scheduled route, the GUI prompts to
link it (`track_id`) and move status to completed.

### Body metrics are one-per-day, append-mostly

Weight entries are keyed by `(user_id, recorded_at)` — one measurement per
day. The typical flow is: user logs weight, data accumulates over weeks/months,
user views a trend graph. Delete is allowed but rare.

### Pace curves are system-derived but user-adjustable

Pace curve data (`profile_sub_pace_curve`) stores the user's typical speed at
each gradient bin for a given sport type. The initial data is computed from
the user's track history (a background job). The user can then manually
adjust values.

The curve is used by the prediction system to estimate route completion times.

### Likes are simple toggles

Like/unlike a route or journey. One row per (user, entity). No payload beyond
the FK. Used for bookmarking and social signal (like count on entities).

---

## Models (existing)

| Model | Table | Key columns |
|-------|-------|-------------|
| `ProfileSubSchedule` | `profile_sub_schedule` | route_id OR journey_id (CHECK: at least one), track_id, trip_id, planned_at, completed_at, status_id, notes |
| `ProfileSubBodyMetric` | `profile_sub_body_metric` | recorded_at (Date, NOT NULL, unique per user), weight_kg (NOT NULL) |
| `ProfileSubPaceCurve` | `profile_sub_pace_curve` | sport_type_id (NOT NULL), gradient_bin (int, NOT NULL), speed_kmh (NOT NULL), sample_points (NOT NULL); unique per (user, sport, gradient) |
| `ProfileM2mLikedRoute` | `profile_m2m_liked_route` | route_id (NOT NULL, CASCADE); unique per (user, route) |
| `ProfileM2mLikedJourney` | `profile_m2m_liked_journey` | journey_id (NOT NULL, CASCADE); unique per (user, journey) |

---

## API Endpoints

### Schedule

```
GET    /profile/me/schedule               — list scheduled activities (paginated, status filter)
POST   /profile/me/schedule               — create a schedule entry
GET    /profile/me/schedule/{id}          — get schedule entry detail
PATCH  /profile/me/schedule/{id}          — update (change date, status, notes, link track)
DELETE /profile/me/schedule/{id}          — delete schedule entry
```

Query parameters for GET list:
- `status`: filter by status name (planned, completed, skipped, cancelled)
- `from_date`, `to_date`: filter by planned_at range
- `sort`: planned_at asc/desc (default: planned_at asc for upcoming)

### Body Metrics

```
GET    /profile/me/body-metrics           — list measurements (paginated, date range)
POST   /profile/me/body-metrics           — add measurement
PATCH  /profile/me/body-metrics/{id}      — update measurement
DELETE /profile/me/body-metrics/{id}      — delete measurement
```

Query parameters:
- `from_date`, `to_date`: date range filter
- Response includes `trend` when requested: list of `[date, weight_kg]` pairs

No GET by ID needed — the list endpoint with date range covers the use case.

### Pace Curves

```
GET    /profile/me/pace-curves                    — list all curves (grouped by sport_type)
GET    /profile/me/pace-curves/{sport_type_id}    — get curve for one sport
PUT    /profile/me/pace-curves/{sport_type_id}    — replace entire curve for one sport
DELETE /profile/me/pace-curves/{sport_type_id}    — delete curve for one sport
POST   /profile/me/pace-curves/recompute          — trigger background recomputation
```

The PUT payload replaces all gradient bins for the sport type at once:

```json
{
  "bins": [
    { "gradient_bin": -15, "speed_kmh": 5.2 },
    { "gradient_bin": -10, "speed_kmh": 4.8 },
    { "gradient_bin": -5,  "speed_kmh": 4.5 },
    { "gradient_bin": 0,   "speed_kmh": 4.0 },
    { "gradient_bin": 5,   "speed_kmh": 3.2 },
    { "gradient_bin": 10,  "speed_kmh": 2.5 },
    { "gradient_bin": 15,  "speed_kmh": 1.8 }
  ]
}
```

Server:
1. Delete existing rows for (user_id, sport_type_id)
2. Insert new rows with `sample_points = 0` (manual entry)
3. If recomputed data existed, manual override takes precedence

POST `/recompute`:
1. Enqueues a Celery task
2. Task scans user's tracks, groups by sport_type
3. For each track: extract speed at each gradient_bin from the GPX data
4. Aggregate across tracks (weighted average by distance at each gradient)
5. Upsert rows with actual sample_points count
6. Returns 202 with job reference

### Likes

```
POST   /profile/me/likes/routes/{route_id}     — like a route
DELETE /profile/me/likes/routes/{route_id}      — unlike a route
GET    /profile/me/likes/routes                 — list liked routes (paginated)

POST   /profile/me/likes/journeys/{journey_id}  — like a journey
DELETE /profile/me/likes/journeys/{journey_id}   — unlike a journey
GET    /profile/me/likes/journeys               — list liked journeys (paginated)
```

Like POST is idempotent — liking an already-liked entity returns 200 (not 409).
Unlike DELETE is also idempotent — unliking something not liked returns 204.

---

## User Flows

### Flow 1: Plan an activity

```
GUI                                   API
──────────────────────────────────────────────────

User opens route detail ─────────── GET /explorer/routes/{id}
User clicks "Add to Schedule" ───── POST /profile/me/schedule
                                    { "route_id": "uuid",
                                      "planned_at": "2025-08-15T06:00:00Z",
                                      "notes": "bring crampons" }
                                    → 201: { schedule entry }

Later, user records track... ─────── (track upload + processing)

User opens schedule, marks done ─── PATCH /profile/me/schedule/{id}
                                    { "status_id": "completed-uuid",
                                      "track_id": "uuid",
                                      "completed_at": "2025-08-15T14:30:00Z" }
```

### Flow 2: Track weight over time

```
GUI                                   API
──────────────────────────────────────────────────

User opens "Body Metrics" ──────── GET /profile/me/body-metrics
                                    ?from_date=2025-01-01
                                    → 200: { list of measurements }

GUI renders weight chart

User logs today's weight ───────── POST /profile/me/body-metrics
                                    { "recorded_at": "2025-07-20",
                                      "weight_kg": 78.5 }
                                    → 201: { measurement }
```

### Flow 3: View and adjust pace curve

```
GUI                                   API
──────────────────────────────────────────────────

User opens "Pace Curves" ───────── GET /profile/me/pace-curves
                                    → 200: { curves grouped by sport }

User clicks "Recompute from
my tracks" ──────────────────────── POST /profile/me/pace-curves/recompute
                                    → 202: { job_id }

WS notification ─────────────────── (job completed)

User refreshes ──────────────────── GET /profile/me/pace-curves
                                    → 200: { updated curves with sample_points }

User adjusts flat-terrain speed ─── PUT /profile/me/pace-curves/{sport_id}
                                    { "bins": [...modified...] }
                                    → 200: { replaced curve }
```

### Flow 4: Like a route

```
GUI                                   API
──────────────────────────────────────────────────

User views route, clicks heart ──── POST /profile/me/likes/routes/{id}
                                    → 200

Heart icon fills in

User opens "My Likes" ──────────── GET /profile/me/likes/routes
                                    → 200: { paginated list of liked routes }
```

---

## Schemas

### Schedule

```
ScheduleCreate:
  route_id: UUID | None
  journey_id: UUID | None
  planned_at: datetime (required)
  status_id: UUID (required, default: "planned" status)
  notes: str | None

ScheduleUpdate (all optional):
  route_id, journey_id
  planned_at, completed_at
  status_id
  track_id, trip_id
  notes

ScheduleRead:
  id, route_id, journey_id, track_id, trip_id
  planned_at, completed_at
  status: RefRead (nested status name)
  notes
  route: RouteRead | None (nested, when expanded)
  journey: JourneyRead | None
  created_at, updated_at
```

### Body Metrics

```
BodyMetricCreate:
  recorded_at: date (required)
  weight_kg: float (required, > 0)

BodyMetricUpdate:
  weight_kg: float (required, > 0)

BodyMetricRead:
  id, recorded_at, weight_kg, created_at
```

### Pace Curves

```
PaceCurveBin:
  gradient_bin: int (required)
  speed_kmh: float (required, > 0)

PaceCurveReplace:
  bins: list[PaceCurveBin] (required, min 1)

PaceCurveRead:
  sport_type_id: UUID
  sport_type: RefRead (nested)
  bins: list[PaceCurveBinRead]

PaceCurveBinRead:
  gradient_bin, speed_kmh, sample_points
```

### Likes

```
LikedRouteRead:
  id, route_id
  route: RouteRead (nested summary)
  created_at

LikedJourneyRead:
  id, journey_id
  journey: JourneyRead (nested summary)
  created_at
```

---

## Services

### schedule_service.py

```python
async def create_schedule(session, data, user_id) -> ProfileSubSchedule
async def update_schedule(session, schedule, changes) -> ProfileSubSchedule
async def delete_schedule(session, schedule) -> None
async def list_schedule(session, user_id, filters) -> list
```

Validation:
- CHECK constraint `route_id IS NOT NULL OR journey_id IS NOT NULL` is enforced at DB level
- Validate route/journey exists and is accessible to the user
- Validate status_id is a valid schedule status ref

### body_metric_service.py

```python
async def create_metric(session, data, user_id) -> ProfileSubBodyMetric
async def update_metric(session, metric, changes) -> ProfileSubBodyMetric
async def delete_metric(session, metric) -> None
async def list_metrics(session, user_id, from_date, to_date) -> list
```

Handle unique constraint violation on `(user_id, recorded_at)` — return
409 with "measurement already exists for this date".

### pace_curve_service.py

```python
async def get_curves(session, user_id) -> dict[UUID, list]
async def get_curve(session, user_id, sport_type_id) -> list
async def replace_curve(session, user_id, sport_type_id, bins) -> list
async def delete_curve(session, user_id, sport_type_id) -> None
```

Background recomputation (sync, Celery):
```python
def recompute_pace_curves(session, user_id) -> dict
```

Recomputation algorithm:
1. Query all user's tracks with geo_performance (has timing data)
2. Group by sport_type_id
3. For each track:
   - Load GPX and compute speed at each point (from the processed data)
   - Bin each point by its local grade into gradient_bin buckets
   - Weight by distance covered
4. For each (sport_type, gradient_bin): weighted average speed
5. Upsert into pace_curve table with actual sample_points

### like_service.py

```python
async def like_route(session, user_id, route_id) -> ProfileM2mLikedRoute
async def unlike_route(session, user_id, route_id) -> None
async def list_liked_routes(session, user_id, pagination) -> list

async def like_journey(session, user_id, journey_id) -> ProfileM2mLikedJourney
async def unlike_journey(session, user_id, journey_id) -> None
async def list_liked_journeys(session, user_id, pagination) -> list
```

Like operations use INSERT ... ON CONFLICT DO NOTHING for idempotency.
Unlike uses DELETE with no error if row doesn't exist.

---

## Celery Tasks

### recompute_pace_curves (new)

```python
@shared_task(name="profile.recompute_pace_curves", base=TrackedTask, ...)
def recompute_pace_curves_task(user_id: str):
    with SyncSessionLocal() as session:
        result = recompute_pace_curves(session, UUID(user_id))
        session.commit()
    return result
```

Trigger: manual (user clicks "Recompute") or after significant track processing
batch (e.g. bulk import).

---

## Open Issues

### 1. Schedule auto-completion

**Question:** Should the system automatically mark a schedule entry as completed
when a matching track is processed?

**Recommendation:** No auto-completion. Instead, show a notification: "You completed
a track on the Inntal Ridge route — mark your scheduled activity as done?" The
user confirms and links the track. Auto-completion risks false positives (the
user may have done a different route nearby).

### 2. Body metric history depth

**Question:** Should old body metrics be archived or pruned?

**Recommendation:** Keep all data. The storage cost is negligible (one row per day,
~365 rows/year). The trend chart benefits from long history.

### 3. Pace curve granularity

**Question:** What gradient bins should be used? Current model has `gradient_bin`
as a free integer.

**Recommendation:** Standardize on 5% increments: -20, -15, -10, -5, 0, 5, 10,
15, 20, 25, 30. The recomputation service uses these bins; manual entry can
use any value but the GUI should present the standard set. Validate
gradient_bin is between -100 and 100.

### 4. Like counts on entities

**Question:** Should routes/journeys have a `like_count` field that is maintained,
or compute it at read time?

**Recommendation:** Store `like_count` on the entity (route/journey) and update
it atomically with `UPDATE ... SET like_count = like_count + 1`. The cost of
a count query per read is too high at scale. Use a trigger or service-level
increment.

### 5. Pace curve conflict: manual vs. recomputed

**Question:** If the user manually adjusts their pace curve and then triggers
recomputation, should manual values be overwritten?

**Recommendation:** Flag manually-edited bins. Add a `is_manual` boolean to
the pace_curve model (or track via `sample_points = 0` convention). Recomputation
skips bins where `is_manual = true` unless the user explicitly selects
"Reset to computed values".

---

## Implementation Phases

### Phase 1: Schedule
- Schedule router (CRUD under /profile/me/schedule)
- Schedule schemas
- Schedule service with validation
- Status transition validation (e.g. can't go from completed → planned)

### Phase 2: Body Metrics
- Body metric router (CRUD under /profile/me/body-metrics)
- Body metric schemas
- Date range query support
- Unique constraint handling

### Phase 3: Likes
- Like router (toggle endpoints under /profile/me/likes/)
- Idempotent like/unlike
- Paginated list of liked entities
- Optional: update like_count on route/journey models

### Phase 4: Pace Curves
- Pace curve router (read/replace/delete per sport type)
- Recompute endpoint + Celery task
- Pace curve computation algorithm
- Integration with prediction system
