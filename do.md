What's done
Database schema — fully designed, ~40+ tables covering all domains (PostGIS-enabled)
SQLAlchemy models — all domains have models defined (explorer, compendium, profile, social, assets, core reference tables, users)
Auth module — complete with routes, schemas, services (register, login, logout, refresh, JWT, password hashing, token-refresh middleware, permissions)
Users module — complete with routes, schemas, services (me endpoint, admin user management)
Core module — base model, pagination/base schemas, database & Redis dependencies, ~18 reference table models
Worker — Celery app configured, cleanup and stats tasks stubbed
Infrastructure — Docker Compose (PostGIS, Redis, API, Celery worker), Dockerfile, config/settings
Push data — seed CSVs for reference tables (companies, gear types, region types, POI/region/country categories)
What's left to do
No routes, schemas, or services exist yet for the main feature domains:

Explorer (the biggest piece)

Track CRUD (ACT-01 through ACT-10) — manual & GPX creation, metadata/conditions editing, GPX replace, delete, photo/gear/POI/waypoint management
Trip CRUD (ACT-11 through ACT-15) — create, edit, delete, assign/remove tracks
Route, Segment, Journey, Gear CRUD endpoints
GPX file upload & parsing (B01, B02, B03)
Auto-detect POIs near track (B10)
Compendium

POI, Region, Country, Card, Post read/admin endpoints
Profile / Gamification engine

POI visit awarding (B11)
Card collection (B12)
Achievement evaluation (B13) — the most complex piece
Points engine (B14, B17)
Statistics recalculation (B15)
Pace curve calculation (B16)
Schedule / body metrics endpoints
Social

Follow/unfollow
Comments (polymorphic on tracks/routes/trips)
Ratings
Assets

Photo upload/management
GPX file storage service
Worker tasks

Actual implementation of stats recalc and cleanup (currently stubs)
In short: the data layer and auth are solid, but all the business logic (the 18 processing blocks from the design doc) and the Explorer/Compendium/Profile/Social API endpoints are unbuilt.
