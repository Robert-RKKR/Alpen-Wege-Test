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
| `CARD_STORAGE_DIR`     | `/data/cards`                  | generated card files           |
| `PHOTO_STORAGE_DIR`    | `/data/photos`                 | `asset_agg_photo.path` is relative to it |
| `CARD_FOOTER`          | `Alpen Wege`                   | small text at the bottom of every card |
| `PHOTO_MAX_UPLOAD_MB`  | `25`                           | largest photo upload           |

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

### Segments and routes (explorer)

A **segment** is a piece of trail with its own geometry (distance, elevation, GeoJSON line, elevation profile, start and end point). It never changes after it is made: to change the geometry, make a new segment. A **route** is an ordered chain of segments (one day). Each slot of the route has one default segment and optional alternatives; a segment can be walked reversed. A route's totals (distance, ascent, descent, highest, lowest point) come from its default segments. Journeys (several routes) are not built yet.

Who sees what: your own segments and routes and the public ones (the role's access policy decides; an administrator sees all). Anything you may not see answers `404`. New segments are private; publishing a route (`is_public: true`) publishes its own segments with it; a segment or route that another user's route or journey (or a public route) uses cannot be deleted or made private (`409`).

| Method | Path | Description |
|--------|------|-------------|
| GET    | `/explorer/segments` | List. Filters: `q`, `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id`, `created_by`, `is_public`, `unused`, `start_poi_id`, `end_poi_id`, `distance_min/max`, `elevation_gain_min/max`, `near=lon,lat` with `radius_m` (segments that start or end near a point); `sort`: `name`, `created_at`, `updated_at`, `distance_m`, `elevation_gain_m` |
| POST   | `/explorer/segments` | Create from a GPX file (multipart: `gpx_file`, `name`, `sport_type_id`, ...). Times, heart rate and cadence are dropped and the file is not kept. At most `SEGMENT_GPX_MAX_UPLOAD_MB` (5) |
| POST   | `/explorer/segments/from-coordinates` | Create from drawn points `[[lon, lat, ele?], ...]` (2 to 5000 points) |
| POST   | `/explorer/segments/from-track` | Create from a part of one of your own tracks (`track_id`, `start_distance_m`, `end_distance_m`) |
| GET    | `/explorer/segments/{id}` | One segment (`?expand=sport_type,difficulty_level,difficulty_sport,start_poi,end_poi,created_by`) |
| GET    | `/explorer/segments/{id}/geometry` | GeoJSON line, elevation profile, start and end location |
| PATCH  | `/explorer/segments/{id}` | Metadata only (name, texts, sport, difficulty, POIs, `is_public`) |
| DELETE | `/explorer/segments/{id}` | `409` while a route uses it |
| GET    | `/explorer/routes` | List. Filters: `q`, `sport_type_id`, `difficulty_level_id`, `difficulty_sport_id`, `created_by`, `is_public`, `distance_min/max`, `elevation_gain_min/max`; `sort`: `name`, `created_at`, `updated_at`, `agg_distance_m`, `agg_elevation_gain_m`, `rating_avg` |
| POST   | `/explorer/routes` | Create the route itself, a draft without segments (name, texts, optional `plan_conditions`) |
| GET    | `/explorer/routes/{id}` | The route with its segment rows, `sport_types`, `derived` and `classification_differs` (`?expand=sport_type,difficulty_level,difficulty_sport,created_by`) |
| PUT    | `/explorer/routes/{id}/segments` | **Replace the segment list** (see below) |
| GET    | `/explorer/routes/{id}/segments` | The rows in slot order, the default of a slot first, as the route walks them |
| POST   | `/explorer/routes/{id}/segments/validate` | The same checks as the save, without saving (a saved segment by id, an unsaved drawing by its first and last point) |
| GET    | `/explorer/routes/{id}/geometry` | Map line and elevation profile of the default path, alternatives as separate lines |
| PATCH  | `/explorer/routes/{id}` | Name, texts, `is_public`, sport and difficulty by hand, `plan_conditions` (only the fields sent) |
| DELETE | `/explorer/routes/{id}` | The segments stay; `409` while a journey uses the route |

**Saving the segments of a route** (`PUT /explorer/routes/{id}/segments`): the body is the complete list, `{"segments": [{"segment_id": "...", "slot_position": 0, "is_default": true, "is_reversed": false}, ...], "validation": "strict"}`. An item is an existing segment (`segment_id`) or a new one that is created in the same transaction (`inline`: drawn `coordinates`, or `track_id` with `start_distance_m` and `end_distance_m`), so drawing a trail and saving the route is one call; the answer lists the new ids in `created_segments` by position. The server checks: slots 0, 1, 2 ... without gaps, exactly one default per slot, `alt_group` (if sent) equal to the slot, at most 50 rows, and that neighbouring segments connect, which means the end of the default of slot N and the start of the default of slot N+1 (as walked, reversed segments swapped) are at most `CONTINUITY_THRESHOLD_M` (50 m) apart or at the same POI; every alternative must start and end where the default of its slot does. `validation: "strict"` answers `422` with the problems and saves nothing (not even the new segments); `"warn"` saves and returns them in `warnings`. Then the totals are recomputed, and an empty sport or difficulty on the route is filled from the segments: the sport with the most distance, the highest difficulty level (by `rank`), the highest grade of the main sport. A value that is already set (by hand) is never changed; `classification_differs` tells when it differs from what the segments give.

Limits (settings): `SEGMENT_DRAW_MAX_POINTS` 5000 points per drawn segment, `ROUTE_SAVE_MAX_POINTS` 20000 drawn points per save, `ROUTE_MAX_SEGMENTS` 50 rows per route, elevations from -1000 to 10000 m (drawn points outside are refused, broken elevations in a GPX file are dropped with the warning `elevation_outliers_dropped`). A named `start_poi_id` or `end_poi_id` must be within 500 m of that end of the segment. Checks of everything above: `scripts/hierarchy_check.py` (live, see its header).

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

**Rank (four tables).** `difficulty-levels`, `difficulty-sports`, `rarities` and `visibilities` are scales and have one more required whole number, `rank` (0 to 1000): the place of the value on the scale, a higher number means harder, rarer or worse; equal numbers are allowed. It is used to find the hardest value, for example the difficulty of a route. For `difficulty-sports` the scale is per `sport_type_id` (only grades of the same sport type are comparable; UIAA and French grades share the climbing scale). Lists take `rank_min` and `rank_max` and `sort=rank`. The other reference tables have no rank. Create needs it (`422` without), Update leaves it unchanged when it is not sent, and a required field (`color`, `icon`, `point_factor`, `rank`) cannot be set to `null` (`422`).

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

Shared geographic / editorial catalog. List endpoints return their nested objects one level deep. A single-object GET returns linked objects as IDs only; ask for the full objects with `?expand=` (see "Expanding linked objects" below). FK IDs are accepted on create/update.

| Method | Path                          | Description          |
|--------|-------------------------------|----------------------|
| GET    | `/compendium/countries`                  | List countries       |
| POST   | `/compendium/countries`                  | Create (201)         |
| GET    | `/compendium/countries/{id}`             | Get one              |
| PATCH  | `/compendium/countries/{id}`             | Update               |
| DELETE | `/compendium/countries/{id}`             | Delete (204)         |
| POST   | `/compendium/countries/upload-csv`       | Bulk import from CSV |

Same pattern for: `/compendium/regions`, `/compendium/pois`, `/compendium/cards`, `/compendium/posts`, `/compendium/poi-regions`. `POST /compendium/pois/{id}/rescan` and `POST /compendium/cards/{id}/rescan` start a rescan job (see the jobs section below). Card graphics: see "Collectible cards" below.

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

`GET /api/v1/compendium/regions/{id}?expand=country,region_type` returns the nested objects:

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

### Assets (photos and GPX files)

| Method | Path | Description |
|---|---|---|
| GET | `/assets/photos` | List photos (filters: `q`, `created_by`, `is_public`, `altitude_min/max`, `taken_from/to`, `created_from/to`, `bbox`, `near` + `radius_m`; sort: `name`, `taken_at`, `altitude_m`, `created_at`) |
| POST | `/assets/photos` | Upload a photo (multipart, `201`) |
| GET | `/assets/photos/{id}` | Get one (`?expand=created_by`) |
| GET | `/assets/photos/{id}/file` | The image |
| PATCH | `/assets/photos/{id}` | Change name, summary, location, altitude, `taken_at`, `is_public` (the image itself cannot be replaced) |
| DELETE | `/assets/photos/{id}` | Delete photo and file (`409` while it is the main photo of something) |
| GET | `/assets/gpx` | List GPX files (filters: `q`, `created_by`, `is_public`, `sha256`, `created_from/to`) |
| GET | `/assets/gpx/{id}` | Get one |
| GET | `/assets/gpx/{id}/file` | Download the file |
| PATCH | `/assets/gpx/{id}` | Change name, summary, `is_public` |
| DELETE | `/assets/gpx/{id}` | Delete a file no track uses (`409` otherwise) |

A GPX file is created by `POST /explorer/tracks`, not here. Access follows the `photo` and `gpx` policies (own, public, all).

**Upload a photo** (form fields besides `file` are optional; `name` defaults to the file name):

```bash
curl -X POST http://localhost:8000/api/v1/assets/photos \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@pfannenstock.jpg" -F "name=Pfannenstock" -F "is_public=true"
```

JPEG, PNG or WebP up to `PHOTO_MAX_UPLOAD_MB`. The image is decoded (anything else answers `400`), turned upright,
shrunk to at most 2560 px and saved without metadata under `PHOTO_STORAGE_DIR/<year>/<month>/<uuid>.<ext>`.
Position, altitude and capture time are taken from the EXIF data unless the form gives `lon` + `lat`, `altitude_m`, `taken_at`.

**Put it on a card, POI or post** with their own update call, like any other link:

```bash
curl -X PATCH http://localhost:8000/api/v1/compendium/cards/<card-uuid> \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"main_photo_id": "<photo-uuid>"}'
```

A card is rendered again. On a POI, every card of the POI without its own photo shows it. Create, update and CSV
import of cards, POIs and posts accept only a photo the caller may read (own, or public when the role reads public
photos); anything else answers `422` on `main_photo_id`, so a private photo of somebody else cannot be published
through a card. `null` removes the photo.

### Collectible cards (graphics)

A card is the printable picture of a POI, by default 63×88 mm (trading-card size), with a dark 3 mm bleed. The front shows the
order number, the flag of every country the POI lies in (main region first, then `compendium/poi-regions` by
`slot_position`), the main photo, the name, region and country, the type, the altitude, the difficulty (only
when set) and the description; the rarity sets the colour of the frame (Legendary and Mythic get a holographic one).

| Card shows | Taken from |
|---|---|
| `No 013` | `card.card_number`: unique, assigned automatically; can be given on create, update or CSV to keep the number of an old printed card |
| Name | `card.name` → `poi.name` |
| Description | `card.description` → `card.summary` → `poi.description` → `poi.summary` |
| Country | `country.name_common` → `country.name` (flags: main region, then `compendium/poi-regions` by `slot_position`) |
| Region, type, rarity, difficulty | their `name` (type: `card.compendium_type_id` → `poi.compendium_type_id`) |
| Photo | `card.main_photo_id` → `poi.main_photo_id` (upload with `POST /assets/photos`, then set `main_photo_id`); without one a placeholder in the rarity colour |
| Altitude | `poi.altitude_m` |
| Difficulty (sport) | `card.difficulty_sport_id`: short name (`SAC T3`) as plain text in the difficulty box, its colour as a diamond before the card number; both left out when empty |
| Difficulty (level) | `card.difficulty_level_id`: its name after the rarity at the bottom (`COMMON / EASY`); left out when empty |
| Frame colour | `card.rarity_id` → `core_ref_rarity.color` |

**Language.** `lang` (`en`, `de`, `pl`) of `GET .../render` sets the language of every text on the card. Each text is
looked up in that language first on every source in the order of the table, and only when none has it in the next
language that has text (en, de, pl in this order). For `lang=de` the name is `card.name_de` → `poi.name_de` →
`card.name` → `poi.name` → `card.name_pl` → `poi.name_pl`: a German card shows the German POI name before an English
name written on the card. Empty or whitespace-only text counts as missing. German and Polish country names are filled by
`scripts/sql/country_names_l18n.sql` (Unicode CLDR; only empty fields are filled).

| Method | Path | Description |
|---|---|---|
| GET | `/compendium/cards/{id}/render?format=svg&lang=en&ratio=63:88` | The card. `format`: `json` (the render model: every value on the card, translated, for your own front end), `svg`, `png` (300 dpi), `jpg` (300 dpi), `pdf` (print). `lang`: `en`, `de`, `pl`. `ratio`: shape as width:height (see below). `download=true` saves instead of showing |
| POST | `/compendium/cards/{id}/render` | Render the stored files again (job, `202` with `job_id`; `409` when one is already queued or running) |

**Shape.** `ratio` is width:height with whole numbers 1 to 100, between 2:5 and 5:2 (so `100:1` answers `422`):
`63:88` (default, trading card), `1:1`, `4:5`, `9:16`, `3:2`, `16:9`, ... The shorter side is always 63 mm, so text keeps its
size on every shape; the photo grows with the longer side. From 13:10 on (wide cards) the photo sits on the left and the
type, altitude, difficulty and description on the right.

**Colours.** The card body is a soft gradient of the rarity colour, the 3 mm bleed is dark navy and a ring of the two
mixed sits between them (holographic from Legendary). Every text on the body is dark or white, whichever has more contrast
on that rarity colour (WCAG formula); the boxes behind type, altitude and description get a light or dark veil that is
made just strong enough for 4.5 : 1. The colour of the sport difficulty only appears as the diamond before the card
number, on the dark number pill with a white outline, so it reads on every rarity. A new rarity colour needs no code change.

**Postman variables.** `card_lang` and `card_ratio` are Postman environment variables that fill the API parameters `lang`
and `ratio` in the saved requests. The API itself only knows `format`, `lang`, `ratio` and `download`; any other parameter
(such as `card_ratio=1:1` typed into the URL) answers `422`.

Creating or changing a card queues a `card.render` job automatically (follow it like any job, see below). It writes
`svg`, `png`, `jpg` and `pdf` (63:88) in the three languages to `CARD_STORAGE_DIR/{card_id}/{lang}.{format}` and sets
`render_status` (`pending`, `rendering`, `done`, `failed`), `render_version` and `rendered_at` on the card. `GET .../render`
serves those files while they are up to date (other ratios are always drawn on request); when the card, its POI or a reference value changed since (or the
template is newer), the card is drawn on the spot, so the answer is always current. Deleting a card deletes its files.
The list takes `sort=card_number` and the filters `difficulty_level_id`, `difficulty_sport_id` and `render_status`.

```bash
# print-ready PDF of card 013 in German
curl -H "Authorization: Bearer $TOKEN" -o card-013.pdf \
  "http://localhost:8000/api/v1/compendium/cards/<card-uuid>/render?format=pdf&lang=de"
```

The design is one Jinja2 SVG template, `app/compendium/cards/templates/card.svg.j2`; text is wrapped and sized in
`app/compendium/cards/render.py` with the metrics of the bundled Inter font. After changing the template or the
layout, raise `TEMPLATE_VERSION` in `render.py`: every card then counts as stale and is drawn fresh until it is rendered again.
Flags: [flag-icons](https://github.com/lipis/flag-icons) (MIT), font: [Inter](https://rsms.me/inter/) (SIL OFL), both in `app/compendium/cards/`.

Database changes: `scripts/sql/card_render_ddl.sql`, `scripts/sql/country_names_l18n.sql`.

### Expanding linked objects (`?expand=`)

A single-object GET (for example `/compendium/pois/{id}`, `/explorer/tracks/{id}`, `/core/rarities/{id}`,
`/management/event-log/{id}`) returns every linked object as its ID only. Add `expand` with a comma-separated list of
links to get the full object instead. The allowed names are in the description of the `expand` parameter of each
endpoint in Swagger.

```bash
curl "http://localhost:8000/api/v1/compendium/pois/<id>?expand=main_region.country,compendium_type" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/explorer/tracks/<id>?expand=sport_type,start_poi,created_by" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/management/event-log/<id>?expand=changed_by,entity_type" -H "Authorization: Bearer $TOKEN"
```

| Rule | Detail |
|------|--------|
| Names | A link is asked for by name (`main_region`, `poi`, ...). `created_by`, `changed_by` and `updated_by` fill `created_by_user`, `changed_by_user` and `updated_by_user`; every other name fills the field of the same name |
| Depth | Dotted paths go at most 3 levels deep (`main_region.country.created_by`); the parents of a path are included. One request may ask for at most 10 links in total |
| Not asked | A link that is not asked for stays `null` next to its ID (`"main_region_id": "...", "main_region": null`); `null` also appears when the ID itself is empty |
| Errors | An unknown name, a path deeper than 3 levels or more than 10 links answers `400`; `response_details.error_message` names the allowed links |
| Who sees what | Whoever may read an object may see what is expanded inside it. Of a user behind `created_by`, `changed_by`, `updated_by` or `user` everybody sees `id` and `username`; the other profile fields (email, birth date, heart rates, ...) are `null` unless the caller is an administrator or that user himself |
| Lists | List endpoints do not take `expand` and keep returning their nested objects |
| Repeating | Write `?expand=a,b`; if the parameter is repeated only the last value counts |

---

### Lists: filters and sorting

Every list endpoint (`GET /compendium/pois`, `/explorer/tracks`, `/core/rarities`, `/management/event-log`, ...) takes
filters that fit its data and an optional `sort`. Paging works as it always did (`limit`, `offset`; the users list
calls the offset `skip`). The filters of each endpoint are in Swagger.

```bash
curl "http://localhost:8000/api/v1/compendium/pois?q=bahnhof&altitude_min=1000&sort=-altitude_m" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/compendium/pois?near=8.54,47.37&radius_m=5000" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/compendium/pois?compendium_type_id=<id1>&compendium_type_id=<id2>&bbox=7,46,8,47" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/explorer/tracks?distance_min=10000&sport_type_id=<id>&sort=-distance_m" -H "Authorization: Bearer $TOKEN"
```

| Rule | Detail |
|------|--------|
| Paging | Unchanged: `limit` defaults to 1000 (100 on tracks, the event log, jobs and my jobs), `offset` skips rows (`skip` on the users list); tracks, jobs and my jobs allow at most 500 per call, the other lists have no maximum. `limit` or `offset` below 1 / 0 or above 1,000,000,000 answer `422` |
| Counting | `response_pagination.pagination_total` counts the rows that match the filters, not the whole table |
| Sorting | `sort=name` ascending, `sort=-name` descending, one field; the allowed names are in the description of `sort` in Swagger, an unknown name answers `422`. Rows without a value come last; equal values are ordered by `id`, so pages do not repeat or skip rows. Without `sort` each list keeps its old order |
| Text search | `q` searches the name in English, German and Polish (and for some lists the summary, model or e-mail), not case sensitive, at least 2 characters (an empty `q` means no search); `%` and `_` are ordinary characters |
| Values | A filter that names a row (`compendium_type_id`, `sport_type_id`, ...) takes one id or the same parameter several times (`compendium_type_id=a&compendium_type_id=b` means a or b), at most 50. Different filters are combined with AND. A text filter that is sent empty (`kind=`) counts as not given; an id, a number or a date has to be valid or left out. Ranges are `..._min` and `..._max` (both included, whole numbers between -1,000,000,000 and 1,000,000,000); dates are `..._from` (included) and `..._to` (not included), the year between 1900 and 2200; give a time zone (`2026-10-01T00:00:00Z`), without one the time zone of the database session applies |
| Geography | `bbox=min_lon,min_lat,max_lon,max_lat` (west, south, east, north; plain decimals; a box over the 180th meridian has to be asked twice; on regions the area of the region has to touch the box, on POIs the point has to be inside) and, on POIs, `near=lon,lat` with `radius_m` (default 5000, at most 100000) |
| Who sees what | The filters narrow the rows the caller may already see; they never widen them. A viewer who asks for `created_by=<someone>` still only gets what the access policy allows |
| Unknown parameters | A parameter that a list does not know is ignored, as before (so check the spelling of a filter) |
| Errors | An unknown `sort` name, a bad `bbox`, a one-character `q`, more than 50 ids, a number, date, `limit` or `offset` out of range or a NUL character answer `422`; `response_details.error_errors` names the field (`query.sort`, ...) and what is allowed |

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
| Required columns| A column that is `NOT NULL` without a default (the table in Swagger shows them as **yes**, for example `rank` on the four scale tables) must be in the header, otherwise nothing is inserted and `errors` names the missing columns; a row with an empty required cell is reported (`row 3: missing value for rank`) and the other rows are still imported |

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
- **Single-object GETs take `?expand=`.** Their `get_one.py` uses a `*Detail` schema (next to the `*Read` schema, with `Link()` fields) and `plan: ExpandPlan = Depends(expand_plan(XDetail))` from `app/core/utils/expand.py`; `select(...).options(*plan.load_options(Model))` loads the asked links and `ok(plan.render(obj))` builds the answer. A new GET-by-id route must be added to `tests/test_expand_routes.py` (and its schema to `tests/test_expand_wiring.py`).
- Helpers used by several resources live in `app/core/utils/` (`scope.py`, `api_paths.py`, `expand.py`); route files never import from other resources; URLs are never written as strings in route files (`api_paths.py` builds the `Location` header and names the upload path).
- Check after any change to routes: `python scripts/route_map.py dump route_dumps/x.json`, then `compare` against an earlier dump, `probe` and `names` (see `scripts/route_map.py`); `tests/test_routes_standard.py` and `tests/test_api_paths.py` enforce the rules above; `python scripts/route_map.py compare BEFORE AFTER --expand` accepts exactly the changes of the expand option; `scripts/expand_check.py` is the live check of `?expand=` (needs the seeded users and compendium data).

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
├── assets/                # Uploaded files: photos (upload, EXIF, resize) and GPX files
│   ├── models/  routes/ (photo/, gpx/)  schemas/  services/photo_storage.py
├── compendium/            # Geographic / editorial catalog
│   ├── cards/             # card graphics: render.py, service.py, templates/card.svg.j2, fonts/, flags/
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

Work that runs in the background (GPX processing, POI and card rescans, card rendering) is tracked as a **job**.
`POST /explorer/tracks`, `POST /explorer/tracks/{id}/reprocess`, `POST /compendium/pois/{id}/rescan`, `POST /compendium/cards/{id}/rescan` and `POST /compendium/cards/{id}/render`
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
