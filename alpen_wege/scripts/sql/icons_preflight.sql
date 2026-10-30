-- Icons step 1, PRE-FLIGHT: read-only checks to run BEFORE icons_ddl.sql. Changes nothing.
-- Step 1 only: it reads the old text column icon, so after icons_drop_text.sql it stops with "column icon does not exist".
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_preflight.sql
-- Every line says OK or PROBLEM. Fix every PROBLEM first.
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on

SELECT CASE WHEN to_regclass('asset_agg_icon') IS NULL THEN 'OK      asset_agg_icon does not exist yet (fresh run)'
            ELSE 'NOTE    asset_agg_icon already exists (the DDL is idempotent; it will not touch its rows)' END;

-- 1. all 22 target tables exist
WITH t(name) AS (VALUES
 ('core_ref_resource_type'),('core_ref_achievement_category'),('core_ref_achievement_scope'),('core_ref_achievement_type'),
 ('core_ref_company'),('core_ref_compendium_type'),('core_ref_difficulty_level'),('core_ref_difficulty_sport'),
 ('core_ref_gear_type'),('core_ref_point_reason'),('core_ref_post_type'),('core_ref_rarity'),('core_ref_region_type'),
 ('core_ref_schedule_status'),('core_ref_snow_condition'),('core_ref_sport_type'),('core_ref_trail_condition'),
 ('core_ref_visibility'),('core_ref_waypoint_type'),('core_ref_weather_condition'),
 ('compendium_cat_country'),('compendium_cat_region'))
SELECT CASE WHEN to_regclass(name) IS NULL THEN 'PROBLEM table missing: ' || name ELSE 'OK      table exists: ' || name END
  FROM t ORDER BY 1 DESC, 1;

-- 2. no icon_id column exists already on a table that is not ours (name clash)
SELECT 'PROBLEM column icon_id already exists on ' || table_name || ' with type ' || data_type
  FROM information_schema.columns
 WHERE table_schema = 'public' AND column_name = 'icon_id' AND data_type <> 'uuid';

-- 3. every existing icon text can later become a key (in lower case: letters, digits, _ . - only, 1 to 100 characters)
SELECT 'PROBLEM icon text is not a valid key: ' || t || ' / ' || icon
  FROM (
    SELECT 'core_ref_resource_type' AS t, icon FROM core_ref_resource_type UNION ALL
    SELECT 'core_ref_achievement_category', icon FROM core_ref_achievement_category UNION ALL
    SELECT 'core_ref_achievement_scope', icon FROM core_ref_achievement_scope UNION ALL
    SELECT 'core_ref_achievement_type', icon FROM core_ref_achievement_type UNION ALL
    SELECT 'core_ref_company', icon FROM core_ref_company UNION ALL
    SELECT 'core_ref_compendium_type', icon FROM core_ref_compendium_type UNION ALL
    SELECT 'core_ref_difficulty_level', icon FROM core_ref_difficulty_level UNION ALL
    SELECT 'core_ref_difficulty_sport', icon FROM core_ref_difficulty_sport UNION ALL
    SELECT 'core_ref_gear_type', icon FROM core_ref_gear_type UNION ALL
    SELECT 'core_ref_point_reason', icon FROM core_ref_point_reason UNION ALL
    SELECT 'core_ref_post_type', icon FROM core_ref_post_type UNION ALL
    SELECT 'core_ref_rarity', icon FROM core_ref_rarity UNION ALL
    SELECT 'core_ref_region_type', icon FROM core_ref_region_type UNION ALL
    SELECT 'core_ref_schedule_status', icon FROM core_ref_schedule_status UNION ALL
    SELECT 'core_ref_snow_condition', icon FROM core_ref_snow_condition UNION ALL
    SELECT 'core_ref_sport_type', icon FROM core_ref_sport_type UNION ALL
    SELECT 'core_ref_trail_condition', icon FROM core_ref_trail_condition UNION ALL
    SELECT 'core_ref_visibility', icon FROM core_ref_visibility UNION ALL
    SELECT 'core_ref_waypoint_type', icon FROM core_ref_waypoint_type UNION ALL
    SELECT 'core_ref_weather_condition', icon FROM core_ref_weather_condition
  ) x
 WHERE lower(icon) !~ '^[a-z0-9_.-]{1,100}$';

-- 3b. icon texts that differ only in letter case will share ONE icon (keys are lower case)
SELECT 'NOTE    icon texts that differ only in case: ' || string_agg(DISTINCT icon, ' / ' ORDER BY icon)
  FROM (SELECT icon FROM (
    SELECT icon FROM core_ref_resource_type UNION ALL SELECT icon FROM core_ref_achievement_category UNION ALL
    SELECT icon FROM core_ref_achievement_scope UNION ALL SELECT icon FROM core_ref_achievement_type UNION ALL
    SELECT icon FROM core_ref_company UNION ALL SELECT icon FROM core_ref_compendium_type UNION ALL
    SELECT icon FROM core_ref_difficulty_level UNION ALL SELECT icon FROM core_ref_difficulty_sport UNION ALL
    SELECT icon FROM core_ref_gear_type UNION ALL SELECT icon FROM core_ref_point_reason UNION ALL
    SELECT icon FROM core_ref_post_type UNION ALL SELECT icon FROM core_ref_rarity UNION ALL
    SELECT icon FROM core_ref_region_type UNION ALL SELECT icon FROM core_ref_schedule_status UNION ALL
    SELECT icon FROM core_ref_snow_condition UNION ALL SELECT icon FROM core_ref_sport_type UNION ALL
    SELECT icon FROM core_ref_trail_condition UNION ALL SELECT icon FROM core_ref_visibility UNION ALL
    SELECT icon FROM core_ref_waypoint_type UNION ALL SELECT icon FROM core_ref_weather_condition) a
    GROUP BY icon) b
 GROUP BY lower(icon) HAVING count(*) > 1;

-- 4. numbers for the record
SELECT 'INFO    countries: ' || count(*) || ', with iso_code: ' || count(iso_code) FROM compendium_cat_country;
SELECT 'INFO    regions: ' || count(*) || ', with iso_code: ' || count(iso_code) FROM compendium_cat_region;
SELECT 'INFO    distinct icon texts in the 20 reference tables: ' || count(DISTINCT lower(icon)) FROM (
    SELECT icon FROM core_ref_resource_type UNION ALL SELECT icon FROM core_ref_achievement_category UNION ALL
    SELECT icon FROM core_ref_achievement_scope UNION ALL SELECT icon FROM core_ref_achievement_type UNION ALL
    SELECT icon FROM core_ref_company UNION ALL SELECT icon FROM core_ref_compendium_type UNION ALL
    SELECT icon FROM core_ref_difficulty_level UNION ALL SELECT icon FROM core_ref_difficulty_sport UNION ALL
    SELECT icon FROM core_ref_gear_type UNION ALL SELECT icon FROM core_ref_point_reason UNION ALL
    SELECT icon FROM core_ref_post_type UNION ALL SELECT icon FROM core_ref_rarity UNION ALL
    SELECT icon FROM core_ref_region_type UNION ALL SELECT icon FROM core_ref_schedule_status UNION ALL
    SELECT icon FROM core_ref_snow_condition UNION ALL SELECT icon FROM core_ref_sport_type UNION ALL
    SELECT icon FROM core_ref_trail_condition UNION ALL SELECT icon FROM core_ref_visibility UNION ALL
    SELECT icon FROM core_ref_waypoint_type UNION ALL SELECT icon FROM core_ref_weather_condition) x;

-- 5. the moddatetime extension (needed for the updated_at trigger) can be created
SELECT CASE WHEN EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'moddatetime')
            THEN 'OK      extension moddatetime is available'
            ELSE 'PROBLEM extension moddatetime is not available' END;
