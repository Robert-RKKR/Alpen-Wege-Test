-- fix_icon_names.sql
-- Normalises the icon column in every core_ref_* table so that each value
-- follows the pattern:  {table_name}_{some_name}
--
-- Rules applied per row when icon does NOT already start with {table_name}_:
--   icon contains '_'  →  strip everything up to and including the first '_',
--                          keep the rest as {some_name}
--   icon has no '_'    →  use the whole value as {some_name}, replacing '-' with '_'
--
-- Usage:
--   sudo docker exec -i alpenwege-postgres \
--     psql -U alpenwege -d alpenwege < fix_icon_names.sql

BEGIN;

DO $$
DECLARE
    rec    RECORD;
    tbl    TEXT;
    prefix TEXT;
    cnt    INTEGER;
    total  INTEGER := 0;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== Fixing icon names in core_ref_* tables ===';
    RAISE NOTICE '';

    FOR rec IN
        SELECT c.table_name
        FROM information_schema.columns c
        WHERE c.table_schema = 'public'
          AND c.table_name LIKE 'core\_ref\_%' ESCAPE '\'
          AND c.column_name = 'icon'
        ORDER BY c.table_name
    LOOP
        tbl    := rec.table_name;
        prefix := tbl || '_';

        -- Preview rows that will change
        EXECUTE format(
            'SELECT count(*) FROM %I
             WHERE icon IS NOT NULL
               AND left(icon, length($1)) <> $1',
            tbl
        ) INTO cnt USING prefix;

        IF cnt = 0 THEN
            RAISE NOTICE '[OK]   % — all icons already correct', tbl;
            CONTINUE;
        END IF;

        -- Show before → after for each affected row
        DECLARE
            preview RECORD;
        BEGIN
            FOR preview IN
                EXECUTE format(
                    'SELECT icon AS old_icon,
                            $1 ||
                            CASE
                                WHEN position(''_'' in icon) > 0
                                THEN substring(icon from position(''_'' in icon) + 1)
                                ELSE replace(icon, ''-'', ''_'')
                            END AS new_icon
                     FROM %I
                     WHERE icon IS NOT NULL
                       AND left(icon, length($1)) <> $1
                     ORDER BY icon
                     LIMIT 10',
                    tbl
                ) USING prefix
            LOOP
                RAISE NOTICE '       % → %', preview.old_icon, preview.new_icon;
            END LOOP;
        END;

        -- Apply the update
        EXECUTE format(
            'UPDATE %I
             SET icon = $1 ||
                        CASE
                            WHEN position(''_'' in icon) > 0
                            THEN substring(icon from position(''_'' in icon) + 1)
                            ELSE replace(icon, ''-'', ''_'')
                        END,
                 updated_at = now()
             WHERE icon IS NOT NULL
               AND left(icon, length($1)) <> $1',
            tbl
        ) USING prefix;

        GET DIAGNOSTICS cnt = ROW_COUNT;
        total := total + cnt;

        RAISE NOTICE '[FIX]  % — % rows updated', tbl, cnt;
    END LOOP;

    RAISE NOTICE '';
    RAISE NOTICE '=== Done — % total rows updated ===', total;
    RAISE NOTICE '';
END $$;

COMMIT;
