# Alpen Wege — Local Development Environment

## Prerequisites

- Docker & Docker Compose
- `python3` (for JSON parsing in the import script)

## Quick Start

```bash
chmod 644 alpen_wege_schema.sql
sudo docker compose up -d
```

This starts three containers:

| Container | Purpose | Port |
|-----------|---------|------|
| `alpenwege-postgres` | Application database (PostGIS) | 5432 |
| `alpenwege-nocodb-postgres` | NocoDB metadata storage | — |
| `alpenwege-nocodb` | NocoDB UI | 8080 |

Open **http://localhost:8080** to access NocoDB. On first launch, create an admin account.

## Connecting NocoDB to the Database

1. Create a new **Base**
2. Add a **Data Source** with:

| Field | Value |
|-------|-------|
| Host address | `postgres` |
| Port number | `5432` |
| Username | `alpenwege` |
| Password | `alpenwege` |
| Database | `alpenwege` |
| Schema name | `public` |

## Importing Data from CSV

### Directory Structure

```
push_data/
├── order.json                  # FK-safe insertion order (do not reorder)
├── profile_usr_user.csv
├── core_ref_sport_type.csv
├── compendium_cat_country.csv
└── ...
```

### CSV Format

- First row must be a **header** matching the column names exactly
- UUID columns must contain valid UUIDs
- Foreign key UUIDs must reference rows that exist (or are being loaded earlier in the order)
- `geometry` columns use WKT format, e.g. `SRID=4326;POINT(8.5417 47.3769)`
- `timestamptz` columns use ISO 8601, e.g. `2026-07-15T10:30:00Z`
- `integer[]` / `text[]` columns use PostgreSQL array syntax, e.g. `{1,2,3}` or `{de,en,fr}`
- `jsonb` columns use JSON strings, e.g. `{"key": "value"}`
- Empty values for nullable columns can be left blank

Example (`core_ref_sport_type.csv`):

```csv
id,created_at,updated_at,created_by,name,name_de,name_pl,color,icon,point_factor
a1b2c3d4-0000-0000-0000-000000000001,2026-07-15T00:00:00Z,2026-07-15T00:00:00Z,<admin-user-uuid>,Hiking,Wandern,Piesze wędrówki,#2E7D32,hiking,1.0
```

### Running the Import

```bash
# Import all CSVs (skips tables without a CSV file)
sudo bash update_database.sh

# Wipe all tables first, then reimport
sudo bash update_database.sh --clean
```

The `--clean` flag truncates all tables in reverse FK order before importing.

### Insertion Order

The file `push_data/order.json` defines the insertion sequence. Tables are loaded
top-to-bottom to satisfy foreign key constraints:

1. `profile_usr_user` — must be first (all `created_by` columns reference it)
2. `core_ref_*` — reference tables
3. `asset_agg_*` — GPX files and photos
4. `compendium_*` — countries, regions, POIs, cards, posts
5. `explorer_sub_*` — geo records, conditions, waypoints
6. `explorer_agg_*` — gear, segments, routes, journeys, tracks, trips
7. `explorer_m2m_*` — many-to-many link tables
8. `profile_*` — pace curves, achievements, points, schedules, statistics, collections
9. `social_*` — follows, comments, ratings

> **Do not reorder** entries in `order.json` unless you understand the FK dependencies.

## Common Commands

```bash
# Start
sudo docker compose up -d

# Stop
sudo docker compose down

# Stop and delete all data
sudo docker compose down -v

# View postgres logs
sudo docker logs alpenwege-postgres

# View nocodb logs
sudo docker logs alpenwege-nocodb

# Connect to database directly
sudo docker exec -it alpenwege-postgres psql -U alpenwege -d alpenwege

# List all tables
sudo docker exec alpenwege-postgres psql -U alpenwege -d alpenwege -c "\dt"

# Rebuild from scratch (fresh schema + reimport)
sudo docker compose down -v
sudo docker compose up -d
sudo bash update_database.sh
```

## Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Container orchestration |
| `alpen_wege_schema.sql` | Database schema (loaded on first start) |
| `update_database.sh` | CSV import script |
| `push_data/order.json` | FK-safe table insertion order |
| `push_data/*.csv` | Data files to import |
