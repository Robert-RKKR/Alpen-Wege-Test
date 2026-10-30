-- Every distinct icon text (the old approach) of the 20 reference tables, one row per icon KEY (the text in lower case, which is
-- what asset_agg_icon.key and icons_link.sql use). Read only; run it as often as you like.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_list_keys.sql
-- Columns: key (create an icon with exactly this key), written_as (the spellings found, "Ship | ship" = two rows share one
-- icon), rows_using (reference rows with this text), used_by (tables), icon_exists (an icon with this key is already in
-- asset_agg_icon), rows_linked (rows that already have icon_id set). Icons still to create come first (icon_exists = f).
-- To a CSV file:  ... psql -U alpenwege -d alpenwege -A -F ',' --csv < scripts/sql/icons_list_keys.sql > icon_keys.csv
WITH u(table_name, icon, icon_id) AS (
    SELECT 'core_ref_resource_type', icon, icon_id FROM core_ref_resource_type UNION ALL
    SELECT 'core_ref_achievement_category', icon, icon_id FROM core_ref_achievement_category UNION ALL
    SELECT 'core_ref_achievement_scope', icon, icon_id FROM core_ref_achievement_scope UNION ALL
    SELECT 'core_ref_achievement_type', icon, icon_id FROM core_ref_achievement_type UNION ALL
    SELECT 'core_ref_company', icon, icon_id FROM core_ref_company UNION ALL
    SELECT 'core_ref_compendium_type', icon, icon_id FROM core_ref_compendium_type UNION ALL
    SELECT 'core_ref_difficulty_level', icon, icon_id FROM core_ref_difficulty_level UNION ALL
    SELECT 'core_ref_difficulty_sport', icon, icon_id FROM core_ref_difficulty_sport UNION ALL
    SELECT 'core_ref_gear_type', icon, icon_id FROM core_ref_gear_type UNION ALL
    SELECT 'core_ref_point_reason', icon, icon_id FROM core_ref_point_reason UNION ALL
    SELECT 'core_ref_post_type', icon, icon_id FROM core_ref_post_type UNION ALL
    SELECT 'core_ref_rarity', icon, icon_id FROM core_ref_rarity UNION ALL
    SELECT 'core_ref_region_type', icon, icon_id FROM core_ref_region_type UNION ALL
    SELECT 'core_ref_schedule_status', icon, icon_id FROM core_ref_schedule_status UNION ALL
    SELECT 'core_ref_snow_condition', icon, icon_id FROM core_ref_snow_condition UNION ALL
    SELECT 'core_ref_sport_type', icon, icon_id FROM core_ref_sport_type UNION ALL
    SELECT 'core_ref_trail_condition', icon, icon_id FROM core_ref_trail_condition UNION ALL
    SELECT 'core_ref_visibility', icon, icon_id FROM core_ref_visibility UNION ALL
    SELECT 'core_ref_waypoint_type', icon, icon_id FROM core_ref_waypoint_type UNION ALL
    SELECT 'core_ref_weather_condition', icon, icon_id FROM core_ref_weather_condition
)
SELECT k.key, k.written_as, k.rows_using, k.used_by,
       EXISTS (SELECT 1 FROM asset_agg_icon i WHERE i.key = k.key) AS icon_exists,
       k.rows_linked
  FROM (
        SELECT lower(u.icon)                                      AS key,
               string_agg(DISTINCT u.icon, ' | ' ORDER BY u.icon) AS written_as,
               count(*)                                           AS rows_using,
               string_agg(DISTINCT replace(u.table_name, 'core_ref_', ''), ', ' ORDER BY replace(u.table_name, 'core_ref_', '')) AS used_by,
               count(u.icon_id)                                   AS rows_linked
          FROM u
         GROUP BY lower(u.icon)
       ) k
 ORDER BY icon_exists, k.key;
