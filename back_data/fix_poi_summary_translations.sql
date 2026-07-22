-- fix_poi_summary_translations.sql
-- Generates summary_de and summary_pl for every compendium_cat_poi row
-- using static type translations and replacing "in" with the localised preposition.
--
-- English pattern:  "{company} {type} in {location}."
-- German pattern:   "{company} {type_de} in {location}."
-- Polish pattern:   "{company} {type_pl} w {location}."
--
-- Usage:
--   sudo docker exec -i alpenwege-postgres \
--     psql -U alpenwege -d alpenwege < fix_poi_summary_translations.sql

BEGIN;

-- Static mapping: all 27 station types → DE + PL
-- Longest entries first so compound types match before their substrings.
CREATE TEMP TABLE _type_map (en TEXT PRIMARY KEY, de TEXT NOT NULL, pl TEXT NOT NULL);
INSERT INTO _type_map (en, de, pl) VALUES
    -- 5-part compound
    ('Cable car/Cable railway/Chairlift station',  'Seilbahn-/Standseilbahn-/Sesselliftstation',       'Stacja kolejki linowej/linowo-terenowej/wyciągu krzesełkowego'),
    ('Bus/Cable railway/Tram station',              'Bus-/Standseilbahn-/Tramhaltestelle',              'Przystanek autobusowo-tramwajowy/stacja kolejki linowo-terenowej'),
    ('Bus/Rack railway/Tram station',               'Bus-/Zahnradbahn-/Tramhaltestelle',               'Przystanek autobusowo-tramwajowy/stacja kolei zębatej'),
    ('Bus/Metro/Tram station',                      'Bus-/Metro-/Tramhaltestelle',                      'Przystanek autobusowo-metrowo-tramwajowy'),
    ('Bus/Train/Tram station',                      'Bus-/Bahn-/Tramhaltestelle',                       'Przystanek autobusowo-kolejowo-tramwajowy'),
    -- 3-part compound
    ('Boat/Cable railway station',                  'Schiff-/Standseilbahnstation',                     'Przystań/stacja kolejki linowo-terenowej'),
    ('Boat/Rack railway station',                   'Schiff-/Zahnradbahnstation',                       'Przystań/stacja kolei zębatej'),
    ('Bus/Cable car station',                       'Bus-/Seilbahnstation',                             'Przystanek autobusowy/stacja kolejki linowej'),
    ('Bus/Cable railway station',                   'Bus-/Standseilbahnstation',                        'Przystanek autobusowy/stacja kolejki linowo-terenowej'),
    ('Bus/Metro station',                           'Bus-/Metrostation',                                'Przystanek autobusowo-metrowy'),
    ('Bus/Train station',                           'Bus-/Bahnhaltestelle',                             'Przystanek autobusowo-kolejowy'),
    ('Bus/Tram station',                            'Bus-/Tramhaltestelle',                             'Przystanek autobusowo-tramwajowy'),
    ('Cable car/Cable railway station',             'Seilbahn-/Standseilbahnstation',                   'Stacja kolejki linowej/linowo-terenowej'),
    ('Cable car/Chairlift station',                 'Seilbahn-/Sesselliftstation',                      'Stacja kolejki linowej/wyciągu krzesełkowego'),
    ('Cable car/Rack railway station',              'Seilbahn-/Zahnradbahnstation',                     'Stacja kolejki linowej/kolei zębatej'),
    ('Cable car/Train station',                     'Seilbahn-/Bahnstation',                            'Stacja kolejki linowej/dworzec kolejowy'),
    ('Train/Tram station',                          'Bahn-/Tramhaltestelle',                            'Przystanek kolejowo-tramwajowy'),
    -- single types
    ('Boat station',                                'Schiffstation',                                    'Przystań'),
    ('Bus station',                                 'Bushaltestelle',                                   'Przystanek autobusowy'),
    ('Cable car station',                           'Seilbahnstation',                                  'Stacja kolejki linowej'),
    ('Cable railway station',                       'Standseilbahnstation',                             'Stacja kolejki linowo-terenowej'),
    ('Chairlift station',                           'Sesselliftstation',                                'Stacja wyciągu krzesełkowego'),
    ('Elevator station',                            'Aufzugstation',                                    'Stacja windy'),
    ('Metro station',                               'Metrostation',                                     'Stacja metra'),
    ('Rack railway station',                        'Zahnradbahnstation',                               'Stacja kolei zębatej'),
    ('Train station',                               'Bahnhof',                                          'Dworzec kolejowy'),
    ('Tram station',                                'Tramhaltestelle',                                  'Przystanek tramwajowy');

-- Preview: one example per type
DO $$
DECLARE
    rec RECORD;
BEGIN
    RAISE NOTICE '';
    RAISE NOTICE '=== Preview (first match per type) ===';
    RAISE NOTICE '';
    FOR rec IN
        SELECT DISTINCT ON (tm.en)
            tm.en                                                       AS type_en,
            p.summary                                                   AS original,
            replace(p.summary, tm.en || ' in ', tm.de || ' in ')        AS de,
            replace(p.summary, tm.en || ' in ', tm.pl || ' w ')         AS pl
        FROM compendium_cat_poi p
        JOIN _type_map tm ON p.summary LIKE '%' || tm.en || ' in %'
        ORDER BY tm.en, p.id
    LOOP
        RAISE NOTICE '  [%]', rec.type_en;
        RAISE NOTICE '    EN: %', rec.original;
        RAISE NOTICE '    DE: %', rec.de;
        RAISE NOTICE '    PL: %', rec.pl;
        RAISE NOTICE '';
    END LOOP;
END $$;

-- Apply: pick longest matching type per POI to avoid substring collisions
-- (e.g. "Bus/Cable car station" must not match the shorter "Bus station")
WITH best_match AS (
    SELECT DISTINCT ON (p.id)
        p.id,
        tm.en,
        tm.de,
        tm.pl
    FROM compendium_cat_poi p
    JOIN _type_map tm ON p.summary LIKE '%' || tm.en || ' in %'
    ORDER BY p.id, length(tm.en) DESC
)
UPDATE compendium_cat_poi p
SET summary_de = replace(p.summary, bm.en || ' in ', bm.de || ' in '),
    summary_pl = replace(p.summary, bm.en || ' in ', bm.pl || ' w '),
    updated_at = now()
FROM best_match bm
WHERE p.id = bm.id;

-- Report
DO $$
DECLARE
    total     INTEGER;
    updated   INTEGER;
    remaining INTEGER;
BEGIN
    SELECT count(*) INTO total FROM compendium_cat_poi;
    SELECT count(*) INTO updated
    FROM compendium_cat_poi WHERE summary_de IS NOT NULL;
    remaining := total - updated;

    RAISE NOTICE '=== Done ===';
    RAISE NOTICE '  Total POIs:     %', total;
    RAISE NOTICE '  Translated:     %', updated;
    IF remaining > 0 THEN
        RAISE NOTICE '  NOT matched:    % (check these manually)', remaining;
    END IF;
    RAISE NOTICE '';
END $$;

-- Show any rows that were NOT matched (should be 0)
DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT summary FROM compendium_cat_poi
        WHERE summary IS NOT NULL AND summary_de IS NULL
        LIMIT 10
    LOOP
        RAISE WARNING '  Unmatched: %', rec.summary;
    END LOOP;
END $$;

DROP TABLE _type_map;

COMMIT;
