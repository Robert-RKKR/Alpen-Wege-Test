-- Icons: give countries and regions their flag wherever an icon with the matching key exists. Idempotent; run it again
-- after every load of new flags. It only fills EMPTY icon_id values and never changes a link that is already set.
-- The reference tables are not here: since icons_drop_text.sql their icon_id is required and set on create.
--   countries        : icon.key = 'flag_' + lower(iso_code)    (flag_at)
--   regions          : icon.key = 'flag_' + lower(iso_code with - replaced by _)   (CH-ZH -> flag_ch_zh)
--   the 1,544 Swiss municipalities (CH-ZH-AK -> flag_ch_zh_ak) get a link only if somebody loads such an icon.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/icons_link.sql
\set ON_ERROR_STOP on
BEGIN;

DO $$
DECLARE
    n bigint;
    total_empty bigint;
BEGIN
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
