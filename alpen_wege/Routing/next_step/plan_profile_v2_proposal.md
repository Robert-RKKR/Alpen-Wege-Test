# Profile area: proposal v2, checked against the code (2026-10-27)

This note joins the three plans `plan_profile_editable.md`, `plan_profile_readonly.md` and `plan_profile_sticky.md` into one build plan. I read all three plans and then the real code (models, workers, services, seeds, route layout, tests). Where the plan and the code disagree, the code wins and the plan is corrected here.

Nothing was built or changed in the repo. The only thing I ran is one small PostgreSQL test (finding F6).

How to answer: for each decision D1 to D12 below, write the number and "recommended" or your own text. If you agree with everything, write **"all recommended"**.

---

## 1. What exists today

| Table (model) | Written today by | API today |
|---|---|---|
| `profile_sub_schedule` | nobody | none |
| `profile_sub_body_metric` | nobody | none |
| `profile_sub_pace_curve` | nobody | none |
| `profile_m2m_liked_route`, `profile_m2m_liked_journey` | nobody | none |
| `profile_sub_point` | nobody | none |
| `profile_cat_achievement` (the catalog) | nobody; no seed file for it in `push_data/` | none |
| `profile_m2m_user_achievement` | nobody | none |
| `profile_m2m_user_poi` (visit log) | `detect_for_track`, `rescan_poi_batch` (POI detection) | none |
| `profile_m2m_user_card` | the same two functions, and `rescan_card` | none |
| `profile_sub_statistic` | `recompute_user_statistics` (Celery task `stats.recompute_user`) | none |

So the whole profile area has **no routes at all** (the router has only auth, users, access-policies). About 43 new routes are needed (count in section 3).

Parts of the plans that I checked and that hold as written: cards and POI visits are created by the system (`detect_for_track`), no DELETE for event-log data, PATCH changes only `comment`, one weight per user and day (unique on `user_id, recorded_at`), the partial unique index for non-repeatable achievements exists (`ix_profile_m2m_user_achievement_unique_first`), progress is computed when read, gradient bins are a free integer today.

---

## 2. Where the plans and the code disagree

| # | Finding | Evidence | Effect on the plan |
|---|---|---|---|
| F1 | The statistics service fills much less than the readonly plan says ("already exists and works"). It fills 10 columns and `unique_pois_count`. It **never** fills: `current_streak_days`, `longest_streak_days`, `total_points`, `total_plans_created/completed/skipped`, `unique_regions_count`, and the four `*_graph` columns. | `explorer/services/track_statistics.py` (all SQL read) | The plan lists only graphs and regions as missing. The overview (streak badge, points tile) would show zeros. Four more gaps to close. |
| F2 | The seeded schedule statuses are **10**: Draft, Planned, Confirmed, In Progress, Completed, Postponed, On Hold, Cancelled, Failed, Aborted. There is no "Skipped". Names have spaces. | `push_data/core_ref_schedule_status.csv` | The plan's 5 statuses and its transitions do not match. See D5. |
| F3 | The seeded point reasons are **20**. The names in the plan ("Achievement Earned", "POI Visited", "Trip Completed") do not exist. Real names: Activity Completed, Achievement Unlocked, POI Discovered, Card Collected, Summit Reached, Streak Bonus, Distance Milestone, ... There is no "Trip Completed". Every reason has its own `point_factor` (1, 1.2 for Streak Bonus, 1.5 for Summit Reached, 2 for First Ascent). | `push_data/core_ref_point_reason.csv` | Reasons must be looked up by name; the plan's fixed `*_REASON_ID` constants do not exist. Points need a formula. See D6. |
| F4 | The event chain in the sticky plan ("track processed, then detect_pois, then recompute_statistics, then evaluate_achievements") does not exist. In the code, `process_track_gpx` starts `detect_pois` **and** `request_stats_recompute` side by side. Stats recompute is debounced (Redis key `stats:pending:<user>`, delay `STATS_RECOMPUTE_DELAY_S` = 5 s). It is also requested from archive, restore, update, reprocess, rescan_poi and rescan_card. | `worker/tasks/track_processing.py` lines 163-173, `explorer/services/dispatch.py` `request_stats_recompute`, `explorer/routes/track/{archive,restore,update}.py` | Achievements must start at the **end of the stats task** (one place that every trigger already reaches). See D7. |
| F5 | The profile tables are owned through `user_id`. The project's access helpers (`apply_scope`, `check_object_access`) look at `created_by` and `is_public`, which these tables do not have. | `core/utils/scope.py`, `profile/permissions/resource_access.py`, `core/base.py` (`UserScopedMixin`) | The helpers cannot be reused as they are. Own-data routes need an "owner gate": filter by `user_id`, answer 404 for rows of others (the same as `my-jobs`, kind C in the security proposal). See D2. |
| F6 | **Real bug waiting:** `schedule.route_id` and `journey_id` are `ON DELETE SET NULL`, but a CHECK says one of them must stay set. Deleting a route that is the only target of a schedule entry fails inside the database. I proved it in a throw-away PostgreSQL: deleting the route gives `new row for relation violates check constraint`. Today the route delete code catches every `IntegrityError` and answers 409 "used by 0 journey(s)" (a wrong message). | model `profile/models/models_sub/schedule.py`; `explorer/routes/route/delete.py` (the `except IntegrityError` block); `explorer/services/visibility.py` `in_use_error` | A route could not be deleted and the user would get a confusing text. Must be solved before schedule goes live. See D4. |
| F7 | The `achievement` resource key exists in the seeded policies, but with rules that fit the wrong thing: viewer and editor get create/update/delete "own", guest gets read "public". The catalog model has no `is_public` column, so `apply_scope` with scope "public" would fail. And there are no routes and no seed rows for the catalog, so the engine would have nothing to evaluate. | `scripts/init_seed.py` (`ACHIEVEMENT_KEYS`, `build_policies`), `profile/models/models_cat/achievement.py` (has `CreatorMixin`, no `PublicMixin`) | The catalog needs its own admin-managed routes and a first set of achievements. See D7. |
| F8 | The plans use `page=1`, `from_date`, `to_date`, `sort` asc/desc, and nested objects "when expanded". The project now has one standard: `limit` / `offset`, `ok_list`, `sort=-field`, `moment_query` ranges, `ids_query`, and `?expand=` for nested objects (all delivered 2026-10-26). | `core/utils/listing.py`, `core/utils/expand.py` | Every list in this proposal uses those building blocks. Names change, behaviour stays. |
| F9 | The plans use `/profile/me/<thing>`. The URL standard is `/api/v1/{app}/{resource}` and a route folder per resource (sub tables in `routes/sub/`, link tables in `routes/m2m/`). `me` is not a resource. | `tests/test_routes_standard.py`, `api_routes_phase3_uniform_layout.md` | New URL names. See D1. |
| F10 | "Public profile" and "followers" cannot be built now. The user model has no visibility flag. `SocialM2mFollow` exists, but the social app has no routes and is not registered in `main.py`. | `profile/models/user.py`, `social/`, `main.py` | The two public endpoints (`/users/{id}/statistics`, achievements, cards summary) must wait. See D11. |
| F11 | Pace curves: (a) nothing reads them; `ExplorerSubPrediction` is only a model and the prediction plan (`plan_recorded_hierarchy.md`) is not built. (b) The speed per gradient is **not stored**: `geo_performance` keeps averages and `speed_pattern`, a graph cut down to 300 points for display. So the recompute must read each GPX file again (as POI detection does with `load_clean_segments`), not "use the processed data" as the plan says. (c) The window-grade code exists in `gpx/metrics.py` (`_windowed_grade`, grade clipped to -100..100). | `explorer/models/models_sub/prediction.py`, `explorer/services/gpx/metrics.py` | "Integration with prediction" is out of scope now. The recompute is heavier than the plan suggests. See D10. |
| F12 | `like_count` does not exist on routes or journeys (the plan's open issue 4 recommends adding it). Route and journey already store `rating_avg` / `rating_count` the same way. | grep over `app/` finds no `like_count` | One DDL line per table. See D9. |
| F13 | Points have no protection against doing the same award twice. A track that is reprocessed becomes `ready` again, and `rescan_poi` / `rescan_card` run again. The plan's `award_activity_points` has no duplicate check. | `profile/models/models_sub/point.py` (no unique rule), `tracks.reprocess` in `track_processing.py` | Points would double. See D6. |
| F14 | The statistics plan's flow 2 shows a "Monthly breakdown table" for a year, but the year response has no months. Also statistic rows exist only for periods that have tracks. | readonly plan flow 2 and schemas; `track_statistics.py` | Year detail must carry a `months` list, and an empty user must get a zero answer, not 404. See D8. |
| F15 | The region count in the plan uses `region.boundary`. The column is called `bbox` (a bounding box, nullable), and boxes of neighbouring regions overlap. POIs already carry `main_region_id` (NOT NULL). | `compendium/models/models_cat/region.py`, `poi.py` | Use the region of visited POIs. See D8. |
| F16 | There is no way to link a track to a route (the track table has no route column). So "the system notices a track matches the plan" cannot work yet. The plan already says no auto-complete, so only manual linking is possible. | `explorer/models/models_agg/track.py` | Link by `PATCH` with a `track_id` that must be the user's own. No change to the plan's decision, only the reason is stronger. |
| F17 | `received_at` on points is a **date**, not a time. Many rows share the same value. | `profile/models/models_sub/point.py` | Sort needs a tie breaker (`created_at`, then `id`). The `sort_params` helper already supports it. |
| F18 | Every table is in the event log (`tracking_mode "all"`, except a short list) and the write routes I checked call `log_created/updated/deleted` (segment create does it through its `_shared.py`; settings update has its own audit). The plans do not mention it. | `management/utils/seed_entity_types.py`, `explorer/routes/route/delete.py` | All new write routes must log. Rows written by workers with raw SQL (statistics, points, visits) are not logged today, and I keep it so. |

---

## 3. Proposed URLs and folders (decision D1)

All paths start with `/api/v1/profile`. Everything here is always the caller's **own** data, so no `/me` and no user id in the path. Folder names follow the model names (like `m2m/poi_region` becomes `/poi-regions`).

| Folder in `profile/routes/` | URL | Endpoints |
|---|---|---|
| `sub/schedule/` | `/schedule` | list, get, create, update (PATCH), delete |
| `sub/body_metric/` | `/body-metrics` | list, create, update, delete |
| `sub/pace_curve/` | `/pace-curves` | list, get `{sport_type_id}`, replace (PUT), delete, `POST /recompute` (202 + job) |
| `m2m/liked_route/` | `/liked-routes` | list, `PUT /{route_id}` (like), `DELETE /{route_id}` (unlike) |
| `m2m/liked_journey/` | `/liked-journeys` | the same three |
| `sub/statistic/` | `/statistics` | overview, `/all`, `/year/{year}`, `/month/{year}/{month}` |
| `sub/point/` | `/points` | list, `/summary` |
| `m2m/user_poi/` | `/user-pois` | list, get, update comment, `/map` |
| `m2m/user_card/` | `/user-cards` | list, get, update comment, `/summary` |
| `m2m/user_achievement/` | `/user-achievements` | list, get, update comment, `/progress` |
| `achievement/` (the catalog, regular resource) | `/achievements` | list, get, create, update, delete (create/update/delete administrator only) |

That is 5 + 4 + 5 + 3 + 3 + 4 + 2 + 4 + 4 + 4 + 5 = **43 routes**. Fixed paths (`/summary`, `/map`, `/progress`, `/recompute`, `/all`) are imported before `/{id}` paths, as the folder rule says. Likes use PUT instead of POST because repeating the call must give the same answer (the plan wants that too).

Lists use the standard parts: `limit`/`offset`, `sort=`, filters named like the existing ones. Examples: schedule `status_id` (several allowed), `planned_from`, `planned_to`, sort `planned_at` (default); body metrics `recorded_from`, `recorded_to`; points `reason_id`, `received_from`, `received_to`; user-pois `poi_id`; user-achievements `category_id`, `rarity_id`. Nested route, journey, status, POI, card or achievement come through `?expand=`.

---

## 4. Build order (decision D3)

The plans start with schedule. The code suggests another order, because the system **already collects** visits and cards and statistics, so reading them is cheap and gives value at once.

| Step | Content | Why here |
|---|---|---|
| 0 | One DDL script `scripts/sql/profile_ddl.sql` (list below), seed of the new policy key | the only SQL for the whole area |
| A | Read-only: `/user-pois`, `/user-cards` (with comment PATCH), `/statistics` (with what is computed today) | data exists, no new writers, low risk |
| B | Schedule, body metrics, likes (+ `like_count`) | plain CRUD, needs no worker |
| C | Fill the statistics gaps: streaks, plan counts, regions, graphs, months | needs schedule from B for plan counts |
| D | Points: award helper, hooks in the pipeline, `/points`, points sum into statistics, backfill script for existing data | needs the dedupe column from step 0 |
| E | Achievements: catalog routes + first seed rows, engine at the end of the stats task, `/user-achievements`, `/progress` | needs C and D |
| F | Pace curves: CRUD, recompute job (new job kind), no prediction yet | independent, heaviest worker |
| G | Public profile (statistics, achievements, cards summary) | waits for D11 |

DDL in step 0: `profile_sub_point.dedupe_key` + unique index (D6); `like_count` on route and journey (D9); schedule CHECK change (D4); policy key `profile` and its policies (D2). Nothing else. No `is_manual` column (D10).

Every step is delivered the way the last ones were: backup tarball, unit tests, live check script against a real stack, mutation tests on the new tests, an independent review pass, `route_map compare`, rebuilt Postman collection, README section, a delivery note in `next_step/`, and the host changes added to the combined runbook. New worker modules must be added to the `include` list in `worker/celery_app.py`. I did not plan this as one delivery: it is 7 deliveries.

---

## 5. Decisions

**D1. URL names.** Why: the URL standard has no place for `/me`, and everything here is the caller's own data anyway.
Options: (A) section 3 (no `/me`, names like the models); (B) keep the plan's `/profile/me/...` and add `me` as an allowed segment.
Recommended: **A**. It follows the standard without an exception. Note for the GUI: `/profile/users/me` stays for the account itself.

**D2. Who may use these routes (access).** Why: the policy table cannot filter on `user_id` (F5), and `plan_improvements.md` (section on resource types) proposes one new key per table (among them `schedule`, `body_metric`, `pace_curve`). Each key adds 16 cells to the permission test matrix (4 groups x 4 actions).
Options: (A) no policy, any active user (owner gate only); (B) **one** new key `profile` ("own profile data") in the policy table, owner filter by `user_id` in the code; (C) one key per table.
Recommended: **B**. An administrator can still switch an action off for a group (for example guests cannot write, which fits their read-only role) and the tests need one more key only. Scope is always "own", even for administrators (nobody reads another person's weight through this API). Guest default proposed: read yes, write no. Needs one decision from you: **may guests like routes, log weight and plan?** My default is no.

**D3. Build order.** Why: see section 4.
Options: (A) the plans' order (schedule first); (B) section 4 (read-only first, then CRUD, statistics gaps, points, achievements, pace curves, public last).
Recommended: **B**. Each step is small enough to be tested with evidence, and the order follows the dependencies (plan counts need schedule, achievements need statistics and points).

**D4. Schedule entry whose route or journey is deleted (F6).** Why: today it breaks route delete.
Options: (A) change the foreign keys to RESTRICT: the route cannot be deleted while a plan uses it (409 "used by N planned activities"). Same rule as "route used by a journey". But a stranger's private plan blocks the owner, and the owner is not allowed to see it; (B) keep SET NULL and **drop the CHECK**; "at least one of route or journey" is checked by the API on create and update only. The entry survives with an empty target (the GUI shows "route deleted"), and finished entries keep their history; (C) CASCADE: the plan disappears silently, completed history is lost.
Recommended: **B**. It never blocks anyone and loses nothing. Cost: one `ALTER TABLE` and a test. The route delete code needs no change then. (If you prefer A, route delete gets a second "used by" check and a message.)

**D5. Schedule statuses and moves (F2).** Why: the seed has 10 statuses, the plan assumed 5.
Proposal: open = Draft, Planned, Confirmed, In Progress, Postponed, On Hold; finished = Completed, Cancelled, Failed, Aborted. Moves inside open are free. From open to finished is allowed. From finished back to open is refused (409), as the plan wants for "completed back to planned". For the statistics: completed = Completed; "skipped" = Cancelled, Failed, Aborted (the column comment says "skipped or cancelled"). Default status on create: Planned, found by name, not by id. `completed_at` is set by the server when the status becomes Completed and none is given. Validations: route or journey must be visible to the user (same rule as reading it); `track_id` must be the user's own track; status must exist. Two entries for the same route and day are allowed.
Recommended: **accept as proposed.**

**D6. Points: no doubles, and how many points (F3, F13).** Why: reprocess and rescan run the same award again; and the real reasons carry factors.
Idempotency options: (A) add one column `dedupe_key` (text) with a unique index `(user_id, dedupe_key)`; keys like `activity:<track_id>`, `poi:<poi_id>`, `card:<card_id>`, `achievement:<user_achievement_id>`; the insert uses `ON CONFLICT DO NOTHING`; manual or admin points leave it empty; (B) several nullable link columns and a wide unique index.
Amount options: (A) amount = base x `reason.point_factor` (achievements: base x achievement factor x rarity factor, not all ref factors multiplied); base values live in the existing runtime settings so you can change them without a deploy; (B) fixed numbers in code.
Where it is awarded: Activity Completed at the end of track processing and reprocess; POI Discovered only on the **first** visit of a POI (later visits give nothing, so the plan's "+points per visit" would not pay twice); Card Collected when a card row is really inserted; Achievement Unlocked by the engine. Points are written in the same transaction as the visit or card row. Each new award also calls `request_stats_recompute`.
Existing users: a script `scripts/backfill_points.py` (like `recompute_stats.py`) awards for data that already exists, safe to run twice because of the key.
Recommended: **A and A.** Starting base values as placeholders for you to change: activity 50 (from the plan), POI 20, card 30, achievement 100. Tell me other numbers if you have them.

**D7. Achievements: catalog, engine, trigger (F4, F7).** Why: the engine has no data and no defined criteria today.
Catalog: administrator-only create/update/delete (`require_groups`, like access-policies), read for every active user, with a small seed file of about 10 achievements (distance, elevation, streak, POI count). The unused `achievement` policy key stays as it is (no routes use it) and I will list it as a clean-up item, not change it now.
Criteria: the table already has `criteria_type_id` (12 seeded types) and `criteria_scope_id` (13 seeded scopes). Engine v1 understands only: Cumulative and Milestone (a statistics field at least a value), Streak (`current_streak_days` or `longest_streak_days`), and a count field (`unique_pois_count`, `active_days`). Scope Lifetime, Yearly, Monthly map to statistics scope `all`, `year`, `month`. The JSON holds only `field`, `value`, optional `sport_type_id`; **no `scope` key** (the plan's example repeats what the scope column already says). Other types and scopes are skipped, and each skipped achievement is logged once, never an error. Repeatable achievements (`is_repeatable`) are skipped in v1.
Trigger: the stats task calls the engine as its last step, so every route to a recompute (upload, archive, rescan, new plan) also re-checks achievements. Awarding inserts the user achievement and its points, with the `ix_..._unique_first` index as the second safety.
Recommended: **accept as proposed.**

**D8. Statistics gaps (F1, F14, F15).** Why: see F1. Proposal for each missing column:
- Streaks: from the days with at least one ready, non-archived track (UTC). Longest streak on the all-sports row of every scope; current streak only on the lifetime row.
- Plan counts: from the schedule by `planned_at` (UTC year and month), on the all-sports rows only (a plan has no sport). Needs D5.
- Points: sum of points by `received_at`, all-sports rows only.
- Regions: `unique_regions_count` = distinct `main_region_id` of the POIs the user visited (same source as `unique_pois_count`). Not the bounding box.
- Graphs: accept the plan's format, `[[day_of_year, value]]` for year, `[[day_of_month, value]]` for month, `[[year, value]]` for lifetime. They are cumulative values per day, written by the same recompute.
- Answers: a user without statistics gets a full zero answer, not 404. The year detail gets a `months` list (the month rows of that year, all-sports). Every answer carries `updated_at`. `include_graphs=false` by default, as the plan says. Month-over-month comparison stays in the GUI (plan: agree).
- New recompute triggers: schedule create, update, delete, and awarded points.
Recommended: **accept as proposed.**

**D9. Likes (F12).** Why: `like_count` does not exist.
Proposal: add `like_count` (integer, default 0) to route and journey. Like inserts with `ON CONFLICT DO NOTHING` and adds 1 only when a row was really inserted; unlike removes with `DELETE` and subtracts 1 only when a row was really removed, so repeats are safe. A user can only like what they may read (same visibility rule as the route read); a like of something that later became private stays stored but is not shown in the list. Journeys have no routes yet, so the journey like and the schedule's `journey_id` are written generically and tested with hand-made rows, as was done for the journey rules in the hierarchy phases.
Options for the count: (A) stored column as in the plan; (B) count at read time.
Recommended: **A**, like the plan and like `rating_count`.

**D10. Pace curves (F11).** Why: heavy worker and no consumer yet.
Proposal for now: CRUD and the recompute job only. Prediction use is left to the recorded-hierarchy plan.
- Manual marker: keep the plan's convention `sample_points = 0` means a manual bin. No new column. Recompute writes only bins with at least one sample, so it never makes 0 itself. Recompute skips manual bins; "reset to computed" is DELETE of the sport's curve followed by recompute.
- Bins: accept the plan's 5% steps as the standard shown to the GUI; the API accepts any integer from -100 to 100 (the grade code clips at those values) and refuses duplicates in one PUT.
- Recompute: a new job kind `pace.recompute` in `management/jobs/kinds.py`, started like `reprocess` (202, `JobAccepted`, `Location` header, progress by the existing job WebSocket, which is the plan's "WS notification"). It reads the GPX files again (ready, non-archived tracks with a sport type and time stamps) and reuses the grade code from `gpx/metrics.py`. Resting intervals are ignored. To keep it bounded it reads at most the newest N tracks per sport (N is a runtime setting, proposed 200).
Recommended: **accept as proposed.**

**D11. Public profile (F10).** Why: no visibility flag and no follow routes exist.
Options: (A) leave out of this work; build later together with the social follow routes (`plan_improvements.md` P0) and a visibility flag on the user (private, followers, public); (B) build now with a new `profile_visibility` column and no followers (public or private only).
Recommended: **A.** Otherwise a flag is invented before its rules (who counts as follower) are decided. Statistics, achievements and cards summary for other users are step G.

**D12. Archived tracks and points, cards, visits.** Why: it is a visible rule. Archiving a track removes it from distance and time, but the visits, cards and points from it stay (the plan calls this "sticky"). The statistics code already behaves this way for POIs: `unique_pois_count` counts all visit rows. There is also no track delete route, only archive.
Recommended: **keep it sticky**, and write this sentence into the API description so the GUI is not surprised.

---

## 6. What I did not check

- The 43 routes are counted from the plan, not yet shaped as code; the final count can change by a few (for example `get_one` for body metrics).
- The prices of step F (how long a recompute takes for a user with hundreds of tracks) are not measured. I suggest measuring on the sample GPX set when step F starts.
- I did not read `plan_recorded_hierarchy.md` in full; only the lines about pace curve and prediction.
- The one thing I tested: `ON DELETE SET NULL` against a CHECK (F6). I ran it on PostgreSQL 16.10 in my sandbox; your host image is `postgis/postgis:15-3.4` (`docker-compose.yml`). I did not run it on 15. I expect the same result, and the test is a few lines, so it will be repeated on the real stack when step B is built.
