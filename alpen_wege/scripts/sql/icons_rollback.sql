-- Icons, STEP 1: ROLLBACK. Removes the 22 icon_id columns (their foreign keys and indexes go with them) and the table
-- asset_agg_icon WITH ALL ITS ROWS. Nothing else is touched: the old text column icon was never changed, so the
-- previous application version works again as soon as this has run. The icons can be rebuilt with seed_icons.py.
-- Start the OLD application code only AFTER this script, and stop the new code BEFORE it.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_rollback.sql
\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    t text;
BEGIN
    IF to_regclass('asset_agg_icon') IS NOT NULL THEN
        EXECUTE 'SELECT count(*) FROM asset_agg_icon' INTO STRICT t;
        RAISE NOTICE 'dropping asset_agg_icon with % rows', t;
    END IF;
    FOREACH t IN ARRAY ARRAY[
        'core_ref_resource_type', 'core_ref_achievement_category', 'core_ref_achievement_scope', 'core_ref_achievement_type',
        'core_ref_company', 'core_ref_compendium_type', 'core_ref_difficulty_level', 'core_ref_difficulty_sport',
        'core_ref_gear_type', 'core_ref_point_reason', 'core_ref_post_type', 'core_ref_rarity', 'core_ref_region_type',
        'core_ref_schedule_status', 'core_ref_snow_condition', 'core_ref_sport_type', 'core_ref_trail_condition',
        'core_ref_visibility', 'core_ref_waypoint_type', 'core_ref_weather_condition',
        'compendium_cat_country', 'compendium_cat_region']
    LOOP
        EXECUTE format('ALTER TABLE %I DROP COLUMN IF EXISTS icon_id', t);
    END LOOP;
END $$;

DROP TABLE IF EXISTS asset_agg_icon;

COMMIT;
