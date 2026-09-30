-- ============================================================================
-- EXPLORER — full database schema (v2, corrected)
-- Target: PostgreSQL 15+ with PostGIS (self-hosted / Hetzner)
-- Changes vs v1:
--   * integer -> integer for distances, durations, steps, calories,
--     point counts, elevation gain/loss
--   * no defaults on FK columns; created_by set by the service layer
--   * no UNIQUE on agg "name" columns; no UNIQUE on sort columns
--   * all sort columns renamed to "slot_position" (segment_route: v1
--     "order" + "position" merged into a single slot_position)
--   * "title" renamed to "name" (day_title -> day_name)
--   * timestamptz everywhere; updated_at NOT NULL + moddatetime trigger
--   * json -> jsonb; moving_ratio -> real; best_months -> integer[]
--   * bbox -> geometry(Polygon,4326); explicit geometry types (SRID 4326)
--   * m2m_track_gear: uuid PK + created_by
--   * missing FK on compendium_cat_card.rarity_id added
--   * is_public NOT NULL DEFAULT false everywhere
--   * FK + GIST indexes added
--   * i18n: name/summary/description _de and _pl columns on all
--     compendium_cat_* tables (base column = English default)
--   * core_ref_*: name_de/name_pl added, "value" column removed
--     (English "name" is now the stable programmatic key)
--   * i18n extended to: poi_access notes, country name_common/
--     name_official/capital, plan_conditions permit_info/
--     best_months_note, asset name/summary
--   * i18n on explorer_agg_*: name/summary/description _de/_pl
--   * added profile.profile_sub_pace_curve + explorer.explorer_sub_prediction
--   * profile schema: usr_user, body_metric, achievements, points ledger,
--     schedule, statistics, collections/likes; social schema: follow,
--     comment, rating; created_by/user_id wired to profile_usr_user;
--     rating_count added next to rating_avg
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS moddatetime;

CREATE SCHEMA IF NOT EXISTS core;
CREATE SCHEMA IF NOT EXISTS asset;
CREATE SCHEMA IF NOT EXISTS compendium;
CREATE SCHEMA IF NOT EXISTS explorer;
CREATE SCHEMA IF NOT EXISTS profile;
CREATE SCHEMA IF NOT EXISTS social;


-- ============================================================================
-- SCHEMA: profile — user (created first: every created_by references it)
-- Seed note: insert a system/admin user before seeding core_ref_* data.
-- ============================================================================

CREATE TABLE profile.profile_usr_user (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    email              text NOT NULL UNIQUE,
    username           text NOT NULL UNIQUE,
    first_name         text,
    middle_name        text,
    last_name          text,
    gender             text CHECK (gender IN ('male', 'female', 'not_specified')),
    birth_date         date,
    height_cm          integer,
    max_heart_rate     integer,
    resting_heart_rate integer,
    home_location      geometry(Point, 4326),
    is_active          boolean NOT NULL DEFAULT true,
    last_active_at     timestamptz,
    avatar_photo_id    uuid   -- FK added after asset_agg_photo exists (ALTER below)
);

-- ============================================================================
-- SCHEMA: core — reference tables
-- ============================================================================

CREATE TABLE core.core_ref_sport_type (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL CHECK (color ~ '^#[0-9a-fA-F]{6}$'),
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_achievement_category (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_achievement_scope (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_achievement_type (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_company (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name       text NOT NULL UNIQUE,
    name_de    text,
    name_pl    text,
    color      text NOT NULL,
    icon       text NOT NULL
);

CREATE TABLE core.core_ref_compendium_type (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_difficulty_level (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_difficulty_sport (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name          text NOT NULL UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL,
    sport_type_id uuid REFERENCES core.core_ref_sport_type (id)
);

CREATE TABLE core.core_ref_gear_type (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name       text NOT NULL UNIQUE,
    name_de    text,
    name_pl    text,
    color      text NOT NULL,
    icon       text NOT NULL
);

CREATE TABLE core.core_ref_point_reason (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_post_type (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_rarity (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_region_type (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_schedule_status (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_snow_condition (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_trail_condition (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_visibility (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_waypoint_type (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

CREATE TABLE core.core_ref_weather_condition (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    created_by   uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name         text NOT NULL UNIQUE,
    name_de      text,
    name_pl      text,
    color        text NOT NULL,
    icon         text NOT NULL,
    point_factor real NOT NULL
);

-- ============================================================================
-- SCHEMA: asset
-- ============================================================================

CREATE TABLE asset.asset_agg_gpx (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public  boolean NOT NULL DEFAULT false,
    name       text NOT NULL,
    name_de    text,
    name_pl    text,
    summary    text,
    summary_de text,
    summary_pl text,
    path       text NOT NULL UNIQUE
);

CREATE TABLE asset.asset_agg_photo (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public  boolean NOT NULL DEFAULT false,
    name       text NOT NULL,
    name_de    text,
    name_pl    text,
    summary    text,
    summary_de text,
    summary_pl text,
    location   geometry(Point, 4326),
    altitude_m integer,
    taken_at   timestamptz,
    path       text NOT NULL UNIQUE
);

ALTER TABLE profile.profile_usr_user
    ADD CONSTRAINT fk_user_avatar_photo
    FOREIGN KEY (avatar_photo_id) REFERENCES asset.asset_agg_photo (id) ON DELETE SET NULL;

-- ============================================================================
-- SCHEMA: compendium
-- ============================================================================

CREATE TABLE compendium.compendium_sub_poi_access (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    public_transport      boolean,
    public_transport_info text,
    public_transport_info_de text,
    public_transport_info_pl text,
    parking_available     boolean,
    parking_capacity      integer,
    parking_price         real,
    parking_notes         text,
    parking_notes_de      text,
    parking_notes_pl      text,
    toilet_available      boolean,
    water_available       boolean,
    access_notes          text,
    access_notes_de       text,
    access_notes_pl       text
);

CREATE TABLE compendium.compendium_cat_country (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    created_by           uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name                 text NOT NULL UNIQUE,
    name_de              text,
    name_pl              text,
    summary              text,
    summary_de           text,
    summary_pl           text,
    description          text,
    description_de       text,
    description_pl       text,
    iso_code             text NOT NULL UNIQUE,
    -- NOTE: assumed centroid; switch to geometry(MultiPolygon,4326) if you
    -- store boundaries here.
    location             geometry(Point, 4326) NOT NULL,
    name_common          text,
    name_common_de       text,
    name_common_pl       text,
    name_official        text,
    name_official_de     text,
    name_official_pl     text,
    name_native_common   text[],
    name_native_official text[],
    languages            text[],
    currencies           text[],
    capital              text,
    capital_de           text,
    capital_pl           text
);

CREATE TABLE compendium.compendium_cat_region (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name           text NOT NULL UNIQUE,
    name_de        text,
    name_pl        text,
    summary        text,
    summary_de     text,
    summary_pl     text,
    description    text,
    description_de text,
    description_pl text,
    location       geometry(Point, 4326) NOT NULL,
    country_id     uuid REFERENCES compendium.compendium_cat_country (id),
    region_type_id uuid REFERENCES core.core_ref_region_type (id),
    iso_code       text,
    parent_id      uuid REFERENCES compendium.compendium_cat_region (id),
    bbox           geometry(Polygon, 4326)
);

CREATE TABLE compendium.compendium_cat_poi (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    created_by         uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name               text NOT NULL UNIQUE,
    name_de            text,
    name_pl            text,
    summary            text,
    summary_de         text,
    summary_pl         text,
    description        text,
    description_de     text,
    description_pl     text,
    location           geometry(Point, 4326) NOT NULL,
    altitude_m         integer,
    data_source_url    text,
    compendium_type_id uuid NOT NULL REFERENCES core.core_ref_compendium_type (id),
    poi_access_id      uuid REFERENCES compendium.compendium_sub_poi_access (id),
    main_photo_id      uuid REFERENCES asset.asset_agg_photo (id),
    main_region_id     uuid NOT NULL REFERENCES compendium.compendium_cat_region (id)
);

CREATE TABLE compendium.compendium_cat_card (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    created_by         uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name               text,
    name_de            text,
    name_pl            text,
    summary            text,
    summary_de         text,
    summary_pl         text,
    description        text,
    description_de     text,
    description_pl     text,
    rarity_id          uuid REFERENCES core.core_ref_rarity (id),  -- FK was missing in v1
    compendium_type_id uuid REFERENCES core.core_ref_compendium_type (id),
    poi_id             uuid REFERENCES compendium.compendium_cat_poi (id),
    main_photo_id      uuid REFERENCES asset.asset_agg_photo (id)
);

CREATE TABLE compendium.compendium_cat_post (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name          text NOT NULL,
    name_de       text,
    name_pl       text,
    summary       text,
    summary_de    text,
    summary_pl    text,
    description   text,
    description_de text,
    description_pl text,
    main_photo_id uuid REFERENCES asset.asset_agg_photo (id),
    post_type_id  uuid NOT NULL REFERENCES core.core_ref_post_type (id)
);

CREATE TABLE compendium.compendium_m2m_poi_region (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    poi_id     uuid NOT NULL REFERENCES compendium.compendium_cat_poi (id) ON DELETE CASCADE,
    region_id  uuid NOT NULL REFERENCES compendium.compendium_cat_region (id) ON DELETE CASCADE,
    slot_position integer NOT NULL
);

-- ============================================================================
-- SCHEMA: explorer — sub tables
-- ============================================================================

CREATE TABLE explorer.explorer_sub_geo_performance (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    started_at            timestamptz,
    ended_at              timestamptz,
    total_time_s          integer,
    moving_time_s         integer,
    stop_time_s           integer,
    moving_ratio          real,
    avg_speed_kmh         real,
    moving_avg_speed_kmh  real,
    ascent_avg_speed_kmh  real,
    descent_avg_speed_kmh real,
    max_speed_kmh         real,
    max_ascent_speed_kmh  real,
    max_descent_speed_kmh real,
    avg_heart_rate        integer,
    max_heart_rate        integer,
    min_heart_rate        integer,
    calories_burned       integer,
    steps_count           integer,
    heart_graph           jsonb,
    speed_pattern         jsonb
);

CREATE TABLE explorer.explorer_sub_geo_record (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    gpx_id              uuid REFERENCES asset.asset_agg_gpx (id),
    geo_performance_id  uuid REFERENCES explorer.explorer_sub_geo_performance (id),
    geojson             jsonb,
    elevation_graph     jsonb,
    track_types         jsonb,
    elevation           integer,
    total_points        integer,
    distance_m          integer,
    elevation_gain_m    integer,
    elevation_loss_m    integer,
    highest_elevation_m integer,
    lowest_elevation_m  integer,
    avg_grade           real,
    highest_grade       real,
    start_location      geometry(Point, 4326),
    end_location        geometry(Point, 4326)
);

CREATE TABLE explorer.explorer_sub_conditions (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    temperature_avg      integer,
    temperature_min      integer,
    temperature_max      integer,
    equipment_used       jsonb,
    visibility_id        uuid REFERENCES core.core_ref_visibility (id),
    snow_condition_id    uuid REFERENCES core.core_ref_snow_condition (id),
    trail_condition_id   uuid REFERENCES core.core_ref_trail_condition (id),
    weather_condition_id uuid REFERENCES core.core_ref_weather_condition (id)
);

CREATE TABLE explorer.explorer_sub_plan_conditions (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    equipment_required jsonb,
    equipment_optional jsonb,
    permit_required    boolean,
    permit_info        text,
    permit_info_de     text,
    permit_info_pl     text,
    guide_recommended  boolean,
    min_age            integer,
    max_group_size     integer,
    best_months        integer[],
    best_months_note   text,
    best_months_note_de text,
    best_months_note_pl text
);

CREATE TABLE explorer.explorer_sub_waypoint (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    name        text,
    summary     text,
    description text,
    location    geometry(Point, 4326),
    altitude_m  integer,
    arrived_at  timestamptz,
    departed_at timestamptz,
    duration_min integer,
    poi_id      uuid REFERENCES compendium.compendium_cat_poi (id)
);

-- ============================================================================
-- SCHEMA: explorer — agg tables
-- ============================================================================

CREATE TABLE explorer.explorer_agg_gear (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public     boolean NOT NULL DEFAULT false,
    name          text NOT NULL,
    name_de       text,
    name_pl       text,
    summary       text,
    summary_de    text,
    summary_pl    text,
    description   text,
    description_de text,
    description_pl text,
    company_id    uuid NOT NULL REFERENCES core.core_ref_company (id),
    model         text,
    weight_g      integer,
    gear_type_id  uuid NOT NULL REFERENCES core.core_ref_gear_type (id),
    main_photo_id uuid REFERENCES asset.asset_agg_photo (id)
);

CREATE TABLE explorer.explorer_agg_segment (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    created_by          uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public           boolean NOT NULL DEFAULT false,
    name                text,
    name_de             text,
    name_pl             text,
    summary             text,
    summary_de          text,
    summary_pl          text,
    description         text,
    description_de      text,
    description_pl      text,
    rating_avg          real,
    rating_count          integer NOT NULL DEFAULT 0,
    sport_type_id       uuid NOT NULL REFERENCES core.core_ref_sport_type (id),
    geo_record_id       uuid NOT NULL REFERENCES explorer.explorer_sub_geo_record (id),
    main_photo_id       uuid REFERENCES asset.asset_agg_photo (id),
    start_poi_id        uuid REFERENCES compendium.compendium_cat_poi (id),
    end_poi_id          uuid REFERENCES compendium.compendium_cat_poi (id),
    difficulty_level_id uuid REFERENCES core.core_ref_difficulty_level (id),
    difficulty_sport_id uuid REFERENCES core.core_ref_difficulty_sport (id)
);

CREATE TABLE explorer.explorer_agg_route (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    created_by           uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public            boolean NOT NULL DEFAULT false,
    name                 text NOT NULL,
    name_de              text,
    name_pl              text,
    summary              text,
    summary_de           text,
    summary_pl           text,
    description          text,
    description_de       text,
    description_pl       text,
    rating_avg           real,
    rating_count           integer NOT NULL DEFAULT 0,
    agg_distance_m       integer,
    agg_elevation_gain_m integer,
    agg_elevation_loss_m integer,
    agg_highest_point_m  integer,
    agg_lowest_point_m   integer,
    agg_duration_s       integer,
    plan_condition_id    uuid REFERENCES explorer.explorer_sub_plan_conditions (id),
    sport_type_id        uuid NOT NULL REFERENCES core.core_ref_sport_type (id),
    difficulty_level_id  uuid NOT NULL REFERENCES core.core_ref_difficulty_level (id),
    difficulty_sport_id  uuid NOT NULL REFERENCES core.core_ref_difficulty_sport (id)
);

CREATE TABLE explorer.explorer_agg_journey (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    created_by           uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public            boolean NOT NULL DEFAULT false,
    name                 text NOT NULL,
    name_de              text,
    name_pl              text,
    summary              text,
    summary_de           text,
    summary_pl           text,
    description          text,
    description_de       text,
    description_pl       text,
    rating_avg           real,
    rating_count           integer NOT NULL DEFAULT 0,
    length_days          integer,
    agg_distance_m       integer,
    agg_elevation_gain_m integer,
    agg_elevation_loss_m integer,
    agg_highest_point_m  integer,
    agg_lowest_point_m   integer,
    agg_duration_s       integer,
    difficulty_level_id  uuid REFERENCES core.core_ref_difficulty_level (id),
    difficulty_sport_id  uuid REFERENCES core.core_ref_difficulty_sport (id),
    sport_type_id        uuid REFERENCES core.core_ref_sport_type (id),
    -- NOTE: journey is a *planned* entity, so this points at plan_conditions.
    -- Change to explorer_sub_conditions if that was the intent in v1.
    condition_id         uuid REFERENCES explorer.explorer_sub_plan_conditions (id)
);

CREATE TABLE explorer.explorer_agg_track (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    created_by          uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public           boolean NOT NULL DEFAULT false,
    name                text NOT NULL,
    name_de             text,
    name_pl             text,
    summary             text,
    summary_de          text,
    summary_pl          text,
    description         text,
    description_de      text,
    description_pl      text,
    recorded_at         timestamptz,
    sport_type_id       uuid REFERENCES core.core_ref_sport_type (id),
    difficulty_level_id uuid REFERENCES core.core_ref_difficulty_level (id),
    difficulty_sport_id uuid REFERENCES core.core_ref_difficulty_sport (id),
    main_photo_id       uuid REFERENCES asset.asset_agg_photo (id),
    geo_record_id       uuid REFERENCES explorer.explorer_sub_geo_record (id),
    condition_id        uuid REFERENCES explorer.explorer_sub_conditions (id),
    start_poi_id        uuid REFERENCES compendium.compendium_cat_poi (id),
    end_poi_id          uuid REFERENCES compendium.compendium_cat_poi (id)
);

CREATE TABLE explorer.explorer_agg_trip (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    is_public     boolean NOT NULL DEFAULT false,
    name          text NOT NULL,
    name_de       text,
    name_pl       text,
    summary       text,
    summary_de    text,
    summary_pl    text,
    description   text,
    description_de text,
    description_pl text,
    length_days   integer,
    first_day     date,
    last_day      date,
    sport_type_id uuid REFERENCES core.core_ref_sport_type (id)
);

-- ============================================================================
-- SCHEMA: explorer — m2m tables
-- ============================================================================

CREATE TABLE explorer.explorer_m2m_route_journey (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position      integer NOT NULL,
    route_id        uuid NOT NULL REFERENCES explorer.explorer_agg_route (id) ON DELETE CASCADE,
    journey_id      uuid NOT NULL REFERENCES explorer.explorer_agg_journey (id) ON DELETE CASCADE,
    poi_id          uuid REFERENCES compendium.compendium_cat_poi (id),
    day_name        text NOT NULL,
    day_summary     text,
    day_description text
);

CREATE TABLE explorer.explorer_m2m_segment_photo (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position integer NOT NULL,
    segment_id uuid NOT NULL REFERENCES explorer.explorer_agg_segment (id) ON DELETE CASCADE,
    photo_id   uuid NOT NULL REFERENCES asset.asset_agg_photo (id) ON DELETE CASCADE,
    summary    text
);

CREATE TABLE explorer.explorer_m2m_segment_poi (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position integer NOT NULL,
    segment_id uuid NOT NULL REFERENCES explorer.explorer_agg_segment (id) ON DELETE CASCADE,
    poi_id     uuid NOT NULL REFERENCES compendium.compendium_cat_poi (id) ON DELETE CASCADE,
    distance_m integer
);

CREATE TABLE explorer.explorer_m2m_segment_route (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    segment_id    uuid NOT NULL REFERENCES explorer.explorer_agg_segment (id) ON DELETE CASCADE,
    route_id      uuid NOT NULL REFERENCES explorer.explorer_agg_route (id) ON DELETE CASCADE,
    -- v1 had both "order" and "position"; merged into a single slot_position.
    slot_position integer NOT NULL,
    alt_group     integer NOT NULL,
    is_default    boolean NOT NULL,
    is_reversed   boolean NOT NULL
);

CREATE TABLE explorer.explorer_m2m_track_gear (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),  -- was bigint in v1
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),                               -- was missing in v1
    slot_position integer NOT NULL,
    track_id   uuid NOT NULL REFERENCES explorer.explorer_agg_track (id) ON DELETE CASCADE,
    gear_id    uuid NOT NULL REFERENCES explorer.explorer_agg_gear (id) ON DELETE CASCADE,
    notes      text,
    points     integer
);

CREATE TABLE explorer.explorer_m2m_track_photo (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position integer NOT NULL,
    track_id   uuid NOT NULL REFERENCES explorer.explorer_agg_track (id) ON DELETE CASCADE,
    photo_id   uuid NOT NULL REFERENCES asset.asset_agg_photo (id) ON DELETE CASCADE
);

CREATE TABLE explorer.explorer_m2m_track_poi (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    created_by uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position integer NOT NULL,
    track_id   uuid NOT NULL REFERENCES explorer.explorer_agg_track (id) ON DELETE CASCADE,
    poi_id     uuid NOT NULL REFERENCES compendium.compendium_cat_poi (id) ON DELETE CASCADE,
    distance_m integer
);

CREATE TABLE explorer.explorer_m2m_track_trip (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position      integer NOT NULL,
    track_id        uuid NOT NULL REFERENCES explorer.explorer_agg_track (id) ON DELETE CASCADE,
    trip_id         uuid NOT NULL REFERENCES explorer.explorer_agg_trip (id) ON DELETE CASCADE,
    waypoint_id     uuid REFERENCES explorer.explorer_sub_waypoint (id),
    day_name        text NOT NULL,
    day_summary     text,
    day_description text
);

CREATE TABLE explorer.explorer_m2m_track_waypoint (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    slot_position  integer NOT NULL,
    track_id    uuid NOT NULL REFERENCES explorer.explorer_agg_track (id) ON DELETE CASCADE,
    waypoint_id uuid NOT NULL REFERENCES explorer.explorer_sub_waypoint (id) ON DELETE CASCADE
);


-- ============================================================================
-- SCHEMA: profile — pace curve (personal speed-vs-gradient profile)
-- user_id: FK to profile user table will be added when profile lands.
-- ============================================================================

CREATE TABLE profile.profile_sub_pace_curve (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    user_id       uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    sport_type_id uuid NOT NULL REFERENCES core.core_ref_sport_type (id),
    gradient_bin  integer NOT NULL,   -- lower bound of 2%-wide bin, e.g. -10 = [-10%,-8%)
    speed_kmh     real NOT NULL,
    sample_points integer NOT NULL,   -- confidence weight for prior blending
    UNIQUE (user_id, sport_type_id, gradient_bin)
);

-- ============================================================================
-- SCHEMA: explorer — route time prediction (closes the plan->record loop)
-- ============================================================================

CREATE TABLE explorer.explorer_sub_prediction (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    created_by         uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    route_id           uuid NOT NULL REFERENCES explorer.explorer_agg_route (id) ON DELETE CASCADE,
    predicted_s        integer NOT NULL,
    predicted_moving_s integer,
    model_version      integer NOT NULL,
    inputs             jsonb,          -- pack weight, conditions, blend weights used
    track_id           uuid REFERENCES explorer.explorer_agg_track (id) ON DELETE SET NULL
);


-- ============================================================================
-- SCHEMA: profile — body metrics, achievements, points, schedule, statistics
-- ============================================================================

CREATE TABLE profile.profile_sub_body_metric (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    user_id     uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    recorded_at date NOT NULL,
    weight_kg   real NOT NULL,
    UNIQUE (user_id, recorded_at)
);

CREATE TABLE profile.profile_cat_achievement (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    created_by        uuid NOT NULL REFERENCES profile.profile_usr_user (id),
    name              text NOT NULL UNIQUE,
    name_de           text,
    name_pl           text,
    summary           text,
    summary_de        text,
    summary_pl        text,
    description       text,
    description_de    text,
    description_pl    text,
    point_factor      real NOT NULL,
    criteria          jsonb,   -- machine-readable, e.g. {"metric":"total_distance_m","threshold":1000000}
    is_active         boolean NOT NULL DEFAULT true,
    is_repeatable     boolean NOT NULL DEFAULT false,
    rarity_id         uuid NOT NULL REFERENCES core.core_ref_rarity (id),
    category_id       uuid NOT NULL REFERENCES core.core_ref_achievement_category (id),
    criteria_scope_id uuid NOT NULL REFERENCES core.core_ref_achievement_scope (id),
    criteria_type_id  uuid NOT NULL REFERENCES core.core_ref_achievement_type (id)
);

CREATE TABLE profile.profile_m2m_user_achievement (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    user_id        uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    achievement_id uuid NOT NULL REFERENCES profile.profile_cat_achievement (id),
    collected_at   timestamptz NOT NULL,
    comment        text,
    is_repeat      boolean NOT NULL DEFAULT false,  -- copied from achievement at grant time
    track_id       uuid REFERENCES explorer.explorer_agg_track (id) ON DELETE SET NULL,
    trip_id        uuid REFERENCES explorer.explorer_agg_trip (id) ON DELETE SET NULL
);

-- one-time achievements cannot be granted twice; repeatable ones can
CREATE UNIQUE INDEX uniq_onetime_achievement
    ON profile.profile_m2m_user_achievement (user_id, achievement_id)
    WHERE NOT is_repeat;

-- immutable points ledger (no updated_at on purpose)
CREATE TABLE profile.profile_sub_point (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    user_id             uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    received_at         date NOT NULL,
    points              integer NOT NULL,   -- awarded value, stored (factors may change later)
    reason_id           uuid NOT NULL REFERENCES core.core_ref_point_reason (id),
    user_achievement_id uuid REFERENCES profile.profile_m2m_user_achievement (id) ON DELETE SET NULL,
    track_id            uuid REFERENCES explorer.explorer_agg_track (id) ON DELETE SET NULL,
    trip_id             uuid REFERENCES explorer.explorer_agg_trip (id) ON DELETE SET NULL
);

CREATE TABLE profile.profile_sub_schedule (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    user_id      uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    route_id     uuid REFERENCES explorer.explorer_agg_route (id) ON DELETE SET NULL,
    journey_id   uuid REFERENCES explorer.explorer_agg_journey (id) ON DELETE SET NULL,
    track_id     uuid REFERENCES explorer.explorer_agg_track (id) ON DELETE SET NULL,
    trip_id      uuid REFERENCES explorer.explorer_agg_trip (id) ON DELETE SET NULL,
    planned_at   timestamptz NOT NULL,
    completed_at timestamptz,
    status_id    uuid NOT NULL REFERENCES core.core_ref_schedule_status (id),
    notes        text,
    CHECK (route_id IS NOT NULL OR journey_id IS NOT NULL)
);

-- materialized per-user statistics cache (recomputed by the Go worker)
CREATE TABLE profile.profile_sub_statistic (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    user_id                uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    scope                  text NOT NULL CHECK (scope IN ('all', 'year', 'month')),
    scope_year             integer,
    scope_month            integer,
    total_distance_m       bigint NOT NULL DEFAULT 0,
    total_distance_graph   jsonb,
    total_elevation_m      bigint NOT NULL DEFAULT 0,
    total_elevation_graph  jsonb,
    total_activities       integer NOT NULL DEFAULT 0,
    total_activities_graph jsonb,
    total_time_s           bigint NOT NULL DEFAULT 0,
    total_time_graph       jsonb,
    total_plans_created    integer NOT NULL DEFAULT 0,
    total_plans_completed  integer NOT NULL DEFAULT 0,
    total_plans_skipped    integer NOT NULL DEFAULT 0,
    current_streak_days    integer NOT NULL DEFAULT 0,
    longest_streak_days    integer NOT NULL DEFAULT 0,
    total_points           bigint NOT NULL DEFAULT 0,
    unique_pois_count      integer NOT NULL DEFAULT 0,
    unique_regions_count   integer NOT NULL DEFAULT 0,
    UNIQUE NULLS NOT DISTINCT (user_id, scope, scope_year, scope_month)
);

-- ============================================================================
-- SCHEMA: profile — collections & likes
-- ============================================================================

CREATE TABLE profile.profile_m2m_user_card (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    user_id      uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    card_id      uuid NOT NULL REFERENCES compendium.compendium_cat_card (id) ON DELETE CASCADE,
    collected_at timestamptz NOT NULL,
    comment      text,
    track_id     uuid REFERENCES explorer.explorer_agg_track (id) ON DELETE SET NULL,
    UNIQUE (user_id, card_id)
);

CREATE TABLE profile.profile_m2m_user_poi (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    user_id      uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    poi_id       uuid NOT NULL REFERENCES compendium.compendium_cat_poi (id) ON DELETE CASCADE,
    collected_at timestamptz NOT NULL,
    comment      text,
    track_id     uuid REFERENCES explorer.explorer_agg_track (id) ON DELETE SET NULL,
    UNIQUE (user_id, poi_id)   -- first visit; repeat visits derivable from tracks
);

CREATE TABLE profile.profile_m2m_liked_route (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    user_id    uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    route_id   uuid NOT NULL REFERENCES explorer.explorer_agg_route (id) ON DELETE CASCADE,
    UNIQUE (user_id, route_id)
);

CREATE TABLE profile.profile_m2m_liked_journey (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at timestamptz NOT NULL DEFAULT now(),
    user_id    uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    journey_id uuid NOT NULL REFERENCES explorer.explorer_agg_journey (id) ON DELETE CASCADE,
    UNIQUE (user_id, journey_id)
);

-- ============================================================================
-- SCHEMA: social — follows, comments, ratings
-- ============================================================================

CREATE TABLE social.social_m2m_follow (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    follower_id  uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    following_id uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    UNIQUE (follower_id, following_id),
    CHECK (follower_id <> following_id)
);

-- polymorphic target: no FK possible on entity_id; integrity enforced in Go
CREATE TABLE social.social_sub_comment (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    user_id     uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    entity_type text NOT NULL CHECK (entity_type IN ('route', 'journey', 'segment', 'track', 'trip', 'post')),
    entity_id   uuid NOT NULL,
    comment     text NOT NULL,
    parent_id   uuid REFERENCES social.social_sub_comment (id) ON DELETE CASCADE
);

CREATE TABLE social.social_sub_rating (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    user_id     uuid NOT NULL REFERENCES profile.profile_usr_user (id) ON DELETE CASCADE,
    entity_type text NOT NULL CHECK (entity_type IN ('route', 'journey', 'segment')),
    entity_id   uuid NOT NULL,
    score       integer NOT NULL CHECK (score BETWEEN 1 AND 5),
    UNIQUE (user_id, entity_type, entity_id)
);

-- ============================================================================
-- INDEXES
-- Postgres does not create indexes on FK columns automatically.
-- ============================================================================

CREATE INDEX idx_pace_curve_user       ON profile.profile_sub_pace_curve (user_id, sport_type_id);
CREATE INDEX idx_prediction_route      ON explorer.explorer_sub_prediction (route_id);
CREATE INDEX idx_prediction_created_by ON explorer.explorer_sub_prediction (created_by);
CREATE INDEX idx_prediction_track      ON explorer.explorer_sub_prediction (track_id);

CREATE INDEX idx_body_metric_user      ON profile.profile_sub_body_metric (user_id, recorded_at);
CREATE INDEX idx_user_achievement_user ON profile.profile_m2m_user_achievement (user_id);
CREATE INDEX idx_user_achievement_ach  ON profile.profile_m2m_user_achievement (achievement_id);
CREATE INDEX idx_point_user            ON profile.profile_sub_point (user_id, received_at);
CREATE INDEX idx_schedule_user         ON profile.profile_sub_schedule (user_id, planned_at);
CREATE INDEX idx_user_card_user        ON profile.profile_m2m_user_card (user_id);
CREATE INDEX idx_user_poi_user         ON profile.profile_m2m_user_poi (user_id);
CREATE INDEX idx_follow_following      ON social.social_m2m_follow (following_id);
CREATE INDEX idx_comment_entity        ON social.social_sub_comment (entity_type, entity_id);
CREATE INDEX idx_comment_parent        ON social.social_sub_comment (parent_id);
CREATE INDEX idx_rating_entity         ON social.social_sub_rating (entity_type, entity_id);

-- geometry (GIST)
CREATE INDEX idx_user_home_location    ON profile.profile_usr_user           USING gist (home_location);
CREATE INDEX idx_photo_location        ON asset.asset_agg_photo               USING gist (location);
CREATE INDEX idx_country_location      ON compendium.compendium_cat_country   USING gist (location);
CREATE INDEX idx_region_location       ON compendium.compendium_cat_region    USING gist (location);
CREATE INDEX idx_region_bbox           ON compendium.compendium_cat_region    USING gist (bbox);
CREATE INDEX idx_poi_location          ON compendium.compendium_cat_poi       USING gist (location);
CREATE INDEX idx_waypoint_location     ON explorer.explorer_sub_waypoint      USING gist (location);
CREATE INDEX idx_geo_record_start      ON explorer.explorer_sub_geo_record    USING gist (start_location);
CREATE INDEX idx_geo_record_end        ON explorer.explorer_sub_geo_record    USING gist (end_location);

-- ownership (RLS / per-user queries)
CREATE INDEX idx_gpx_created_by        ON asset.asset_agg_gpx      (created_by);
CREATE INDEX idx_photo_created_by      ON asset.asset_agg_photo    (created_by);
CREATE INDEX idx_gear_created_by       ON explorer.explorer_agg_gear    (created_by);
CREATE INDEX idx_segment_created_by    ON explorer.explorer_agg_segment (created_by);
CREATE INDEX idx_route_created_by      ON explorer.explorer_agg_route   (created_by);
CREATE INDEX idx_journey_created_by    ON explorer.explorer_agg_journey (created_by);
CREATE INDEX idx_track_created_by      ON explorer.explorer_agg_track   (created_by);
CREATE INDEX idx_trip_created_by       ON explorer.explorer_agg_trip    (created_by);

-- compendium FKs
CREATE INDEX idx_region_country        ON compendium.compendium_cat_region  (country_id);
CREATE INDEX idx_region_parent         ON compendium.compendium_cat_region  (parent_id);
CREATE INDEX idx_poi_type              ON compendium.compendium_cat_poi     (compendium_type_id);
CREATE INDEX idx_poi_main_region       ON compendium.compendium_cat_poi     (main_region_id);
CREATE INDEX idx_card_poi              ON compendium.compendium_cat_card    (poi_id);
CREATE INDEX idx_m2m_poi_region_poi    ON compendium.compendium_m2m_poi_region (poi_id);
CREATE INDEX idx_m2m_poi_region_region ON compendium.compendium_m2m_poi_region (region_id);

-- explorer FKs
CREATE INDEX idx_segment_geo_record    ON explorer.explorer_agg_segment (geo_record_id);
CREATE INDEX idx_track_geo_record      ON explorer.explorer_agg_track   (geo_record_id);
CREATE INDEX idx_geo_record_gpx        ON explorer.explorer_sub_geo_record (gpx_id);
CREATE INDEX idx_m2m_rj_route          ON explorer.explorer_m2m_route_journey (route_id);
CREATE INDEX idx_m2m_rj_journey        ON explorer.explorer_m2m_route_journey (journey_id);
CREATE INDEX idx_m2m_sp_segment        ON explorer.explorer_m2m_segment_photo (segment_id);
CREATE INDEX idx_m2m_sp_photo          ON explorer.explorer_m2m_segment_photo (photo_id);
CREATE INDEX idx_m2m_spoi_segment      ON explorer.explorer_m2m_segment_poi (segment_id);
CREATE INDEX idx_m2m_spoi_poi          ON explorer.explorer_m2m_segment_poi (poi_id);
CREATE INDEX idx_m2m_sr_segment        ON explorer.explorer_m2m_segment_route (segment_id);
CREATE INDEX idx_m2m_sr_route          ON explorer.explorer_m2m_segment_route (route_id);
CREATE INDEX idx_m2m_tg_track          ON explorer.explorer_m2m_track_gear (track_id);
CREATE INDEX idx_m2m_tg_gear           ON explorer.explorer_m2m_track_gear (gear_id);
CREATE INDEX idx_m2m_tph_track         ON explorer.explorer_m2m_track_photo (track_id);
CREATE INDEX idx_m2m_tph_photo         ON explorer.explorer_m2m_track_photo (photo_id);
CREATE INDEX idx_m2m_tpoi_track        ON explorer.explorer_m2m_track_poi (track_id);
CREATE INDEX idx_m2m_tpoi_poi          ON explorer.explorer_m2m_track_poi (poi_id);
CREATE INDEX idx_m2m_tt_track          ON explorer.explorer_m2m_track_trip (track_id);
CREATE INDEX idx_m2m_tt_trip           ON explorer.explorer_m2m_track_trip (trip_id);
CREATE INDEX idx_m2m_tw_track          ON explorer.explorer_m2m_track_waypoint (track_id);
CREATE INDEX idx_m2m_tw_waypoint       ON explorer.explorer_m2m_track_waypoint (waypoint_id);

-- ============================================================================
-- updated_at TRIGGERS (moddatetime) — auto-attached to every table that has
-- an updated_at column in the four app schemas.
-- ============================================================================

DO $$
DECLARE
    t record;
BEGIN
    FOR t IN
        SELECT table_schema, table_name
        FROM information_schema.columns
        WHERE column_name = 'updated_at'
          AND table_schema IN ('asset', 'compendium', 'core', 'explorer', 'profile', 'social')
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_set_updated_at
                 BEFORE UPDATE ON %I.%I
                 FOR EACH ROW
                 EXECUTE FUNCTION moddatetime(updated_at);',
            t.table_schema, t.table_name
        );
    END LOOP;
END $$;
