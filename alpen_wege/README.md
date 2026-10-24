# Alpen Wege API

Mountain and hiking activity tracker — FastAPI backend with PostGIS, Redis and Celery.

## Tech stack

| Component       | Technology                              |
|-----------------|-----------------------------------------|
| API framework   | FastAPI 0.111+ / Python 3.12            |
| ORM             | SQLAlchemy 2.0 (async, mapped columns)  |
| Database        | PostgreSQL 15 + PostGIS 3.4             |
| Geo             | GeoAlchemy2 (WKT / WKB / GeoJSON)      |
| Cache / tokens  | Redis 7                                 |
| Task queue      | Celery 5.4 (Redis broker)               |
| Auth            | JWT (python-jose), bcrypt               |

---

## Quick start

```bash
# 1. Copy environment file
cp .env.example .env          # edit JWT_SECRET_KEY for production

# 2. Start everything
sudo docker compose up -d --build

# 3. Verify
curl http://localhost:8000/health
```

| Service       | Host port |
|---------------|-----------|
| API           | 8000      |
| PostgreSQL    | 5433      |
| Redis         | 6381      |

Swagger UI is available at **http://localhost:8000/docs**.

### Environment variables

| Variable               | Default                        | Notes                          |
|------------------------|--------------------------------|--------------------------------|
| `DATABASE_URL`         | see `.env.example`             | async (asyncpg) connection     |
| `DATABASE_URL_SYNC`    | see `.env.example`             | sync (psycopg2), used by Celery|
| `REDIS_URL`            | `redis://localhost:6379/2`     | token blacklist + cache        |
| `CELERY_BROKER_URL`    | `redis://localhost:6379/0`     |                                |
| `CELERY_RESULT_BACKEND`| `redis://localhost:6379/1`     |                                |
| `JWT_SECRET_KEY`       | `change-me-in-production`      | **must** be changed for prod   |
| `JWT_EXPIRE_MINUTES`   | `5`                            | access token lifetime          |

---

## Authentication

All endpoints (except `/health`) require a valid JWT Bearer token.

### Register

```bash
curl -X POST http://localhost:8000/api/v1/profile/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "username": "hiker01",
    "password": "securepass123",
    "first_name": "Alex",
    "last_name": "Walker"
  }'
```

Response (`201`):

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 300
}
```

### Login

```bash
curl -X POST http://localhost:8000/api/v1/profile/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepass123"}'
```

### Using the token

Pass the token as a Bearer header on every request:

```bash
TOKEN="eyJ..."

curl http://localhost:8000/api/v1/profile/users/me \
  -H "Authorization: Bearer $TOKEN"
```

> **Token rotation:** The middleware automatically issues a fresh token
> (returned in the `X-Access-Token` response header) when less than half
> the token's lifetime remains. Use the newest token you receive.

### Refresh / Logout

| Method | Endpoint                    | Notes                                |
|--------|-----------------------------|--------------------------------------|
| POST   | `/api/v1/profile/auth/refresh`      | Returns a new token                  |
| POST   | `/api/v1/profile/auth/logout`       | Blacklists the current token (204)   |

---

## API endpoints

Base path: `/api/v1`. Every endpoint is `/api/v1/{app}/{resource}`; the apps are `core`, `compendium`, `explorer`, `profile` and `management`. The paths in the tables below include the app.

### User profile

| Method | Path          | Description              |
|--------|---------------|--------------------------|
| GET    | `/profile/users/me` | Get current user profile |
| PUT    | `/profile/users/me` | Update own profile       |

Update accepts: `first_name`, `last_name`, `middle_name`, `gender` (`male`/`female`/`not_specified`), `birth_date`, `height_cm`, `max_heart_rate`, `resting_heart_rate`.

### Gear (explorer)

User-scoped — each user sees only their own gear.

| Method | Path                    | Description          |
|--------|-------------------------|----------------------|
| GET    | `/explorer/gear`                 | List my gear         |
| POST   | `/explorer/gear`                 | Create gear          |
| GET    | `/explorer/gear/{id}`            | Get one              |
| PATCH  | `/explorer/gear/{id}`            | Update               |
| DELETE | `/explorer/gear/{id}`            | Delete (204)         |
| POST   | `/explorer/gear/upload-csv`      | Bulk import from CSV |

### Reference data (core_ref)

19 lookup tables, all under `/core/`. Shared data (no ownership filter).

| Slug                    | Path                                 |
|-------------------------|--------------------------------------|
| `companies`             | `/core/companies`                     |
| `gear-types`            | `/core/gear-types`                    |
| `sport-types`           | `/core/sport-types`                   |
| `difficulty-sports`     | `/core/difficulty-sports`             |
| `difficulty-levels`     | `/core/difficulty-levels`             |
| `compendium-types`      | `/core/compendium-types`              |
| `region-types`          | `/core/region-types`                  |
| `achievement-categories`| `/core/achievement-categories`        |
| `achievement-scopes`    | `/core/achievement-scopes`            |
| `achievement-types`     | `/core/achievement-types`             |
| `point-reasons`         | `/core/point-reasons`                 |
| `post-types`            | `/core/post-types`                    |
| `rarities`              | `/core/rarities`                      |
| `schedule-statuses`     | `/core/schedule-statuses`             |
| `snow-conditions`       | `/core/snow-conditions`               |
| `trail-conditions`      | `/core/trail-conditions`              |
| `visibilities`          | `/core/visibilities`                  |
| `waypoint-types`        | `/core/waypoint-types`                |
| `weather-conditions`    | `/core/weather-conditions`            |

Each table supports the same 6 operations:

| Method | Path                          | Description          |
|--------|-------------------------------|----------------------|
| GET    | `/core/{slug}`                 | List all             |
| POST   | `/core/{slug}`                 | Create (201)         |
| GET    | `/core/{slug}/{id}`            | Get one              |
| PATCH  | `/core/{slug}/{id}`            | Update               |
| DELETE | `/core/{slug}/{id}`            | Delete (204)         |
| POST   | `/core/{slug}/upload-csv`      | Bulk import from CSV |

**Create example** (sport type):

```bash
curl -X POST http://localhost:8000/api/v1/core/sport-types \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Hiking",
    "name_de": "Wandern",
    "name_pl": "Piesze wędrówki",
    "color": "#4CAF50",
    "icon": "hiking",
    "point_factor": 1.0
  }'
```

### Compendium (catalog)

Shared geographic / editorial catalog. GET endpoints return nested objects one level deep (FK IDs are accepted on create/update; full sub-objects come back on read).

| Method | Path                          | Description          |
|--------|-------------------------------|----------------------|
| GET    | `/compendium/countries`                  | List countries       |
| POST   | `/compendium/countries`                  | Create (201)         |
| GET    | `/compendium/countries/{id}`             | Get one              |
| PATCH  | `/compendium/countries/{id}`             | Update               |
| DELETE | `/compendium/countries/{id}`             | Delete (204)         |
| POST   | `/compendium/countries/upload-csv`       | Bulk import from CSV |

Same pattern for: `/compendium/regions`, `/compendium/pois`, `/compendium/cards`, `/compendium/posts`, `/compendium/poi-regions`. `POST /compendium/pois/{id}/rescan` and `POST /compendium/cards/{id}/rescan` start a rescan job (see the jobs section below).

**Create country example** (with GeoJSON location):

```bash
curl -X POST http://localhost:8000/api/v1/compendium/countries \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Austria",
    "iso_code": "AT",
    "location": {"type": "Point", "coordinates": [13.3333, 47.3333]},
    "capital": "Vienna",
    "capital_de": "Wien",
    "languages": ["de"],
    "currencies": ["EUR"]
  }'
```

**Create region** (references country and region-type by ID):

```bash
curl -X POST http://localhost:8000/api/v1/compendium/regions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Zillertal Alps",
    "location": {"type": "Point", "coordinates": [11.87, 47.05]},
    "country_id": "<country-uuid>",
    "region_type_id": "<region-type-uuid>"
  }'
```

The GET response returns the full nested objects:

```json
{
  "id": "...",
  "name": "Zillertal Alps",
  "location": {"type": "Point", "coordinates": [11.87, 47.05]},
  "country_id": "...",
  "country": {
    "id": "...",
    "name": "Austria",
    "iso_code": "AT",
    "location": {"type": "Point", "coordinates": [13.3333, 47.3333]}
  },
  "region_type_id": "...",
  "region_type": {
    "id": "...",
    "name": "Mountain range",
    "color": "#795548",
    "icon": "mountains",
    "point_factor": 1.0,
    "..."
  },
  "parent_id": null,
  "parent": null,
  "..."
}
```

---

## CSV bulk import

Every entity has a `POST .../upload-csv` endpoint. Upload a standard CSV file (UTF-8, comma-separated, first row = header) to insert multiple rows at once.

### How to use

```bash
curl -X POST http://localhost:8000/api/v1/core/sport-types/upload-csv \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@sport_types.csv"
```

Response:

```json
{
  "inserted": 5,
  "errors": []
}
```

If some rows fail, they are skipped and reported:

```json
{
  "inserted": 3,
  "errors": [
    "row 4: invalid literal for int() with base 10: 'abc'",
    "row 6: badly formed hexadecimal UUID string"
  ]
}
```

### CSV format rules

| Topic           | Rule                                                                                     |
|-----------------|------------------------------------------------------------------------------------------|
| Encoding        | UTF-8 (BOM is handled automatically)                                                    |
| Delimiter       | Comma (standard CSV)                                                                     |
| Header row      | **Required** — column names must match the database column names exactly                 |
| `id`            | Optional — if omitted the database generates a UUID automatically                        |
| `created_by`    | Optional — defaults to the authenticated user                                            |
| `created_at`    | Optional — defaults to current timestamp                                                 |
| UUID columns    | Full UUID string, e.g. `550e8400-e29b-41d4-a716-446655440000`                            |
| Boolean         | `true`/`1`/`yes`/`t` → true; anything else → false                                      |
| Array columns   | Pipe-separated `de\|en\|fr` **or** JSON `["de","en","fr"]`                               |
| Geometry (WKT)  | `POINT(13.37 47.27)` or `POLYGON((10 47, 11 47, 11 48, 10 48, 10 47))`                  |
| Geometry (pair)  | Use `location_lon` + `location_lat` columns instead of WKT for Point geometries         |
| Empty cell      | Treated as `NULL`                                                                        |

### Example CSV files

**Reference table** (`sport_types.csv`):

```csv
name,name_de,name_pl,color,icon,point_factor
Hiking,Wandern,Piesze wędrówki,#4CAF50,hiking,1.0
Skiing,Skifahren,Narciarstwo,#2196F3,skiing,1.5
Climbing,Klettern,Wspinaczka,#FF5722,climbing,2.0
```

**Countries** (`countries.csv`) — with lon/lat pair columns:

```csv
name,iso_code,location_lon,location_lat,capital,capital_de,languages,currencies
Austria,AT,13.3333,47.3333,Vienna,Wien,de,EUR
Switzerland,CH,8.2275,46.8182,Bern,Bern,de|fr|it|rm,CHF
Germany,DE,10.4515,51.1657,Berlin,Berlin,de,EUR
```

**Countries** (`countries_wkt.csv`) — same data with WKT geometry:

```csv
name,iso_code,location,capital,languages
Austria,AT,POINT(13.3333 47.3333),Vienna,de
Switzerland,CH,POINT(8.2275 46.8182),Bern,de|fr|it|rm
```

**POIs** (`pois.csv`):

```csv
name,location_lon,location_lat,altitude_m,compendium_type_id,main_region_id
Zugspitze,10.9863,47.4211,2962,<compendium-type-uuid>,<region-uuid>
Grossglockner,12.6944,47.0742,3798,<compendium-type-uuid>,<region-uuid>
```

**POI-Region links** (`poi_regions.csv`):

```csv
poi_id,region_id,slot_position
<poi-uuid>,<region-uuid>,1
<poi-uuid>,<another-region-uuid>,2
```

### Swagger documentation

Open **http://localhost:8000/docs** — every `upload-csv` endpoint shows a full column reference table (generated from the model) with types, required/optional status, and format notes. Use the **Try it out** button to upload a file directly from the browser.

---

## URL scheme and routes layout

Every endpoint is `/api/v1/{app}/{resource}`: `app` is the app folder that holds the route file (`core`, `compendium`, `explorer`, `profile`, `management`), `resource` is plural and kebab-case (for example `poi-regions`). Examples: `/api/v1/compendium/pois`, `/api/v1/profile/auth/login`, `/api/v1/management/settings`. Only `/health` and the documentation URLs (`/docs`, `/openapi.json`) are outside. The app prefix is written once, in each app's `routes/__init__.py`.

Inside an app's `routes/` folder **every resource is a folder** with one file per action. There are no loose resource files:

```
routes/
  country/                 # a resource = a folder (compendium)
    __init__.py            # imports the endpoint files (fixed paths such as /upload-csv first), exports `router`
    _router.py             # the one APIRouter of the resource: prefix and Swagger tag
    _shared.py             # helpers used by several endpoint files (only when needed)
    get_many.py  get_one.py  create.py  update.py  delete.py  upload_csv.py
  poi/                     # special actions get their own file: rescan.py
  m2m/                     # type folder for link tables: poi_region/ ...
  ref/                     # type folder for reference tables (core): company/ ... resource_type/
```

- **One concept in every app.** Regular models and features sit directly in `routes/` (`country/`, `track/`, `auth/`, `celery/`, `ws/`, ...). Only the special kinds of tables get a type folder, with the same names as in `models/`: `m2m/`, `ref/` and later `sub/`. Nothing else groups resources, and a resource folder never contains folders.
- **File names are actions:** `get_many`, `get_one`, `create`, `update`, `delete`, `upload_csv`, and special ones (`rescan`, `geometry`, `restore`, `stats`, `compare`, ...). Several actions that belong together in one workflow still get one file each.
- **`_router.py`** holds the one `APIRouter` object of the resource (for example the prefix `cards` and the tag `Compendium - Card`). Every endpoint file imports it and registers its function on it; `__init__.py` imports all endpoint files. Endpoint files never create their own router, because FastAPI refuses sub-routers with an empty path (the list and create endpoints).
- **`post/` is the Post model** (editorial posts, `/compendium/posts`), not the HTTP method. The reference tables are written out like every other model, not generated.
- Helpers used by several resources live in `app/core/utils/` (`scope.py`, `api_paths.py`); route files never import from other resources; URLs are never written as strings in route files (`api_paths.py` builds the `Location` header and names the upload path).
- Check after any change to routes: `python scripts/route_map.py dump route_dumps/x.json`, then `compare` against an earlier dump, `probe` and `names` (see `scripts/route_map.py`); `tests/test_routes_standard.py` and `tests/test_api_paths.py` enforce the rules above.

---

## Project structure

```
app/
├── profile/               # Users, authentication, access policies
│   ├── dependencies/      # get_current_user, get_current_active_user
│   ├── middleware/        # TokenRefreshMiddleware (auto-rotation)
│   ├── models/            # ProfileUsrUser, credentials, access policies, ...
│   ├── permissions/       # require_groups, resource_access
│   ├── routes/            # auth/ (register, login, refresh, logout), user/ (me, admin), access_policy/
│   ├── schemas/           # RegisterRequest, LoginRequest, TokenResponse, UserRead, UserUpdate
│   └── services/          # jwt (create/verify/blacklist), passwords (bcrypt)
├── core/                  # Shared base + reference data
│   ├── base.py            # DeclarativeBase, all mixins
│   ├── dependencies.py    # get_db session provider
│   ├── models/            # 19 CoreRef* models
│   ├── routes/            # ref/ (one folder per reference table, plus resource_type/)
│   ├── schemas/           # ref.py (6 schema classes), geo.py (GeoJSON utils)
│   └── utils/             # csv_import.py (shared CSV bulk import)
├── management/            # Event log, jobs, runtime settings, WebSocket, Celery API
│   ├── models/            # MgmtLogEvent, MgmtRefEntityType, MgmtLogJob, MgmtSettings
│   ├── jobs/              # job service, TrackedTask (Celery base class), Redis events
│   ├── runtime_settings/  # settings registry, cached reader, seed
│   ├── routes/            # /management/* (event-log, settings, jobs, my-jobs, ws, celery, broadcast)
│   ├── schemas/
│   └── utils/             # event_logger.py, seed_entity_types.py
├── compendium/            # Geographic / editorial catalog
│   ├── models/
│   │   ├── models_cat/    # Country, Region, POI, Card, Post
│   │   └── models_m2m/    # PoiRegion
│   ├── routes/            # one folder per entity (country/, poi/, ...), m2m/poi_region/
│   └── schemas/           # Create/Update/Read/SlimRead per entity
├── explorer/              # User activity data
│   ├── models/            # ExplorerAggGear, ...
│   ├── routes/            # gear/ (CRUD + CSV upload), track/ (GPX upload, geometry, performance, archive)
│   └── schemas/           # GearCreate/Update/Read
├── config.py              # Pydantic settings
├── database.py            # Async engine + session factory
├── redis.py               # Redis pool (init/close/get)
├── worker/                # Celery app and tasks (tracks, stats, cleanup, management)
└── main.py                # App factory, router wiring, health check
```

---

## Jobs, WebSocket and management

Work that runs in the background (GPX processing, POI and card rescans) is tracked as a **job**.
`POST /explorer/tracks`, `POST /explorer/tracks/{id}/reprocess`, `POST /compendium/pois/{id}/rescan` and `POST /compendium/cards/{id}/rescan`
answer `202` with a `job_id` (and a `Location: /api/v1/management/my-jobs/{job_id}` header). The job id is also the Celery task id.

| Endpoint | Who | Purpose |
|---|---|---|
| `GET /api/v1/management/my-jobs`, `GET /api/v1/management/my-jobs/{id}` | any active user | own jobs (filters: `status`, `kind`, `subject_type`, `subject_id`, `active`) |
| `POST /api/v1/management/ws/ticket` | any active user | one-time ticket (30 s) for a WebSocket |
| `WS /api/v1/management/ws?ticket=...` | ticket holder | all my job events, broadcast notices |
| `WS /api/v1/management/ws/jobs/{job_id}?ticket=...` | ticket holder | one job, closes when it ends |
| `GET /api/v1/management/jobs`, `/api/v1/management/jobs/stats`, `/api/v1/management/jobs/{id}` | administrator | all jobs |
| `GET /api/v1/management/event-log` (and `/entity-types`, `/{id}`, `/{id_1}/compare/{id_2}`) | administrator | object change history (moved from `/event-log`) |
| `GET/PATCH /api/v1/management/settings[/{key}]`, `POST .../{key}/reset` | administrator | runtime settings (retention, WebSocket limits, ...) |
| `POST /api/v1/management/broadcast` | administrator | notice to every connected WebSocket |
| `GET /api/v1/management/celery/status`, `/workers`, `/tasks/registered`, `/tasks/active`, `/tasks/{id}`, `/beat` | administrator | Celery health and tasks (read-only) |

**Following a job over WebSocket.** Get a ticket with `POST /api/v1/management/ws/ticket` (normal bearer token),
then open `wss://<host>/api/v1/management/ws?ticket=<ticket>` within 30 seconds. The first message is `sync`
(your queued and running jobs plus those finished in the last minutes); after that wait for updates.
On every (re)connect: wait for `sync`, replace local state with it, then apply updates. Terminal states
(`succeeded`, `failed`, `cancelled`) are final. Message types: `sync`, `job.update`, `job.progress`,
`system.notice`, `control`. Close codes: `4401` bad ticket or logout, `4403` account deactivated,
`4404` dedicated socket: not your job, `4408` maximum lifetime reached (reconnect with a new ticket),
`4429` too many sockets. The WebSocket is only a hint: `GET /api/v1/management/my-jobs/{id}` always gives the truth.

Database changes for the management app: `scripts/sql/management_x1_move.sql`, `management_x2_settings.sql`,
`management_x3_jobs.sql` (run in this order with the api and worker stopped, before the code is deployed).
Try it without a GPX file: `python scripts/demo_job.py --user-id <uuid> --seconds 8` and
`python scripts/ws_check.py --token "$TOKEN"` (both inside the api container, `PYTHONPATH=/app`).

---

## Health check

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ok",
  "database_tables": 42,
  "redis_connected": true
}
```
