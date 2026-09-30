# Executed Activities -- API Actions Execution Plan

> Covers all user actions related to **recorded/executed activities** (tracks, trips, and their
> associated entities). Each action lists required data, optional data, processing blocks,
> affected tables, and side-effects on statistics/achievements/points.

---

## Table of Contents

1. [Design Decisions](#1-design-decisions)
2. [Processing Blocks Reference](#2-processing-blocks-reference)
3. [Track Actions](#3-track-actions)
   - [ACT-01: Create Track (manual entry)](#act-01-create-track-manual-entry)
   - [ACT-02: Create Track (with GPX file)](#act-02-create-track-with-gpx-file)
   - [ACT-03: Edit Track Metadata](#act-03-edit-track-metadata)
   - [ACT-04: Edit Track Conditions](#act-04-edit-track-conditions)
   - [ACT-05: Replace Track GPX](#act-05-replace-track-gpx)
   - [ACT-06: Delete Track](#act-06-delete-track)
   - [ACT-07: Manage Track Photos](#act-07-manage-track-photos)
   - [ACT-08: Manage Track Gear](#act-08-manage-track-gear)
   - [ACT-09: Manage Track POIs](#act-09-manage-track-pois)
   - [ACT-10: Manage Track Waypoints](#act-10-manage-track-waypoints)
4. [Trip Actions](#4-trip-actions)
   - [ACT-11: Create Trip](#act-11-create-trip)
   - [ACT-12: Edit Trip](#act-12-edit-trip)
   - [ACT-13: Delete Trip](#act-13-delete-trip)
   - [ACT-14: Assign Track to Trip](#act-14-assign-track-to-trip)
   - [ACT-15: Remove Track from Trip](#act-15-remove-track-from-trip)
5. [Side-Effect Policies](#5-side-effect-policies)
6. [Action-to-Block Matrix](#6-action-to-block-matrix)

---

## 1. Design Decisions

### 1.1 What the user can and cannot edit

| Aspect | Editable? | Reason |
|--------|-----------|--------|
| Name, summary, description | YES | Descriptive metadata, no impact on stats |
| Sport type | YES | User might misclassify; changes point_factor, pace_curve, stats per sport |
| Difficulty level / sport difficulty | YES | Subjective assessment |
| Conditions (weather, trail, snow) | YES | Recalled from memory, may need correction |
| Recorded date (`recorded_at`) | YES | User may import old activities or fix timezone issues |
| Start/end POI | YES | User picks from catalog, may correct |
| Visibility (`is_public`) | YES | Privacy toggle |
| Main photo | YES | User preference |
| **GPS data (map, distance, elevation)** | **NO** | Factual record from GPX; changing it would falsify stats. User must delete and re-upload if GPX was wrong |
| **Performance data (time, speed, HR)** | **NO** | Derived from GPX; same reasoning as above |

### 1.2 Delete vs. achievement integrity

The schema uses `ON DELETE SET NULL` on `profile_m2m_user_achievement.track_id`,
`profile_sub_point.track_id`, `profile_m2m_user_card.track_id`, and `profile_m2m_user_poi.track_id`.
This means **deleting a track does NOT revoke achievements, points, cards, or POI visits**.

**Policy: "Earned is earned"**
- Achievements, cards, and POI visits are permanent once awarded. If you climbed a peak and got
  the badge, deleting the GPS track doesn't un-climb the peak.
- Points from achievements/cards stay as well (they reference `user_achievement_id`, not `track_id` directly).
- Points awarded directly for the track activity (reason = "activity_completed") **should be
  soft-revoked**: insert a negative-points correction row in `profile_sub_point` with
  `reason_id` = "activity_deleted".
- Statistics (`profile_sub_statistic`) are **always recalculated** to reflect the actual current
  data. A user who deletes a 50km track will see 50km less in their totals, even if they keep
  the "100km total" achievement badge.
- Pace curve (`profile_sub_pace_curve`) **is recalculated** from remaining tracks.

### 1.3 Sport type change and cascading recalculations

When `sport_type_id` changes on a track:
- Points for activity may change (different `point_factor`).
- Statistics recalculate for both old and new sport type.
- Pace curve recalculates for both old and new sport type.
- Achievements may need re-evaluation (a hiking achievement won't count a cycling track).

---

## 2. Processing Blocks Reference

Reusable processing blocks that actions reference. Each block is atomic and independently testable.

### B01 -- GPX File Upload

| Field | Value |
|-------|-------|
| **Input** | GPX file binary, user_id |
| **Tables** | `asset_agg_gpx` |
| **Steps** | 1. Validate file format (valid GPX XML). 2. Generate unique filename/path. 3. Store file on disk/object storage. 4. Insert row into `asset_agg_gpx` with `path`, `name`, `created_by`. |
| **Output** | `gpx_id` (uuid) |

### B02 -- GPX Parse to Geo Record

| Field | Value |
|-------|-------|
| **Input** | `gpx_id` |
| **Tables** | `explorer_sub_geo_record`, reads `asset_agg_gpx` |
| **Steps** | 1. Read GPX file from storage. 2. Parse trackpoints. 3. Calculate: `distance_m`, `elevation_gain_m`, `elevation_loss_m`, `highest_elevation_m`, `lowest_elevation_m`, `total_points`, `avg_grade`, `highest_grade`. 4. Build `geojson` (LineString). 5. Build `elevation_graph` (jsonb array of distance→elevation). 6. Detect `track_types` (jsonb, surface categories if encoded in GPX extensions). 7. Extract `start_location` and `end_location` (first/last point as PostGIS Point). 8. Compute `elevation` (start altitude, for display). 9. Insert row into `explorer_sub_geo_record`. |
| **Output** | `geo_record_id` (uuid) |

### B03 -- GPX Parse to Geo Performance

| Field | Value |
|-------|-------|
| **Input** | GPX trackpoints (from B02 parse), optional heart rate data |
| **Tables** | `explorer_sub_geo_performance` |
| **Steps** | 1. Calculate time metrics: `started_at`, `ended_at`, `total_time_s`. 2. Detect stops (speed < threshold) → `moving_time_s`, `stop_time_s`, `moving_ratio`. 3. Speed: `avg_speed_kmh`, `moving_avg_speed_kmh`, `max_speed_kmh`. 4. Ascent/descent speeds: `ascent_avg_speed_kmh`, `descent_avg_speed_kmh`, `max_ascent_speed_kmh`, `max_descent_speed_kmh`. 5. Heart rate (if available): `avg_heart_rate`, `max_heart_rate`, `min_heart_rate`, `heart_graph`. 6. Estimate `calories_burned` (from HR + user weight/age, or from MET × time × weight). 7. `steps_count` (if available from GPX extensions). 8. Build `speed_pattern` (jsonb, speed over time/distance). 9. Insert row into `explorer_sub_geo_performance`. |
| **Output** | `geo_performance_id` (uuid) |
| **Note** | Links to geo_record via `explorer_sub_geo_record.geo_performance_id` |

### B04 -- Create / Update Conditions

| Field | Value |
|-------|-------|
| **Input** | Condition data (temperatures, visibility, snow, trail, weather refs) |
| **Tables** | `explorer_sub_conditions` |
| **Steps** | 1. Validate all reference IDs exist. 2. INSERT or UPDATE `explorer_sub_conditions`. |
| **Output** | `condition_id` (uuid) |

### B05 -- Create Track Record

| Field | Value |
|-------|-------|
| **Input** | Track metadata + `geo_record_id` + `condition_id` + user_id |
| **Tables** | `explorer_agg_track` |
| **Steps** | 1. Validate all FK references. 2. INSERT into `explorer_agg_track`. |
| **Output** | `track_id` (uuid) |

### B06 -- Link Photos to Track

| Field | Value |
|-------|-------|
| **Input** | `track_id`, list of `{photo_id, slot_position}` |
| **Tables** | `explorer_m2m_track_photo` |
| **Steps** | 1. Validate photos exist and belong to user. 2. INSERT rows into `explorer_m2m_track_photo`. |
| **Output** | -- |

### B07 -- Link Gear to Track

| Field | Value |
|-------|-------|
| **Input** | `track_id`, list of `{gear_id, slot_position, notes}` |
| **Tables** | `explorer_m2m_track_gear` |
| **Steps** | 1. Validate gear exists and belongs to user. 2. INSERT rows into `explorer_m2m_track_gear`. |
| **Output** | -- |

### B08 -- Link POIs to Track

| Field | Value |
|-------|-------|
| **Input** | `track_id`, list of `{poi_id, slot_position, distance_m}` |
| **Tables** | `explorer_m2m_track_poi` |
| **Steps** | 1. Validate POIs exist. 2. INSERT rows into `explorer_m2m_track_poi`. |
| **Output** | -- |

### B09 -- Link Waypoints to Track

| Field | Value |
|-------|-------|
| **Input** | `track_id`, list of waypoint data |
| **Tables** | `explorer_sub_waypoint`, `explorer_m2m_track_waypoint` |
| **Steps** | 1. For each waypoint: INSERT into `explorer_sub_waypoint` (name, location, altitude, arrived_at, departed_at, duration_min, poi_id). 2. Link via INSERT into `explorer_m2m_track_waypoint`. |
| **Output** | -- |

### B10 -- Auto-Detect POIs Near Track

| Field | Value |
|-------|-------|
| **Input** | `geo_record_id` (has geojson LineString) |
| **Tables** | reads `compendium_cat_poi`, `explorer_sub_geo_record` |
| **Steps** | 1. Buffer the track LineString by a threshold (e.g. 100m). 2. Query `compendium_cat_poi` where `ST_DWithin(location, track_line, 100)`. 3. For each hit, compute `distance_m` along track to the nearest point. 4. Return list of `{poi_id, distance_m}` sorted by distance along track. |
| **Output** | List of candidate POIs for user confirmation |
| **Note** | User should confirm which POIs they actually visited; auto-detect is a suggestion |

### B11 -- Award POI Visits

| Field | Value |
|-------|-------|
| **Input** | `user_id`, `track_id`, list of `poi_id` |
| **Tables** | `profile_m2m_user_poi` |
| **Steps** | 1. For each POI: INSERT into `profile_m2m_user_poi` with `ON CONFLICT (user_id, poi_id) DO NOTHING` (first visit wins). 2. Collect list of newly-awarded POI visit IDs. |
| **Output** | List of newly visited POI IDs (not previously visited) |

### B12 -- Award Cards from POI Visits

| Field | Value |
|-------|-------|
| **Input** | `user_id`, `track_id`, list of newly visited `poi_id` |
| **Tables** | `compendium_cat_card`, `profile_m2m_user_card` |
| **Steps** | 1. Query cards linked to newly-visited POIs: `SELECT * FROM compendium_cat_card WHERE poi_id = ANY(...)`. 2. For each card: INSERT into `profile_m2m_user_card` with `ON CONFLICT (user_id, card_id) DO NOTHING`. |
| **Output** | List of newly collected card IDs |

### B13 -- Evaluate Achievements

| Field | Value |
|-------|-------|
| **Input** | `user_id`, `track_id`, event context (new track / modified track / new trip) |
| **Tables** | `profile_cat_achievement`, `profile_m2m_user_achievement`, reads `profile_sub_statistic` |
| **Steps** | 1. Load all active achievements: `SELECT * FROM profile_cat_achievement WHERE is_active = true`. 2. For each achievement, evaluate `criteria` (jsonb) against current user state (statistics, track data, POI visits, card count, etc.). 3. Check if already awarded: query `profile_m2m_user_achievement`. 4. If criteria met AND (not awarded OR `is_repeatable = true`): INSERT into `profile_m2m_user_achievement` with `track_id` and `collected_at = now()`. Set `is_repeat = true` if repeatable and already exists. |
| **Output** | List of newly awarded achievement IDs |
| **Note** | This is the most complex block. Achievement criteria types include: cumulative distance, elevation, activity count, streak, specific POI visits, region coverage, card collection, etc. |

### B14 -- Award Points

| Field | Value |
|-------|-------|
| **Input** | `user_id`, `track_id`, list of events (activity completed, achievements earned, cards collected, POIs visited) |
| **Tables** | `profile_sub_point` |
| **Steps** | 1. For "activity_completed": calculate points from `sport_type.point_factor × distance/elevation formula`. INSERT into `profile_sub_point` with `reason_id` = activity_completed, `track_id`. 2. For each new achievement: INSERT with `reason_id` = achievement_earned, `user_achievement_id`. Points = `achievement.point_factor × rarity.point_factor`. 3. For each new card: INSERT with `reason_id` = card_collected. 4. For each new POI visit: INSERT with `reason_id` = poi_visited. |
| **Output** | Total points awarded in this action |

### B15 -- Update Statistics

| Field | Value |
|-------|-------|
| **Input** | `user_id`, optional `scope_hint` (which scopes need refresh) |
| **Tables** | `profile_sub_statistic`, reads `explorer_agg_track`, `explorer_sub_geo_record`, `explorer_sub_geo_performance`, `profile_sub_point`, `profile_m2m_user_poi`, `compendium_m2m_poi_region`, `profile_sub_schedule` |
| **Steps** | 1. Determine affected scopes: `all`, `year` (for track's year), `month` (for track's year+month). 2. For each scope, recalculate from source data: `total_distance_m` = SUM of all geo_record.distance_m for user's tracks in scope. `total_elevation_m` = SUM of elevation_gain_m. `total_activities` = COUNT of tracks. `total_time_s` = SUM of geo_performance.total_time_s. `total_points` = SUM from profile_sub_point. `unique_pois_count` = COUNT DISTINCT from profile_m2m_user_poi. `unique_regions_count` = derived from POI regions. 3. Recalculate streak data (current_streak_days, longest_streak_days) from track dates. 4. Build graph jsonb fields (distance over time, elevation over time, etc.). 5. Update plan stats: total_plans_created, completed, skipped from profile_sub_schedule. 6. UPSERT into `profile_sub_statistic` for each scope. |
| **Output** | -- |
| **Note** | This is a heavy operation. In production, consider async/worker-based recalculation. |

### B16 -- Update Pace Curve

| Field | Value |
|-------|-------|
| **Input** | `user_id`, `sport_type_id` |
| **Tables** | `profile_sub_pace_curve`, reads `explorer_agg_track`, `explorer_sub_geo_record`, `explorer_sub_geo_performance` |
| **Steps** | 1. Collect all tracks for user + sport type that have geo_record + geo_performance. 2. For each track, extract speed at various gradient bins from the GPX data. 3. Aggregate across tracks: average speed per gradient_bin weighted by sample_points. 4. UPSERT into `profile_sub_pace_curve` for each gradient_bin. |
| **Output** | -- |

### B17 -- Revoke Activity Points

| Field | Value |
|-------|-------|
| **Input** | `user_id`, `track_id`, original activity points amount |
| **Tables** | `profile_sub_point` |
| **Steps** | 1. Find the original "activity_completed" point row for this track. 2. INSERT a new correction row with negative `points` value and `reason_id` = "activity_deleted". |
| **Output** | -- |
| **Note** | Points ledger is append-only (immutable). We never DELETE from profile_sub_point. |

### B18 -- Cascade Delete Track Sub-entities

| Field | Value |
|-------|-------|
| **Input** | `track_id` |
| **Tables** | `explorer_sub_geo_record`, `explorer_sub_geo_performance`, `explorer_sub_conditions`, `explorer_sub_waypoint`, `asset_agg_gpx`, m2m tables |
| **Steps** | 1. M2M tables auto-cascade (ON DELETE CASCADE): track_gear, track_photo, track_poi, track_trip, track_waypoint. 2. Read geo_record_id, condition_id from track before delete. 3. Read geo_performance_id, gpx_id from geo_record. 4. DELETE track (cascades m2m). 5. DELETE geo_record (orphaned). 6. DELETE geo_performance (orphaned). 7. DELETE conditions (orphaned). 8. DELETE waypoints (orphaned, since m2m cascade removed the links). 9. DELETE gpx record + remove GPX file from storage. |
| **Output** | -- |
| **Note** | Photos are NOT deleted (they may be used elsewhere). Only the m2m links are removed. |

---

## 3. Track Actions

---

### ACT-01: Create Track (manual entry)

**Use case**: User logs an activity without a GPX file (e.g. gym session, swim, or forgot
to record). User manually enters distance, time, and other data.

#### Required Data

| Field | Table Column | Type | Notes |
|-------|-------------|------|-------|
| name | `explorer_agg_track.name` | text | Activity title |
| sport_type_id | `explorer_agg_track.sport_type_id` | uuid | From `core_ref_sport_type` |
| recorded_at | `explorer_agg_track.recorded_at` | timestamptz | When the activity happened |
| distance_m | `explorer_sub_geo_record.distance_m` | integer | Manually entered |
| total_time_s | `explorer_sub_geo_performance.total_time_s` | integer | Manually entered |

#### Optional Data

| Field | Table Column | Type | Notes |
|-------|-------------|------|-------|
| summary | `explorer_agg_track.summary` | text | Short description |
| description | `explorer_agg_track.description` | text | Detailed description |
| is_public | `explorer_agg_track.is_public` | boolean | Default false |
| difficulty_level_id | `explorer_agg_track.difficulty_level_id` | uuid | From `core_ref_difficulty_level` |
| difficulty_sport_id | `explorer_agg_track.difficulty_sport_id` | uuid | From `core_ref_difficulty_sport` |
| start_poi_id | `explorer_agg_track.start_poi_id` | uuid | Starting point |
| end_poi_id | `explorer_agg_track.end_poi_id` | uuid | End point |
| elevation_gain_m | `explorer_sub_geo_record.elevation_gain_m` | integer | Manually entered |
| elevation_loss_m | `explorer_sub_geo_record.elevation_loss_m` | integer | Manually entered |
| highest_elevation_m | `explorer_sub_geo_record.highest_elevation_m` | integer | Manually entered |
| moving_time_s | `explorer_sub_geo_performance.moving_time_s` | integer | If different from total |
| avg_heart_rate | `explorer_sub_geo_performance.avg_heart_rate` | integer | Manual entry |
| max_heart_rate | `explorer_sub_geo_performance.max_heart_rate` | integer | Manual entry |
| calories_burned | `explorer_sub_geo_performance.calories_burned` | integer | Manual entry |
| steps_count | `explorer_sub_geo_performance.steps_count` | integer | From watch/phone |
| conditions | (see B04) | object | Weather/trail conditions |
| gear_ids | (see B07) | uuid[] | Gear used |
| photo_ids | (see B06) | uuid[] | Attached photos |
| poi_ids | (see B08) | uuid[] | POIs visited |
| main_photo_id | `explorer_agg_track.main_photo_id` | uuid | Cover photo |

#### Processing Flow

```
Step 1 ── Create geo_performance (partial, manual data only)        → B03 (manual variant)
Step 2 ── Create geo_record (partial, manual data, no geojson)      → B02 (manual variant)
          Link geo_performance to geo_record
Step 3 ── Create conditions (if provided)                           → B04
Step 4 ── Create track record                                       → B05
Step 5 ── Link photos, gear, POIs (if provided)                     → B06, B07, B08
Step 6 ── Award POI visits (if POIs provided)                       → B11
Step 7 ── Award cards from POI visits                               → B12
Step 8 ── Evaluate achievements                                     → B13
Step 9 ── Award points (activity + achievements + cards + POIs)     → B14
Step 10 ─ Update statistics (all + year + month)                    → B15
Step 11 ─ Update pace curve (if enough data)                        → B16
```

#### Response

```json
{
  "track_id": "uuid",
  "points_awarded": 150,
  "new_achievements": ["uuid", "..."],
  "new_cards": ["uuid", "..."],
  "new_poi_visits": ["uuid", "..."]
}
```

---

### ACT-02: Create Track (with GPX file)

**Use case**: User uploads a GPX file from their GPS watch/phone. System extracts all
geodata automatically. User provides metadata and optional enrichments.

#### Required Data

| Field | Type | Notes |
|-------|------|-------|
| gpx_file | binary | GPX file upload |
| name | text | Activity title |
| sport_type_id | uuid | From `core_ref_sport_type` |

#### Optional Data

| Field | Type | Notes |
|-------|------|-------|
| recorded_at | timestamptz | Override; otherwise derived from GPX first trackpoint |
| summary | text | |
| description | text | |
| is_public | boolean | Default false |
| difficulty_level_id | uuid | |
| difficulty_sport_id | uuid | |
| start_poi_id | uuid | Override auto-detected start |
| end_poi_id | uuid | Override auto-detected end |
| conditions | object | Weather/trail conditions |
| gear_ids | uuid[] | Gear used |
| photo_ids | uuid[] | Attached photos |
| waypoints | object[] | Manual waypoints (in addition to GPX waypoints) |
| confirm_pois | boolean | If false, skip auto-detected POI suggestions (default true) |
| main_photo_id | uuid | Cover photo |

#### Processing Flow

```
Step 1 ── Upload GPX file to storage                                → B01
Step 2 ── Parse GPX → geo_record                                   → B02
Step 3 ── Parse GPX → geo_performance                              → B03
          Link geo_performance to geo_record
Step 4 ── Auto-detect POIs near track                               → B10
          Return detected POIs to user for confirmation (async/sync decision)
Step 5 ── Create conditions (if provided)                           → B04
Step 6 ── Create track record                                       → B05
Step 7 ── Extract & link GPX waypoints                              → B09
Step 8 ── Link photos, gear, user-confirmed POIs                    → B06, B07, B08
Step 9 ── Award POI visits                                          → B11
Step 10 ─ Award cards from POI visits                               → B12
Step 11 ─ Evaluate achievements                                     → B13
Step 12 ─ Award points                                              → B14
Step 13 ─ Update statistics                                         → B15
Step 14 ─ Update pace curve                                         → B16
```

#### Response

```json
{
  "track_id": "uuid",
  "geo_record": {
    "distance_m": 14250,
    "elevation_gain_m": 890,
    "elevation_loss_m": 890,
    "total_time_s": 18000,
    "moving_time_s": 15200
  },
  "detected_pois": [
    {"poi_id": "uuid", "name": "Alpspitze", "distance_m": 7200, "auto_matched": true}
  ],
  "points_awarded": 320,
  "new_achievements": ["uuid"],
  "new_cards": ["uuid"],
  "new_poi_visits": ["uuid"]
}
```

---

### ACT-03: Edit Track Metadata

**Use case**: User wants to fix the name, change sport type, update description, or adjust
non-geodata fields.

#### Editable Fields

| Field | Type | Side-effects |
|-------|------|-------------|
| name | text | None |
| name_de | text | None |
| name_pl | text | None |
| summary | text | None |
| summary_de | text | None |
| summary_pl | text | None |
| description | text | None |
| description_de | text | None |
| description_pl | text | None |
| recorded_at | timestamptz | **Triggers**: B15 (stats recalc for old+new year/month), streak recalc |
| sport_type_id | uuid | **Triggers**: B14 (points recalc), B15 (stats for old+new sport), B16 (pace curve for old+new sport), B13 (re-evaluate achievements) |
| difficulty_level_id | uuid | None |
| difficulty_sport_id | uuid | None |
| start_poi_id | uuid | None |
| end_poi_id | uuid | None |
| is_public | boolean | None |
| main_photo_id | uuid | None |

#### NOT Editable (returns 400)

- `distance_m`, `elevation_gain_m`, `elevation_loss_m` (geo_record data)
- `total_time_s`, `moving_time_s`, speeds (geo_performance data)
- `geojson`, `elevation_graph` (map data)
- `gpx_id` (use ACT-05 to replace GPX)

#### Processing Flow

```
Step 1 ── Validate ownership (track.created_by = current_user)
Step 2 ── Detect which fields changed
Step 3 ── UPDATE explorer_agg_track with new values
Step 4 ── IF sport_type_id changed:
           4a. Recalculate activity points (revoke old, award new)    → B17 + B14
           4b. Re-evaluate achievements                               → B13
           4c. Update statistics for BOTH old and new sport            → B15
           4d. Update pace curve for BOTH old and new sport            → B16
Step 5 ── IF recorded_at changed:
           5a. Update statistics for old AND new year/month scopes     → B15
           5b. Recalculate streaks                                     → B15 (streak part)
```

#### Response

```json
{
  "track_id": "uuid",
  "updated_fields": ["name", "sport_type_id"],
  "points_delta": -30,
  "achievements_revoked": [],
  "achievements_awarded": ["uuid"],
  "stats_recalculated": true
}
```

---

### ACT-04: Edit Track Conditions

**Use case**: User updates weather, trail, or snow conditions for an already-recorded track.

#### Editable Fields

| Field | Type | Notes |
|-------|------|-------|
| temperature_avg | integer | Celsius |
| temperature_min | integer | |
| temperature_max | integer | |
| equipment_used | jsonb | List of equipment items |
| visibility_id | uuid | From `core_ref_visibility` |
| snow_condition_id | uuid | From `core_ref_snow_condition` |
| trail_condition_id | uuid | From `core_ref_trail_condition` |
| weather_condition_id | uuid | From `core_ref_weather_condition` |

#### Processing Flow

```
Step 1 ── Validate ownership
Step 2 ── IF track has no condition_id:
           Create new conditions record                               → B04
           UPDATE track.condition_id
Step 3 ── ELSE:
           UPDATE existing explorer_sub_conditions
```

#### Side-effects

None. Conditions don't affect statistics, achievements, or points.

---

### ACT-05: Replace Track GPX

**Use case**: User uploaded wrong GPX file, or has a corrected version. This is a
**destructive operation** that replaces all geodata.

#### Required Data

| Field | Type | Notes |
|-------|------|-------|
| track_id | uuid | Target track |
| gpx_file | binary | New GPX file |

#### Processing Flow

```
Step 1 ── Validate ownership
Step 2 ── Store old geo_record data for comparison
Step 3 ── Upload new GPX file                                        → B01
Step 4 ── Parse GPX → new geo_record                                → B02
Step 5 ── Parse GPX → new geo_performance                           → B03
Step 6 ── DELETE old geo_performance, geo_record, gpx file + record  → (cleanup)
Step 7 ── UPDATE track with new geo_record_id
Step 8 ── Auto-detect POIs near new track                            → B10
Step 9 ── Clear and re-link waypoints from new GPX                   → B09
Step 10 ─ Recalculate points (distance/elevation changed)            → B17 + B14
Step 11 ─ Re-evaluate achievements                                   → B13
Step 12 ─ Update statistics                                          → B15
Step 13 ─ Update pace curve                                          → B16
```

#### Warning to User

Before executing, inform user:
- Old GPS track, performance data, and waypoints will be permanently replaced
- POI distances will be recalculated
- Statistics and points will be recalculated
- Achievements already earned will NOT be revoked (earned-is-earned policy)

---

### ACT-06: Delete Track

**Use case**: User wants to remove a recorded activity entirely.

#### Required Data

| Field | Type | Notes |
|-------|------|-------|
| track_id | uuid | Track to delete |

#### Processing Flow

```
Step 1 ── Validate ownership
Step 2 ── Collect pre-delete data:
           - track.sport_type_id (for stats/pace recalc)
           - track.recorded_at (for year/month scope)
           - geo_record.distance_m, elevation_gain_m (for point revocation)
           - geo_performance.total_time_s
Step 3 ── Revoke activity points (insert negative correction)        → B17
Step 4 ── Cascade delete sub-entities                                → B18
           (FK ON DELETE SET NULL preserves achievements, cards,
            POI visits, and related points)
Step 5 ── Update statistics (all + year + month)                     → B15
Step 6 ── Update pace curve for sport type                           → B16
Step 7 ── Recalculate streaks                                        → B15 (streak part)
```

#### What STAYS after delete

| Entity | Behavior | Reason |
|--------|----------|--------|
| `profile_m2m_user_achievement` | `track_id → NULL`, row stays | Earned is earned |
| `profile_sub_point` (achievement points) | Stays, `track_id → NULL` | Points from achievement, not track |
| `profile_sub_point` (activity points) | **Correction row added** (negative) | Track no longer exists |
| `profile_m2m_user_card` | `track_id → NULL`, row stays | Card was collected |
| `profile_m2m_user_poi` | `track_id → NULL`, row stays | POI was visited |
| `profile_sub_statistic` | **Recalculated** | Must reflect current data |
| `profile_sub_pace_curve` | **Recalculated** | Must reflect current data |
| `social_sub_comment` (on track) | Orphaned (`entity_id` dangling) | Consider: soft-delete track or cascade |
| `social_sub_rating` | N/A (ratings are for routes/segments, not tracks) | -- |

#### Open Design Question: Comments on Deleted Track

`social_sub_comment` uses polymorphic `entity_type` + `entity_id` with no FK constraint.
When a track is deleted, comments referencing it become orphaned. Options:
1. **Delete comments** in B18 (explicit cleanup query).
2. **Keep comments** and show "activity deleted" in UI.
3. **Soft-delete the track** (`is_deleted` flag) instead of hard delete.

Recommendation: Option 1 (delete comments) for simplicity. Comments on personal tracks
have low social value compared to comments on public routes.

---

### ACT-07: Manage Track Photos

**Use case**: User adds or removes photos from a track.

#### Sub-action: Add Photos

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| photos | array | Each: `{photo_id, slot_position}` |

Processing: Validate ownership → B06

#### Sub-action: Remove Photos

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| photo_ids | uuid[] | Photos to unlink |

Processing: DELETE from `explorer_m2m_track_photo` WHERE track_id AND photo_id IN (...).
If removed photo was `main_photo_id` → set `main_photo_id = NULL` on track.

#### Sub-action: Reorder Photos

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| order | array | `[{photo_id, new_slot_position}]` |

Processing: UPDATE `slot_position` for each entry.

#### Side-effects

None. Photos don't affect statistics, achievements, or points.

---

### ACT-08: Manage Track Gear

**Use case**: User adds or removes gear used during the activity.

#### Sub-action: Add Gear

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| gear_items | array | Each: `{gear_id, slot_position, notes}` |

Processing: Validate ownership → B07

#### Sub-action: Remove Gear

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| gear_ids | uuid[] | Gear to unlink |

Processing: DELETE from `explorer_m2m_track_gear`.

#### Side-effects

None. Gear links don't affect statistics or achievements.
Future consideration: gear-based achievements ("used crampons 10 times").

---

### ACT-09: Manage Track POIs

**Use case**: User adds or removes POIs visited during the activity. This DOES affect
POI visits, cards, achievements, and points.

#### Sub-action: Add POIs

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| pois | array | Each: `{poi_id, slot_position, distance_m}` |

```
Step 1 ── Link POIs to track                                        → B08
Step 2 ── Award POI visits (new only)                               → B11
Step 3 ── Award cards from new POI visits                            → B12
Step 4 ── Evaluate achievements                                     → B13
Step 5 ── Award points (new POIs + cards + achievements)             → B14
Step 6 ── Update statistics (unique_pois_count, unique_regions_count) → B15
```

#### Sub-action: Remove POIs

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| poi_ids | uuid[] | POIs to unlink |

```
Step 1 ── DELETE from explorer_m2m_track_poi
Step 2 ── Check if removed POIs still have other tracks linking them
          (query profile_m2m_user_poi for other tracks visiting same POI)
Step 3 ── POI visit stays (earned-is-earned, track_id just gets SET NULL)
Step 4 ── No point revocation for POI visits (earned-is-earned)
```

**Note**: Removing a POI from a track does NOT revoke the POI visit or card. The user
visited the POI -- unlinking it from this specific track doesn't undo that visit.

---

### ACT-10: Manage Track Waypoints

**Use case**: User adds, edits, or removes waypoints along their track.

#### Sub-action: Add Waypoints

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| waypoints | array | Each: `{name, location, altitude_m, arrived_at, departed_at, duration_min, poi_id, slot_position}` |

Processing: B09

#### Sub-action: Edit Waypoint

| Required | Type | Notes |
|----------|------|-------|
| waypoint_id | uuid | |

Editable: name, summary, description, arrived_at, departed_at, duration_min, poi_id.
NOT editable: location, altitude_m (factual from GPS).

#### Sub-action: Remove Waypoints

| Required | Type | Notes |
|----------|------|-------|
| track_id | uuid | |
| waypoint_ids | uuid[] | |

Processing: DELETE from `explorer_m2m_track_waypoint`, then DELETE orphaned `explorer_sub_waypoint` rows.

#### Side-effects

None directly. Waypoints are informational.

---

## 4. Trip Actions

---

### ACT-11: Create Trip

**Use case**: User creates a multi-day trip container to group related tracks.

#### Required Data

| Field | Table Column | Type | Notes |
|-------|-------------|------|-------|
| name | `explorer_agg_trip.name` | text | Trip title |

#### Optional Data

| Field | Table Column | Type | Notes |
|-------|-------------|------|-------|
| summary | `explorer_agg_trip.summary` | text | |
| description | `explorer_agg_trip.description` | text | |
| is_public | `explorer_agg_trip.is_public` | boolean | Default false |
| length_days | `explorer_agg_trip.length_days` | integer | |
| first_day | `explorer_agg_trip.first_day` | date | |
| last_day | `explorer_agg_trip.last_day` | date | |
| sport_type_id | `explorer_agg_trip.sport_type_id` | uuid | Primary sport for the trip |
| track_assignments | array | object[] | Tracks to assign immediately (see ACT-14) |

#### Processing Flow

```
Step 1 ── INSERT into explorer_agg_trip
Step 2 ── IF track_assignments provided:
           For each: execute ACT-14
Step 3 ── Evaluate trip-based achievements                           → B13
Step 4 ── Award points for trip creation                             → B14
```

---

### ACT-12: Edit Trip

**Use case**: User updates trip metadata.

#### Editable Fields

| Field | Side-effects |
|-------|-------------|
| name, summary, description (+ i18n) | None |
| is_public | None |
| length_days | None |
| first_day, last_day | None |
| sport_type_id | None (trip is a container, sport is informational) |

#### Processing Flow

```
Step 1 ── Validate ownership
Step 2 ── UPDATE explorer_agg_trip
```

No side-effects on statistics, achievements, or points.

---

### ACT-13: Delete Trip

**Use case**: User deletes a trip. Tracks inside are NOT deleted, only unlinked.

#### Processing Flow

```
Step 1 ── Validate ownership
Step 2 ── explorer_m2m_track_trip cascades on trip DELETE (ON DELETE CASCADE)
          → All track-trip links removed automatically
Step 3 ── profile_m2m_user_achievement.trip_id → SET NULL (achievements stay)
Step 4 ── profile_sub_point.trip_id → SET NULL (points stay)
Step 5 ── DELETE explorer_agg_trip
Step 6 ── Clean up orphaned comments (entity_type = 'trip', entity_id = trip_id)
```

Tracks themselves remain intact with all their data.

---

### ACT-14: Assign Track to Trip

**Use case**: User links an existing track to a trip, specifying which day it belongs to.

#### Required Data

| Field | Type | Notes |
|-------|------|-------|
| track_id | uuid | |
| trip_id | uuid | |
| day_name | text | "Day 1", "Day 2", etc. |
| slot_position | integer | Order within that day |

#### Optional Data

| Field | Type | Notes |
|-------|------|-------|
| day_summary | text | |
| day_description | text | |
| waypoint_id | uuid | Key waypoint for this day |

#### Processing Flow

```
Step 1 ── Validate both track and trip belong to current user
Step 2 ── INSERT into explorer_m2m_track_trip
Step 3 ── Recalculate trip aggregates:
           length_days, first_day, last_day from assigned tracks
Step 4 ── Evaluate trip-based achievements                           → B13
Step 5 ── Award points if new achievements                           → B14
```

---

### ACT-15: Remove Track from Trip

**Use case**: User unlinks a track from a trip.

#### Required Data

| Field | Type |
|-------|------|
| track_id | uuid |
| trip_id | uuid |

#### Processing Flow

```
Step 1 ── Validate ownership
Step 2 ── DELETE from explorer_m2m_track_trip
Step 3 ── Recalculate trip aggregates (length_days, first_day, last_day)
Step 4 ── Re-evaluate trip-based achievements (trip might no longer qualify)
          → But earned-is-earned: do NOT revoke
```

---

## 5. Side-Effect Policies

### 5.1 Statistics Recalculation Policy

| Trigger | Scopes to recalculate |
|---------|-----------------------|
| Track created | `all`, `year(recorded_at)`, `month(recorded_at)` |
| Track deleted | `all`, `year(recorded_at)`, `month(recorded_at)` |
| Track sport_type changed | `all`, both old+new year/month if recorded_at also changed |
| Track recorded_at changed | `all`, old year/month, new year/month |
| POI added to track | `all` (unique_pois_count, unique_regions_count) |

### 5.2 Achievement Evaluation Policy

| Trigger | Evaluation scope |
|---------|-----------------|
| Track created | All active achievements |
| Track sport_type changed | All sport-filtered achievements for old+new type |
| POI added | POI-based achievements, card-based achievements |
| Trip modified | Trip-based achievements (multi-day, cumulative trip distance) |

Achievements are **never revoked**. If a track is deleted or changed such that criteria are
no longer met, the existing `profile_m2m_user_achievement` row stays with `track_id = NULL`.

### 5.3 Points Policy

| Event | Points behavior |
|-------|----------------|
| Track created | Award activity points + award for new achievements/cards/POIs |
| Track deleted | Insert negative correction for activity points only |
| Track sport_type changed | Revoke old activity points, award new (different point_factor) |
| Achievement earned | Award points (never revoked) |
| Card collected | Award points (never revoked) |
| POI visited | Award points (never revoked) |

### 5.4 Pace Curve Policy

| Trigger | Action |
|---------|--------|
| Track created (with GPX) | Recalculate for track's sport_type |
| Track deleted | Recalculate for track's sport_type |
| Track sport_type changed | Recalculate for both old and new sport_type |
| Track GPX replaced | Recalculate for track's sport_type |

---

## 6. Action-to-Block Matrix

| Action | B01 | B02 | B03 | B04 | B05 | B06 | B07 | B08 | B09 | B10 | B11 | B12 | B13 | B14 | B15 | B16 | B17 | B18 |
|--------|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|-----|
| ACT-01 Create (manual) | | M | M | ? | X | ? | ? | ? | | | ? | ? | X | X | X | ? | | |
| ACT-02 Create (GPX) | X | X | X | ? | X | ? | ? | ? | X | X | ? | ? | X | X | X | X | | |
| ACT-03 Edit metadata | | | | | | | | | | | | | ? | ? | ? | ? | ? | |
| ACT-04 Edit conditions | | | | X | | | | | | | | | | | | | | |
| ACT-05 Replace GPX | X | X | X | | | | | | X | X | | | X | X | X | X | X | |
| ACT-06 Delete | | | | | | | | | | | | | | | X | X | X | X |
| ACT-07 Photos | | | | | | X | | | | | | | | | | | | |
| ACT-08 Gear | | | | | | | X | | | | | | | | | | | |
| ACT-09 POIs (add) | | | | | | | | X | | | X | X | X | X | X | | | |
| ACT-09 POIs (remove) | | | | | | | | | | | | | | | | | | |
| ACT-10 Waypoints | | | | | | | | | X | | | | | | | | | |
| ACT-14 Assign to trip | | | | | | | | | | | | | X | X | | | | |
| ACT-15 Remove from trip| | | | | | | | | | | | | | | | | | |

**Legend**: `X` = always executed, `?` = conditional (if data provided or field changed),
`M` = manual variant of block (partial data, no GPX source)
