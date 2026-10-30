-- Icons, STEP 2: ROLLBACK of icons_drop_text.sql. Brings back the text column icon on the 20 reference tables, filled with the
-- key of the linked icon (the old text in lower case: 'Ship' comes back as 'ship'), makes it NOT NULL again and makes icon_id
-- optional again. Stop the new code BEFORE it and start the old code only AFTER it. Idempotent, one transaction.
-- For the exact old spelling restore the pg_dump taken before icons_drop_text.sql instead.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_rollback_text.sql
\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'core_ref_resource_type', 'core_ref_achievement_category', 'core_ref_achievement_scope', 'core_ref_achievement_type',
        'core_ref_company', 'core_ref_compendium_type', 'core_ref_difficulty_level', 'core_ref_difficulty_sport',
        'core_ref_gear_type', 'core_ref_point_reason', 'core_ref_post_type', 'core_ref_rarity', 'core_ref_region_type',
        'core_ref_schedule_status', 'core_ref_snow_condition', 'core_ref_sport_type', 'core_ref_trail_condition',
        'core_ref_visibility', 'core_ref_waypoint_type', 'core_ref_weather_condition']
    LOOP
        EXECUTE format('ALTER TABLE %I ADD COLUMN IF NOT EXISTS icon text', t);
        EXECUTE format('UPDATE %I r SET icon = i.key FROM asset_agg_icon i WHERE r.icon IS NULL AND i.id = r.icon_id', t);
        EXECUTE format('ALTER TABLE %I ALTER COLUMN icon SET NOT NULL', t);
        EXECUTE format('COMMENT ON COLUMN %I.icon IS %L', t,
                       'Icon identifier or key name used to render the visual icon for this reference value in the UI.');
        EXECUTE format('ALTER TABLE %I ALTER COLUMN icon_id DROP NOT NULL', t);
        EXECUTE format('COMMENT ON COLUMN %I.icon_id IS %L', t,
                       'FK to asset_agg_icon with RESTRICT delete. The picture of this reference value (an SVG). NULL until one is linked; the text column icon is still used until then.');
    END LOOP;
END $$;

COMMENT ON COLUMN asset_agg_icon.key IS 'Unique machine-readable name, lower-case letters, digits and _ . - only (for example flag_at, flag_ch_zh, sport_hiking). The same text that the reference tables hold in their old icon column (compared in lower case); icons_link.sql uses it to set icon_id.';

COMMIT;
