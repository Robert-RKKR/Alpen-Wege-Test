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
curl -X POST http://localhost:8000/api/v1/auth/register \
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
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "securepass123"}'
```

### Using the token

Pass the token as a Bearer header on every request:

```bash
TOKEN="eyJ..."

curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer $TOKEN"
```

> **Token rotation:** The middleware automatically issues a fresh token
> (returned in the `Authorization` response header) when less than half
> the token's lifetime remains. Use the newest token you receive.

### Refresh / Logout

| Method | Endpoint                    | Notes                                |
|--------|-----------------------------|--------------------------------------|
| POST   | `/api/v1/auth/refresh`      | Returns a new token                  |
| POST   | `/api/v1/auth/logout`       | Blacklists the current token (204)   |

---

## API endpoints

Base path: `/api/v1`

### User profile

| Method | Path          | Description              |
|--------|---------------|--------------------------|
| GET    | `/users/me`   | Get current user profile |
| PUT    | `/users/me`   | Update own profile       |

Update accepts: `first_name`, `last_name`, `middle_name`, `gender` (`male`/`female`/`not_specified`), `birth_date`, `height_cm`, `max_heart_rate`, `resting_heart_rate`.

### Gear (explorer)

User-scoped — each user sees only their own gear.

| Method | Path                    | Description          |
|--------|-------------------------|----------------------|
| GET    | `/gear`                 | List my gear         |
| POST   | `/gear`                 | Create gear          |
| GET    | `/gear/{id}`            | Get one              |
| PATCH  | `/gear/{id}`            | Update               |
| DELETE | `/gear/{id}`            | Delete (204)         |
| POST   | `/gear/upload-csv`      | Bulk import from CSV |

### Reference data (core_ref)

19 lookup tables, all under `/ref/`. Shared data (no ownership filter).

| Slug                    | Path                                 |
|-------------------------|--------------------------------------|
| `companies`             | `/ref/companies`                     |
| `gear-types`            | `/ref/gear-types`                    |
| `sport-types`           | `/ref/sport-types`                   |
| `difficulty-sports`     | `/ref/difficulty-sports`             |
| `difficulty-levels`     | `/ref/difficulty-levels`             |
| `compendium-types`      | `/ref/compendium-types`              |
| `region-types`          | `/ref/region-types`                  |
| `achievement-categories`| `/ref/achievement-categories`        |
| `achievement-scopes`    | `/ref/achievement-scopes`            |
| `achievement-types`     | `/ref/achievement-types`             |
| `point-reasons`         | `/ref/point-reasons`                 |
| `post-types`            | `/ref/post-types`                    |
| `rarities`              | `/ref/rarities`                      |
| `schedule-statuses`     | `/ref/schedule-statuses`             |
| `snow-conditions`       | `/ref/snow-conditions`               |
| `trail-conditions`      | `/ref/trail-conditions`              |
| `visibilities`          | `/ref/visibilities`                  |
| `waypoint-types`        | `/ref/waypoint-types`                |
| `weather-conditions`    | `/ref/weather-conditions`            |

Each table supports the same 6 operations:

| Method | Path                          | Description          |
|--------|-------------------------------|----------------------|
| GET    | `/ref/{slug}`                 | List all             |
| POST   | `/ref/{slug}`                 | Create (201)         |
| GET    | `/ref/{slug}/{id}`            | Get one              |
| PATCH  | `/ref/{slug}/{id}`            | Update               |
| DELETE | `/ref/{slug}/{id}`            | Delete (204)         |
| POST   | `/ref/{slug}/upload-csv`      | Bulk import from CSV |

**Create example** (sport type):

```bash
curl -X POST http://localhost:8000/api/v1/ref/sport-types \
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
| GET    | `/countries`                  | List countries       |
| POST   | `/countries`                  | Create (201)         |
| GET    | `/countries/{id}`             | Get one              |
| PATCH  | `/countries/{id}`             | Update               |
| DELETE | `/countries/{id}`             | Delete (204)         |
| POST   | `/countries/upload-csv`       | Bulk import from CSV |

Same pattern for: `/regions`, `/pois`, `/cards`, `/posts`, `/poi-regions`.

**Create country example** (with GeoJSON location):

```bash
curl -X POST http://localhost:8000/api/v1/countries \
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
curl -X POST http://localhost:8000/api/v1/regions \
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
curl -X POST http://localhost:8000/api/v1/ref/sport-types/upload-csv \
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

## Project structure

```
app/
├── auth/                  # Authentication (JWT, register, login, logout)
│   ├── dependencies/      # get_current_user, get_current_active_user
│   ├── middleware/         # TokenRefreshMiddleware (auto-rotation)
│   ├── routes/            # register, login, refresh, logout
│   ├── schemas/           # RegisterRequest, LoginRequest, TokenResponse
│   └── services/          # jwt (create/verify/blacklist), passwords (bcrypt)
├── users/                 # User profile management
│   ├── models/            # ProfileUsrUser
│   ├── routes/            # /me, /admin
│   └── schemas/           # UserRead, UserUpdate
├── core/                  # Shared base + reference data
│   ├── base.py            # DeclarativeBase, all mixins
│   ├── dependencies.py    # get_db session provider
│   ├── models/            # 19 CoreRef* models
│   ├── routes/            # Factory-generated CRUD for all ref tables
│   ├── schemas/           # ref.py (6 schema classes), geo.py (GeoJSON utils)
│   └── utils/             # csv_import.py (shared CSV bulk import)
├── compendium/            # Geographic / editorial catalog
│   ├── models/
│   │   ├── models_cat/    # Country, Region, POI, Card, Post
│   │   └── models_m2m/    # PoiRegion
│   ├── routes/            # Individual CRUD per entity + CSV upload
│   └── schemas/           # Create/Update/Read/SlimRead per entity
├── explorer/              # User activity data
│   ├── models/            # ExplorerAggGear, ...
│   ├── routes/            # gear CRUD + CSV upload
│   └── schemas/           # GearCreate/Update/Read
├── config.py              # Pydantic settings
├── database.py            # Async engine + session factory
├── redis.py               # Redis pool (init/close/get)
├── worker.py              # Celery app
└── main.py                # App factory, router wiring, health check
```

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
