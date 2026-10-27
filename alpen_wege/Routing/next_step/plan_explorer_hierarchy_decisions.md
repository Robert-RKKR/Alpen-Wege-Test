# Explorer hierarchy (segment, route, journey): decisions

Status: agreed with the user on 2026-10-27, except the items marked **CHECK** (new points found while reading the code and data; they need a short yes/no).
Plan text: `plan_explorer_hierarchy_v2.md` (v1 stays in `plan_explorer_hierarchy.md`).

## Agreed

| # | Topic | Decision |
|---|---|---|
| D1 | Route classification columns | `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id` on the route become **nullable**. A route without segments is a draft with no classification. |
| D2 | "Hardest segment" | A new numeric column **`rank`** (like `point_factor`) on the reference tables that have a real scale. Higher number = harder / rarer / worse. API, DB, CSV seed files, tests and Postman are updated together. |
| D3 | Schema changes | Everything here is test, not production. Models are changed directly. No migration framework. One short SQL script for the test database (or a database reset), because `create_all` does not alter existing tables. |
| D4 | Delete protection | Both: the code answers 409 when a segment is used by a route, and the foreign key `segment_route.segment_id` changes from CASCADE to RESTRICT. The 409 shows a count and only the routes the caller may see. |
| D5 | Inline segment processing | Drawn coordinates are processed inside the route save (with size caps). A GPX file goes through `POST /segments` (multipart) and returns an ID the route then references. Clip-from-track runs inline. No generic upload endpoint. |
| D6 | Sport and difficulty override | No `sport_type_manual` column. Auto-derive only when the value is empty; never overwrite a value the user set. |
| D7 | Privacy of segments | Clip-from-track removes timestamps and heart rate. Only the track owner can clip it. New standalone segments start private. A segment used by another user's route cannot be made private or deleted. |
| D8 | Geometry assembly and size limits | The combined elevation graph adds the distance offset per segment and is reversed for reversed segments. Caps on points per segment, points per save and segments per route. |
| D9 | Build order | Step 0 rank, then Phase 1 segments, Phase 2 routes, Phase 3 journeys. Each step follows the folder layout, the filters and `?expand=` conventions, and gets tests and Postman requests. |

## Corrections found while reading the code and data (CHECK)

| # | Finding | Proposal |
|---|---|---|
| C1 | I first proposed `rank` for 8 tables. The CSV files show that `snow_condition` (12 values), `trail_condition` (13) and `weather_condition` (15) have `point_factor = 1` for every row and are plain categories (Powder, Wet, Corn / Dry, Muddy, Closed / Sunny, Hail), not a scale. `schedule_status` mixes a lifecycle with branches (Postponed, Cancelled, Failed). A rank there would be invented. | `rank` only on 4 tables: `difficulty_level`, `difficulty_sport`, `rarity`, `visibility`. The other 4 can get it later if a feature needs it. |
| C2 | `difficulty_sport` has 50+ grades in 10 grading systems. UIAA and French share one sport type (climbing). Grades are only comparable inside the same `sport_type_id`. | `rank` is a scale per `sport_type_id`; equal ranks are allowed (equivalent grades). A route's `difficulty_sport_id` is the highest rank among its default segments of the **primary sport** only. The UIAA/French mapping needs your review in the CSV. |
| C3 | v1 lists `POST /segments/upload-csv`. A segment needs a geo record (`geo_record_id` NOT NULL), so CSV import of segments cannot work. | Drop it. |
| C4 | v1 never recalculates journeys when a route changes. After `PUT /routes/{id}/segments` every journey that contains the route has stale totals. | After a route save, recompute all journeys that contain the route, in the same transaction. |
| C5 | `route_journey.route_id` is also CASCADE: deleting a route silently removes days from journeys. | Same rule as D4: RESTRICT plus a 409. A route used by another user's journey cannot be made private or deleted (same as D7). |
| C6 | A public route that uses private segments would show those segments to other users. | Publishing a route publishes its own segments in the same transaction. A segment owned by someone else must already be public, otherwise 422. Unpublishing a route leaves segments alone. A segment used by a public route cannot be made private. |
| C7 | After the first automatic sport/difficulty (D6), later segment edits would not update it, and a route could be labelled easier than its hardest segment. | Detail responses get read-only computed fields (`derived` and `classification_differs`). No new column. |
| C8 | v1 stores a GPX file for every segment. An uploaded "planned" GPX may be a recorded one with times and heart rate. | Segments store no GPX file (`gpx_id` stays NULL). The upload is processed (times and heart rate dropped) and then deleted. A GPX download can be generated from the geometry later. |
| C9 | Processing a segment GPX or a clip inside the request is a change from tracks (202 and Celery). | Run in a threadpool with a small limit for segment uploads. Measure the time on the largest allowed file in the sandbox; if it is slow (more than about 5 s), move it to a job like tracks. |

Answer with "C1 yes, C2 yes ..." or send changes.
