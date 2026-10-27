# Phase 0 of the explorer hierarchy: delivered to the repo (2026-10-27)

Plan: `plan_explorer_hierarchy_v2.md` (section 2 and 3). Decisions: `plan_explorer_hierarchy_decisions.md` (D1 to D4, C1, C2, C5).
Everything is in the OneDrive repo. **Not deployed on any host.** Backups in `Routing/`: `backup_before_hierarchy_2026-10-27.tar.gz` and `backup_after_hierarchy_phase0_2026-10-27.tar.gz` (folders `app`, `scripts`, `tests`, `push_data`).

## What changed

| Part | Change |
|---|---|
| `rank` | New column `rank` (smallint, required, higher = harder, rarer or worse) on `difficulty_level`, `difficulty_sport`, `rarity`, `visibility` (mixin `ReferenceWithRankMixin` in `core/base.py`). |
| API of the four tables | Create needs `rank` (0 to 1000, otherwise 422). Update accepts it. Lists take `rank_min`, `rank_max` and `sort=rank`. Single GET and nested objects (`card.rarity`, `track.difficulty_level`, `track.difficulty_sport`) show it. New shared classes `RefRankedCreate/Update/Read/Detail` and `RankFilters`. |
| Seed data | `push_data/core_ref_{difficulty_level,difficulty_sport,rarity,visibility}.csv` have a `rank` column. |
| Route | `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id` are nullable (a draft route has no classification). |
| `segment_route` | `segment_id` is `ON DELETE RESTRICT`; unique `(route_id, slot_position, segment_id)`; unique partial index on `(route_id, alt_group) WHERE is_default`; index on `segment_id`. |
| `route_journey` | `route_id` is `ON DELETE RESTRICT`; unique `(journey_id, slot_position)`; index on `route_id`. |
| Test database | `scripts/sql/hierarchy_phase0_ddl.sql` (idempotent, one transaction). A fresh `create_all` database needs nothing. |

Side fixes found by the checks (small, in the same delivery):

| Fix | Why |
|---|---|
| `PATCH` with `null` on `color`, `icon`, `point_factor`, `rank` of any reference table answers 422 | before, it went to the database and answered 500 |
| CSV import (all 29 upload routes): a header without a required column inserts nothing and says which column is missing; a row with an empty required cell is reported (`row 3: missing value for rank`) and the other rows are still imported | before, one missing required value made the whole upload a 500. It matters now because old CSV exports of the four tables have no `rank` column |
| `push_data/seed.py` creates the seed user with group `administrator` (was `admin`) | a fresh database could not be seeded (side finding S1 of the `?expand=` plan) |

## Check results (sandbox: Postgres 16 + PostGIS, Redis, Celery, uvicorn)

| Check | Result |
|---|---|
| `pytest` | **262 passed** (223 before; new: `test_hierarchy_schema.py` 33, `test_csv_import.py` 6) |
| Mutation test of `test_hierarchy_schema.py` | 9 deliberate mistakes (FK back to CASCADE, route sport required again, rank removed from a table, rank optional on create, rank limit removed, one-default index not unique, slot rule removed, rank missing in a CSV) all caught |
| SQL script on a database built from the OLD code and seeded with the OLD csv files | runs twice without error; the ranks it computes are identical to the ranks in the new CSV files for all 88 rows (7 + 67 + 6 + 8); a hand-added row without a known icon gets a fallback rank; the resulting schema is identical to a fresh `create_all` of the new code (`pg_dump -s` diff: only the column order of `rank` differs) |
| Route map (`route_map.py`) | 214 routes before and after; 30 route records differ and all of them belong to the four tables (parameters, request bodies, responses, CSV descriptions); `probe`: 211 routes, 0 problems; `names`: 0 undefined names |
| Live: `scripts/rank_check.py` (new) | 59 of 59 |
| Live: `list_check.py` | 900 passed, 0 failed (the 7 compression checks are skipped as before) |
| Live: `expand_check.py` | 73 passed, 0 failed |
| Postman collection rebuilt (`Routing/postman`) | 245 requests as before; exactly 12 differ: 4 lists (new `rank_min`, `rank_max`), 4 Create and 4 Update bodies with `rank`. Newman live: 258 requests, 259 assertions, 36 failing requests, **the same 36** as in the last delivered run (the Upload CSV and track-file calls that need a file chosen in Postman) |

Not run in this phase: `e2e_check.py` (no changes to tracks, uploads or jobs) and the three library-stack variants (no new library call).

## What you should review

1. The climbing scale (`sport_type_id` 434c1738): UIAA and French grades share one rank scale, built from the order of `point_factor`. The result in `push_data/core_ref_difficulty_sport.csv`:

   | rank | grade(s) |
   |---|---|
   | 1 | UIAA I |
   | 2 | French 4 |
   | 3 | UIAA II |
   | 4 | French 5, UIAA III |
   | 5 | UIAA IV |
   | 6 | French 6a |
   | 7 | UIAA V |
   | 8 | French 6c, UIAA VI |
   | 9 | UIAA VII |
   | 10 | French 7a |
   | 11 | UIAA VIII |
   | 12 | French 7c |
   | 13 | UIAA IX |
   | 14 | UIAA X |
   | 15 | French 8a+ |

   Change a number in the CSV (or with `PATCH /core/difficulty-sports/{id}`) if a pair is wrong. The other eight sport types are single systems and need no review.
2. The fallback of the SQL script for rows you added by hand: they get the order of `point_factor` inside their table, which can tie with a seeded row. Set their rank by hand.

## Your commands (test database or host)

Order matters: database first, then code (the application reads the new column at once).

```bash
cd ~/jrdurt
P="sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege"
$P < scripts/sql/hierarchy_phase0_ddl.sql          # ends with COMMIT; a second run only prints NOTICE lines
# copy the folders app, scripts, tests and push_data from the OneDrive repo (whole folders)
sudo docker compose up -d --build
sleep 15; sudo docker logs --tail 40 alpen-api       # started, no traceback
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -3    # 262 passed
sudo docker exec -w /app alpen-api sh -c "pip install -q httpx && python scripts/rank_check.py" | tail -3       # 59 passed, 0 failed
```

`rank_check.py` creates and deletes a few rows in `/core/rarities` (the event log keeps the entries). If the host later gets the combined deployment of `host_deploy_all_changes_runbook.md`, add `hierarchy_phase0_ddl` as the last script of the SQL loop in its section 4; the file count (507) and the file-list hash (`59a0472fc22afb1b`) of that runbook did not change because no app file was added, but the content hash and the test count (now 262) did. That runbook gets one rewrite when all phases are done.

## Next: Phase 1 (segments)

Pipeline split (`process_cleaned`), segment builder and persist, the three create endpoints, get, update, delete with protection, visibility rules, timing of the largest GPX and of a track clip (C9). See `plan_explorer_hierarchy_v2.md` sections 4.1, 4.2, 5 and 6.
