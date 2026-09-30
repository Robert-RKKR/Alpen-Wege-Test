-- ============================================================================
-- alpenwege — full schema (generated from live catalog)
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS fuzzystrmatch;
CREATE EXTENSION IF NOT EXISTS moddatetime;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_tiger_geocoder;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- ============================================================================
-- profile
-- ============================================================================

CREATE TABLE profile_usr_user (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    email               text NOT NULL UNIQUE,
    username            text UNIQUE,
    first_name          text,
    middle_name         text,
    last_name           text,
    gender              text,
    birth_date          date,
    height_cm           integer,
    max_heart_rate      integer,
    resting_heart_rate  integer,
    home_location       geometry(Point, 4326),
    is_active           boolean NOT NULL DEFAULT true,
    last_active_at      timestamptz,
    avatar_photo_id     uuid,
    CHECK ((gender = ANY (ARRAY['male'::text, 'female'::text, 'not_specified'::text])))
);

-- ============================================================================
-- core
-- ============================================================================

CREATE TABLE core_ref_achievement_category (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_achievement_scope (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_achievement_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_company (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  numeric
);

CREATE TABLE core_ref_compendium_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_difficulty_level (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_gear_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  numeric
);

CREATE TABLE core_ref_point_reason (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_post_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_rarity (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_region_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_schedule_status (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_snow_condition (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_sport_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL,
    CHECK ((color ~ '^#[0-9a-fA-F]{6}$'::text))
);

CREATE TABLE core_ref_difficulty_sport (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    name           text UNIQUE,
    name_de        text,
    name_pl        text,
    color          text NOT NULL,
    icon           text NOT NULL,
    point_factor   real NOT NULL,
    sport_type_id  uuid REFERENCES core_ref_sport_type (id)
);

CREATE TABLE core_ref_trail_condition (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_visibility (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_waypoint_type (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

CREATE TABLE core_ref_weather_condition (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    created_by    uuid NOT NULL REFERENCES profile_usr_user (id),
    name          text UNIQUE,
    name_de       text,
    name_pl       text,
    color         text NOT NULL,
    icon          text NOT NULL,
    point_factor  real NOT NULL
);

-- ============================================================================
-- asset
-- ============================================================================

CREATE TABLE asset_agg_gpx (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public   boolean NOT NULL DEFAULT false,
    name        text,
    name_de     text,
    name_pl     text,
    summary     text,
    summary_de  text,
    summary_pl  text,
    path        text NOT NULL UNIQUE
);

CREATE TABLE asset_agg_photo (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    created_by  uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public   boolean NOT NULL DEFAULT false,
    name        text,
    name_de     text,
    name_pl     text,
    summary     text,
    summary_de  text,
    summary_pl  text,
    location    geometry(Point, 4326),
    altitude_m  integer,
    taken_at    timestamptz,
    path        text NOT NULL UNIQUE
);

-- ============================================================================
-- compendium
-- ============================================================================

CREATE TABLE compendium_cat_country (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    created_by            uuid NOT NULL REFERENCES profile_usr_user (id),
    name                  text UNIQUE,
    name_de               text,
    name_pl               text,
    summary               text,
    summary_de            text,
    summary_pl            text,
    description           text,
    description_de        text,
    description_pl        text,
    iso_code              text NOT NULL UNIQUE,
    location              geometry(Point, 4326) NOT NULL,
    name_common           text,
    name_common_de        text,
    name_common_pl        text,
    name_official         text,
    name_official_de      text,
    name_official_pl      text,
    name_native_common    text[],
    name_native_official  text[],
    languages             text[],
    currencies            text[],
    capital               text,
    capital_de            text,
    capital_pl            text
);

CREATE TABLE compendium_cat_post (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid NOT NULL REFERENCES profile_usr_user (id),
    name            text,
    name_de         text,
    name_pl         text,
    summary         text,
    summary_de      text,
    summary_pl      text,
    description     text,
    description_de  text,
    description_pl  text,
    main_photo_id   uuid REFERENCES asset_agg_photo (id),
    post_type_id    uuid NOT NULL REFERENCES core_ref_post_type (id)
);

CREATE TABLE compendium_cat_region (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid NOT NULL REFERENCES profile_usr_user (id),
    name            text UNIQUE,
    name_de         text,
    name_pl         text,
    summary         text,
    summary_de      text,
    summary_pl      text,
    description     text,
    description_de  text,
    description_pl  text,
    location        geometry(Point, 4326) NOT NULL,
    country_id      uuid REFERENCES compendium_cat_country (id),
    region_type_id  uuid REFERENCES core_ref_region_type (id),
    iso_code        text,
    parent_id       uuid REFERENCES compendium_cat_region (id),
    bbox            geometry(Polygon, 4326)
);

CREATE TABLE compendium_sub_poi_access (
    id                        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at                timestamptz NOT NULL DEFAULT now(),
    updated_at                timestamptz NOT NULL DEFAULT now(),
    public_transport          boolean,
    public_transport_info     text,
    public_transport_info_de  text,
    public_transport_info_pl  text,
    parking_available         boolean,
    parking_capacity          integer,
    parking_price             real,
    parking_notes             text,
    parking_notes_de          text,
    parking_notes_pl          text,
    toilet_available          boolean,
    water_available           boolean,
    access_notes              text,
    access_notes_de           text,
    access_notes_pl           text
);

CREATE TABLE compendium_cat_poi (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    created_by          uuid NOT NULL REFERENCES profile_usr_user (id),
    name                text UNIQUE,
    name_de             text,
    name_pl             text,
    summary             text,
    summary_de          text,
    summary_pl          text,
    description         text,
    description_de      text,
    description_pl      text,
    location            geometry(Point, 4326) NOT NULL,
    altitude_m          integer,
    data_source_url     text,
    compendium_type_id  uuid NOT NULL REFERENCES core_ref_compendium_type (id),
    poi_access_id       uuid REFERENCES compendium_sub_poi_access (id),
    main_photo_id       uuid REFERENCES asset_agg_photo (id),
    main_region_id      uuid NOT NULL REFERENCES compendium_cat_region (id)
);

CREATE TABLE compendium_cat_card (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    created_by          uuid NOT NULL REFERENCES profile_usr_user (id),
    name                text,
    name_de             text,
    name_pl             text,
    summary             text,
    summary_de          text,
    summary_pl          text,
    description         text,
    description_de      text,
    description_pl      text,
    rarity_id           uuid REFERENCES core_ref_rarity (id),
    compendium_type_id  uuid REFERENCES core_ref_compendium_type (id),
    poi_id              uuid REFERENCES compendium_cat_poi (id),
    main_photo_id       uuid REFERENCES asset_agg_photo (id)
);

CREATE TABLE compendium_m2m_poi_region (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    poi_id         uuid NOT NULL REFERENCES compendium_cat_poi (id) ON DELETE CASCADE,
    region_id      uuid NOT NULL REFERENCES compendium_cat_region (id) ON DELETE CASCADE,
    slot_position  integer NOT NULL
);

-- ============================================================================
-- explorer
-- ============================================================================

CREATE TABLE explorer_sub_conditions (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    temperature_avg       integer,
    temperature_min       integer,
    temperature_max       integer,
    equipment_used        jsonb,
    visibility_id         uuid REFERENCES core_ref_visibility (id),
    snow_condition_id     uuid REFERENCES core_ref_snow_condition (id),
    trail_condition_id    uuid REFERENCES core_ref_trail_condition (id),
    weather_condition_id  uuid REFERENCES core_ref_weather_condition (id)
);

CREATE TABLE explorer_sub_geo_performance (
    id                     uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at             timestamptz NOT NULL DEFAULT now(),
    updated_at             timestamptz NOT NULL DEFAULT now(),
    started_at             timestamptz,
    ended_at               timestamptz,
    total_time_s           integer,
    moving_time_s          integer,
    stop_time_s            integer,
    moving_ratio           real,
    avg_speed_kmh          real,
    moving_avg_speed_kmh   real,
    ascent_avg_speed_kmh   real,
    descent_avg_speed_kmh  real,
    max_speed_kmh          real,
    max_ascent_speed_kmh   real,
    max_descent_speed_kmh  real,
    avg_heart_rate         integer,
    max_heart_rate         integer,
    min_heart_rate         integer,
    calories_burned        integer,
    steps_count            integer,
    heart_graph            jsonb,
    speed_pattern          jsonb
);

CREATE TABLE explorer_sub_geo_record (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    gpx_id               uuid REFERENCES asset_agg_gpx (id),
    geo_performance_id   uuid REFERENCES explorer_sub_geo_performance (id),
    geojson              jsonb,
    elevation_graph      jsonb,
    track_types          jsonb,
    elevation            integer,
    total_points         integer,
    distance_m           integer,
    elevation_gain_m     integer,
    elevation_loss_m     integer,
    highest_elevation_m  integer,
    lowest_elevation_m   integer,
    avg_grade            real,
    highest_grade        real,
    start_location       geometry(Point, 4326),
    end_location         geometry(Point, 4326)
);

CREATE TABLE explorer_sub_plan_conditions (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    equipment_required   jsonb,
    equipment_optional   jsonb,
    permit_required      boolean,
    permit_info          text,
    permit_info_de       text,
    permit_info_pl       text,
    guide_recommended    boolean,
    min_age              integer,
    max_group_size       integer,
    best_months          integer[],
    best_months_note     text,
    best_months_note_de  text,
    best_months_note_pl  text
);

CREATE TABLE explorer_sub_waypoint (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    name          text,
    summary       text,
    description   text,
    location      geometry(Point, 4326),
    altitude_m    integer,
    arrived_at    timestamptz,
    departed_at   timestamptz,
    duration_min  integer,
    poi_id        uuid REFERENCES compendium_cat_poi (id)
);

CREATE TABLE explorer_agg_gear (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public       boolean NOT NULL DEFAULT false,
    name            text,
    name_de         text,
    name_pl         text,
    summary         text,
    summary_de      text,
    summary_pl      text,
    description     text,
    description_de  text,
    description_pl  text,
    company_id      uuid NOT NULL REFERENCES core_ref_company (id),
    model           text,
    weight_g        integer,
    gear_type_id    uuid NOT NULL REFERENCES core_ref_gear_type (id),
    main_photo_id   uuid REFERENCES asset_agg_photo (id)
);

CREATE TABLE explorer_agg_journey (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    created_by            uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public             boolean NOT NULL DEFAULT false,
    name                  text,
    name_de               text,
    name_pl               text,
    summary               text,
    summary_de            text,
    summary_pl            text,
    description           text,
    description_de        text,
    description_pl        text,
    rating_avg            real,
    rating_count          integer NOT NULL DEFAULT 0,
    length_days           integer,
    agg_distance_m        integer,
    agg_elevation_gain_m  integer,
    agg_elevation_loss_m  integer,
    agg_highest_point_m   integer,
    agg_lowest_point_m    integer,
    agg_duration_s        integer,
    difficulty_level_id   uuid REFERENCES core_ref_difficulty_level (id),
    difficulty_sport_id   uuid REFERENCES core_ref_difficulty_sport (id),
    sport_type_id         uuid REFERENCES core_ref_sport_type (id),
    condition_id          uuid REFERENCES explorer_sub_plan_conditions (id)
);

CREATE TABLE explorer_agg_route (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now(),
    created_by            uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public             boolean NOT NULL DEFAULT false,
    name                  text,
    name_de               text,
    name_pl               text,
    summary               text,
    summary_de            text,
    summary_pl            text,
    description           text,
    description_de        text,
    description_pl        text,
    rating_avg            real,
    rating_count          integer NOT NULL DEFAULT 0,
    agg_distance_m        integer,
    agg_elevation_gain_m  integer,
    agg_elevation_loss_m  integer,
    agg_highest_point_m   integer,
    agg_lowest_point_m    integer,
    agg_duration_s        integer,
    plan_condition_id     uuid REFERENCES explorer_sub_plan_conditions (id),
    sport_type_id         uuid NOT NULL REFERENCES core_ref_sport_type (id),
    difficulty_level_id   uuid NOT NULL REFERENCES core_ref_difficulty_level (id),
    difficulty_sport_id   uuid NOT NULL REFERENCES core_ref_difficulty_sport (id)
);

CREATE TABLE explorer_agg_segment (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    created_by           uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public            boolean NOT NULL DEFAULT false,
    name                 text,
    name_de              text,
    name_pl              text,
    summary              text,
    summary_de           text,
    summary_pl           text,
    description          text,
    description_de       text,
    description_pl       text,
    rating_avg           real,
    rating_count         integer NOT NULL DEFAULT 0,
    sport_type_id        uuid NOT NULL REFERENCES core_ref_sport_type (id),
    geo_record_id        uuid NOT NULL REFERENCES explorer_sub_geo_record (id),
    main_photo_id        uuid REFERENCES asset_agg_photo (id),
    start_poi_id         uuid REFERENCES compendium_cat_poi (id),
    end_poi_id           uuid REFERENCES compendium_cat_poi (id),
    difficulty_level_id  uuid REFERENCES core_ref_difficulty_level (id),
    difficulty_sport_id  uuid REFERENCES core_ref_difficulty_sport (id)
);

CREATE TABLE explorer_agg_track (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    updated_at           timestamptz NOT NULL DEFAULT now(),
    created_by           uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public            boolean NOT NULL DEFAULT false,
    name                 text,
    name_de              text,
    name_pl              text,
    summary              text,
    summary_de           text,
    summary_pl           text,
    description          text,
    description_de       text,
    description_pl       text,
    recorded_at          timestamptz,
    sport_type_id        uuid REFERENCES core_ref_sport_type (id),
    difficulty_level_id  uuid REFERENCES core_ref_difficulty_level (id),
    difficulty_sport_id  uuid REFERENCES core_ref_difficulty_sport (id),
    main_photo_id        uuid REFERENCES asset_agg_photo (id),
    geo_record_id        uuid REFERENCES explorer_sub_geo_record (id),
    condition_id         uuid REFERENCES explorer_sub_conditions (id),
    start_poi_id         uuid REFERENCES compendium_cat_poi (id),
    end_poi_id           uuid REFERENCES compendium_cat_poi (id)
);

CREATE TABLE explorer_sub_prediction (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at          timestamptz NOT NULL DEFAULT now(),
    updated_at          timestamptz NOT NULL DEFAULT now(),
    created_by          uuid NOT NULL REFERENCES profile_usr_user (id),
    route_id            uuid NOT NULL REFERENCES explorer_agg_route (id) ON DELETE CASCADE,
    predicted_s         integer NOT NULL,
    predicted_moving_s  integer,
    model_version       integer NOT NULL,
    inputs              jsonb,
    track_id            uuid REFERENCES explorer_agg_track (id) ON DELETE SET NULL
);

CREATE TABLE explorer_agg_trip (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    created_by      uuid NOT NULL REFERENCES profile_usr_user (id),
    is_public       boolean NOT NULL DEFAULT false,
    name            text,
    name_de         text,
    name_pl         text,
    summary         text,
    summary_de      text,
    summary_pl      text,
    description     text,
    description_de  text,
    description_pl  text,
    length_days     integer,
    first_day       date,
    last_day        date,
    sport_type_id   uuid REFERENCES core_ref_sport_type (id)
);

CREATE TABLE explorer_m2m_route_journey (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    created_by       uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position    integer NOT NULL,
    route_id         uuid NOT NULL REFERENCES explorer_agg_route (id) ON DELETE CASCADE,
    journey_id       uuid NOT NULL REFERENCES explorer_agg_journey (id) ON DELETE CASCADE,
    poi_id           uuid REFERENCES compendium_cat_poi (id),
    day_name         text NOT NULL,
    day_summary      text,
    day_description  text
);

CREATE TABLE explorer_m2m_segment_photo (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position  integer NOT NULL,
    segment_id     uuid NOT NULL REFERENCES explorer_agg_segment (id) ON DELETE CASCADE,
    photo_id       uuid NOT NULL REFERENCES asset_agg_photo (id) ON DELETE CASCADE,
    summary        text
);

CREATE TABLE explorer_m2m_segment_poi (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position  integer NOT NULL,
    segment_id     uuid NOT NULL REFERENCES explorer_agg_segment (id) ON DELETE CASCADE,
    poi_id         uuid NOT NULL REFERENCES compendium_cat_poi (id) ON DELETE CASCADE,
    distance_m     integer
);

CREATE TABLE explorer_m2m_segment_route (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    segment_id     uuid NOT NULL REFERENCES explorer_agg_segment (id) ON DELETE CASCADE,
    route_id       uuid NOT NULL REFERENCES explorer_agg_route (id) ON DELETE CASCADE,
    slot_position  integer NOT NULL,
    alt_group      integer NOT NULL,
    is_default     boolean NOT NULL,
    is_reversed    boolean NOT NULL
);

CREATE TABLE explorer_m2m_track_gear (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position  integer NOT NULL,
    track_id       uuid NOT NULL REFERENCES explorer_agg_track (id) ON DELETE CASCADE,
    gear_id        uuid NOT NULL REFERENCES explorer_agg_gear (id) ON DELETE CASCADE,
    notes          text,
    points         integer
);

CREATE TABLE explorer_m2m_track_photo (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position  integer NOT NULL,
    track_id       uuid NOT NULL REFERENCES explorer_agg_track (id) ON DELETE CASCADE,
    photo_id       uuid NOT NULL REFERENCES asset_agg_photo (id) ON DELETE CASCADE
);

CREATE TABLE explorer_m2m_track_poi (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position  integer NOT NULL,
    track_id       uuid NOT NULL REFERENCES explorer_agg_track (id) ON DELETE CASCADE,
    poi_id         uuid NOT NULL REFERENCES compendium_cat_poi (id) ON DELETE CASCADE,
    distance_m     integer
);

CREATE TABLE explorer_m2m_track_trip (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    created_by       uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position    integer NOT NULL,
    track_id         uuid NOT NULL REFERENCES explorer_agg_track (id) ON DELETE CASCADE,
    trip_id          uuid NOT NULL REFERENCES explorer_agg_trip (id) ON DELETE CASCADE,
    waypoint_id      uuid REFERENCES explorer_sub_waypoint (id),
    day_name         text NOT NULL,
    day_summary      text,
    day_description  text
);

CREATE TABLE explorer_m2m_track_waypoint (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    created_by     uuid NOT NULL REFERENCES profile_usr_user (id),
    slot_position  integer NOT NULL,
    track_id       uuid NOT NULL REFERENCES explorer_agg_track (id) ON DELETE CASCADE,
    waypoint_id    uuid NOT NULL REFERENCES explorer_sub_waypoint (id) ON DELETE CASCADE
);

-- ============================================================================
-- profile
-- ============================================================================

CREATE TABLE profile_cat_achievement (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    created_by         uuid NOT NULL REFERENCES profile_usr_user (id),
    name               text UNIQUE,
    name_de            text,
    name_pl            text,
    summary            text,
    summary_de         text,
    summary_pl         text,
    description        text,
    description_de     text,
    description_pl     text,
    point_factor       real NOT NULL,
    criteria           jsonb,
    is_active          boolean NOT NULL DEFAULT true,
    is_repeatable      boolean NOT NULL DEFAULT false,
    rarity_id          uuid NOT NULL REFERENCES core_ref_rarity (id),
    category_id        uuid NOT NULL REFERENCES core_ref_achievement_category (id),
    criteria_scope_id  uuid NOT NULL REFERENCES core_ref_achievement_scope (id),
    criteria_type_id   uuid NOT NULL REFERENCES core_ref_achievement_type (id)
);

CREATE TABLE profile_sub_body_metric (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    user_id      uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    recorded_at  date NOT NULL,
    weight_kg    real NOT NULL,
    UNIQUE (user_id, recorded_at)
);

CREATE TABLE profile_sub_pace_curve (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now(),
    user_id        uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    sport_type_id  uuid NOT NULL REFERENCES core_ref_sport_type (id),
    gradient_bin   integer NOT NULL,
    speed_kmh      real NOT NULL,
    sample_points  integer NOT NULL,
    UNIQUE (user_id, sport_type_id, gradient_bin)
);

CREATE TABLE profile_sub_schedule (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    user_id       uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    route_id      uuid REFERENCES explorer_agg_route (id) ON DELETE SET NULL,
    journey_id    uuid REFERENCES explorer_agg_journey (id) ON DELETE SET NULL,
    track_id      uuid REFERENCES explorer_agg_track (id) ON DELETE SET NULL,
    trip_id       uuid REFERENCES explorer_agg_trip (id) ON DELETE SET NULL,
    planned_at    timestamptz NOT NULL,
    completed_at  timestamptz,
    status_id     uuid NOT NULL REFERENCES core_ref_schedule_status (id),
    notes         text,
    CHECK (((route_id IS NOT NULL) OR (journey_id IS NOT NULL)))
);

CREATE TABLE profile_sub_statistic (
    id                      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    user_id                 uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    scope                   text NOT NULL,
    scope_year              integer,
    scope_month             integer,
    total_distance_m        bigint NOT NULL DEFAULT 0,
    total_distance_graph    jsonb,
    total_elevation_m       bigint NOT NULL DEFAULT 0,
    total_elevation_graph   jsonb,
    total_activities        integer NOT NULL DEFAULT 0,
    total_activities_graph  jsonb,
    total_time_s            bigint NOT NULL DEFAULT 0,
    total_time_graph        jsonb,
    total_plans_created     integer NOT NULL DEFAULT 0,
    total_plans_completed   integer NOT NULL DEFAULT 0,
    total_plans_skipped     integer NOT NULL DEFAULT 0,
    current_streak_days     integer NOT NULL DEFAULT 0,
    longest_streak_days     integer NOT NULL DEFAULT 0,
    total_points            bigint NOT NULL DEFAULT 0,
    unique_pois_count       integer NOT NULL DEFAULT 0,
    unique_regions_count    integer NOT NULL DEFAULT 0,
    CHECK ((scope = ANY (ARRAY['all'::text, 'year'::text, 'month'::text]))),
    UNIQUE NULLS NOT DISTINCT (user_id, scope, scope_year, scope_month)
);

CREATE TABLE profile_m2m_liked_journey (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    user_id     uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    journey_id  uuid NOT NULL REFERENCES explorer_agg_journey (id) ON DELETE CASCADE,
    UNIQUE (user_id, journey_id)
);

CREATE TABLE profile_m2m_liked_route (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at  timestamptz NOT NULL DEFAULT now(),
    user_id     uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    route_id    uuid NOT NULL REFERENCES explorer_agg_route (id) ON DELETE CASCADE,
    UNIQUE (user_id, route_id)
);

CREATE TABLE profile_m2m_user_achievement (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    user_id         uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    achievement_id  uuid NOT NULL REFERENCES profile_cat_achievement (id),
    collected_at    timestamptz NOT NULL,
    comment         text,
    is_repeat       boolean NOT NULL DEFAULT false,
    track_id        uuid REFERENCES explorer_agg_track (id) ON DELETE SET NULL,
    trip_id         uuid REFERENCES explorer_agg_trip (id) ON DELETE SET NULL
);

CREATE TABLE profile_sub_point (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at           timestamptz NOT NULL DEFAULT now(),
    user_id              uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    received_at          date NOT NULL,
    points               integer NOT NULL,
    reason_id            uuid NOT NULL REFERENCES core_ref_point_reason (id),
    user_achievement_id  uuid REFERENCES profile_m2m_user_achievement (id) ON DELETE SET NULL,
    track_id             uuid REFERENCES explorer_agg_track (id) ON DELETE SET NULL,
    trip_id              uuid REFERENCES explorer_agg_trip (id) ON DELETE SET NULL
);

CREATE TABLE profile_m2m_user_card (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    user_id       uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    card_id       uuid NOT NULL REFERENCES compendium_cat_card (id) ON DELETE CASCADE,
    collected_at  timestamptz NOT NULL,
    comment       text,
    track_id      uuid REFERENCES explorer_agg_track (id) ON DELETE SET NULL,
    UNIQUE (user_id, card_id)
);

CREATE TABLE profile_m2m_user_poi (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    user_id       uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    poi_id        uuid NOT NULL REFERENCES compendium_cat_poi (id) ON DELETE CASCADE,
    collected_at  timestamptz NOT NULL,
    comment       text,
    track_id      uuid REFERENCES explorer_agg_track (id) ON DELETE SET NULL,
    UNIQUE (user_id, poi_id)
);

-- ============================================================================
-- social
-- ============================================================================

CREATE TABLE social_sub_comment (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    user_id      uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    entity_type  text NOT NULL,
    entity_id    uuid NOT NULL,
    comment      text NOT NULL,
    parent_id    uuid REFERENCES social_sub_comment (id) ON DELETE CASCADE,
    CHECK ((entity_type = ANY (ARRAY['route'::text, 'journey'::text, 'segment'::text, 'track'::text, 'trip'::text, 'post'::text])))
);

CREATE TABLE social_sub_rating (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    user_id      uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    entity_type  text NOT NULL,
    entity_id    uuid NOT NULL,
    score        integer NOT NULL,
    CHECK ((entity_type = ANY (ARRAY['route'::text, 'journey'::text, 'segment'::text]))),
    CHECK (((score >= 1) AND (score <= 5))),
    UNIQUE (user_id, entity_type, entity_id)
);

CREATE TABLE social_m2m_follow (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at    timestamptz NOT NULL DEFAULT now(),
    follower_id   uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    following_id  uuid NOT NULL REFERENCES profile_usr_user (id) ON DELETE CASCADE,
    CHECK ((follower_id <> following_id)),
    UNIQUE (follower_id, following_id)
);

-- ============================================================================
-- deferred foreign keys (break dependency cycles)
-- ============================================================================

ALTER TABLE profile_usr_user
    ADD CONSTRAINT fk_user_avatar_photo FOREIGN KEY (avatar_photo_id) REFERENCES asset_agg_photo(id) ON DELETE SET NULL;

-- ============================================================================
-- indexes
-- ============================================================================

CREATE INDEX idx_user_home_location ON profile_usr_user USING gist (home_location);
CREATE INDEX idx_gpx_created_by ON asset_agg_gpx USING btree (created_by);
CREATE INDEX idx_photo_created_by ON asset_agg_photo USING btree (created_by);
CREATE INDEX idx_photo_location ON asset_agg_photo USING gist (location);
CREATE INDEX idx_country_location ON compendium_cat_country USING gist (location);
CREATE INDEX idx_region_bbox ON compendium_cat_region USING gist (bbox);
CREATE INDEX idx_region_country ON compendium_cat_region USING btree (country_id);
CREATE INDEX idx_region_location ON compendium_cat_region USING gist (location);
CREATE INDEX idx_region_parent ON compendium_cat_region USING btree (parent_id);
CREATE INDEX idx_poi_location ON compendium_cat_poi USING gist (location);
CREATE INDEX idx_poi_main_region ON compendium_cat_poi USING btree (main_region_id);
CREATE INDEX idx_poi_type ON compendium_cat_poi USING btree (compendium_type_id);
CREATE INDEX idx_card_poi ON compendium_cat_card USING btree (poi_id);
CREATE INDEX idx_m2m_poi_region_poi ON compendium_m2m_poi_region USING btree (poi_id);
CREATE INDEX idx_m2m_poi_region_region ON compendium_m2m_poi_region USING btree (region_id);
CREATE INDEX idx_geo_record_end ON explorer_sub_geo_record USING gist (end_location);
CREATE INDEX idx_geo_record_gpx ON explorer_sub_geo_record USING btree (gpx_id);
CREATE INDEX idx_geo_record_start ON explorer_sub_geo_record USING gist (start_location);
CREATE INDEX idx_waypoint_location ON explorer_sub_waypoint USING gist (location);
CREATE INDEX idx_gear_created_by ON explorer_agg_gear USING btree (created_by);
CREATE INDEX idx_journey_created_by ON explorer_agg_journey USING btree (created_by);
CREATE INDEX idx_route_created_by ON explorer_agg_route USING btree (created_by);
CREATE INDEX idx_segment_created_by ON explorer_agg_segment USING btree (created_by);
CREATE INDEX idx_segment_geo_record ON explorer_agg_segment USING btree (geo_record_id);
CREATE INDEX idx_track_created_by ON explorer_agg_track USING btree (created_by);
CREATE INDEX idx_track_geo_record ON explorer_agg_track USING btree (geo_record_id);
CREATE INDEX idx_prediction_created_by ON explorer_sub_prediction USING btree (created_by);
CREATE INDEX idx_prediction_route ON explorer_sub_prediction USING btree (route_id);
CREATE INDEX idx_prediction_track ON explorer_sub_prediction USING btree (track_id);
CREATE INDEX idx_trip_created_by ON explorer_agg_trip USING btree (created_by);
CREATE INDEX idx_m2m_rj_journey ON explorer_m2m_route_journey USING btree (journey_id);
CREATE INDEX idx_m2m_rj_route ON explorer_m2m_route_journey USING btree (route_id);
CREATE INDEX idx_m2m_sp_photo ON explorer_m2m_segment_photo USING btree (photo_id);
CREATE INDEX idx_m2m_sp_segment ON explorer_m2m_segment_photo USING btree (segment_id);
CREATE INDEX idx_m2m_spoi_poi ON explorer_m2m_segment_poi USING btree (poi_id);
CREATE INDEX idx_m2m_spoi_segment ON explorer_m2m_segment_poi USING btree (segment_id);
CREATE INDEX idx_m2m_sr_route ON explorer_m2m_segment_route USING btree (route_id);
CREATE INDEX idx_m2m_sr_segment ON explorer_m2m_segment_route USING btree (segment_id);
CREATE INDEX idx_m2m_tg_gear ON explorer_m2m_track_gear USING btree (gear_id);
CREATE INDEX idx_m2m_tg_track ON explorer_m2m_track_gear USING btree (track_id);
CREATE INDEX idx_m2m_tph_photo ON explorer_m2m_track_photo USING btree (photo_id);
CREATE INDEX idx_m2m_tph_track ON explorer_m2m_track_photo USING btree (track_id);
CREATE INDEX idx_m2m_tpoi_poi ON explorer_m2m_track_poi USING btree (poi_id);
CREATE INDEX idx_m2m_tpoi_track ON explorer_m2m_track_poi USING btree (track_id);
CREATE INDEX idx_m2m_tt_track ON explorer_m2m_track_trip USING btree (track_id);
CREATE INDEX idx_m2m_tt_trip ON explorer_m2m_track_trip USING btree (trip_id);
CREATE INDEX idx_m2m_tw_track ON explorer_m2m_track_waypoint USING btree (track_id);
CREATE INDEX idx_m2m_tw_waypoint ON explorer_m2m_track_waypoint USING btree (waypoint_id);
CREATE INDEX idx_body_metric_user ON profile_sub_body_metric USING btree (user_id, recorded_at);
CREATE INDEX idx_pace_curve_user ON profile_sub_pace_curve USING btree (user_id, sport_type_id);
CREATE INDEX idx_schedule_user ON profile_sub_schedule USING btree (user_id, planned_at);
CREATE INDEX idx_user_achievement_ach ON profile_m2m_user_achievement USING btree (achievement_id);
CREATE INDEX idx_user_achievement_user ON profile_m2m_user_achievement USING btree (user_id);
CREATE UNIQUE INDEX uniq_onetime_achievement ON profile_m2m_user_achievement USING btree (user_id, achievement_id) WHERE (NOT is_repeat);
CREATE INDEX idx_point_user ON profile_sub_point USING btree (user_id, received_at);
CREATE INDEX idx_user_card_user ON profile_m2m_user_card USING btree (user_id);
CREATE INDEX idx_user_poi_user ON profile_m2m_user_poi USING btree (user_id);
CREATE INDEX idx_comment_entity ON social_sub_comment USING btree (entity_type, entity_id);
CREATE INDEX idx_comment_parent ON social_sub_comment USING btree (parent_id);
CREATE INDEX idx_rating_entity ON social_sub_rating USING btree (entity_type, entity_id);
CREATE INDEX idx_follow_following ON social_m2m_follow USING btree (following_id);

-- ============================================================================
-- triggers
-- ============================================================================

CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_usr_user FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_achievement_category FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_achievement_scope FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_achievement_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_company FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_compendium_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_difficulty_level FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_gear_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_point_reason FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_post_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_rarity FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_region_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_schedule_status FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_snow_condition FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_sport_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_difficulty_sport FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_trail_condition FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_visibility FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_waypoint_type FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON core_ref_weather_condition FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON asset_agg_gpx FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON asset_agg_photo FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_cat_country FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_cat_post FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_cat_region FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_sub_poi_access FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_cat_poi FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_cat_card FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON compendium_m2m_poi_region FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_sub_conditions FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_sub_geo_performance FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_sub_geo_record FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_sub_plan_conditions FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_sub_waypoint FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_gear FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_journey FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_route FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_segment FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_track FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_sub_prediction FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_trip FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_route_journey FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_segment_photo FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_segment_poi FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_segment_route FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_track_gear FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_track_photo FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_track_poi FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_track_trip FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_m2m_track_waypoint FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_cat_achievement FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_sub_pace_curve FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_sub_schedule FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_sub_statistic FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_m2m_user_achievement FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_m2m_user_card FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON profile_m2m_user_poi FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social_sub_comment FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON social_sub_rating FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');
