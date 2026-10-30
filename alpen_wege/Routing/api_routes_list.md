# All API routes (current repo, 2026-10-30)

Every URL starts with the base URL of your API plus `/api/v1`. On your machine that is `http://localhost:8000/api/v1` (in Postman: `{{hostname}}:{{port}}/{{api_path}}`). This list was written from the app's own route table, so it matches the code: 251 HTTP routes under `/api/v1`, `GET /health`, and 2 WebSocket routes (254 in total). Swagger is at `/docs`, ReDoc at `/redoc`, the OpenAPI file at `/openapi.json`.

**Access** column: `login` = any logged-in user; `administrator` = administrator group only; `key.action` (for example `track.read`, `segment.create`, `icon.read`) = the access policy of your role for that resource and action (scope own, public or all); `public` = no token needed.

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
| POST | `/api/v1/profile/auth/logout` | `login` | Logout |
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

### achievement-categories

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/achievement-categories` | `ref.read` | List Items |
| POST | `/api/v1/core/achievement-categories` | `ref.create` | Create Item |
| POST | `/api/v1/core/achievement-categories/upload-csv` | `ref.create` | Import achievement-categories from CSV |
| DELETE | `/api/v1/core/achievement-categories/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/achievement-categories/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/achievement-categories/{item_id}` | `ref.update` | Update Item |

### achievement-scopes

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/achievement-scopes` | `ref.read` | List Items |
| POST | `/api/v1/core/achievement-scopes` | `ref.create` | Create Item |
| POST | `/api/v1/core/achievement-scopes/upload-csv` | `ref.create` | Import achievement-scopes from CSV |
| DELETE | `/api/v1/core/achievement-scopes/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/achievement-scopes/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/achievement-scopes/{item_id}` | `ref.update` | Update Item |

### achievement-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/achievement-types` | `ref.read` | List Items |
| POST | `/api/v1/core/achievement-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/achievement-types/upload-csv` | `ref.create` | Import achievement-types from CSV |
| DELETE | `/api/v1/core/achievement-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/achievement-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/achievement-types/{item_id}` | `ref.update` | Update Item |

### companies

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/companies` | `ref.read` | List Items |
| POST | `/api/v1/core/companies` | `ref.create` | Create Item |
| POST | `/api/v1/core/companies/upload-csv` | `ref.create` | Import companies from CSV |
| DELETE | `/api/v1/core/companies/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/companies/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/companies/{item_id}` | `ref.update` | Update Item |

### compendium-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/compendium-types` | `ref.read` | List Items |
| POST | `/api/v1/core/compendium-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/compendium-types/upload-csv` | `ref.create` | Import compendium-types from CSV |
| DELETE | `/api/v1/core/compendium-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/compendium-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/compendium-types/{item_id}` | `ref.update` | Update Item |

### difficulty-levels

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/difficulty-levels` | `ref.read` | List Items |
| POST | `/api/v1/core/difficulty-levels` | `ref.create` | Create Item |
| POST | `/api/v1/core/difficulty-levels/upload-csv` | `ref.create` | Import difficulty-levels from CSV |
| DELETE | `/api/v1/core/difficulty-levels/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/difficulty-levels/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/difficulty-levels/{item_id}` | `ref.update` | Update Item |

### difficulty-sports

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/difficulty-sports` | `ref.read` | List Items |
| POST | `/api/v1/core/difficulty-sports` | `ref.create` | Create Item |
| POST | `/api/v1/core/difficulty-sports/upload-csv` | `ref.create` | Import difficulty-sports from CSV |
| DELETE | `/api/v1/core/difficulty-sports/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/difficulty-sports/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/difficulty-sports/{item_id}` | `ref.update` | Update Item |

### gear-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/gear-types` | `ref.read` | List Items |
| POST | `/api/v1/core/gear-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/gear-types/upload-csv` | `ref.create` | Import gear-types from CSV |
| DELETE | `/api/v1/core/gear-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/gear-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/gear-types/{item_id}` | `ref.update` | Update Item |

### point-reasons

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/point-reasons` | `ref.read` | List Items |
| POST | `/api/v1/core/point-reasons` | `ref.create` | Create Item |
| POST | `/api/v1/core/point-reasons/upload-csv` | `ref.create` | Import point-reasons from CSV |
| DELETE | `/api/v1/core/point-reasons/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/point-reasons/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/point-reasons/{item_id}` | `ref.update` | Update Item |

### post-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/post-types` | `ref.read` | List Items |
| POST | `/api/v1/core/post-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/post-types/upload-csv` | `ref.create` | Import post-types from CSV |
| DELETE | `/api/v1/core/post-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/post-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/post-types/{item_id}` | `ref.update` | Update Item |

### rarities

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/rarities` | `ref.read` | List Items |
| POST | `/api/v1/core/rarities` | `ref.create` | Create Item |
| POST | `/api/v1/core/rarities/upload-csv` | `ref.create` | Import rarities from CSV |
| DELETE | `/api/v1/core/rarities/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/rarities/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/rarities/{item_id}` | `ref.update` | Update Item |

### region-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/region-types` | `ref.read` | List Items |
| POST | `/api/v1/core/region-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/region-types/upload-csv` | `ref.create` | Import region-types from CSV |
| DELETE | `/api/v1/core/region-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/region-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/region-types/{item_id}` | `ref.update` | Update Item |

### resource-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/resource-types` | `administrator` | List Resource Types |
| POST | `/api/v1/core/resource-types` | `administrator` | Create Resource Type |
| POST | `/api/v1/core/resource-types/upload-csv` | `administrator` | Import resource types from CSV |
| DELETE | `/api/v1/core/resource-types/{item_id}` | `administrator` | Delete Resource Type |
| GET | `/api/v1/core/resource-types/{item_id}` | `administrator` | Get Resource Type |
| PATCH | `/api/v1/core/resource-types/{item_id}` | `administrator` | Update Resource Type |

### schedule-statuses

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/schedule-statuses` | `ref.read` | List Items |
| POST | `/api/v1/core/schedule-statuses` | `ref.create` | Create Item |
| POST | `/api/v1/core/schedule-statuses/upload-csv` | `ref.create` | Import schedule-statuses from CSV |
| DELETE | `/api/v1/core/schedule-statuses/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/schedule-statuses/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/schedule-statuses/{item_id}` | `ref.update` | Update Item |

### snow-conditions

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/snow-conditions` | `ref.read` | List Items |
| POST | `/api/v1/core/snow-conditions` | `ref.create` | Create Item |
| POST | `/api/v1/core/snow-conditions/upload-csv` | `ref.create` | Import snow-conditions from CSV |
| DELETE | `/api/v1/core/snow-conditions/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/snow-conditions/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/snow-conditions/{item_id}` | `ref.update` | Update Item |

### sport-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/sport-types` | `ref.read` | List Items |
| POST | `/api/v1/core/sport-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/sport-types/upload-csv` | `ref.create` | Import sport-types from CSV |
| DELETE | `/api/v1/core/sport-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/sport-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/sport-types/{item_id}` | `ref.update` | Update Item |

### trail-conditions

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/trail-conditions` | `ref.read` | List Items |
| POST | `/api/v1/core/trail-conditions` | `ref.create` | Create Item |
| POST | `/api/v1/core/trail-conditions/upload-csv` | `ref.create` | Import trail-conditions from CSV |
| DELETE | `/api/v1/core/trail-conditions/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/trail-conditions/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/trail-conditions/{item_id}` | `ref.update` | Update Item |

### visibilities

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/visibilities` | `ref.read` | List Items |
| POST | `/api/v1/core/visibilities` | `ref.create` | Create Item |
| POST | `/api/v1/core/visibilities/upload-csv` | `ref.create` | Import visibilities from CSV |
| DELETE | `/api/v1/core/visibilities/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/visibilities/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/visibilities/{item_id}` | `ref.update` | Update Item |

### waypoint-types

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/waypoint-types` | `ref.read` | List Items |
| POST | `/api/v1/core/waypoint-types` | `ref.create` | Create Item |
| POST | `/api/v1/core/waypoint-types/upload-csv` | `ref.create` | Import waypoint-types from CSV |
| DELETE | `/api/v1/core/waypoint-types/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/waypoint-types/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/waypoint-types/{item_id}` | `ref.update` | Update Item |

### weather-conditions

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/core/weather-conditions` | `ref.read` | List Items |
| POST | `/api/v1/core/weather-conditions` | `ref.create` | Create Item |
| POST | `/api/v1/core/weather-conditions/upload-csv` | `ref.create` | Import weather-conditions from CSV |
| DELETE | `/api/v1/core/weather-conditions/{item_id}` | `ref.delete` | Delete Item |
| GET | `/api/v1/core/weather-conditions/{item_id}` | `ref.read` | Get Item |
| PATCH | `/api/v1/core/weather-conditions/{item_id}` | `ref.update` | Update Item |

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
| GET | `/api/v1/compendium/cards/{card_id}/render` | `card.read` | Card graphic (JSON, SVG, PNG, JPG or PDF) |
| POST | `/api/v1/compendium/cards/{card_id}/render` | `card.update` | Render the card files again |
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

## assets

### gpx

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/assets/gpx` | `gpx.read` | List Gpx |
| DELETE | `/api/v1/assets/gpx/{gpx_id}` | `gpx.delete` | Delete Gpx |
| GET | `/api/v1/assets/gpx/{gpx_id}` | `gpx.read` | Get Gpx |
| PATCH | `/api/v1/assets/gpx/{gpx_id}` | `gpx.update` | Update Gpx |
| GET | `/api/v1/assets/gpx/{gpx_id}/file` | `gpx.read` | Download the GPX file |

### icons

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/assets/icons` | `icon.read` | List Icons |
| POST | `/api/v1/assets/icons` | `icon.create` | Upload an icon |
| GET | `/api/v1/assets/icons/by-key/{key}/file` | `icon.read` | The picture of an icon, found by its key |
| POST | `/api/v1/assets/icons/link` | `ref.update` | Link rows to their icons by key |
| POST | `/api/v1/assets/icons/upload-csv` | `icon.create` | Create many icons from one CSV file |
| DELETE | `/api/v1/assets/icons/{icon_id}` | `icon.delete` | Delete Icon |
| GET | `/api/v1/assets/icons/{icon_id}` | `icon.read` | Get Icon |
| PATCH | `/api/v1/assets/icons/{icon_id}` | `icon.update` | Update Icon |
| GET | `/api/v1/assets/icons/{icon_id}/file` | `icon.read` | The picture of an icon |
| PUT | `/api/v1/assets/icons/{icon_id}/file` | `icon.update` | Replace the SVG of an icon |

### photos

| Method | URL | Access | What |
|---|---|---|---|
| GET | `/api/v1/assets/photos` | `photo.read` | List Photos |
| POST | `/api/v1/assets/photos` | `photo.create` | Upload a photo |
| DELETE | `/api/v1/assets/photos/{photo_id}` | `photo.delete` | Delete Photo |
| GET | `/api/v1/assets/photos/{photo_id}` | `photo.read` | Get Photo |
| PATCH | `/api/v1/assets/photos/{photo_id}` | `photo.update` | Update Photo |
| GET | `/api/v1/assets/photos/{photo_id}/file` | `photo.read` | The image file |

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
