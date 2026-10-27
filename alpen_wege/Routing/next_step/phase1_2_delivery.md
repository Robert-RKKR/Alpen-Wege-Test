# Segments and routes (phases 1 and 2): delivered to the repo (2026-10-27)

Plan: `plan_explorer_hierarchy_v2.md`. Phase 0 (rank, schema) is in `phase0_rank_delivery.md`. Everything is in the OneDrive repo. **Not deployed on any host.** Journeys (phase 3) are not built.
Backups in `Routing/`: `backup_before_hierarchy_2026-10-27.tar.gz` (before phase 0) and `backup_after_hierarchy_phase1_2_2026-10-27.tar.gz` (now; folders `app`, `scripts`, `tests`, `push_data`).

## What you can call now (17 new routes, base `/api/v1/explorer`)

| Segments | Routes |
|---|---|
| `GET /segments` (filters, `near`, sort) | `GET /routes` |
| `POST /segments` (GPX file, multipart) | `POST /routes` (a draft, name only) |
| `POST /segments/from-coordinates` (drawn points) | `GET /routes/{id}` |
| `POST /segments/from-track` (a part of your track) | `PUT /routes/{id}/segments` (replace the list, new segments inline) |
| `GET /segments/{id}`, `GET /segments/{id}/geometry` | `GET /routes/{id}/segments`, `GET /routes/{id}/geometry` |
| `PATCH /segments/{id}`, `DELETE /segments/{id}` | `POST /routes/{id}/segments/validate`, `PATCH /routes/{id}`, `DELETE /routes/{id}` |

Your test (route with one segment from your GPX file) is in the Postman collection, folders `explorer / segments` and `explorer / routes`: run **Create segment from a GPX file** (choose your file in the body), then **1. Create route**, then **2. Put the segment into the route**, then **Get one route**. The route then has the distance and elevation of the segment and its sport (taken from the segment because the route had none). The folder **Cleanup (optional)** deletes everything the collection made.

## How the build differs from `plan_explorer_hierarchy_v2.md`

| Plan | Built |
|---|---|
| `GET /segments?mine=true` | no `mine`: use `created_by=<your id>` (a filter that needs the caller does not fit the standard list filters) |
| segment GPX limit proposal 2 MB | 5 MB (`SEGMENT_GPX_MAX_UPLOAD_MB`): 2 MB is only about 7000 points with times; a 4.65 MB file with 16000 points takes 3.3 to 4 s in the request |
| inline GPX not possible | same: upload a GPX with `POST /segments`, then use its `segment_id` |
| journeys recomputed after a route save (C4) | not applicable yet, there is no journey API; the database rule and the check "route used by a journey: 409" are built and tested with rows made by hand |
| segment POIs and photos endpoints | not built (later) |

Rules that were added during the review (all tested):

| Rule | Why |
|---|---|
| The owner of a route must be able to see every segment in it (his own or public): an administrator cannot put a private segment of his own into somebody else's route (`422 segment_not_usable`) | otherwise the owner would see a private segment of another user |
| A named `start_poi_id` / `end_poi_id` must be within 500 m of that end of the segment (`422 poi_too_far`) | two segments at "the same POI" count as connected whatever their distance |
| Drawn elevations must be between -1000 and 10000 m (`422`); broken elevations in a GPX file are dropped with the warning `elevation_outliers_dropped` | a value like 1e10 gave a 500 and ruins totals |
| Row locks: a save locks the route and the segments it uses; making a segment private, publishing a route and the save wait for each other | two users at the same moment could break the visibility rules (tested with 50 random races and 4 deterministic scenarios) |
| The size guard (`UploadSizeLimitMiddleware`) also watches `POST /segments` | a big upload is refused before it is read |
| A track that several inline clips cut from is read once per save | 50 clips of one track would parse it 50 times |

## Check results (sandbox: Postgres 16 + PostGIS, Redis, Celery worker, uvicorn)

| Check | Result |
|---|---|
| `pytest` | **362 passed** (262 after phase 0; new: continuity, route totals and classification, route geometry, segment builder, visibility, upload guard, 100 more) |
| Pipeline split: old and new `process_gpx_file` on the 6 sample GPX files | identical output (full JSON compared) |
| Live `scripts/hierarchy_check.py --worker --gpx-dir ... --dsn ...` (new) | **217 passed**: segments from GPX, drawn points and track; visibility between administrator, editor, viewer, guest; delete protection; routes with inline segments, alternatives, reversed segments, gaps (strict and warn), totals, sport and difficulty derivation, plan conditions, publishing, geometry; 50 races; locks; journey rules and database rules by SQL; no GPX file left on disk |
| Live `rank_check.py`, `expand_check.py`, `list_check.py` | 59, 73, 947 passed (the counts of routes in the last two were updated: 35 expand routes, 229 operations, 35 lists) |
| Route map | 214 routes before, 231 after: **exactly the 17 new routes**, no existing route changed, `probe` 228 routes 0 problems, `names` 0 undefined |
| Mutation tests | I broke the code on purpose and ran the checks. Pure logic and builder: 53 mistakes, all caught. Endpoints (live check): 36 mistakes, 34 caught; the other 2 are covered elsewhere (removing the distance clamp cannot change a result; the upload size guard is caught by its own unit test). Where a mistake got through at first, the tests were improved until it was caught (a second sport on a grade, the administrator adding a new inline segment, the visibility check of the validate endpoint, the track clip rules, the locks). Removing the lock of a delete is not caught on purpose: the database foreign key protects the same thing |
| Independent review (another reader, code only) | 12 findings; 9 fixed (races, 500s on odd input, unbounded input, admin leak, lock order, POI rule, log of published segments, error after rollback), 1 not reproducible (see below), 3 left as they are (below) |
| Postman | 268 requests (245 + 21 segment and route requests + 2 cleanup); Newman live: 279 requests, 288 assertions, the only failures are the 28 Upload CSV calls with no file chosen (as before), the whole segment and route flow passes |

## Left as it is (please decide)

1. **Deleting a reference row that something still uses answers 500 instead of 409** (for example a sport type that segments use). This is how all 19 reference tables already behaved for tracks and gear; segments make it easier to hit. The fix would be one handler for "delete violates a foreign key" that answers 409. It changes global error handling, so I did not do it. Say if you want it.
2. Reading a route shows its segments (name, geometry) to everybody who may read the route. The rules at write time keep that safe (a public route holds only public segments, the owner sees all segments of his route). A role with `route:read` but no `segment:read` would still see them through the route.
3. A clip from a track keeps whole points: a window shorter than the spacing of the track points gives `422 no_usable_path`.
4. Deleting a route removes likes and predictions of it and sets `schedule.route_id` to NULL (existing database design); other users' likes disappear without a warning.
5. The review also claimed that the distance function can crash for opposite points. I could not reproduce it (3 million random opposite pairs: the value exceeds 1 by one rounding step at most and the square root brings it back to 1). I added the clamp anyway; it cannot change any result.

## Your commands

No new SQL: the database script of phase 0 (`scripts/sql/hierarchy_phase0_ddl.sql`) is all that is needed. Copy the folders `app`, `scripts`, `tests` and `push_data` from the OneDrive repo, restart, then:

```bash
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -3                        # 362 passed
sudo docker exec -w /app alpen-api sh -c "pip install -q httpx && python scripts/hierarchy_check.py" | tail -3                    # 186 passed (no worker, no --dsn)
```

With the worker and the database: `python scripts/hierarchy_check.py --worker --gpx-dir /data/gpx --dsn "dbname=alpenwege user=alpenwege password=... host=postgres port=5432"` (217 checks). `hierarchy_check.py` creates and deletes its own rows (the event log keeps the entries); `list_check.py` must run without a worker (as before).
The file count of `app` is now **543** and the file-list hash starts with **7ac91878ccb7e673** (it was 507 and 59a0472fc22afb1b); the combined host runbook (`host_deploy_all_changes_runbook.md`) gets one rewrite when you decide to deploy.
