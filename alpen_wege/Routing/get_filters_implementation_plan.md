# List endpoints: filters and sorting. Implementation plan v2

Plan v2, 2026-10-26. **Status 2026-10-26: delivered to the repo with all recommended answers, gzip included (Appendix B); not yet deployed on your host (6.6 is your next step).** The tools are in `filters_tools/` (Appendix D). v2 replaces the first proposal of the same day, which also changed the paging; you decided to keep the paging as it is (answers of 2026-10-26: "keep exactly as today" and "keep only the 500-bug fixes"). It touches only list endpoints (`GET` of a collection); single-object GETs (`?expand=`), POST, PATCH, DELETE, CSV upload and WebSocket do not change.

Four words used below: **scratch copy** = a copy of the repo in the sandbox where the scripts run first; **delivery** = copying the verified result from the scratch copy into the real repo in one go; **filter** = a query parameter that narrows the rows (`q`, `compendium_type_id`, `altitude_min`, ...); **list** = a `GET` that returns a page of rows.

## 0. What happens, in short

1. All **33 list endpoints** get **filters** that fit their data (text search `q` over the name, ids, ranges, dates, map box `bbox`, distance `near`) and an optional **`sort`** (`sort=name` or `sort=-name`). The filters are listed per endpoint in section 4.
2. **The paging does not change.** Every list keeps its default `limit` (1000 on 29 lists, 100 on tracks, the event log, jobs and my jobs), its maximum (none, except 500 on tracks, jobs and my jobs), and its `offset` (the users list keeps calling it `skip`). Without a filter or `sort` a list answers exactly as today, in the same order.
3. **Unknown parameters are still ignored**, as today. Only values that make the database fail are refused with `422` instead of `500`: `limit` or `offset` below 1 / 0 or above 1,000,000,000, a number or date out of range, a NUL character. A filter that is sent empty (`kind=`) counts as not given, as in the old lists.
4. Filters narrow what the caller may already see; they never widen it (the access policy is applied first, in the same place as today).
5. The code follows your standard: one new helper `app/core/utils/listing.py` (like `scope.py` and `expand.py`), every `get_many.py` stays one file with one function and explicit code (no factories), the route table is checked with `route_map.py compare --lists`, tests in `tests/`, a live check in `scripts/`.
6. **No database change, no SQL, no new index.** The Celery worker needs no rebuild.
7. **It fixes a bug on the way:** `GET /management/jobs` with no parameter answers `500` today (the open "jobs-500" item). The rewritten list answers `200`. A negative `limit` or `offset` (`500` today) answers `422`.
8. **Gzip compression** of the answers is included (question 3, recommended); to leave it out, remove the two `GZipMiddleware` lines of `app/main.py`.

## 1. What was measured, and what was not

All of this ran on a copy of your repo (state of 2026-10-26: 506 `.py` files, hash `5a0dee4fcbd0cf7e`, with the `?expand=` change) with the real application code, a real Postgres 16 + PostGIS with the compendium seed (20,758 POIs, 1,570 regions, 250 countries), Redis and a Celery worker. Your repo was not touched.

### 1.1 What a page costs (old code; `filters_tools/measure_before_2026-10-26.txt`)

| Rows | POIs: KB | gzip KB | ms | Regions: KB | ms |
|---|---|---|---|---|---|
| 100 | 119 | 8 | 37 | 136 | 40 |
| 500 | 600 | 42 | 77 | 680 | 113 |
| **1000 (the default)** | **1,197** | **83** | **150** | 1,355 | 364 |
| all 20,758 | 24,922 | 1,694 | 3,721 | | |

A POI row is about 1.2 KB. Paging deep is cheap: `offset=20000` takes about 50 to 77 ms. You keep the 1000 default; on a 1.2 MB page gzip would save 1.1 MB (question 3). There is no maximum on most lists, so `?limit=1000000` still returns every row (25 MB for POIs, 3.7 s); that is today's behaviour and stays (finding S4).

### 1.2 Old answers to odd values (`measure_out.txt`, 12 lists)

| Value | Old answer | New answer |
|---|---|---|
| `limit=-1` | `500` on 9 of 12 lists (users `422`; the two job lists `200` with 1 row) | `422` |
| `limit=0` | `200`, empty page on 9 of 12 | `422` |
| `offset=-5` | `500` on 11 of 12 (users `422`) | `422` |
| `limit=1000000` | every row on 9 of 12 lists; capped at 500 on tracks, jobs, my jobs | the same |
| misspelled filter | ignored | ignored |
| `GET /management/jobs` with no parameter | `500` | `200` |

### 1.3 Cost of the filters (`filters_tools/measure_filters_2026-10-26.txt`, the same data)

| Call | ms | Rows |
|---|---|---|
| POIs, default page (100 rows) | 28 | 20,758 |
| `q=bahnhof` (text search over the name in 3 languages, no index) | 49 | 701 |
| `q=zzzz` (no hit: every row is read) | 43 | 0 |
| `compendium_type_id=...` | 39 | 1,250 |
| `bbox=7,46,8,47` (existing GiST index) | 41 | 3,774 |
| `near=8.54,47.37&radius_m=5000` (existing index on `location::geography`) | 34 | 421 |
| `near ... radius_m=100000` | 102 | 12,143 |
| `sort=altitude_m`, `sort=-created_at` | 42, 46 | 20,758 |
| regions `bbox`, `q=bern` | 32, 16 | 264, 8 |

The total (`pagination_total`) is one `count(*)` over the same filters; it is part of these times. **No index is needed today**: the slowest filtered page is 49 ms (a 100 km radius matching 12,143 rows takes 102 ms). If a table grows past about 200,000 rows, the text search should get a trigram index; the statements are ready (6.5). `pg_trgm` is already installed in your database.

Two mistakes were found by measuring and are fixed: (1) my first `near` filter used SQLAlchemy's `cast(..., Geography)`, which writes `geography(Geometry,4326)`; PostgreSQL then did not use the existing index and read the whole table (54 ms in the database against 5 ms; 120 ms against 34 ms through the API). The final code uses the function form `geography(location)`. (2) My first sort always wrote `NULLS LAST`; on a `NOT NULL` column (the event log's `changed_at`) PostgreSQL then cannot read the index in order: on 1,000,000 event-log rows the newest 100 took 92 ms instead of 0.15 ms. The final code writes it only for columns that can be `NULL`. Both have a test.

### 1.4 What was tested

| Test | Result |
|---|---|
| The change applied by one script (`apply_filters.py`) to a fresh copy; run again on the result | Applied without a `STOP`; the second run stops with "already applied". The tools in `filters_tools/` reproduce the tested tree byte for byte (507 files, name hash `59a0472fc22afb1b`, content hash `01590a406e24dbde`) |
| `pytest` | Before: 107 passed. After: **223 passed** (107 + 116 new in `test_listing.py` and `test_list_routes.py`). The new tests also read the SQL of every filter and every sort, so a filter or a sort on the wrong column fails without a database |
| `route_map.py compare before after --lists` | `OK: 214 routes before, 214 after, identical except the list routes`, 33 list routes changed. Without `--lists` the same compare fails (71 problems). It is strict, see 6.1 |
| `route_map.py probe`, `names` | 211 routes probed, 0 problems; 0 undefined names |
| Live: `scripts/list_check.py` (new, **903 checks**) | 903 of 903: every list route (limit with and without a maximum, offset, sort in both directions, every filter once, all filters together, the errors, the old defaults); every filter of POIs, regions, countries, event log, users, access policies and jobs against a full export computed in Python (exact row sets); filters on rows it creates (gear, a card, a post, a poi-region link, two tracks) and deletes again; the scope of a caller (a policy is changed and put back); values the database cannot take must be `422`; empty text parameters; the area semantics of the region box |
| Live: your `scripts/e2e_check.py --worker` and the new `expand_check.py --worker` on the changed code | 35 of 35 and 75 of 75 |
| Three library stacks, each with the final code | the oldest your `requirements.txt` allows (FastAPI 0.111.0, Starlette 0.37.2, pydantic 2.7.0, SQLAlchemy 2.0.30, Python 3.10); FastAPI 0.161.1 (Starlette 1.7.0, pydantic 2.14.1, SQLAlchemy 2.0.55, Python 3.10); the newest (FastAPI 0.162.0, Starlette 1.10.0, pydantic 2.14.1, SQLAlchemy 2.1.6, Python 3.12). On all three: 223 passed, the compare is `OK`, `list_check.py` 903 of 903 (the newest also probe and names `OK`) |
| Postman | `build_postman.py` accepts the new API (212 routes, 245 requests) and adds the new parameters to every "List" request, switched off. A plain Newman run executes 219 requests; on the old code **36** assertions fail, on the new code **36**: the same set (the file-upload requests and what depends on them). No new failure |
| Deliberate mistakes | 39 mistakes were put into the changed code one at a time (an inclusive end date, no escaping of `%`, no tie breaker, `NULL`s first or on every column, a lost default of 1000, a lost or added maximum, a plain cast in `near`, an inverted sort, a total that ignores the filters, a dropped or wrong filter column, a wrong sort column, a dropped scope on POIs, gear, lookup tables and tracks, an inner join on tracks, the login check after the paging, one language missing in the text search, a lost default order, an offset or limit that is ignored or unbounded, a date or NUL character not refused, `skip` renamed on the users list, swapped map-box axes, the region box on the centre, and more). **All 39 are caught**: 36 by the unit tests, 3 only by the live check (the total that ignores the filters, the inner join on tracks, the ignored `offset`). In the first round three mistakes (a dropped scope on POIs, gear and lookup tables) slipped through, because the seeded policy gives every group `all`; they are now caught by a test that reads the code and by a live step that changes a policy and puts it back |
| Independent review | Appendix D (done on the first version; every finding that applies to v2 is fixed) |
| Not tested | A frontend that calls these lists (I do not have one); tables far bigger than the seed (only the POIs and regions are real volumes) |

## 2. Your decisions

Answered: the paging stays as today (default 1000, depth as before) and unknown parameters stay ignored; on 2026-10-26 you asked me to implement the proposal, which I took as **all recommended answers** (the table shows them). Tell me if one of them should be different.

| # | Question | Recommendation |
|---|---|---|
| 1 | **The filter set per endpoint** (section 4): `q` where there is a name, ids, ranges, dates, `bbox`, `near`. Anything missing or too much? | **As in section 4.** Gear has no `is_public` filter on purpose: the API cannot set or show it (finding S3) |
| 2 | **Text search `q`**: `ILIKE '%text%'` over the names (English, German, Polish) and, per list, the summary (tracks), the model (gear), the user name, e-mail and names (users); at least 2 characters; `%` and `_` are ordinary characters. Or PostgreSQL full-text search | **ILIKE.** 49 ms at worst on 20,758 rows, finds parts of words ("bahn" finds "Bahnhof"), and a trigram index can be added later without any code change (6.5) |
| 3 | **Compression** (taken as yes; `apply_filters.py` adds it only with `--gzip`): gzip in the application (`apply_filters.py --gzip`, `GZipMiddleware`, answers above 1000 bytes when the client sends `Accept-Encoding: gzip`). A default page of 1000 POIs is 1.2 MB and becomes 83 KB | **Yes, if your host's proxy does not already compress.** It changes no content, only the transfer. Starlette compresses every answer that a middleware streams, whatever its size (a 250-byte `/health` too); correct and cheap. Left out by default, as you asked for no other change |
| 4 | **Sorting**: `sort=name` / `sort=-name`, one field, a fixed list per endpoint (shown in Swagger), the old order stays the default, ties by `id`. Or leave sorting out and only add filters | **Include.** It changes nothing unless the caller sends `sort`, and "newest first" or "highest first" is what a list screen needs next to a filter |
| 5 | **Map filters**: `bbox` on POIs and regions, `near` + `radius_m` (default 5000, maximum 100,000 m) on POIs | **Include.** Both use existing indexes (1.3); on regions `bbox` means "the area of the region touches the box" (all 1,570 seeded regions have an area), on POIs "the point is inside". A box over the 180th meridian has to be asked twice |
| 6 | **Paging style**: keep `limit`/`offset` with a `total` that counts the filtered rows | **Keep** (it is what you decided) |
| 7 | **Remove the now unused `UserService.list_users`**, or keep it | **Keep** (a later cleanup) |
| 8 | Gate (still open from `?expand=`): does your host already run the Phase 3 layout? | **Answered 2026-10-26: no.** The host gets everything in one step: `host_deploy_all_changes_runbook.md` replaces 6.6 |

## 3. How it is built

**One helper, `app/core/utils/listing.py`**, like `scope.py` and `expand.py`:

| Piece | What it does |
|---|---|
| `PAGE_1000 = (1000, None)`, `PAGE_100 = (100, None)`, `PAGE_100_MAX_500 = (100, 500)` | the three page profiles that exist today; the only place where a number is written |
| `page_params(profile, offset_alias=None)` | dependency: documented `limit` and `offset` (`skip` on the users list), lowers `limit` to the maximum where the profile has one, answers `422` for a value below the minimum or above 1,000,000,000, and refuses a NUL character in any query value |
| `sort_params(options, default, tie_breaker)` and `Sort.apply(stmt)` | `?sort=-name`; a name that is not in the route's table answers `422`; `NULL`s last where the column can be `NULL`; the `id` (for access policies resource key, action and id) as tie breaker so pages never repeat or skip a row |
| `contains`, `one_of`, `at_least`, `at_most`, `since`, `before`, `equals`, `where_all` | small functions that return a condition, or `None` when the filter was not given (`0` and `false` are values; an empty text counts as not given, as in the old lists); `since` includes the date, `before` excludes it |
| `search_query`, `ids_query`, `number_query`, `moment_query` | the documented query parameters: text (at most 100 characters), ids (repeat the parameter, at most 50), whole numbers within ±1,000,000,000, dates with the year between 1900 and 2200 (outside: `422`; before they were `500`) |
| `bbox_condition`, `near_condition` | validate the numbers (plain decimals, longitude, latitude, west before east, radius 1 to 100,000) and build `ST_Intersects` / `ST_DWithin` in the form that uses the index |
| `NameFilters` | `q` (name, German, Polish) and `created_by`, shared by the lookup tables |
| `invalid(...)` | the `422` in the same shape as FastAPI's own (field `query.sort`, ...), so a client has one error format |

**One list route** keeps your layout: a `get_many.py` per resource, one function. Example (`app/compendium/routes/poi/get_many.py`, shortened):

```python
M = CompendiumCatPoi
SORT = {"name": M.name, "altitude_m": M.altitude_m, "created_at": M.created_at, "updated_at": M.updated_at}

class PoiFilters:                       # explicit parameters (they show up in Swagger), one apply()
    def __init__(self, q: str | None = search_query("name in English, German or Polish"),
                 compendium_type_id: list[UUID] | None = ids_query("POI type"), ...):
        ...
    def apply(self, stmt):
        return where_all(stmt, contains(self.q, M.name, M.name_de, M.name_pl), one_of(M.compendium_type_id, ...), ...)

@router.get("", response_model=ApiResponse[list[PoiRead]])
async def list_pois(
    access: AccessContext = Depends(resource_access("poi", "read")),     # the login check first
    page: Page = Depends(page_params()),                                  # 1000 rows by default, as before
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: PoiFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))             # scope first, the filters only narrow it
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    stmt = sort.apply(base.options(*EAGER)).limit(page.limit).offset(page.offset)
    ...
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
```

Rules that every list follows (each is a test, 6.2): the login dependency is the **first** parameter; the scope (`apply_scope`, `apply_visibility` for tracks, the own-scope condition of the lookup tables) is applied before the filters; `total` counts the filtered rows; the default order is the old one; the page profile is the old one.

Three lists are different on purpose:

- **Tracks** have metric filters (`distance_min`, `elevation_gain_min`, ...) and metric sorts that live in a joined table. The route joins it (outer join, as the old one did), so a track that is not processed yet (no metrics) stays in the unfiltered list, is left out when a metric filter is used and comes last when sorting by a metric. `recorded_from` and `recorded_to` use the value the default order uses (`coalesce(recorded_at, created_at)`).
- **Users** filter `user_group` through the credentials table (outer join) and keep `skip`.
- **Event log** keeps `entity_type` as the key (table name) it has today (a subquery on the entity-type table).

Not changed: `GET /management/settings` and `/management/event-log/entity-types` (small fixed sets without paging), Celery task endpoints, single-object GETs, the `?expand=` option (lists still return their nested objects as before).

## 4. The filters, per endpoint

Every list also has `limit`, the offset (`offset`, `skip` on users) and `sort` (allowed names and default below). The column "Filters" lists the new ones; `old` marks a parameter that existed.

| Endpoint | Page today | Sort (default first) | Filters |
|---|---|---|---|
| `GET /compendium/pois` | 1000 | `name`, `altitude_m`, `created_at`, `updated_at` | `q` (name in 3 languages), `compendium_type_id`\*, `main_region_id`, `created_by`, `altitude_min`, `altitude_max`, `created_from`, `created_to`, `bbox`, `near` + `radius_m` |
| `GET /compendium/regions` | 1000 | `name`, `created_at`, `updated_at` | `q`, `country_id`, `region_type_id`, `parent_id`, `created_by`, `bbox` (the area of the region touches the box) |
| `GET /compendium/countries` | 1000 | `name`, `iso_code`, `created_at` | `q`, `iso_code` (2 to 3 letters, any case), `created_by` |
| `GET /compendium/cards` | 1000 | `name`, `created_at`, `updated_at` | `q`, `rarity_id`, `compendium_type_id`, `poi_id`, `created_by` |
| `GET /compendium/posts` | 1000 | `name`, `created_at`, `updated_at` | `q`, `post_type_id`, `created_by` |
| `GET /compendium/poi-regions` | 1000 | `slot_position`, `created_at` | `poi_id`, `region_id`, `created_by` |
| `GET /explorer/gear` | 1000 | `created_at` (newest first), `name`, `weight_g` | `q` (name, model), `company_id`\*, `gear_type_id`\*, `created_by`, `weight_min`, `weight_max` |
| `GET /explorer/tracks` | 100, max 500 | `recorded_at` (newest first), `created_at`, `name`, `distance_m`, `elevation_gain_m` | `archived` (old), `processing_status` (old), `sport_type_id` (old, now\*), `q` (name, summary), `is_public`, `created_by`, `difficulty_level_id`\*, `difficulty_sport_id`\*, `start_poi_id`, `end_poi_id`, `recorded_from`, `recorded_to`, `distance_min`, `distance_max`, `elevation_gain_min`, `elevation_gain_max` |
| `GET /management/event-log` | 100 | `changed_at` (newest first), `seq` | `entity_type` (old), `entity_id` (old), `action` (old), `changed_by` (old), `changed_from`, `changed_to` |
| `GET /management/jobs` | 100, max 500 | `created_at` (newest first), `finished_at`, `status` | `status`, `kind`, `user_id`, `task_name`, `subject_type`, `subject_id`, `active` (all old), `created_from`, `created_to` (old) |
| `GET /management/my-jobs` | 100, max 500 | as jobs | `status`, `kind`, `subject_type`, `subject_id`, `active` (old), `created_from`, `created_to` |
| `GET /profile/users/` | 1000 (`skip`) | `created_at` (newest first), `username`, `last_active_at` | `q` (username, e-mail, names), `is_active` (old), `user_group`, `created_from`, `created_to` |
| `GET /profile/access-policies` | 1000 | `group`, `resource_key`, `action` | `group` (old), `resource_key` (old), `action`, `scope` |
| `GET /core/resource-types` | 1000 | `key`, `created_at` | `q` (key) |
| the 19 lookup tables under `/core/` | 1000 | `name`, `created_at`, `updated_at`, plus `point_factor` on the 17 that have one | `q` (name 3 languages), `created_by`; `compendium-types` also `is_collectable`; `difficulty-sports` also `sport_type_id`\* |

\* may be repeated: `compendium_type_id=a&compendium_type_id=b` means a or b, at most 50 values. Different filters are combined with AND. Ranges include both ends; `..._from` includes the date, `..._to` does not (so `created_from=2026-10-01&created_to=2026-10-02` is exactly one day). Give dates a time zone (`2026-10-01T00:00:00Z`); without one the time zone of the database session applies. `parent_id` on regions cannot select the regions that have no parent (a `root=true` filter is a three-line addition if you need it). `status` of jobs and `processing_status` of tracks are still checked against their allowed values (`422`); `group`, `user_group`, `action` and `scope` of access policies and users are checked the same way (an unknown value answers `422`, where it used to give an empty page); empty means not given.

## 5. What changes for callers

| What | Before | After |
|---|---|---|
| Paging (default, maximum, `skip` on users) | as described in section 4 | **the same** |
| Order without `sort` | the old default order, equal values in no fixed order | the same default order, ties by `id` (stable pages) |
| Unknown parameters | ignored | ignored |
| `limit=0`, a negative `limit`, a negative `offset` | an empty page / `500` | `422` |
| Out-of-range numbers, dates, `offset` or `limit` over 1,000,000,000, a NUL character | `500` | `422` |
| Empty text parameters (`kind=`, `resource_key=`) | not given (jobs: `500`) | not given |
| An unknown value of a fixed-value filter (`group=admin`) | an empty page | `422` (empty means not given) |
| `GET /management/jobs` without parameters | `500` | `200` |
| `sport_type_id` of tracks | one id | one id or several |
| Error field names | FastAPI's `query.limit` | the same form for the new errors (`query.sort`, `query.bbox`, ...) |
| Answer size | plain | plain (gzip only if you say yes to question 3) |

Nothing that works today changes its answer, except the cases that were errors (`500`) or an empty page for a value that could never match.

## 6. Implementation

### 6.1 The change as files

`apply_filters.py` writes all of this to a scratch copy and refuses to run when a file is not in the state of the repo of 2026-10-26: every reference-table list file must equal the old template text exactly; the other files must still have their old paging parameters.

| | Files | What |
|---|---|---|
| added | 4 | `app/core/utils/listing.py`, `tests/test_listing.py`, `tests/test_list_routes.py`, `scripts/list_check.py` |
| changed | 35 | 33 `get_many.py` files (6 compendium, gear, tracks, 20 under `core/routes/ref/`, event log, jobs, my jobs, users, access policies), `scripts/route_map.py` (the new `--lists` mode), `app/main.py` (the two gzip lines; without `--gzip` it stays unchanged) |
| deleted | 0 | |
| by hand | | `README.md` (a new section "Lists: filters and sorting", `filters_tools/readme_section.md`), the Postman collection (rebuilt, see F3) |

After the change (as delivered, with gzip): **507 `.py` files under `app/`**, name hash `59a0472fc22afb1b` (`find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum`, the list of file names only) and **content hash `ed98da707669c12f`** (`... | LC_ALL=C sort | xargs sha256sum | sha256sum`, names and contents). Before the change: 506 files, name hash `5a0dee4fcbd0cf7e`, content hash `03a5760631f9d4c3`. The content hash notices a hand-edited file; it also changes with line endings, so a mismatch means "tell me", not necessarily a wrong file. (Without gzip the content hash would be `01590a406e24dbde`.)

`route_map.py compare --lists` accepts a difference only on a list route (a GET that had the parameter `limit`), and then only: the parameter list (every old parameter except `limit`, `offset` and `skip` is still there with the same type, a description or pattern may be added, one value may become a list of values; `limit` and the offset (`skip` on users) are there; every new parameter is a query parameter), the dependencies (the login and permission ones must be identical, only the paging, sort and filter ones may be added) and the classes the function names (only `UserService`, `AppError` and `MgmtRefEntityType` may disappear: the filter classes use them now). The 200 answer, status, tags, summary and security must be identical; the middleware list may only gain `GZipMiddleware`. Nothing may be added or removed.

### 6.2 What the checks pin

| Check | Pins |
|---|---|
| `tests/test_listing.py` | the three page profiles (1000, 100, 100 with 500); no clamp without a maximum, a clamp with one; `422` for `limit` 0, -1, text, decimal, above 1,000,000,000 and a bad `offset`; unknown parameters ignored; the offset alias `skip`; more than 50 ids; the sort syntax, the tie breaker, `NULL`s last only on nullable columns, 7 hostile sort values; `ILIKE` with escaping (`50%_off`), at least 2 characters, empty means none; `0` and `false` as values; `since` inclusive, `before` exclusive; out-of-range numbers and dates, NUL; `bbox` and `near` (bad inputs including `nan`, `inf`, `1e9`, `1_0`, west after east, radius 0 and 100,001); the function form of the geography cast |
| `tests/test_list_routes.py` | the 33 list routes are exactly the known ones (a new list route fails until added); per route the page profile, default sort, sort names and the exact filter names; the login dependency comes **before** the paging one; the OpenAPI `limit` default and minimum, the offset name, every `sort` and `q` described; no own `limit`/`offset` and no `count_stmt` left; every list with an `AccessContext` applies the scope; **the default order of every list is the old one**; **every sort name sorts by the column it is named after**; **every filter, one at a time, puts the right column and its value into the SQL**; the map filters use the right geometry column; the text search looks at the right columns; a bad paging value without a token answers `401` on all 33 |
| `scripts/list_check.py` (903) | section 1.4 |
| `route_map.py compare --lists`, `probe`, `names` | section 6.1 |

### 6.3 Steps

| Step | Who | What |
|---|---|---|
| F0.0 | You | Answer questions 1 to 8 (**done 2026-10-26: all recommended**) |
| F0.1 | Claude | **Done.** Backup: `Routing/backup_before_filters_<date>.tar.gz` of `app`, `scripts`, `tests`, `README.md` and `Routing/postman`; tripwire `find app scripts tests README.md -newer <backup> -type f` must list nothing |
| F0.2 | Claude | **Done.** Fresh scratch copies `old/` (never changed) and `work/`; check that the repo still has 506 files and hash `5a0dee4fcbd0cf7e` (otherwise the plan is adapted); baseline `route_map.py dump route_dumps/before_filters.json` |
| F1 | Claude | **Done.** `python filters_tools/apply_filters.py work --gzip` |
| F2 | Claude | **Done.** The checks of 6.4 in `work/` on all three library stacks |
| F3 | Claude | **Done.** **Delivery** `python deliver.py work <repo> old --dry-run` (expect `4 added, 35 changed, 0 deleted`; without gzip 34 changed), then for real; copy `work/README.md`; rebuild the Postman collection from the new `/openapi.json` and copy both files to `Routing/postman/` (also drop the two switched-on `created_from`/`created_to` of "List all jobs", which only worked around the `500`); note count and hash in Appendix C |
| F4 | You | The commands of 6.6 on the host (**open**) |
| F5 | Claude | **Done.** Update `get_filters_decisions.md` and the memory notes with your answers and the host result |

### 6.4 The checks (scratch copy, about five minutes; on the host after deploying: 6.6)

```bash
python scripts/route_map.py dump route_dumps/after_filters.json
python scripts/route_map.py compare <old>/route_dumps/before_filters.json route_dumps/after_filters.json --lists
        # NOTE 33 list route(s) changed their parameters / OK: 214 routes before, 214 after, identical except the list routes
python scripts/route_map.py probe route_dumps/after_filters.json        # OK: probed 211 routes, 0 problem(s)
python scripts/route_map.py names                                      # OK: 0 undefined name(s)
python -m pytest -q                                                    # 223 passed
python scripts/list_check.py --gpx /tmp/full.gpx                       # 903 passed, 0 failed (it changes and restores three access policies, see below)
python scripts/expand_check.py --gpx /tmp/full.gpx --worker            # 75 passed, 0 failed
python scripts/e2e_check.py --gpx /tmp/full.gpx --worker               # 35 passed, 0 failed
```

`list_check.py` needs the seeded users (`scripts/init_seed.py`) and the compendium data (`push_data/seed.py`, finding S1), and creates and deletes gear, a card, a post, a poi-region link and two tracks (archived, not deleted: that is what DELETE does). **It changes data on the database it runs against:** part 3b sets the read scope of the viewer for POIs, lookup tables and regions to `own` and puts it back (also when the script stops on an error; a line `RESTORE  PATCH /api/v1/profile/access-policies/<id> {"scope": "all"}` is printed before each change, so a killed run can be undone by hand), and the event log keeps the rows that all these writes cause. For a database that other people are using, run it with `--skip-policy-step` (part 3b is skipped, the rest runs). With `--gzip` it also checks compression (only when the application has the middleware).

### 6.5 Indexes, when a table grows (not part of the change)

Not needed with 20,758 rows (1.3). If a list passes about 200,000 rows and the text search `q` gets slow, these statements add a trigram index; the application code does not change. Run them in a quiet period (`CREATE INDEX CONCURRENTLY` cannot run inside a transaction):

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;                       -- already installed here
CREATE INDEX CONCURRENTLY ix_poi_name_trgm    ON compendium_cat_poi USING gin (name gin_trgm_ops);
CREATE INDEX CONCURRENTLY ix_poi_name_de_trgm ON compendium_cat_poi USING gin (name_de gin_trgm_ops);
CREATE INDEX CONCURRENTLY ix_poi_name_pl_trgm ON compendium_cat_poi USING gin (name_pl gin_trgm_ops);
-- for a metric filter or sort on tracks:  CREATE INDEX CONCURRENTLY ix_geo_record_distance ON explorer_sub_geo_record (distance_m);
```

Check with `EXPLAIN ANALYZE` first; the indexes cost space and slow every insert a little. The table names are the ones of today's database; check them with `\d` before running.

### 6.6 Your commands on the host

Same procedure as for `?expand=` (plan `get_expand_implementation_plan_v2.md`, section 6): the api container bind-mounts the repo; files that `docker exec` creates in `route_dumps/` belong to root.

```bash
cd ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                   # expect 506 (the host runs the ?expand= state)
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum              # must start with 5a0dee4fcbd0cf7e
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | xargs sha256sum | sha256sum   # should start with 03a5760631f9d4c3
        # if the count or a hash differs: STOP and tell me
r() { sudo docker exec -w /app -e PYTHONPATH=/app alpen-api python scripts/route_map.py "$@"; }
r dump route_dumps/host_before_filters.json                                                  # 214 routes (2 WebSocket)
B=~/before_filters_$(date +%F_%H%M); echo "rollback folder: $B"
mkdir "$B" && sudo docker stop alpen-api && mv app scripts tests "$B"/ && { cp README.md "$B"/ 2>/dev/null || true; }
# copy the folders app/, scripts/, tests/ (whole folders) and README.md from the OneDrive repo into ~/jrdurt
find app -name '*.py' -not -path '*/__pycache__/*' | wc -l                                   # expect 507
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | sha256sum              # must start with 59a0472fc22afb1b
find app -name '*.py' -not -path '*/__pycache__/*' | LC_ALL=C sort | xargs sha256sum | sha256sum   # should start with ed98da707669c12f
sudo docker start alpen-api
sleep 10 && sudo docker logs --tail 30 alpen-api                                             # started, no traceback
r dump route_dumps/host_after_filters.json
r compare route_dumps/host_before_filters.json route_dumps/host_after_filters.json --lists   # NOTE 33 list route(s) ..., then OK
r probe route_dumps/host_after_filters.json                                                  # OK: probed 211 routes, 0 problem(s)
r names                                                                                      # OK: 0 undefined name(s)
sudo docker exec alpen-api sh -c "pip install -q -r requirements-dev.txt && python -m pytest -q" | tail -3     # 223 passed
sudo docker exec -w /app alpen-api sh -c "pip install -q httpx && python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx && python scripts/list_check.py --gpx /tmp/full.gpx --skip-policy-step" | tail -6
        # 0 failed (use --skip-policy-step if anybody else uses the host; without it the script also changes and restores three policies)
sudo docker exec -w /app alpen-api python scripts/e2e_check.py --gpx /tmp/full.gpx --worker | tail -2     # 35 passed
# in your database (psql, any way you use): \d compendium_cat_poi   ->  ix_poi_location_geog must exist (the `near` filter uses it; without it `near` still works, about 50 ms slower)
```

If the host runs a database with other data than the seed, `list_check.py` part 2 compares against a full export of what is there, so it still holds; the numbers in the messages differ. The Celery container is not rebuilt. If the host does not yet run the `?expand=` state (505 files), deploy that first (`get_expand_implementation_plan_v2.md`, section 6).

## 7. Rollback

There is no database change, so rollback is file-only.

| Situation | What to do |
|---|---|
| A check fails in the scratch copy | Nothing was delivered. Claude throws `work/` away, fixes and starts again from `old/` |
| Delivered to the repo, not yet deployed | Restore the repo from `Routing/backup_before_filters_<date>.tar.gz`: delete `app`, `scripts`, `tests`, `README.md` and `Routing/postman` first (needs the delete permission of the folder), then extract the archive |
| Deployed and a check fails on the host | The command below, then restore the repo as in the line above |

```bash
cd ~/jrdurt && F=~/failed_filters_$(date +%F_%H%M) && sudo docker stop alpen-api && mkdir "$F" && mv app scripts tests "$F"/ && mv "$B"/* . && sudo docker start alpen-api
```

If `$B` is gone (a new shell): `ls -d ~/before_filters_*`. A folder that the container filled with `__pycache__` needs `sudo` to be removed.

## 8. Risks and how they are covered

| Risk | Covered by |
|---|---|
| A list answers differently without a filter | `compare --lists` (the 200 answer schema must be identical), the default order and the page profile of all 33 lists are tests, the live check compares the defaults, and a full export of the POIs and regions is compared with the filtered pages |
| A filter widens what a caller may see | the scope is applied before the filters in the same statement; `test_every_list_route_with_an_access_context_narrows_by_the_scope`; the live step that sets a policy to `own` and checks that no filter (`q`, `bbox`, `near`, `created_by`, sort) brings rows back; scope checks on gear and tracks for editor and viewer |
| SQL injection through `sort`, `q`, `entity_type` | `sort` is looked up in a fixed table (7 hostile values tested); everything else is a bound parameter; `%` and `_` in `q` are escaped |
| A request makes the database work too hard | `q` is at most 100 characters, at most 50 ids per filter, `radius_m` at most 100,000, a `bbox`/`near` must be valid numbers, no regular expressions; the count and the page use the same filters. The old unlimited `limit` stays (finding S4) |
| A value the database cannot take answers `500` | numbers, dates, `limit`, `offset` and NUL are bounded (`422`); the extreme requests of `list_check.py` (16 named ones and 6 per list) and parametrized unit tests |
| The default page of a big table stops using its index | `NULLS LAST` only on nullable columns (1.3) |
| A new list route is added later without the standard | `test_the_list_routes_are_exactly_the_known_ones`, `test_list_route_files_use_the_helpers_and_not_their_own_paging` |
| Pages repeat or skip a row because many rows share a value | the `id` tie breaker; live: 15 pages of 100 sorted by `altitude_m` (many equal values) have no row twice |
| A filter or sort on the wrong column | `test_every_filter_filters_the_column_it_is_named_after`, `test_every_sort_name_sorts_by_the_column_it_is_named_after`, the live check against a full export |
| `list_check.py` changes data on a shared host | `--skip-policy-step`, the `RESTORE` lines, 6.4 |
| Library versions (`requirements.txt` is not pinned) | three stacks tested (including the oldest FastAPI 0.111.0 and pydantic 2.7.0, where the date validator is the delicate part) |
| A metric filter hides tracks that are still being processed | stated in section 3; live check; the unfiltered list keeps them |
| Costs | measured (1.3); no index needed today, statements ready (6.5) |

## 9. Findings (not part of the change)

- **S1.** `push_data/seed.py` stops on a fresh database (group `admin` against `administrator`; `get_expand_implementation_plan_v2.md`, S1). Not changed.
- **S2. `GET /management/jobs` answered `500`** without parameters (`Only '=', '!=', 'is_()' ... operators can be used with None/True/False`, and the connection was reset). The rewritten list fixes it; the old Postman workaround (the two switched-on date parameters) can go (F3).
- **S3. Gear has no way to become public.** The table has `is_public` (default `false`), but the create and update schemas do not take it and the read schema does not show it, so every gear item is private and an editor or viewer (policy `public`) sees only their own. That is why gear has no `is_public` filter. If gear should be shareable, `GearCreate`/`GearUpdate`/`GearRead` need the field: a separate, small change; tell me if you want it.
- **S4. No maximum on most lists.** `?limit=1000000` on POIs returns every row (25 MB, 3.7 s). This is how it is today and you asked to keep it; if you ever want a ceiling, it is one number per list (`PAGE_1000 = (1000, 5000)` for example) and a clamp that is already built and tested in the first version of this plan.
- **S5.** A track is visible to others only when it is `ready` (and public); an unprocessed track is visible to its owner and an administrator only. This is today's rule in `apply_visibility`, unchanged; it explains why the live check expects the viewer to see neither of the two uploaded tracks.
- **S6.** Access policies are ordered by group, resource key, action with the database's own text order (`poi_region` sorts before `poi` because the collation ignores `_`); that is the old order and stays.
- **S7.** `UserService.list_users` has no caller after the change (question 7).

## Appendix A. Examples

```bash
# everything within 5 km of Zurich (sorted by name)
curl "http://localhost:8000/api/v1/compendium/pois?near=8.54,47.37&radius_m=5000" -H "Authorization: Bearer $TOKEN"
# the POIs of two types above 1000 m, highest first, 100 rows from row 200
curl "http://localhost:8000/api/v1/compendium/pois?compendium_type_id=A&compendium_type_id=B&altitude_min=1000&sort=-altitude_m&limit=100&offset=200" -H "Authorization: Bearer $TOKEN"
# tracks from October with at least 10 km
curl "http://localhost:8000/api/v1/explorer/tracks?recorded_from=2026-10-01&recorded_to=2026-11-01&distance_min=10000" -H "Authorization: Bearer $TOKEN"
# lookup tables: find by name in any language
curl "http://localhost:8000/api/v1/core/compendium-types?q=bahn" -H "Authorization: Bearer $TOKEN"
```

## Appendix B. Execution log

| Date | Step | Result | Note |
|---|---|---|---|
| 2026-10-26 | Inventory and measurements | 33 lists, section 1.1 and 1.2 | a first measurement run crashed on a reset connection after a `500`; the script now sends `Connection: close` |
| 2026-10-26 | First version (also changed the paging) | built, tested, independently reviewed | the review findings are in Appendix D |
| 2026-10-26 | v2: your answers "keep exactly as today" and "keep only the 500-bug fixes" | applied, `223 passed`, compare `OK`, probe `OK`, names `OK`, `list_check.py` 903 of 903, `expand_check.py` 75, `e2e_check.py` 35; three stacks; Newman 36 failing before and after (the same set); 39 of 39 deliberate mistakes caught; `--gzip` variant checked (898 of 898 with `--skip-policy-step`) | |
| 2026-10-26 | F0.1 backup | `Routing/backup_before_filters_2026-10-26.tar.gz` (640 entries: app, scripts, tests, README.md, Routing/postman); repo at that time: 506 files, name hash `5a0dee4fcbd0cf7e`, content hash `03a5760631f9d4c3`, equal to the scratch base | |
| 2026-10-26 | F1/F2 apply with `--gzip` and checks | `223 passed`; compare `OK` (33 routes); probe `OK`; names `OK`; `list_check.py --gzip` **907 of 907**; `expand_check.py` 75; `e2e_check.py` 35; oldest stack (FastAPI 0.111.0): 223 passed, `list_check.py` 903 of 903 and 898 of 898 with `--gzip`; second stack 223 and 903 | |
| 2026-10-26 | F3 delivery D5 (`deliver.py`) | dry run and real run: **4 added, 35 changed, 0 deleted**; README section copied; repo: **507 files, name hash `59a0472fc22afb1b`, content hash `ed98da707669c12f`**, `app/` and `tests/` identical to the scratch copy; pytest on a copy of the delivered repo: 223 passed | |
| 2026-10-26 | Postman | `build_postman.py` rebuilt (212 routes, 245 requests); "List all jobs" no longer has the two switched-on dates; collection copied to `Routing/postman/`; Newman: 36 failing, the same set as before | |
| 2026-10-26 | Swagger and Postman follow-up | `app/main.py` got an overview text for `/docs` (`API_DESCRIPTION`) and 5 `get_many.py` files got descriptions for the filters that had none (jobs, my jobs, event log, access policies, users); delivered with `deliver.py` (0 added, 6 changed); content hash now `ed98da707669c12f`; Postman rebuilt with a "Collect first IDs" folder and first-id fallbacks (246 requests), Newman 36 failing, the same set | |
| | F4 host commands (6.6) | **open: you** | expect 506 before, 507 after, pytest 223, `list_check.py` 907 (with `--gzip`) |

## Appendix C. The tools (`filters_tools/`)

| File | What |
|---|---|
| `apply_filters.py` | applies the change to a scratch copy (guarded, `--gzip` for question 3) |
| `listing.py`, `files/` | the helper and the explicit list routes that the script copies |
| `route_map_lists.patch.py` | the `compare --lists` mode, patched into `scripts/route_map.py` |
| `test_listing.py`, `test_list_routes.py`, `list_check.py`, `readme_section.md` | copied into the repo by the script |
| `measure_lists.py`, `measure_filters.py`, `measure_before_2026-10-26.txt`, `measure_filters_2026-10-26.txt` | the measurements of section 1 |
| `mutate.py` | the 39 deliberate mistakes (usage: `python mutate.py 1 2 3`; needs the sandbox layout) |
| `stack_run.sh` | runs the checks on another library stack |

## Appendix D. Review (of the first version, 2026-10-26)

One independent reviewer read the code, compared every new list with its old version, re-ran the tests on the three library stacks and the live checks, tried mistakes of his own and a 1,000,000-row event log. He confirmed the counts, the old odd-value answers, the filter lists and sort defaults, the scope handling (no filter widens it), the totals of the live data, the use of the two map indexes, the Newman result, and that the tools reproduce the tested tree byte for byte. What he found, and what was done:

| # | Finding | Result in v2 |
|---|---|---|
| 1 | **Blocker:** the access-policy default order was `group, id`, not the old `group, resource key, action`; no check saw it | Fixed (the tie breaker takes several columns); a test pins the default order of all 33 lists |
| 2 | Eight requests still answered `500` (`altitude_min=99999999999`, `offset=9999999999999999999`, `created_to=9999-12-31`, `q` with a NUL character, ...) | Fixed: bounded numbers, years 1900 to 2200, `limit` and `offset` up to 1,000,000,000, NUL refused; unit and live checks |
| 3 | The host hash covered file names only | A content hash was added next to it (6.1, 6.6) |
| 4 | `NULLS LAST` on a `NOT NULL` column stopped the event log from using its index (92 ms against 0.15 ms at 1,000,000 rows) | Fixed (1.3), a test pins it |
| 5 | Empty text parameters behaved differently (`my-jobs?kind=` 54 rows before, 0 rows) | Empty means not given again |
| 6 | The unit tests could not see a filter or a sort on the wrong column | Tests read the SQL of every filter and every sort |
| 7 | `list_check.py` changes policies on the database it runs against | `--skip-policy-step`, the `RESTORE` lines, a warning in 6.4 and 6.6 |
| 8 | Wording and smaller points (the linear-time claim, an example, the region box tested the centre, `1_0` accepted as a number, datetimes without a zone) | Corrected; the region box tests the area; numbers are plain decimals; the time-zone advice is in section 4 |
| (first version only) | `limit` maximum, `422` for unknown parameters, `skip` renamed, the clamp, the page profiles 100/500 and 500/1000, gzip on by default | **Dropped in v2** at your request (paging as today; unknown parameters ignored); gzip is now optional |
