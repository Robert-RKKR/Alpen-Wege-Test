-- Track pipeline DDL — idempotent, one transaction.
-- Run: sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/track_pipeline_ddl.sql
\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS moddatetime;

-- 0. Preconditions
DO $$
BEGIN
    IF current_setting('server_version_num')::int < 150000 THEN
        RAISE EXCEPTION 'PostgreSQL 15 or newer is required (UNIQUE NULLS NOT DISTINCT)';
    END IF;
    IF EXISTS (SELECT 1 FROM compendium_cat_card WHERE poi_id IS NULL) THEN
        RAISE EXCEPTION 'compendium_cat_card has rows with poi_id IS NULL; fix or delete them first';
    END IF;
    IF EXISTS (SELECT 1 FROM explorer_m2m_track_poi GROUP BY track_id, poi_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'explorer_m2m_track_poi has duplicate (track_id, poi_id) pairs';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_profile_sub_statistic_bucket')
       AND EXISTS (SELECT 1 FROM profile_sub_statistic
                   GROUP BY user_id, scope, scope_year, scope_month HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'profile_sub_statistic has duplicate buckets; remove them first';
    END IF;
END $$;

-- 1. asset_agg_gpx
ALTER TABLE asset_agg_gpx ADD COLUMN IF NOT EXISTS sha256 varchar(64);
ALTER TABLE asset_agg_gpx ADD COLUMN IF NOT EXISTS size_bytes bigint;
CREATE INDEX IF NOT EXISTS ix_asset_agg_gpx_sha256 ON asset_agg_gpx (sha256);

-- 2. explorer_agg_track
ALTER TABLE explorer_agg_track
    ADD COLUMN IF NOT EXISTS processing_status varchar(16) NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS processing_error text,
    ADD COLUMN IF NOT EXISTS processing_warnings jsonb,
    ADD COLUMN IF NOT EXISTS processing_started_at timestamptz,
    ADD COLUMN IF NOT EXISTS processed_at timestamptz,
    ADD COLUMN IF NOT EXISTS archived_at timestamptz,
    ADD COLUMN IF NOT EXISTS gpx_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_track_processing_status') THEN
        ALTER TABLE explorer_agg_track ADD CONSTRAINT ck_track_processing_status
            CHECK (processing_status IN ('pending', 'processing', 'ready', 'failed'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'explorer_agg_track_gpx_id_fkey') THEN
        ALTER TABLE explorer_agg_track ADD CONSTRAINT explorer_agg_track_gpx_id_fkey
            FOREIGN KEY (gpx_id) REFERENCES asset_agg_gpx (id);
    END IF;
END $$;

ALTER TABLE explorer_agg_track
    DROP CONSTRAINT IF EXISTS explorer_agg_track_start_poi_id_fkey,
    DROP CONSTRAINT IF EXISTS explorer_agg_track_end_poi_id_fkey;
ALTER TABLE explorer_agg_track
    ADD CONSTRAINT explorer_agg_track_start_poi_id_fkey
        FOREIGN KEY (start_poi_id) REFERENCES compendium_cat_poi (id) ON DELETE SET NULL,
    ADD CONSTRAINT explorer_agg_track_end_poi_id_fkey
        FOREIGN KEY (end_poi_id) REFERENCES compendium_cat_poi (id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_track_active_owner
    ON explorer_agg_track (created_by, recorded_at) WHERE archived_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_track_processing_status ON explorer_agg_track (processing_status);
CREATE INDEX IF NOT EXISTS ix_track_gpx_id ON explorer_agg_track (gpx_id);

DROP TRIGGER IF EXISTS trg_set_updated_at ON explorer_agg_track;
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON explorer_agg_track
    FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');

-- 3. explorer_sub_geo_record
ALTER TABLE explorer_sub_geo_record
    ADD COLUMN IF NOT EXISTS route geography(MultiLineString, 4326),
    ADD COLUMN IF NOT EXISTS processor_version smallint;
CREATE INDEX IF NOT EXISTS idx_explorer_sub_geo_record_route
    ON explorer_sub_geo_record USING gist (route);

-- 4. compendium
CREATE INDEX IF NOT EXISTS ix_poi_location_geog
    ON compendium_cat_poi USING gist ((location::geography));
ALTER TABLE compendium_cat_card ALTER COLUMN poi_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_compendium_cat_card_poi_id ON compendium_cat_card (poi_id);

DO $$
DECLARE n integer;
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                   WHERE table_schema = current_schema()
                     AND table_name = 'core_ref_compendium_type'
                     AND column_name = 'is_collectable') THEN
        ALTER TABLE core_ref_compendium_type
            ADD COLUMN is_collectable boolean NOT NULL DEFAULT true;
        UPDATE core_ref_compendium_type SET is_collectable = false WHERE name IN (
            'Bus Stop', 'Train Station', 'Tram', 'Cable Car Station', 'Gondola Station',
            'Chair Lift', 'Funicular Station', 'Rack Railway', 'Mountain Railway',
            'Ferry Crossing', 'Multi transport station',
            'Multi transport station (Bus/Cable Car)', 'Multi transport station (Tram/Bus)',
            'Parking', 'Lake Harbor', 'Helipad');
        GET DIAGNOSTICS n = ROW_COUNT;
        RAISE NOTICE 'is_collectable set to false on % rows (16 names were expected)', n;
    END IF;
END $$;

-- 5. Tier 3 visit log and track-poi uniqueness
ALTER TABLE profile_m2m_user_poi
    DROP CONSTRAINT IF EXISTS profile_m2m_user_poi_user_id_poi_id_key;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_profile_m2m_user_poi_visit') THEN
        ALTER TABLE profile_m2m_user_poi ADD CONSTRAINT uq_profile_m2m_user_poi_visit
            UNIQUE (user_id, poi_id, track_id);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_explorer_m2m_track_poi_track_poi') THEN
        ALTER TABLE explorer_m2m_track_poi ADD CONSTRAINT uq_explorer_m2m_track_poi_track_poi
            UNIQUE (track_id, poi_id);
    END IF;
END $$;

-- 6. profile_sub_statistic
ALTER TABLE profile_sub_statistic
    ADD COLUMN IF NOT EXISTS sport_type_id uuid,
    ADD COLUMN IF NOT EXISTS total_moving_time_s bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS total_elevation_loss_m bigint NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS active_days integer NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS max_elevation_m integer,
    ADD COLUMN IF NOT EXISTS longest_track_m integer,
    ADD COLUMN IF NOT EXISTS longest_track_id uuid;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'profile_sub_statistic_sport_type_id_fkey') THEN
        ALTER TABLE profile_sub_statistic ADD CONSTRAINT profile_sub_statistic_sport_type_id_fkey
            FOREIGN KEY (sport_type_id) REFERENCES core_ref_sport_type (id) ON DELETE CASCADE;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'profile_sub_statistic_longest_track_id_fkey') THEN
        ALTER TABLE profile_sub_statistic ADD CONSTRAINT profile_sub_statistic_longest_track_id_fkey
            FOREIGN KEY (longest_track_id) REFERENCES explorer_agg_track (id) ON DELETE SET NULL;
    END IF;
END $$;

ALTER TABLE profile_sub_statistic
    DROP CONSTRAINT IF EXISTS profile_sub_statistic_user_id_scope_scope_year_scope_month_key;
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_profile_sub_statistic_bucket') THEN
        ALTER TABLE profile_sub_statistic ADD CONSTRAINT uq_profile_sub_statistic_bucket
            UNIQUE NULLS NOT DISTINCT (user_id, sport_type_id, scope, scope_year, scope_month);
    END IF;
END $$;

-- 7. Fail loudly if an older unique constraint survived under an unexpected name
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint
                WHERE contype = 'u'
                  AND ((conrelid = 'profile_m2m_user_poi'::regclass
                        AND conname <> 'uq_profile_m2m_user_poi_visit')
                    OR (conrelid = 'profile_sub_statistic'::regclass
                        AND conname <> 'uq_profile_sub_statistic_bucket'))) THEN
        RAISE EXCEPTION 'A stale unique constraint remains on profile_m2m_user_poi or profile_sub_statistic; drop it by its real name (see \d) and run the script again';
    END IF;
END $$;

COMMIT;
