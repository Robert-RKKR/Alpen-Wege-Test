# All API routes (current repo, 2026-10-27)

Every URL starts with the base URL of your API plus `/api/v1`. On your machine that is `http://localhost:8000/api/v1` (in Postman: `{{hostname}}:{{port}}/{{api_path}}`). This list was written from the app's own route table, so it matches the code: 228 HTTP routes under `/api/v1`, `GET /health`, and 2 WebSocket routes (231 in total). Swagger is at `/docs`, ReDoc at `/redoc`, the OpenAPI file at `/openapi.json`.

**Access** column: `login` = any logged-in user; `administrator` = administrator group only; `key.action` (for example `track.read`, `segment.create`) = the access policy of your role for that resource and action (scope own, public or all); `public` = no token needed.

## profile

### access-policies

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/profile/access-policies` | `administrator` | List Access Policies |
| POST | `/api/v1/profile/access-policies` | `administrator` | Create Access Policy |
| POST | `/api/v1/profile/access-policies/upload-csv` | `administrator` | Import access policies from CSV |
| DELETE | `/api/v1/profile/access-policies/{item_id}` | `administrator` | Delete Access Policy |
| GET | `/api/v1/profile/access-policies/{item_id}` | `administrator` | Get Access Policy |
| PATCH | `/api/v1/profile/access-policies/{item_id}` | `administrator` | Update Access Policy |

### auth

| Method | URL | Access | What |
|---|---|---|---|
| POST | `/api/v1/profile/auth/login` | `public` | Login |
| POST | `/api/v1/profile/auth/logout` | `public` | Logout |
| POST | `/api/v1/profile/auth/refresh` | `login` | Refresh Token |
| POST | `/api/v1/profile/auth/register` | `public` | Register |

### users

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/profile/users/` | `administrator` | List Users |
| GET | `/api/v1/profile/users/me` | `login` | Get Me |
| PUT | `/api/v1/profile/users/me` | `login` | Update Me |
| GET | `/api/v1/profile/users/{user_id}` | `administrator` | Get User |
| PUT | `/api/v1/profile/users/{user_id}/activate` | `administrator` | Activate User |
| PUT | `/api/v1/profile/users/{user_id}/deactivate` | `administrator` | Deactivate User |
| PUT | `/api/v1/profile/users/{user_id}/group` | `administrator` | Change Group |

## core

**Lookup tables (19):** `achievement-categories`, `achievement-scopes`, `achievement-types`, `companies`, `compendium-types`, `difficulty-levels`, `difficulty-sports`, `gear-types`, `point-reasons`, `post-types`, `rarities`, `region-types`, `schedule-statuses`, `snow-conditions`, `sport-types`, `trail-conditions`, `visibilities`, `waypoint-types`, `weather-conditions`. Each one has the same routes; `{slug}` stands for the table name:

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/{slug}` | `ref.read` | List Items |
| POST | `/api/v1/core/{slug}` | `ref.create` | Create Item |
| POST | `/api/v1/core/{slug}/upload-csv` | `ref.create` | Import rows from CSV |
| DELETE | `/api/v1/core/{slug}/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/{slug}/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/{slug}/{item_id}` | `ref.update` | Update Item |

Differences: `difficulty-sports` has the extra list filter `sport_type_id`; `compendium-types` has the field `is_collectable`; `difficulty-levels`, `difficulty-sports`, `rarities` and `visibilities` have `rank` and the list filters `rank_min` and `rank_max`.

### resource-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/resource-types` | `administrator` | List Resource Types |
| POST | `/api/v1/core/resource-types` | `administrator` | Create Resource Type |
| POST | `/api/v1/core/resource-types/upload-csv` | `administrator` | Import resource types from CSV |
| DELETE | `/api/v1/core/resource-types/{item_id}` | `administrator` | Delete Resource Type |
| GET | `/api/v1/core/resource-types/{item_id}` | `administrator` | Get Resource Type |
| PATCH | `/api/v1/core/resource-types/{item_id}` | `administrator` | Update Resource Type |

## compendium

### cards

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/compendium/cards` | `card.read` | List Cards |
| POST | `/api/v1/compendium/cards` | `card.create` | Create Card |
| POST | `/api/v1/compendium/cards/upload-csv` | `card.create` | Import cards from CSV |
| DELETE | `/api/v1/compendium/cards/{card_id}` | `card.delete` | Delete Card |
| GET | `/api/v1/compendium/cards/{card_id}` | `card.read` | Get Card |
| PATCH | `/api/v1/compendium/cards/{card_id}` | `card.update` | Update Card |
| POST | `/api/v1/compendium/cards/{card_id}/rescan` | `card.update` | Rescan Card |

### countries

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/compendium/countries` | `country.read` | List Countries |
| POST | `/api/v1/compendium/countries` | `country.create` | Create Country |
| POST | `/api/v1/compendium/countries/upload-csv` | `country.create` | Import countries from CSV |
| DELETE | `/api/v1/compendium/countries/{country_id}` | `country.delete` | Delete Country |
| GET | `/api/v1/compendium/countries/{country_id}` | `country.read` | Get Country |
| PATCH | `/api/v1/compendium/countries/{country_id}` | `country.update` | Update Country |

### poi-regions

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/compendium/poi-regions` | `poi_region.read` | List Poi Regions |
| POST | `/api/v1/compendium/poi-regions` | `poi_region.create` | Create Poi Region |
| POST | `/api/v1/compendium/poi-regions/upload-csv` | `poi_region.create` | Import POI-region links from CSV |
| DELETE | `/api/v1/compendium/poi-regions/{poi_region_id}` | `poi_region.delete` | Delete Poi Region |
| GET | `/api/v1/compendium/poi-regions/{poi_region_id}` | `poi_region.read` | Get Poi Region |
| PATCH | `/api/v1/compendium/poi-regions/{poi_region_id}` | `poi_region.update` | Update Poi Region |

### pois

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/compendium/pois` | `poi.read` | List Pois |
| POST | `/api/v1/compendium/pois` | `poi.create` | Create Poi |
| POST | `/api/v1/compendium/pois/upload-csv` | `poi.create` | Import POIs from CSV |
| DELETE | `/api/v1/compendium/pois/{poi_id}` | `poi.delete` | Delete Poi |
| GET | `/api/v1/compendium/pois/{poi_id}` | `poi.read` | Get Poi |
| PATCH | `/api/v1/compendium/pois/{poi_id}` | `poi.update` | Update Poi |
| POST | `/api/v1/compendium/pois/{poi_id}/rescan` | `poi.update` | Rescan Poi |

### posts

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/compendium/posts` | `post.read` | List Posts |
| POST | `/api/v1/compendium/posts` | `post.create` | Create Post |
| POST | `/api/v1/compendium/posts/upload-csv` | `post.create` | Import posts from CSV |
| DELETE | `/api/v1/compendium/posts/{post_id}` | `post.delete` | Delete Post |
| GET | `/api/v1/compendium/posts/{post_id}` | `post.read` | Get Post |
| PATCH | `/api/v1/compendium/posts/{post_id}` | `post.update` | Update Post |

### regions

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/compendium/regions` | `region.read` | List Regions |
| POST | `/api/v1/compendium/regions` | `region.create` | Create Region |
| POST | `/api/v1/compendium/regions/upload-csv` | `region.create` | Import regions from CSV |
| DELETE | `/api/v1/compendium/regions/{region_id}` | `region.delete` | Delete Region |
| GET | `/api/v1/compendium/regions/{region_id}` | `region.read` | Get Region |
| PATCH | `/api/v1/compendium/regions/{region_id}` | `region.update` | Update Region |

## explorer

### gear

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/explorer/gear` | `gear.read` | List Gear |
| POST | `/api/v1/explorer/gear` | `gear.create` | Create Gear |
| POST | `/api/v1/explorer/gear/upload-csv` | `gear.create` | Import gear from CSV |
| DELETE | `/api/v1/explorer/gear/{gear_id}` | `gear.delete` | Delete Gear |
| GET | `/api/v1/explorer/gear/{gear_id}` | `gear.read` | Get Gear |
| PATCH | `/api/v1/explorer/gear/{gear_id}` | `gear.update` | Update Gear |

### routes

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/explorer/routes` | `route.read` | List Routes |
| POST | `/api/v1/explorer/routes` | `route.create` | Create Route |
| DELETE | `/api/v1/explorer/routes/{route_id}` | `route.delete` | Delete Route |
| GET | `/api/v1/explorer/routes/{route_id}` | `route.read` | Get Route |
| PATCH | `/api/v1/explorer/routes/{route_id}` | `route.update` | Update Route |
| GET | `/api/v1/explorer/routes/{route_id}/geometry` | `route.read` | Get Route Geometry |
| GET | `/api/v1/explorer/routes/{route_id}/segments` | `route.read` | Get Route Segments |
| PUT | `/api/v1/explorer/routes/{route_id}/segments` | `route.update` | Set Route Segments |
| POST | `/api/v1/explorer/routes/{route_id}/segments/validate` | `route.read` | Validate Route Segments |

### segments

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/explorer/segments` | `segment.read` | List Segments |
| POST | `/api/v1/explorer/segments` | `segment.create` | Create Segment |
| POST | `/api/v1/explorer/segments/from-coordinates` | `segment.create` | Create Segment From Coordinates |
| POST | `/api/v1/explorer/segments/from-track` | `segment.create` | Create Segment From Track |
| DELETE | `/api/v1/explorer/segments/{segment_id}` | `segment.delete` | Delete Segment |
| GET | `/api/v1/explorer/segments/{segment_id}` | `segment.read` | Get Segment |
| PATCH | `/api/v1/explorer/segments/{segment_id}` | `segment.update` | Update Segment |
| GET | `/api/v1/explorer/segments/{segment_id}/geometry` | `segment.read` | Get Segment Geometry |

### tracks

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/explorer/tracks` | `track.read` | List Tracks |
| POST | `/api/v1/explorer/tracks` | `track.create` | Create Track |
| DELETE | `/api/v1/explorer/tracks/{track_id}` | `track.delete` | Archive Track |
| GET | `/api/v1/explorer/tracks/{track_id}` | `track.read` | Get Track |
| PATCH | `/api/v1/explorer/tracks/{track_id}` | `track.update` | Update Track |
| GET | `/api/v1/explorer/tracks/{track_id}/geometry` | `track.read` | Get Track Geometry |
| GET | `/api/v1/explorer/tracks/{track_id}/performance` | `track.read` | Get Track Performance |
| POST | `/api/v1/explorer/tracks/{track_id}/reprocess` | `track.update` | Reprocess Track |
| POST | `/api/v1/explorer/tracks/{track_id}/restore` | `track.update` | Restore Track |

## management

### broadcast

| Method | URL | Access | What |
|---|---|---|---|
| POST | `/api/v1/management/broadcast` | `administrator` | Send Broadcast |

### celery

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/management/celery/beat` | `administrator` | Celery Beat |
| GET | `/api/v1/management/celery/status` | `administrator` | Celery Status |
| GET | `/api/v1/management/celery/tasks/active` | `administrator` | Celery Live Tasks |
| GET | `/api/v1/management/celery/tasks/registered` | `administrator` | Celery Registered |
| GET | `/api/v1/management/celery/tasks/{task_id}` | `administrator` | Celery Task Detail |
| GET | `/api/v1/management/celery/workers` | `administrator` | Celery Workers |

### event-log

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/management/event-log` | `administrator` | List Event Logs |
| GET | `/api/v1/management/event-log/entity-types` | `administrator` | List Entity Types |
| GET | `/api/v1/management/event-log/{id_1}/compare/{id_2}` | `administrator` | Compare Event Logs |
| GET | `/api/v1/management/event-log/{log_id}` | `administrator` | Get Event Log |

### jobs

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/management/jobs` | `administrator` | List All Jobs |
| GET | `/api/v1/management/jobs/stats` | `administrator` | Job Stats |
| GET | `/api/v1/management/jobs/{job_id}` | `administrator` | Get Any Job |

### my-jobs

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/management/my-jobs` | `login` | List My Jobs |
| GET | `/api/v1/management/my-jobs/{job_id}` | `login` | Get My Job |

### settings

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/management/settings` | `administrator` | List Settings |
| GET | `/api/v1/management/settings/{key}` | `administrator` | Get Setting Route |
| PATCH | `/api/v1/management/settings/{key}` | `administrator` | Update Setting |
| POST | `/api/v1/management/settings/{key}/reset` | `administrator` | Reset Setting |

### ws

| Method | URL | Access | What |
|---|---|---|---|
| POST | `/api/v1/management/ws/ticket` | `login` | Create Ws Ticket |

## Other

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/health` | `public` | Health |
| WebSocket | `/api/v1/management/ws` | `token` | ws general |
| WebSocket | `/api/v1/management/ws/jobs/{job_id}` | `token` | ws job |
