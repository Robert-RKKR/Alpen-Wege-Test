# Profile: Sticky Event-Log Data — Implementation Plan

## Overview

Sticky event-log data represents **permanent records of things that happened**.
The user can read them but not delete them. They accumulate over time as the
user completes activities, visits POIs, and earns achievements.

```
Profile (Sticky Event-Log)
  ├── Points (gamification point transactions)
  ├── Achievements (earned achievement records)
  ├── Cards (collectible cards from POI visits)
  └── User POIs (POI visit log)
```

**Key principle:** These rows are created by system events (track processing,
POI detection, achievement evaluation). The user does not create them directly.
Some allow a user-editable `comment` field, but the row itself cannot be
deleted — it's a historical record.

---

## Core Design Decisions

### No DELETE endpoints

These are event logs. Deleting a point transaction or POI visit would break
the audit trail. The data is append-only from the user's perspective.

Exception: if a track is deleted, CASCADE rules clean up related rows
(track_id SET NULL on points/achievements, CASCADE on track_poi). But the
user cannot directly delete individual event-log rows.

### Cards and User POIs are auto-created

The `poi_detection` service already creates both:
- `profile_m2m_user_poi`: created when a track passes near a collectable POI
- `profile_m2m_user_card`: created when a POI visit matches a card's POI

This happens in the `detect_for_track()` function, which runs as a Celery
task after track processing. No new write logic needed — only read endpoints.

### Achievements are evaluated by an achievement engine

The achievement engine (not yet built) evaluates criteria against user
statistics after each stats recomputation. When criteria are met, it creates
a `profile_m2m_user_achievement` row and optionally a `profile_sub_point` row.

### Points are awarded by multiple triggers

Point transactions are created by:
- Achievement earned → points based on achievement's `point_factor` × rarity
- Track completed → base points for activity
- POI visited → points for discovery
- Trip completed → bonus points

Each transaction references a `reason_id` (FK to `core_ref_point_reason`)
and optionally links to the triggering entity (track_id, trip_id,
user_achievement_id).

---

## Models (existing)

| Model | Table | Key columns | Auto-created by |
|-------|-------|-------------|-----------------|
| `ProfileSubPoint` | `profile_sub_point` | received_at, points, reason_id, user_achievement_id, track_id, trip_id | Achievement engine, track processing, POI detection |
| `ProfileM2mUserAchievement` | `profile_m2m_user_achievement` | achievement_id, collected_at, comment, is_repeat, track_id, trip_id | Achievement engine |
| `ProfileM2mUserCard` | `profile_m2m_user_card` | card_id (unique per user), collected_at, comment, track_id | POI detection (`detect_for_track`) |
| `ProfileM2mUserPoi` | `profile_m2m_user_poi` | poi_id, collected_at, comment, track_id; unique (user, poi, track) | POI detection (`detect_for_track`) |

Note: `ProfileCatAchievement` is the achievement **definition** (catalog),
not user data. It has: name, criteria (JSONB), point_factor, is_active,
is_repeatable, rarity_id, category_id, criteria_scope_id, criteria_type_id.

---

## API Endpoints

### Points

```
GET /profile/me/points                    — list point transactions (paginated)
GET /profile/me/points/summary            — total points + breakdown by reason
```

List query parameters:
- `from_date`, `to_date`: filter by received_at
- `reason_id`: filter by point reason
- Sort: received_at desc (default, most recent first)

Summary response:
```json
{
  "total_points": 15400,
  "by_reason": [
    { "reason": { "id": "...", "name": "Activity Completed" }, "total": 8200 },
    { "reason": { "id": "...", "name": "POI Visited" }, "total": 3500 },
    { "reason": { "id": "...", "name": "Achievement Earned" }, "total": 2800 },
    { "reason": { "id": "...", "name": "Trip Completed" }, "total": 900 }
  ]
}
```

### Achievements

```
GET /profile/me/achievements              — list earned achievements (paginated)
GET /profile/me/achievements/{id}         — get achievement detail
PATCH /profile/me/achievements/{id}       — update comment only
GET /profile/me/achievements/progress     — list in-progress achievements
```

List query parameters:
- `category_id`: filter by achievement category
- `rarity_id`: filter by rarity
- Sort: collected_at desc (default)

The `progress` endpoint returns achievements the user has not yet earned
but has partial progress toward. This requires the achievement engine to
track intermediate progress (future feature).

PATCH is limited to the `comment` field only — no other fields are editable.

### Cards

```
GET /profile/me/cards                     — list collected cards (paginated)
GET /profile/me/cards/{id}                — get card detail
PATCH /profile/me/cards/{id}              — update comment only
GET /profile/me/cards/summary             — collection progress summary
```

List query parameters:
- `poi_id`: filter cards by POI
- Sort: collected_at desc (default)

Summary response:
```json
{
  "total_collected": 45,
  "total_available": 120,
  "completion_percent": 37.5,
  "by_region": [
    { "region": { "id": "...", "name": "Stubai Alps" }, "collected": 12, "available": 25 },
    { "region": { "id": "...", "name": "Zillertal" }, "collected": 8, "available": 18 }
  ]
}
```

### User POIs (visit log)

```
GET /profile/me/pois                      — list visited POIs (paginated)
GET /profile/me/pois/{id}                 — get visit detail
PATCH /profile/me/pois/{id}               — update comment only
GET /profile/me/pois/map                  — all visited POI locations (for map rendering)
```

List query parameters:
- `poi_id`: filter by specific POI
- Sort: collected_at desc (default)

Map endpoint returns a compact format for rendering all visits on a map:
```json
{
  "visits": [
    { "poi_id": "uuid", "lat": 47.12, "lon": 11.45, "name": "Innsbrucker Hütte", "visit_count": 3 }
  ]
}
```

This endpoint groups by POI (a user may visit the same POI on multiple tracks)
and returns the count.

### Public profile endpoints

For other users' public profiles:

```
GET /profile/users/{id}/achievements      — public achievement list
GET /profile/users/{id}/cards/summary     — public card collection summary
```

Access follows the same rules as public statistics.

---

## User Flows

### Flow 1: View points history

```
GUI                                   API
──────────────────────────────────────────────────

User opens "My Points" ─────────── GET /profile/me/points/summary
                                    → 200: { total, by_reason }

Dashboard shows total points
and pie chart by reason

User scrolls transaction list ───── GET /profile/me/points?page=1
                                    → 200: { list of transactions }

Each row shows:
  "+50 pts — Activity Completed — Jul 15, 2025"
  "+200 pts — Achievement: Peak Bagger — Jul 10, 2025"
```

### Flow 2: View achievement collection

```
GUI                                   API
──────────────────────────────────────────────────

User opens "Achievements" ──────── GET /profile/me/achievements
                                    → 200: { list with achievement details }

GUI renders achievement grid:
  - Earned: full color with collected_at date
  - Available: greyed out with progress bar (future)

User clicks earned achievement ──── GET /profile/me/achievements/{id}
                                    → 200: { achievement + linked track/trip }

User adds a comment ─────────────── PATCH /profile/me/achievements/{id}
                                    { "comment": "My proudest moment!" }
```

### Flow 3: Browse card collection

```
GUI                                   API
──────────────────────────────────────────────────

User opens "Card Collection" ────── GET /profile/me/cards/summary
                                    → 200: { collected/available per region }

GUI renders album view:
  - Cards organized by region
  - Collected: revealed with artwork
  - Not collected: silhouette/placeholder

User taps collected card ────────── GET /profile/me/cards/{id}
                                    → 200: { card detail + POI + track link }
```

### Flow 4: View POI visits on map

```
GUI                                   API
──────────────────────────────────────────────────

User opens "My POIs" map view ───── GET /profile/me/pois/map
                                    → 200: { visits with locations }

GUI renders map with markers
for all visited POIs, colored
by visit count

User clicks marker ──────────────── GET /profile/me/pois?poi_id={id}
                                    → 200: { all visits to this POI }

Shows visit dates and linked tracks
```

---

## Schemas

### Points

```
PointRead:
  id, received_at, points
  reason: RefRead (nested)
  user_achievement_id: UUID | None
  track_id: UUID | None
  trip_id: UUID | None
  created_at

PointSummaryRead:
  total_points: int
  by_reason: list[PointReasonBreakdown]

PointReasonBreakdown:
  reason: RefRead
  total: int
```

### Achievements

```
UserAchievementRead:
  id, collected_at, comment, is_repeat
  achievement: AchievementRead (nested)
  track_id: UUID | None
  trip_id: UUID | None
  created_at

AchievementRead:
  id, name, summary, description, l18n fields
  point_factor
  rarity: RefRead
  category: RefRead
  is_repeatable

UserAchievementUpdate:
  comment: str | None
```

### Cards

```
UserCardRead:
  id, collected_at, comment
  card: CardRead (nested, from compendium)
  track_id: UUID | None
  created_at

UserCardUpdate:
  comment: str | None

CardCollectionSummary:
  total_collected, total_available, completion_percent
  by_region: list[RegionCardBreakdown]
```

### User POIs

```
UserPoiRead:
  id, collected_at, comment
  poi: PoiRead (nested)
  track_id: UUID | None
  created_at

UserPoiUpdate:
  comment: str | None

UserPoiMapRead:
  visits: list[PoiVisitMapItem]

PoiVisitMapItem:
  poi_id, lat, lon, name, visit_count
```

---

## Services

### point_service.py (read-only + write for system)

```python
async def list_points(session, user_id, filters) -> list
async def get_points_summary(session, user_id) -> dict

# Write operations called by other services (not API):
async def award_points(session, user_id, points, reason_id, **links) -> ProfileSubPoint
```

`award_points` is called by:
- Track processing service (after successful processing)
- Achievement engine (when achievement earned)
- POI detection (when new POI visited)

### achievement_service.py (read + evaluate)

```python
async def list_achievements(session, user_id, filters) -> list
async def get_achievement(session, user_id, achievement_id) -> dict
async def update_comment(session, user_achievement, comment) -> ProfileM2mUserAchievement

# Engine (runs in background):
def evaluate_achievements(session, user_id) -> list[ProfileM2mUserAchievement]
```

`evaluate_achievements`:
1. Load user's statistics (from `profile_sub_statistic`)
2. Load all active achievements not yet earned by user
3. For each achievement, evaluate `criteria` JSONB against stats
4. If criteria met: create `ProfileM2mUserAchievement` + award points
5. Return list of newly earned achievements

Criteria JSONB evaluation example:
```json
{
  "type": "threshold",
  "field": "total_distance_m",
  "scope": "all",
  "value": 1000000
}
```
→ Check if user's lifetime total_distance_m >= 1,000,000.

### card_service.py (read-only at API level)

```python
async def list_cards(session, user_id, filters) -> list
async def get_card(session, user_id, card_id) -> dict
async def update_comment(session, user_card, comment) -> ProfileM2mUserCard
async def get_collection_summary(session, user_id) -> dict
```

`get_collection_summary`:
1. Count user's collected cards
2. Count total available cards (from `compendium_cat_card` where POI is collectable)
3. Group by region (join card → POI → poi_region → region)

### user_poi_service.py (read-only at API level)

```python
async def list_visits(session, user_id, filters) -> list
async def get_visit(session, user_id, visit_id) -> dict
async def update_comment(session, user_poi, comment) -> ProfileM2mUserPoi
async def get_visit_map(session, user_id) -> list
```

`get_visit_map`:
1. Query all user's POI visits
2. Join with POI to get location
3. Group by poi_id, count visits
4. Return compact list for map rendering

---

## Celery Tasks

### evaluate_achievements (new)

```python
@shared_task(name="profile.evaluate_achievements")
def evaluate_achievements_task(user_id: str):
    with SyncSessionLocal() as session:
        new_achievements = evaluate_achievements(session, UUID(user_id))
        session.commit()
    return {"earned": len(new_achievements)}
```

**Trigger:** Called after `recompute_user_statistics` completes. The chain is:

```
track processed → detect_pois → recompute_statistics → evaluate_achievements
```

Each step enqueues the next.

### award_activity_points (new)

```python
@shared_task(name="profile.award_activity_points")
def award_activity_points_task(user_id: str, track_id: str):
    with SyncSessionLocal() as session:
        # Base points for completing a track
        award_points(session, UUID(user_id), points=50,
                     reason_id=ACTIVITY_COMPLETED_REASON_ID,
                     track_id=UUID(track_id))
        session.commit()
```

**Trigger:** After track processing succeeds (in the existing pipeline,
after `persist_processed_track`).

---

## Open Issues

### 1. Achievement criteria DSL

**Question:** How complex should the criteria JSONB evaluation be?

**Recommendation:** Start simple with a fixed set of criteria types:
- `threshold`: single stat field >= value
- `streak`: current_streak_days >= value
- `collection`: unique_pois_count >= value
- `cumulative`: total_X >= value over scope

Complex criteria (visit 3 specific POIs, complete a route in under X hours)
can be added later with a plugin pattern. Don't build a full DSL upfront.

### 2. Achievement progress tracking

**Question:** Should the system track partial progress toward achievements?

**Recommendation:** Yes, but as a computed value at read time, not stored.
When the user views an achievement they haven't earned, compute
`current_value / target_value` from their statistics. This avoids storing
and maintaining progress rows.

### 3. Points balance vs. total

**Question:** Can points be spent? Is there a balance separate from total?

**Recommendation:** Points are a total accumulator, not a currency. There's
no spending mechanism. The `total_points` in statistics is the sum of all
`profile_sub_point.points` rows. If spending is added later, add a negative
points transaction with a "spent" reason.

### 4. Card artwork/images

**Question:** How are card images stored and served?

**Recommendation:** Cards reference their POI, which can have photos via
the compendium. The card table itself doesn't store images — the GUI
renders the card design from the card's metadata (rarity, POI type, region)
and the POI's photo. This is a frontend concern.

### 5. User POI comment timing

**Question:** When can a user add a comment to a POI visit?

**Recommendation:** Anytime after the visit is created. The PATCH endpoint
updates only the comment field. There's no time restriction. The comment
is personal annotation (trail conditions, memories), not a public review.

### 6. Duplicate achievement prevention

**Question:** How to prevent duplicate non-repeatable achievements?

**Already handled:** The partial unique index
`ix_profile_m2m_user_achievement_unique_first` on `(user_id, achievement_id)
WHERE NOT is_repeat` prevents duplicates at the DB level. The achievement
engine checks `is_repeatable` before inserting.

---

## Implementation Phases

### Phase 1: Points (read endpoints)
- Points router (GET list, GET summary)
- Point schemas
- Point service (list + summary queries)
- award_points write helper for internal use
- Register router

### Phase 2: User POIs + Cards (read endpoints)
- User POI router (GET list, GET detail, PATCH comment, GET map)
- Card router (GET list, GET detail, PATCH comment, GET summary)
- Schemas for both
- Services with collection summary computation

### Phase 3: Achievements (read + engine)
- Achievement router (GET list, GET detail, PATCH comment)
- Achievement schemas
- Achievement evaluation engine (criteria DSL)
- Celery task for background evaluation
- Wire into stats recomputation chain

### Phase 4: Points (write automation)
- award_activity_points task
- Wire point awarding into existing pipelines
- POI visit points
- Achievement points (via achievement engine)
