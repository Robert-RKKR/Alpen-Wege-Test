# Profile: Read-Only Derived Data — Implementation Plan

## Overview

Derived data is computed by the system from the user's activity history.
The user cannot create, edit, or delete it directly — only view it. The
system recomputes it when underlying data changes.

```
Profile (Read-Only Derived)
  └── Statistics
        ├── Lifetime aggregates (scope = 'all')
        ├── Per-year aggregates (scope = 'year')
        ├── Per-month aggregates (scope = 'month')
        └── Each split by sport_type (NULL = all sports)
```

The statistics recomputation service (`track_statistics.py`) already exists
and works. What's missing is the **API layer**: routes, schemas, and the
read endpoints to expose this data.

---

## Core Design Decisions

### Statistics are fully precomputed

The `profile_sub_statistic` table stores one row per (user, sport_type, scope,
scope_year, scope_month) combination. These are written by `recompute_user_statistics()`
which runs as a Celery task triggered after:

- Track processing completes
- Track is deleted or archived
- POI detection runs (updates `unique_pois_count`)

The API only reads from this table — no computation at request time.

### Three scope levels

| scope | scope_year | scope_month | Meaning |
|-------|-----------|-------------|---------|
| `all` | NULL | NULL | Lifetime total |
| `year` | 2025 | NULL | Calendar year total |
| `month` | 2025 | 7 | Calendar month total |

Each scope level has rows for `sport_type_id = NULL` (all sports combined)
and one row per sport_type the user has tracks for.

### Graphs are stored as JSONB

The statistics model includes `_graph` columns (JSONB): `total_distance_graph`,
`total_elevation_graph`, `total_activities_graph`, `total_time_graph`. These
store time-series data for trend charts, precomputed by the recomputation
service. The API returns them as-is.

---

## Model (existing)

| Model | Table | Key columns |
|-------|-------|-------------|
| `ProfileSubStatistic` | `profile_sub_statistic` | scope, scope_year, scope_month, sport_type_id, total_distance_m, total_elevation_m, total_activities, total_time_s, total_moving_time_s, total_elevation_loss_m, total_plans_created/completed/skipped, current_streak_days, longest_streak_days, total_points, unique_pois_count, unique_regions_count, active_days, max_elevation_m, longest_track_m, longest_track_id, graph columns |

Unique constraint: `(user_id, sport_type_id, scope, scope_year, scope_month)`.

---

## API Endpoints

```
GET /profile/me/statistics                — overview (lifetime + current year)
GET /profile/me/statistics/all            — lifetime statistics
GET /profile/me/statistics/year/{year}    — year statistics
GET /profile/me/statistics/month/{year}/{month} — month statistics
```

All endpoints return data split by sport_type. Each response includes:
- The all-sports aggregate row
- Per-sport_type breakdown rows

### Query parameters

- `sport_type_id`: filter to a single sport type (optional)
- `include_graphs`: boolean, default false — include `_graph` JSONB fields
  (they can be large; omit by default for list/overview views)

### Overview endpoint

`GET /profile/me/statistics` returns a summary object designed for the
profile dashboard:

```json
{
  "lifetime": {
    "total_distance_m": 1250000,
    "total_elevation_m": 85000,
    "total_activities": 342,
    "total_time_s": 1200000,
    "current_streak_days": 5,
    "longest_streak_days": 23,
    "total_points": 15400,
    "unique_pois_count": 89,
    "active_days": 245,
    "max_elevation_m": 3798,
    "longest_track_m": 45200
  },
  "current_year": {
    "total_distance_m": 280000,
    "total_elevation_m": 19500,
    "total_activities": 67,
    "by_sport": [
      {
        "sport_type": { "id": "...", "name": "Hiking" },
        "total_distance_m": 210000,
        "total_activities": 52
      },
      {
        "sport_type": { "id": "...", "name": "Trail Running" },
        "total_distance_m": 70000,
        "total_activities": 15
      }
    ]
  }
}
```

### Detailed endpoint response

`GET /profile/me/statistics/year/2025?include_graphs=true`:

```json
{
  "scope": "year",
  "scope_year": 2025,
  "all_sports": {
    "total_distance_m": 280000,
    "total_elevation_m": 19500,
    "total_elevation_loss_m": 18200,
    "total_activities": 67,
    "total_time_s": 240000,
    "total_moving_time_s": 195000,
    "total_plans_created": 12,
    "total_plans_completed": 9,
    "total_plans_skipped": 2,
    "current_streak_days": 5,
    "longest_streak_days": 14,
    "total_points": 3200,
    "unique_pois_count": 34,
    "unique_regions_count": 8,
    "active_days": 67,
    "max_elevation_m": 3798,
    "longest_track_m": 45200,
    "longest_track_id": "uuid",
    "total_distance_graph": [[1, 4200], [2, 8500], ...],
    "total_elevation_graph": [[1, 350], [2, 720], ...],
    "total_activities_graph": [[1, 1], [2, 1], ...],
    "total_time_graph": [[1, 3600], [2, 7200], ...]
  },
  "by_sport": [
    {
      "sport_type": { "id": "...", "name": "Hiking" },
      "total_distance_m": 210000,
      "total_elevation_m": 15000,
      "total_activities": 52,
      "total_time_s": 190000
    }
  ]
}
```

### Public profile statistics

For other users' public profiles:

```
GET /profile/users/{user_id}/statistics   — public statistics overview
```

This returns the same overview format but only if the target user's profile
is public or the requesting user follows them. Respects access policies.

---

## Schemas

```
StatisticOverviewRead:
  lifetime: StatisticSummaryRead
  current_year: StatisticYearSummaryRead

StatisticSummaryRead:
  total_distance_m, total_elevation_m, total_activities, total_time_s
  current_streak_days, longest_streak_days
  total_points, unique_pois_count, active_days
  max_elevation_m, longest_track_m

StatisticYearSummaryRead:
  total_distance_m, total_elevation_m, total_activities
  by_sport: list[StatisticSportRead]

StatisticSportRead:
  sport_type: RefRead
  total_distance_m, total_elevation_m, total_activities, total_time_s

StatisticDetailRead:
  scope, scope_year, scope_month
  all_sports: StatisticFullRead
  by_sport: list[StatisticSportFullRead]

StatisticFullRead:
  (all numeric columns from the model)
  total_distance_graph: list | None (only when include_graphs=true)
  total_elevation_graph: list | None
  total_activities_graph: list | None
  total_time_graph: list | None
```

---

## Service Layer

No new service needed for the read layer. The existing
`track_statistics.recompute_user_statistics()` handles all writes.

The router queries `ProfileSubStatistic` directly:

```python
async def get_statistics_overview(session, user_id):
    lifetime = await session.execute(
        select(ProfileSubStatistic)
        .where(
            ProfileSubStatistic.user_id == user_id,
            ProfileSubStatistic.scope == "all",
            ProfileSubStatistic.sport_type_id.is_(None),
        )
    )
    current_year_rows = await session.execute(
        select(ProfileSubStatistic)
        .where(
            ProfileSubStatistic.user_id == user_id,
            ProfileSubStatistic.scope == "year",
            ProfileSubStatistic.scope_year == current_year,
        )
    )
    # assemble response
```

For the detailed view, add a helper that loads all rows for a given scope
and splits them into all_sports + by_sport groupings.

---

## User Flows

### Flow 1: View profile dashboard

```
GUI                                   API
──────────────────────────────────────────────────

User opens profile ──────────────── GET /profile/me/statistics
                                    → 200: { lifetime, current_year }

Dashboard renders:
  - Total distance, elevation, activities tiles
  - Current streak badge
  - Points total
  - Sport breakdown chart for current year
```

### Flow 2: Drill into yearly stats

```
GUI                                   API
──────────────────────────────────────────────────

User clicks "2024" in stats nav ─── GET /profile/me/statistics/year/2024
                                    ?include_graphs=true
                                    → 200: { all_sports with graphs, by_sport }

GUI renders:
  - Distance accumulation chart (from total_distance_graph)
  - Elevation accumulation chart
  - Activity frequency chart
  - Monthly breakdown table
```

### Flow 3: View another user's stats

```
GUI                                   API
──────────────────────────────────────────────────

User opens other profile ────────── GET /profile/users/{id}/statistics
                                    → 200: { public overview }
                                    or 403 (private profile)
```

---

## Open Issues

### 1. Graph data format

**Question:** What format should the `_graph` JSONB columns use?

**Current:** The recomputation service writes them, but the format is not
standardized in the codebase yet.

**Recommendation:** Use `[[day_number, value], ...]` for year/month scopes
where `day_number` is the day-of-year (1-366) or day-of-month (1-31).
For lifetime scope, use `[[year, value], ...]`. This keeps the format
compact and chart-library-agnostic.

### 2. Statistics staleness indicator

**Question:** Should the API indicate when statistics were last recomputed?

**Recommendation:** Yes. Return `updated_at` from the statistic row. The GUI
can show "Last updated: 2 hours ago" and optionally a refresh button that
triggers `recompute_user_statistics` via Celery.

### 3. Month-over-month comparison

**Question:** Should the API provide comparison data (this month vs. last month)?

**Recommendation:** Not in the API. The GUI can fetch two months and compute
deltas client-side. Adding comparison logic to the API increases complexity
for minimal benefit — the data is already there.

### 4. Regions counting

**Question:** How are `unique_regions_count` regions determined?

**Recommendation:** Spatial query: for each track's start_location, find the
matching region from `compendium_cat_region` using `ST_Contains(region.boundary,
point)`. Count distinct region IDs. This needs to be added to the recomputation
service — currently `unique_regions_count` defaults to 0.

---

## Implementation Phases

### Phase 1: Statistics read endpoints
- Statistics router under /profile/me/statistics
- Overview endpoint (lifetime + current year)
- Detailed endpoints (all, year, month)
- Schemas for all response shapes
- Register router in profile.__init__

### Phase 2: Public statistics
- GET /profile/users/{id}/statistics
- Access control (public profile or follower)
- Shared query helper for both me and public endpoints

### Phase 3: Graph format standardization
- Define graph format in the recomputation service
- Update recompute_user_statistics to write graphs
- Add include_graphs query parameter handling

### Phase 4: Regions
- Add region detection to recomputation service
- Spatial query: track start_location → region via ST_Contains
- Update unique_regions_count
