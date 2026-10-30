-- Icons, STEP 2: the 20 reference tables (19 core_ref_* + core_ref_resource_type) lose the old text column icon, and their
-- icon_id becomes NOT NULL. Countries and regions are not touched (their icon_id stays optional).
-- Refuses to run (nothing is changed) while any of the 20 tables still has a row without icon_id: load the icons and run
-- icons_link.sql first. Idempotent, one transaction. A fresh create_all database already looks like this.
-- THE TEXT IS GONE AFTERWARDS: take a pg_dump first. Afterwards icons_rollback_text.sql brings the column back, filled from the
-- key of the linked icon.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_drop_text.sql
-- Order: pg_dump -> stop api and celery -> THIS SCRIPT -> start the new application code
\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    t text;
    n bigint;
    problems text := '';
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'core_ref_resource_type', 'core_ref_achievement_category', 'core_ref_achievement_scope', 'core_ref_achievement_type',
        'core_ref_company', 'core_ref_compendium_type', 'core_ref_difficulty_level', 'core_ref_difficulty_sport',
        'core_ref_gear_type', 'core_ref_point_reason', 'core_ref_post_type', 'core_ref_rarity', 'core_ref_region_type',
        'core_ref_schedule_status', 'core_ref_snow_condition', 'core_ref_sport_type', 'core_ref_trail_condition',
        'core_ref_visibility', 'core_ref_waypoint_type', 'core_ref_weather_condition']
    LOOP
        EXECUTE format('SELECT count(*) FROM %I WHERE icon_id IS NULL', t) INTO n;
        IF n > 0 THEN
            problems := problems || format(E'\n  %s: %s rows without icon_id', t, n);
        END IF;
    END LOOP;
    IF problems <> '' THEN
        RAISE EXCEPTION 'not every reference row has an icon; nothing was changed:%', problems
            USING HINT = 'Load the icons (seed_icons.py --csv) and run icons_link.sql, then run this script again.';
    END IF;

    FOREACH t IN ARRAY ARRAY[
        'core_ref_resource_type', 'core_ref_achievement_category', 'core_ref_achievement_scope', 'core_ref_achievement_type',
        'core_ref_company', 'core_ref_compendium_type', 'core_ref_difficulty_level', 'core_ref_difficulty_sport',
        'core_ref_gear_type', 'core_ref_point_reason', 'core_ref_post_type', 'core_ref_rarity', 'core_ref_region_type',
        'core_ref_schedule_status', 'core_ref_snow_condition', 'core_ref_sport_type', 'core_ref_trail_condition',
        'core_ref_visibility', 'core_ref_waypoint_type', 'core_ref_weather_condition']
    LOOP
        EXECUTE format('ALTER TABLE %I ALTER COLUMN icon_id SET NOT NULL', t);
        EXECUTE format('COMMENT ON COLUMN %I.icon_id IS %L', t,
                       'FK to asset_agg_icon with RESTRICT delete. The picture of this reference value (an SVG).');
        EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS icon', t);
        RAISE NOTICE '%: icon dropped, icon_id required', t;
    END LOOP;
END $$;

COMMENT ON COLUMN asset_agg_icon.key IS 'Unique machine-readable name, lower-case letters, digits and _ . - only (for example flag_at, flag_ch_zh, sport_hiking). A seeded icon''s id is computed from it, and icons_link.sql uses it to give countries and regions their flag.';

COMMIT;
