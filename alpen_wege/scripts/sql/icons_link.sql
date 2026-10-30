-- Icons, STEP 1: set icon_id wherever an icon with the matching key exists. Idempotent; run it again after every
-- load of new icons. It only fills EMPTY icon_id values and never changes a link that is already set.
--   reference tables : icon.key = lower(old icon text)         (sport_hiking, ferris-wheel; 'Ship' and 'ship' share 'ship')
--   countries        : icon.key = 'flag_' + lower(iso_code)    (flag_at)
--   regions          : icon.key = 'flag_' + lower(iso_code with - replaced by _)   (CH-ZH -> flag_ch_zh)
--   the 1,544 Swiss municipalities (CH-ZH-AK -> flag_ch_zh_ak) get a link only if somebody loads such an icon.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_link.sql
\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    t text;
    n bigint;
    total_empty bigint;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'core_ref_resource_type', 'core_ref_achievement_category', 'core_ref_achievement_scope', 'core_ref_achievement_type',
        'core_ref_company', 'core_ref_compendium_type', 'core_ref_difficulty_level', 'core_ref_difficulty_sport',
        'core_ref_gear_type', 'core_ref_point_reason', 'core_ref_post_type', 'core_ref_rarity', 'core_ref_region_type',
        'core_ref_schedule_status', 'core_ref_snow_condition', 'core_ref_sport_type', 'core_ref_trail_condition',
        'core_ref_visibility', 'core_ref_waypoint_type', 'core_ref_weather_condition']
    LOOP
        EXECUTE format('UPDATE %I r SET icon_id = i.id FROM asset_agg_icon i WHERE r.icon_id IS NULL AND i.key = lower(r.icon)', t);
        GET DIAGNOSTICS n = ROW_COUNT;
        EXECUTE format('SELECT count(*) FROM %I WHERE icon_id IS NULL', t) INTO total_empty;
        RAISE NOTICE '% : % linked now, % still without icon_id', rpad(t, 32), lpad(n::text, 4), lpad(total_empty::text, 4);
    END LOOP;

    UPDATE compendium_cat_country c SET icon_id = i.id
      FROM asset_agg_icon i WHERE c.icon_id IS NULL AND i.key = 'flag_' || lower(c.iso_code);
    GET DIAGNOSTICS n = ROW_COUNT;
    SELECT count(*) INTO total_empty FROM compendium_cat_country WHERE icon_id IS NULL;
    RAISE NOTICE '% : % linked now, % still without icon_id', rpad('compendium_cat_country', 32), lpad(n::text, 4), lpad(total_empty::text, 4);

    UPDATE compendium_cat_region g SET icon_id = i.id
      FROM asset_agg_icon i WHERE g.icon_id IS NULL AND g.iso_code IS NOT NULL
       AND i.key = 'flag_' || lower(replace(g.iso_code, '-', '_'));
    GET DIAGNOSTICS n = ROW_COUNT;
    SELECT count(*) INTO total_empty FROM compendium_cat_region WHERE icon_id IS NULL;
    RAISE NOTICE '% : % linked now, % still without icon_id', rpad('compendium_cat_region', 32), lpad(n::text, 4), lpad(total_empty::text, 4);
END $$;

COMMIT;
