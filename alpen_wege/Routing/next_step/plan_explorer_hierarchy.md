# Explorer Planned Hierarchy: Implementation Plan

## Overview

The planned hierarchy has three levels:

```
Journey (multi-day plan)
  └── Route (single-day outing)
        └── Segment (one stretch of trail)
              └── geo_record (geometry + metrics, no time data)
```

The user primarily works at the **Route** level.
Segments are the building blocks a route is assembled from.
Journeys are assembled from routes.

---

## Core Design Decisions

### Segments are immutable geometry containers

Once a segment is created and its GPX is processed, its geo_record does not change.
This is intentional: segments are shared across many routes, so editing one
would silently change every route that uses it.

If a user wants different geometry, they create a new segment. The old one stays
for any route that still references it.

### The route editor is the primary UI

Users do not manage segments in isolation. The route editor is where everything
happens. When a user builds or edits a route, the GUI:

1. Shows the map with existing segments available to snap together
2. Lets the user draw new geometry on the map (creates a new segment behind the scenes)
3. Handles ordering, reversing, and alt-group assignment
4. Validates continuity in real time
5. Triggers aggregate recomputation on save

A segment CRUD API still exists for direct access, but the route editor is
the expected workflow.

### This solves the immutability problem

Because the GUI operates at the route level:

- "Edit a segment" in the route context means: detach the old segment, create a
  new one with the changed geometry, attach the new one in the same slot
- The old segment is untouched; other routes keep using it
- The user never notices they created a new segment -- the route editor handles it

### Inline segment creation (segments live inside the route save)

The earlier design required two separate steps: first create a segment via
`POST /segments`, then attach it via `PUT /routes/{id}/segments`. This is
wrong from a UX perspective. Drawing a trail section and saving the route
should be one action.

**Solution:** The `PUT /routes/{id}/segments` payload accepts both existing
segment references AND inline new segments in the same list. The server
creates the segments and attaches them atomically in one transaction.

Each item in the segments array is either:

```
{ "segment_id": "uuid" }              -- reference an existing segment
{ "inline": { coordinates, name, sport_type_id, ... } }  -- create new
{ "inline": { track_id, start_m, end_m, name, ... } }    -- clip from track
{ "inline": { gpx_file_ref, name, ... } }                -- from uploaded GPX
```

This means:
- Drawing on the map and saving = one PUT call with inline segments
- Mixing existing and new segments in one save = one PUT call
- The standalone `POST /segments` endpoint still exists for when the user
  wants to create a reusable segment outside of any route context
- The server returns the created segment IDs in the response so the GUI
  can reference them in future edits without re-creating them

For GPX file uploads within this flow: the GUI uploads the file first via a
generic file upload endpoint (returns a temporary reference), then passes
that reference in the inline block. This avoids mixing multipart form data
with JSON in the same request.

### Mixed sport types on routes

A route currently has a single `sport_type_id` (NOT NULL). This breaks for
multi-sport outings: a route with a hiking segment, then a scrambling segment,
then a ridge walk with via ferrata sections.

Real examples where this matters:
- Hike-and-climb: approach on foot, then rock section
- Bike-and-hike: cycle to trailhead, then hike to summit
- Triathlon: swim, cycle, run
- Ski touring: skin up, boot-pack a steep section, ski down

**Solution:** Each segment already carries its own `sport_type_id`. The route's
sport type information is derived from its segments:

- **Route keeps `sport_type_id`** as the PRIMARY / dominant sport. This is what
  shows in listings, search filters, and category views. For a hike-and-climb
  route, this would be "hiking" if most of the distance is hiking.
- **Add a derived field `sport_types`** to the route read schema (not a DB column).
  This is computed at read time from the segments: the distinct set of sport_type_ids
  used by the route's segments, ordered by total distance contribution.

  ```json
  {
    "sport_type_id": "uuid-hiking",
    "sport_types": [
      { "sport_type_id": "uuid-hiking", "distance_m": 8200, "segment_count": 2 },
      { "sport_type_id": "uuid-scrambling", "distance_m": 1100, "segment_count": 1 }
    ]
  }
  ```

- **Route's `sport_type_id` auto-sets** to the sport with the most distance across
  default segments, unless the user explicitly overrides it. PATCH can still set it
  manually (user says "this is a climbing route even though most distance is approach").

- **Route's `difficulty_level_id` and `difficulty_sport_id`** follow the same logic:
  auto-set to the hardest segment's values, but can be overridden manually. These
  stay as single values because the route's difficulty is its hardest point,
  not a list.

This requires NO schema change on the route table. The `sport_type_id` column
stays as-is (single, NOT NULL, the dominant sport). The `sport_types` breakdown
is computed from segments when the route is read.

On segments: the segment's `sport_type_id` is already NOT NULL and correctly
describes that one stretch of trail. No change needed.

On journeys: same approach. Journey's `sport_type_id` is the dominant sport
across all its routes. Derived `sport_types` shows the full breakdown.

---

## 1. Segment

### What it stores

A segment is a named, reusable trail stretch with:

- Identity: name (l18n), summary, description, sport_type, difficulty
- Geometry: geo_record_id (distance, elevation, geojson, elevation_graph, start/end location)
- Endpoints: start_poi_id, end_poi_id (optional, for continuity validation)
- Ownership: created_by, is_public

### Creating a segment

Three ways to create a segment:

**A) Upload GPX file**

The user uploads a GPX file containing the planned trail geometry.
Reuse the existing GPX pipeline but skip performance metrics:

- parse_gpx -> clean -> geometry_metrics -> build_geojson, build_elevation_graph, build_route_ewkt
- performance_metrics is skipped (returns None since planned GPX has no timestamps)
- Persist into geo_record with geo_performance_id = NULL
- Store the GPX file as asset_agg_gpx (same as tracks)

The existing `process_gpx_file` already handles this: when no timestamps are
present it returns `performance=None`. A thin wrapper `process_segment_gpx()`
can call it and assert performance is None, or skip the performance step
explicitly for clarity.

**B) Clip from an existing track**

The user selects a start and end point on one of their recorded tracks.
The backend:

1. Loads the track's GPX file from storage
2. Runs parse_gpx + clean to get the point array
3. Slices the points between the start and end indices (or nearest points to provided coordinates)
4. Constructs a CleanedGpx from the slice
5. Runs geometry_metrics + shaping on it
6. Saves the sliced points as a new GPX file (so the segment has its own asset_agg_gpx)
7. Persists the geo_record

**C) Draw on map (frontend sends coordinates)**

The frontend sends an array of [lon, lat, ele?] points.
The backend:

1. Constructs GpxPoint objects from the coordinates
2. Wraps them in a CleanedGpx (single segment)
3. Runs geometry_metrics + shaping
4. Optionally saves as GPX file, or leaves gpx_id NULL if no file is stored
5. Persists the geo_record

### Auto-detecting start/end POIs

After creating the geo_record, the backend can optionally run the existing
poi_detection service against the start and end points of the segment to
auto-populate start_poi_id and end_poi_id. This makes continuity validation
much more reliable.

### Segment API endpoints

```
POST   /explorer/segments              -- create (accepts GPX upload or coordinate array)
POST   /explorer/segments/from-track   -- create by clipping from an existing track
GET    /explorer/segments              -- list (with filters: sport_type, near-location, creator)
GET    /explorer/segments/{id}         -- get one (includes geo_record data)
PATCH  /explorer/segments/{id}         -- update metadata only (name, summary, difficulty, POIs)
DELETE /explorer/segments/{id}         -- delete (fails if segment is used in any route)
POST   /explorer/segments/upload-csv   -- bulk import metadata (same pattern as gear)
```

Geometry is NOT editable via PATCH. To change geometry, create a new segment.

### Delete protection

A segment cannot be deleted if any `segment_route` row references it.
The API returns 409 Conflict with a list of route names that use it.
The user must remove the segment from all routes first.

---

## 2. Route

### What it stores

A route is an ordered chain of segments forming a single-day outing:

- Identity: name (required, l18n), summary, description
- Classification: sport_type (required), difficulty_level + difficulty_sport (required)
- Aggregates (server-computed): agg_distance_m, agg_elevation_gain_m, agg_elevation_loss_m,
  agg_highest_point_m, agg_lowest_point_m, agg_duration_s
- Planning: plan_condition_id (equipment, permits, best months)
- Social: rating_avg, rating_count (system-written)

### The segment_route link table

Each row in `explorer_m2m_segment_route` represents one segment placed in a route:

| Field         | Purpose                                                |
|---------------|--------------------------------------------------------|
| slot_position | Order within the route (0, 1, 2, ...)                  |
| segment_id    | Which segment                                          |
| alt_group     | Groups alternative segments at the same slot            |
| is_default    | Which alternative is the primary/recommended one        |
| is_reversed   | Traverse this segment backwards                         |

### How alt_group works

Normal case -- simple chain:

```
slot 0: Segment A  (alt_group=0, is_default=true)
slot 1: Segment B  (alt_group=1, is_default=true)
slot 2: Segment C  (alt_group=2, is_default=true)
```

With variants -- two options for the middle section:

```
slot 0: Segment A  (alt_group=0, is_default=true)
slot 1: Segment B  (alt_group=1, is_default=true)   <-- easy path
slot 1: Segment D  (alt_group=1, is_default=false)  <-- via ferrata variant
slot 2: Segment C  (alt_group=2, is_default=true)
```

Segments B and D share the same slot_position and alt_group. They are
alternatives for the same section of the route. Exactly one must be
is_default=true within each alt_group.

### Continuity validation

This is the key validation rule: **adjacent segments must connect.**

For each consecutive pair of slot positions (considering alt groups), validate:

```
effective_end(slot N) == effective_start(slot N+1)
```

Where:
- effective_end = segment's end_location (or start_location if is_reversed)
- effective_start = segment's start_location (or end_location if is_reversed)

#### Validation algorithm

```
1. Sort segments by slot_position
2. Group by slot_position (each group = one step in the chain)
3. For each consecutive pair of groups (group_N, group_N+1):
   a. Collect all effective_end points from group_N
   b. Collect all effective_start points from group_N+1
   c. For every combination of (end_from_N, start_of_N+1):
      - Check if they are within CONTINUITY_THRESHOLD_M (e.g. 50m)
   d. VALID if: every segment in group_N connects to at least one
      segment in group_N+1, AND every segment in group_N+1 connects
      to at least one segment in group_N
```

#### Alt-group continuity rules

All alternatives within an alt_group must share the same start and end
neighborhoods. This is what makes them valid alternatives:

```
For each alt_group with multiple segments:
  - All segments' effective_start must be within THRESHOLD of each other
  - All segments' effective_end must be within THRESHOLD of each other
```

If segment B (easy path) goes from point X to point Y, then segment D
(via ferrata) must also go from ~X to ~Y. They differ in the middle,
but share endpoints.

#### Validation strictness levels

Two levels, configurable per request:

- **strict** (default for save): all connections must be within threshold,
  all alt-group endpoints must match. Returns 422 with details on failure.
- **warn** (for draft/work-in-progress): runs the same checks but returns
  warnings instead of blocking. Allows saving an incomplete route.

#### POI-based vs coordinate-based matching

If both segments have start_poi_id / end_poi_id set, match by POI identity
(exact UUID match = connected). This is more reliable than coordinate distance
because a POI represents a known point like "Berliner Huette" regardless of
GPS precision.

Fall back to coordinate distance only when POIs are not set on one or both sides.

### Aggregate recomputation

When the segment list changes (add, remove, reorder, change default), the
server recomputes the route's aggregate fields:

```
Use is_default segments only for aggregation:

agg_distance_m        = sum of default segments' geo_record.distance_m
agg_elevation_gain_m  = sum (respecting is_reversed: swap gain/loss)
agg_elevation_loss_m  = sum (respecting is_reversed: swap gain/loss)
agg_highest_point_m   = max across all default segments
agg_lowest_point_m    = min across all default segments
agg_duration_s        = NULL (no time data on segments; filled by Prediction later)
```

When is_reversed is true for a segment:
- elevation_gain and elevation_loss are swapped
- start_location and end_location are swapped (for continuity checks)
- The geojson coordinates are reversed (for map rendering of the full route)

### Route API endpoints

```
POST   /explorer/routes                       -- create route (metadata only)
GET    /explorer/routes                       -- list routes
GET    /explorer/routes/{id}                  -- get route with segments
PATCH  /explorer/routes/{id}                  -- update metadata
DELETE /explorer/routes/{id}                  -- delete route (cascades segment_route links)

PUT    /explorer/routes/{id}/segments         -- replace the full segment list
POST   /explorer/routes/{id}/segments/validate -- validate continuity without saving
GET    /explorer/routes/{id}/segments         -- get ordered segment list with alt groups
```

### PUT /routes/{id}/segments -- the main editing endpoint

This is a full replacement of the segment list. The client sends the complete
desired state:

```json
{
  "segments": [
    {
      "segment_id": "uuid-A",
      "slot_position": 0,
      "alt_group": 0,
      "is_default": true,
      "is_reversed": false
    },
    {
      "segment_id": "uuid-B",
      "slot_position": 1,
      "alt_group": 1,
      "is_default": true,
      "is_reversed": false
    },
    {
      "segment_id": "uuid-D",
      "slot_position": 1,
      "alt_group": 1,
      "is_default": false,
      "is_reversed": false
    },
    {
      "segment_id": "uuid-C",
      "slot_position": 2,
      "alt_group": 2,
      "is_default": true,
      "is_reversed": false
    }
  ],
  "validation": "strict"
}
```

Server processing:

1. Validate the structure (positions are contiguous, exactly one is_default per alt_group)
2. Load all referenced segments' geo_records (need start/end locations)
3. Run continuity validation
4. If valid (or validation="warn"): delete all existing segment_route rows for this route,
   insert the new ones
5. Recompute aggregates
6. Return the updated route with segments

### Route creation workflow from the GUI perspective

The typical flow:

1. User opens "Create Route"
2. User draws the first trail section on the map -> backend creates Segment A
3. User draws the next section -> backend creates Segment B
4. User searches existing segments near the endpoint and picks one -> Segment C (reused)
5. User adds an alternative to Segment B by drawing -> backend creates Segment D
6. GUI sends PUT /routes/{id}/segments with all four segments
7. Server validates, computes aggregates, returns the complete route

For editing an existing route:

1. User opens the route editor, sees existing segments on the map
2. User wants to change Segment B's geometry
3. GUI lets user redraw that section -> backend creates new Segment E
4. GUI sends PUT /routes/{id}/segments replacing B with E in the same slot
5. Segment B still exists for other routes that use it

---

## 3. Journey

### What it stores

A journey is a multi-day plan composed of routes:

- Identity: name (required, l18n), summary, description
- Classification: sport_type, difficulty (optional, can be inferred)
- Aggregates (server-computed): agg_distance_m, agg_elevation_gain_m, etc., length_days
- Planning: condition_id (journey-level plan conditions)

### The route_journey link table

Each row in `explorer_m2m_route_journey` maps a route to a day in the journey:

| Field           | Purpose                                              |
|-----------------|------------------------------------------------------|
| slot_position   | Order within the journey (0, 1, 2, ...)              |
| route_id        | Which route for this day                             |
| journey_id      | Parent journey                                       |
| poi_id          | Overnight stop / stage endpoint (e.g. the hut)       |
| day_name        | "Day 1", "Stage 3: Hut to Summit"                    |
| day_summary     | Short summary of the day                             |
| day_description | Detailed description                                 |

### Journey continuity validation

Simpler than route continuity. For consecutive days:

```
route_N's last segment's effective_end ~= route_N+1's first segment's effective_start
```

This check uses the routes' own aggregate geometry (start/end of the default
segment chain). Gaps are expected between days (overnight at a hut), so the
threshold can be more generous (e.g. 500m or even skipped) -- the poi_id on
each day-link is the semantic connection ("sleep here, start there tomorrow").

Validation is a warning, not a hard block. A journey might intentionally
include a transfer day with no trail connection.

### Aggregate recomputation

When routes are added or removed:

```
agg_distance_m        = sum of routes' agg_distance_m
agg_elevation_gain_m  = sum of routes' agg_elevation_gain_m
agg_elevation_loss_m  = sum of routes' agg_elevation_loss_m
agg_highest_point_m   = max of routes' agg_highest_point_m
agg_lowest_point_m    = min of routes' agg_lowest_point_m
agg_duration_s        = sum of routes' agg_duration_s (if available)
length_days           = count of distinct slot_positions
difficulty_level_id   = max difficulty among routes (if not manually set)
sport_type_id         = most common sport_type among routes (if not manually set)
```

### Journey API endpoints

```
POST   /explorer/journeys                      -- create journey (metadata)
GET    /explorer/journeys                      -- list journeys
GET    /explorer/journeys/{id}                 -- get journey with routes and day info
PATCH  /explorer/journeys/{id}                 -- update metadata
DELETE /explorer/journeys/{id}                 -- delete journey (cascades route_journey links)

PUT    /explorer/journeys/{id}/routes          -- replace the full day-route list
GET    /explorer/journeys/{id}/routes          -- get ordered day-route list
```

### PUT /journeys/{id}/routes payload

```json
{
  "days": [
    {
      "route_id": "uuid-route-1",
      "slot_position": 0,
      "poi_id": "uuid-of-overnight-hut",
      "day_name": "Day 1: Valley to Berliner Huette",
      "day_summary": "Ascent through the forest to the hut",
      "day_description": null
    },
    {
      "route_id": "uuid-route-2",
      "slot_position": 1,
      "poi_id": null,
      "day_name": "Day 2: Berliner Huette to Furtschaglhaus",
      "day_summary": "High alpine traverse",
      "day_description": null
    }
  ]
}
```

---

## User Flows (GUI + API)

### Flow 1: Create a simple route with one segment (draw on map)

The user wants to plan a short summit loop. One trail, no variants.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Clicks "New Route"             Opens route editor                  POST /explorer/routes
                                  with empty map                        body: { name: "Gipfelrunde",
                                                                               difficulty_level_id: "...",
                                                                               difficulty_sport_id: "..." }
                                                                        returns: { id: "route-1", ... }
                                  GUI now has route-1 ID
                                  (sport_type_id left null --
                                  will be derived from segments)

2. Draws a trail line             GUI collects [lon,lat,ele]          (no API call -- just local state,
   on the map                     points as user draws                 user is still drawing)

3. Clicks "Save Route"           GUI sends everything in              PUT /explorer/routes/route-1/segments
                                  one call -- the drawn                  body: {
                                  segment is created inline               segments: [{
                                                                            inline: {
                                                                              coordinates: [[lon,lat,ele], ...],
                                                                              name: "Gipfelrunde",
                                                                              sport_type_id: "uuid-hiking"
                                                                            },
                                                                            slot_position: 0,
                                                                            alt_group: 0,
                                                                            is_default: true,
                                                                            is_reversed: false
                                                                          }],
                                                                          validation: "strict"
                                                                        }
                                                                      Server (single transaction):
                                                                        - sees inline block -> creates segment:
                                                                          - builds CleanedGpx from coordinates
                                                                          - runs geometry_metrics
                                                                          - runs shaping (geojson, elevation_graph)
                                                                          - creates geo_record (no performance)
                                                                          - auto-detects start/end POIs
                                                                          - creates segment row -> seg-1
                                                                        - single segment, no continuity to check
                                                                        - writes segment_route row
                                                                        - recomputes aggregates (copies segment values)
                                                                        - derives route sport_type_id from segments -> hiking
                                                                        returns: {
                                                                          id: "route-1",
                                                                          sport_type_id: "uuid-hiking",
                                                                          agg_distance_m: 4200,
                                                                          segments: [{ segment_id: "seg-1", ... }]
                                                                        }

4. Sees the finished route        GUI shows map with trail,
   with distance, elevation       elevation profile, stats
```

**Result:** 1 route, 1 segment, 1 geo_record. **Two API calls total.**
The segment was created as part of the route save, not as a separate step.

---

### Flow 2: Create a route with multiple segments (mix of drawing and reusing)

The user plans a longer route: valley parking -> hut -> summit -> back to parking.
The hut-to-summit section already exists as a public segment from another user.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Clicks "New Route"             Opens route editor                  POST /explorer/routes
                                                                        body: { name: "Zillertal Rundtour", ... }
                                                                        returns: { id: "route-2" }

2. Draws trail: parking           GUI collects points                 (no API call -- local state)
   to hut

3. Searches for existing          GUI calls search with               GET /explorer/segments?near_lat=47.05&near_lon=11.87
   segments near the hut          hut coordinates                       &radius_m=200&is_public=true
   endpoint                                                             returns: [
                                                                          { id: "seg-B", name: "Huette - Gipfel",
                                                                            start_poi_id: "poi-huette",
                                                                            end_poi_id: "poi-gipfel",
                                                                            sport_type_id: "uuid-scrambling",
                                                                            geo_record: { distance_m: 2400, ... } },
                                                                          ...
                                                                        ]

4. Picks "Huette - Gipfel"       GUI places seg-B at slot 1          (no API call -- just local state)
   from the results               GUI highlights it connects

5. Draws trail: summit            GUI collects points                 (no API call -- local state)
   back to parking

6. Clicks "Save Route"           GUI sends one call with             PUT /explorer/routes/route-2/segments
                                  2 inline + 1 existing                 body: { segments: [
                                                                          { inline: { coordinates: [...],
                                                                              name: "Parkplatz - Huette",
                                                                              sport_type_id: "uuid-hiking" },
                                                                            slot_position: 0, alt_group: 0,
                                                                            is_default: true, is_reversed: false },
                                                                          { segment_id: "seg-B",
                                                                            slot_position: 1, alt_group: 1,
                                                                            is_default: true, is_reversed: false },
                                                                          { inline: { coordinates: [...],
                                                                              name: "Gipfel - Parkplatz",
                                                                              sport_type_id: "uuid-hiking" },
                                                                            slot_position: 2, alt_group: 2,
                                                                            is_default: true, is_reversed: false },
                                                                        ], validation: "strict" }
                                                                      Server (single transaction):
                                                                        - creates seg-A from inline (hiking)
                                                                        - references existing seg-B (scrambling)
                                                                        - creates seg-C from inline (hiking)
                                                                        - validates continuity:
                                                                          seg-A end_poi "poi-huette" == seg-B start_poi OK
                                                                          seg-B end_poi "poi-gipfel" == seg-C start_poi OK
                                                                        - writes 3 segment_route rows
                                                                        - recomputes aggregates:
                                                                          distance = 3100 + 2400 + 3800 = 9300m
                                                                        - derives sport_type_id: hiking has most distance
                                                                        - derives sport_types breakdown:
                                                                          [hiking: 6900m, scrambling: 2400m]
                                                                        returns: route with aggregates + sport_types
```

**Result:** 1 route, 3 segments (2 new inline, 1 reused), **3 API calls total**
(create route, search segments, save with inline). The route's primary sport
is hiking (most distance) but the response shows both hiking and scrambling.

---

### Flow 3: Add a variant (alt-group) to an existing route

The user realizes there is a via ferrata alternative for the hut-to-summit
section. They want to offer both options in the same route.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Opens route-2 in editor        Loads route with segments           GET /explorer/routes/route-2
                                  Shows A -> B -> C on map            GET /explorer/routes/route-2/segments

2. Clicks "Add variant"           GUI enters alt-group mode
   on segment B (slot 1)          for slot 1

3. Draws the via ferrata          GUI collects points                 (no API call -- local state)
   path on the map

4. User marks B as default        GUI toggles is_default              (local state change)
   (the easier path)

5. Clicks "Save Route"                                               PUT /explorer/routes/route-2/segments
                                                                        body: { segments: [
                                                                          { segment_id: "seg-A", slot: 0, alt_group: 0,
                                                                            is_default: true, is_reversed: false },
                                                                          { segment_id: "seg-B", slot: 1, alt_group: 1,
                                                                            is_default: true, is_reversed: false },
                                                                          { inline: { coordinates: [...],
                                                                              name: "Huette - Gipfel (Klettersteig)",
                                                                              sport_type_id: "uuid-via-ferrata" },
                                                                            slot: 1, alt_group: 1,
                                                                            is_default: false, is_reversed: false },
                                                                          { segment_id: "seg-C", slot: 2, alt_group: 2,
                                                                            is_default: true, is_reversed: false },
                                                                        ], validation: "strict" }
                                                                      Server:
                                                                        - creates seg-D from inline (via-ferrata)
                                                                        - validates alt_group 1:
                                                                          seg-B and seg-D share start_poi (huette) OK
                                                                          seg-B and seg-D share end_poi (gipfel) OK
                                                                          exactly one is_default: seg-B OK
                                                                        - validates chain (defaults): A->B->C OK
                                                                        - validates alt connects: A->D->C OK
                                                                        - recomputes aggregates from DEFAULTS only
                                                                        - derives sport_types:
                                                                          defaults: [hiking: 6900m, scrambling: 2400m]
                                                                          alt included: also via-ferrata (1900m, non-default)
                                                                        returns: updated route with sport_types
```

**Result:** Same route, now 4 segment_route rows. The variant was created
inline -- no separate segment creation step needed. Sport types breakdown
shows three sports across default + alt segments.

---

### Flow 4: Edit a segment's geometry within a route

The user notices segment A (parking to hut) takes a wrong turn. They want to
fix the trail. But seg-A might be used by other routes too.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Opens route-2 in editor        Loads route with segments           GET /explorer/routes/route-2
                                                                      GET /explorer/routes/route-2/segments

2. Clicks on segment A            GUI highlights seg-A on map,
   and clicks "Edit geometry"     enters drawing mode with
                                  seg-A's existing trail shown
                                  as reference

3. User redraws the trail         GUI collects new points             (no API call -- user is drawing)
   with the correct path

4. Clicks "Save Route"            GUI sends the redrawn               PUT /explorer/routes/route-2/segments
                                  segment as inline, replacing          body: { segments: [
                                  seg-A's slot with new geometry           { inline: { coordinates: [...],
                                                                               name: "Parkplatz - Huette (corrected)",
                                                                               sport_type_id: "uuid-hiking",
                                                                               end_poi_id: "poi-huette" },
                                                                             slot: 0, alt_group: 0,
                                                                             is_default: true, is_reversed: false },
                                                                           { segment_id: "seg-B", slot: 1, ... },
                                                                           { segment_id: "seg-D", slot: 1, ... },
                                                                           { segment_id: "seg-C", slot: 2, ... },
                                                                         ], validation: "strict" }
                                                                      Server:
                                                                        - creates seg-E from inline
                                                                        - validates: seg-E.end -> seg-B.start OK
                                                                        - deletes old segment_route rows
                                                                        - writes new ones with seg-E instead of seg-A
                                                                        - recomputes aggregates
                                                                        returns: updated route

5. seg-A is now orphaned?         Not necessarily --                  (seg-A still exists in DB,
                                  other routes may use it.             no longer linked to route-2.
                                  If nobody uses it, a cleanup         Cleanup job can find segments
                                  job handles it later.)               with 0 route references.)
```

**Key point:** The user drew a correction and hit save. One API call did
everything: created the new segment, swapped it in, validated, recomputed.
The user never dealt with "segment management."

---

### Flow 5: Edit route metadata (no geometry change)

The user wants to change the route's name, difficulty, or description.
No segments are affected.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Opens route detail page        Shows route info                    GET /explorer/routes/route-2

2. Clicks "Edit" on metadata      Opens edit form

3. Changes name and difficulty    Fills form fields

4. Clicks "Save"                                                     PATCH /explorer/routes/route-2
                                                                        body: { name: "Zillertal Panoramarunde",
                                                                               difficulty_level_id: "new-uuid" }
                                                                      Server:
                                                                        - updates metadata only
                                                                        - no segment changes, no recomputation
                                                                        returns: updated route
```

**Simplest case.** No segment interaction at all.

---

### Flow 6: Reverse a segment in a route

The user wants to walk segment B (hut to summit) in the opposite direction
(summit to hut). The geometry stays the same, just traversed backwards.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Opens route-2 in editor                                           GET /explorer/routes/route-2/segments

2. Clicks "Reverse" on            GUI toggles is_reversed             (local state: seg-B now is_reversed=true)
   segment B                      for seg-B

                                  GUI immediately re-validates:
                                  seg-B reversed means:
                                    effective_start = seg-B's original end (poi-gipfel)
                                    effective_end   = seg-B's original start (poi-huette)
                                  So the chain is now:
                                    seg-A ends at poi-huette
                                    seg-B (reversed) starts at poi-gipfel  <-- BREAK!
                                  GUI shows red warning on the
                                  A -> B connection

3. User realizes the order        Reorders: A, then C (reversed),
   needs to change too,           then B (reversed)
   or reverts the change

4. Clicks "Save"                                                     PUT /explorer/routes/route-2/segments
                                                                        body: { ... updated list ... }
                                                                      Server:
                                                                        - validates the new continuity
                                                                        - recomputes aggregates
                                                                          (swaps gain/loss for reversed segments)
```

**The GUI does the heavy lifting here.** Real-time validation prevents the
user from saving a broken chain. The API just validates and persists the
final state.

---

### Flow 7: Create a segment from an existing track

The user recorded a hike last summer and wants to turn part of it into a
reusable segment for route planning.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Opens the track                Shows recorded track on map         GET /explorer/tracks/track-99
   they hiked last year           with the full trail                 GET /explorer/tracks/track-99/geometry

2. Clicks "Create segment         GUI enters selection mode:
   from this track"               user picks start and end points
                                  on the track line

3. User clicks a point            GUI marks the start (km 2.1)       (local state)
   near the hut (start)

4. User clicks a point            GUI marks the end (km 5.8)         (local state)
   near the summit (end)          GUI highlights the selected
                                  section: 3.7km of trail

5. Clicks "Create segment"                                           POST /explorer/segments/from-track
                                                                        body: {
                                                                          track_id: "track-99",
                                                                          start_distance_m: 2100,
                                                                          end_distance_m: 5800,
                                                                          name: "Huette - Gipfel",
                                                                          sport_type_id: "..."
                                                                        }
                                                                      Server:
                                                                        - loads track-99's GPX file
                                                                        - parses and cleans it
                                                                        - slices points between distance 2100m and 5800m
                                                                        - runs geometry_metrics on the slice
                                                                        - runs shaping (geojson, elevation_graph)
                                                                        - saves sliced points as new GPX file
                                                                        - creates geo_record (no performance)
                                                                        - auto-detects start/end POIs
                                                                        - creates segment
                                                                        returns: { id: "seg-F", geo_record: { distance_m: 3700, ... } }

6. Segment is ready               User can now use seg-F              (seg-F appears in segment search results
                                  in any route                         and can be placed into routes)
```

This flow also works inline. If the user is already in the route editor,
they could clip from a track and place it directly:

```
PUT /explorer/routes/{id}/segments
  body: { segments: [
    { inline: { track_id: "track-99", start_m: 2100, end_m: 5800,
                name: "...", sport_type_id: "..." },
      slot: 0, ... },
    ...
  ] }
```

---

### Flow 8: Multi-sport route (bike + hike)

The user plans a route where they cycle to the trailhead and then hike to
the summit. Two segments, two different sport types.

```
USER                              GUI                                 API
─────────────────────────────────────────────────────────────────────────────

1. Creates route                  Opens editor                        POST /explorer/routes
                                                                        body: { name: "Bike & Hike Karwendel", ... }
                                                                        returns: { id: "route-3" }
                                                                      (no sport_type_id yet -- derived later)

2. Draws cycling section          GUI collects points,                (local state -- user is drawing)
   from town to trailhead         user picks sport = cycling

3. Draws hiking section           GUI collects points,                (local state -- user is drawing)
   from trailhead to summit       user picks sport = hiking

4. Clicks "Save"                                                     PUT /explorer/routes/route-3/segments
                                                                        body: { segments: [
                                                                          { inline: { coordinates: [...],
                                                                              name: "Innsbruck - Hallerangerhaus",
                                                                              sport_type_id: "uuid-cycling" },
                                                                            slot: 0, ... },
                                                                          { inline: { coordinates: [...],
                                                                              name: "Hallerangerhaus - Gipfel",
                                                                              sport_type_id: "uuid-hiking" },
                                                                            slot: 1, ... },
                                                                        ] }
                                                                      Server:
                                                                        - creates 2 segments (cycling + hiking)
                                                                        - validates continuity
                                                                        - recomputes aggregates
                                                                        - derives sport_type_id:
                                                                          cycling segment = 15km, hiking = 6km
                                                                          primary = cycling (most distance)
                                                                        - BUT user may want this to be a "hiking" route
                                                                          that happens to include a bike approach
                                                                        returns: {
                                                                          sport_type_id: "uuid-cycling",  <-- auto-derived
                                                                          sport_types: [
                                                                            { sport_type_id: "uuid-cycling", distance_m: 15000 },
                                                                            { sport_type_id: "uuid-hiking", distance_m: 6000 }
                                                                          ]
                                                                        }

5. User overrides primary         Clicks "Change primary sport"       PATCH /explorer/routes/route-3
   sport to "hiking"              in settings                           body: { sport_type_id: "uuid-hiking" }
                                                                      Server:
                                                                        - sets sport_type_id to hiking (manual override)
                                                                        - sport_types breakdown unchanged
                                                                        returns: {
                                                                          sport_type_id: "uuid-hiking",  <-- user override
                                                                          sport_types: [
                                                                            { sport_type_id: "uuid-cycling", distance_m: 15000 },
                                                                            { sport_type_id: "uuid-hiking", distance_m: 6000 }
                                                                          ]
                                                                        }
```

**The auto-derivation picks the sport with the most distance, but the user
can override it.** The `sport_types` breakdown always reflects reality
regardless of what the primary is set to.

---

### Flow 9: What happens when segment geometry is wrong but used in many routes

A segment is shared across 5 routes. A user discovers the trail data has an
error. What happens?

```
Option A: The segment owner fixes it (creates a new one)

  1. Owner creates a corrected segment (seg-G) via any method
  2. Owner opens each of their routes that use the bad segment
  3. In each route editor, saves with the new segment inline or referenced
     (the old segment is automatically replaced in one PUT call per route)
  4. Other users' routes still use the old segment (they fix their own)
  5. The old segment can be marked is_public=false to prevent new use

Option B: Just fix the metadata (name was wrong, difficulty was wrong)

  PATCH /explorer/segments/{id}
    body: { name: "Corrected Name", difficulty_level_id: "..." }

  This is fine -- metadata changes propagate to all routes intentionally.

Option C: The geometry error is small (GPS drift)

  This is an argument for tolerant thresholds. If the error does not break
  continuity validation, it may not matter for route planning purposes.
```

**The rule is clear:** geometry is never modified in place. Metadata is.
The inline creation flow makes the swap feel invisible to the user.

---

### Summary: when does each API endpoint get called?

| User action in GUI                         | API calls                                           |
|--------------------------------------------|-----------------------------------------------------|
| Open "New Route"                           | POST /routes                                        |
| Draw a trail section                       | (no call -- local state until save)                 |
| Upload a GPX for a section                 | POST /upload (temp file) -- ref used in inline      |
| Search for existing segments nearby        | GET /segments?near_lat=...&near_lon=...              |
| Pick an existing segment from search       | (no call -- adds segment_id to local state)         |
| Add a variant to a slot                    | (no call -- local state until save)                 |
| Reverse a segment                          | (no call -- toggle is_reversed in local state)      |
| Reorder segments                           | (no call -- change slot_positions in local state)   |
| Validate while editing (real-time)         | POST /routes/{id}/segments/validate                 |
| Save the route (with any new segments)     | PUT /routes/{id}/segments (inline + existing mixed) |
| Edit route name/difficulty/sport override  | PATCH /routes/{id}                                  |
| "Edit" a segment's geometry                | PUT /routes/{id}/segments (inline replaces old)     |
| Create standalone reusable segment         | POST /segments (outside route editor)               |
| Create segment from recorded track         | POST /segments/from-track (or inline in PUT)        |
| Delete a route                             | DELETE /routes/{id}                                 |

---

---

## Open Issues and Gaps

Issues found during review. Each needs a decision before implementation.

### Issue 1: Route NOT NULL columns vs auto-derivation (schema conflict)

The route model has three NOT NULL foreign keys:

- `sport_type_id` (NOT NULL)
- `difficulty_level_id` (NOT NULL)
- `difficulty_sport_id` (NOT NULL)

But the plan says these are auto-derived from segments. Problem: at `POST /routes`
time there are no segments yet, so there is nothing to derive from.

**Options:**

A) **Make them nullable** in the model. They start NULL on creation, get auto-set
   when segments are added via PUT. The first PUT with segments is what populates
   them. Routes with no segments show as "draft" with no sport/difficulty.

B) **Require them at creation time**, then auto-update on segment changes. The user
   picks a sport and difficulty when creating the route, and the system overrides
   if the segments say something different. This feels wrong -- user picks "hiking"
   at creation, adds a bike segment, system overrides to "cycling."

C) **Require them at creation, auto-update is opt-in.** User sets them at creation.
   Segment recomputation auto-sets them only if the user hasn't manually overridden.
   Needs a flag like `sport_type_override: bool`.

**Recommendation:** Option A (make nullable) is cleanest. A route without segments
is a draft and should not pretend to have classification data. Add a `status` concept
(draft / complete) based on whether segments exist.

### Issue 2: Sport type override persistence

When the user manually overrides `sport_type_id` via PATCH (Flow 8, bike+hike),
and then later adds or removes segments (PUT /segments), does the recomputation
overwrite the manual override?

**Solution:** Add a boolean column `sport_type_manual` (default false). When set
via PATCH, mark as manual. When recomputing aggregates, skip the sport_type auto-set
if `sport_type_manual` is true. Same pattern for difficulty if needed.

### Issue 3: Route composite geojson and elevation graph

The document describes aggregate numbers (distance, elevation) but never mentions
the route's map geometry or elevation profile. A route needs:

- **Combined geojson** for rendering the full route on a map (concatenation of
  default segments' geojson, with reversed segments' coordinates flipped)
- **Combined elevation graph** for showing the full route elevation profile

**Options:**

A) Compute at read time from segments' geo_records. Simple, always fresh,
   but requires loading all segments' geojson on every route GET.

B) Store as cached/denormalized fields on the route, recomputed with aggregates.
   Faster reads, but adds complexity and staleness risk.

C) Separate endpoint `GET /routes/{id}/geometry` that assembles on demand.
   Keeps the main GET lightweight, map data loaded only when the map is shown.

**Recommendation:** Option C matches the existing track pattern (you already have
`GET /tracks/{id}/geometry`). The route GET returns aggregate numbers; a separate
geometry endpoint returns the combined geojson + elevation graph.

### Issue 4: Segment sub-resources (POIs and photos)

The M2M tables `segment_poi` and `segment_photo` exist but the document never
describes how they are managed. These link POIs and photos to specific points
along a segment (with distance_m from segment start, slot_position for ordering).

**Needed:**

- Segment POIs: `GET/PUT /segments/{id}/pois` -- ordered list of POIs along the segment
- Segment photos: `GET/PUT /segments/{id}/photos` -- photos attached to the segment
- These are separate from start_poi_id / end_poi_id (which are endpoint markers for
  continuity). Segment POIs are points of interest along the trail (viewpoints,
  water sources, etc.)
- Auto-detection: when a segment is created, run poi_detection against its full trail
  (not just endpoints) to auto-populate segment_poi with nearby compendium POIs and
  their distance along the trail

### Issue 5: Plan conditions management

Both route and journey have `plan_condition_id` linking to `explorer_sub_plan_conditions`
(equipment, permits, best months, guide requirements). But there is no mention of how
plan conditions are created or managed.

**Options:**

A) **Nested inline** -- plan_conditions are created/updated as part of the route/journey
   PATCH. The route owns its plan_conditions row. No separate CRUD.
   ```json
   PATCH /routes/{id}
     body: { plan_conditions: { permit_required: true, best_months: [6,7,8], ... } }
   ```

B) **Separate CRUD** for plan_conditions, then link by ID.

**Recommendation:** Option A. Plan conditions are not shared across routes (unlike
segments). They belong to exactly one route or journey. Inline management is simpler.

### Issue 6: Real-time validation with inline segments

The validate endpoint `POST /routes/{id}/segments/validate` needs to work while
the user is still drawing (before save). But inline segments haven't been processed
yet -- the server doesn't have start/end locations for them.

**Options:**

A) The validate endpoint accepts inline blocks and runs full GPX processing just for
   validation. Expensive, wasteful if the user is still editing.

B) The validate endpoint accepts a lightweight format for unpersisted segments: just
   `{ start: [lon, lat], end: [lon, lat] }` instead of full coordinates or segment_id.
   Good enough for continuity checking.

C) The GUI validates locally using the first/last drawn points. No server call for
   inline segments. Server validation only runs on save. The validate endpoint only
   accepts segment_id references.

**Recommendation:** Option C with B as enhancement. The GUI already has the drawn
coordinates and can check "does the end of my drawing match the start of the next
segment?" locally. Server validation at save time is the authority. The validate
endpoint works with existing segment_ids for checking chain integrity of saved
segments.

### Issue 7: alt_group redundancy with slot_position

In all examples, `alt_group` equals `slot_position`. If alternatives always share
the same slot_position, then alt_group is redundant.

**When alt_group differs from slot_position:** A multi-slot alternative. Example:
the normal path is slots 1,2 (two segments), but the shortcut is a single
segment that covers the same ground. The shortcut would be slot 1, alt_group X,
while the normal two segments are slots 1 and 2, both in the default group.
But this breaks the current validation model which works per-slot.

**Decision needed:** Is multi-slot alternative a real use case? If not, alt_group
is redundant and could be removed to simplify. If yes, the validation algorithm
needs rethinking.

**Recommendation:** Keep alt_group for now but document that for v1, alt_group
must equal slot_position. Multi-slot alternatives can be designed later if needed.

### Issue 8: Orphan segment cleanup

Flows 4 and 9 mention that replaced segments may become orphaned (referenced by
zero routes). The document doesn't specify cleanup.

**Options:**

A) **Periodic Celery task** that finds segments with zero segment_route references
   and deletes them after a grace period (e.g., 30 days). Simple, but segments
   created as standalone reusable might get cleaned up unintentionally.

B) **Never auto-delete.** Segments are lightweight. Let users manage their own
   segments via `GET /segments?mine=true` and delete manually. The is_public flag
   controls visibility to others.

C) **Mark as "route-created" vs "standalone."** Inline-created segments are flagged
   as route-created. Only those are candidates for orphan cleanup. Standalone
   segments (created via POST /segments) are never auto-deleted.

**Recommendation:** Option B for v1. Segments are small. Auto-deletion is risky
(what if a user plans to reuse a segment tomorrow?). A "my segments" view in
the GUI lets users see and clean up their own.

### Issue 9: Ownership of inline-created segments

When user A creates a route and inline-creates segments, user A owns both the
route and the segments. Clear.

But if user B later edits route (if permissions allow) and adds inline segments,
who owns those new segments? User B (the creator) or user A (the route owner)?

**Decision:** The segment's `created_by` should be the user who triggered the
inline creation (user B). This follows the existing pattern where created_by
tracks authorship. The route's `created_by` is separate and does not change.

### Issue 10: Concurrency on route segment updates

Two users editing the same route's segments at the same time. PUT is a full
replacement, so last-write-wins silently.

**Options:**

A) **Optimistic locking** -- route has an `updated_at` timestamp. PUT includes
   `if_unmodified_since` or an ETag. If the route was modified between GET and
   PUT, return 409 Conflict.

B) **Accept last-write-wins** for v1. Routes are typically edited by their owner
   alone.

**Recommendation:** Option B for v1, with a note that Option A should be added
when collaborative route editing is introduced.

---

## Implementation Phases

### Phase 1: Segment foundation

1. Segment schemas (SegmentCreate, SegmentRead, SegmentUpdate)
2. `process_segment_gpx()` wrapper (thin layer over existing pipeline)
3. `persist_processed_segment()` (modeled on persist_processed_track, simpler)
4. Segment CRUD routes (following gear.py pattern)
5. "Create from track clip" endpoint
6. Auto-detect start/end POIs

### Phase 2: Route with validation

1. Route schemas
2. Route CRUD routes (metadata only, following the pattern)
3. Continuity validation service (the algorithm described above)
4. PUT /routes/{id}/segments endpoint with validation
5. Aggregate recomputation service
6. Route GET responses include nested segments with geo data

### Phase 3: Journey

1. Journey schemas
2. Journey CRUD routes
3. PUT /journeys/{id}/routes endpoint
4. Journey aggregate recomputation
5. Optional journey continuity warnings

### Phase 4: Integration

1. Wire into Prediction (once pace curves exist, predict route duration)
2. Connect to social module (ratings feed into rating_avg/rating_count)
3. Connect to schedule (plan a route or journey for a date)
4. Connect to liked_routes / liked_journeys

---

## Shared Services

### Aggregate recomputation service

A single service module (`explorer/services/aggregate.py`) with:

- `recompute_route_aggregates(session, route_id)` -- sums default segments
- `recompute_journey_aggregates(session, journey_id)` -- sums routes

Called automatically after any segment list or route list change.
Could also be a Celery task for large journeys, but likely fast enough inline.

### Continuity validation service

A single service module (`explorer/services/continuity.py`) with:

- `validate_route_segments(segments_with_geo, threshold_m) -> ValidationResult`
- `validate_alt_group_endpoints(group_segments, threshold_m) -> ValidationResult`
- `validate_journey_routes(routes_in_order, threshold_m) -> ValidationResult`

Returns a structured result with:
- is_valid: bool
- warnings: list of gap descriptions (which slots, distance between endpoints)
- errors: list of hard failures (missing geo_record, no segments)

Used by both the save endpoint (to block or warn) and the dedicated
validate endpoint (for real-time GUI feedback without saving).
