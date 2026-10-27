-- Explorer hierarchy, phase 0 DDL: rank on 4 reference tables, nullable route classification,
-- RESTRICT foreign keys and unique rules on segment_route and route_journey.
-- Idempotent, one transaction. For the TEST database (a fresh create_all database already has all of this).
-- Run: sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/hierarchy_phase0_ddl.sql
\set ON_ERROR_STOP on
BEGIN;

-- 1. rank (higher = harder, rarer or worse) --------------------------------------------------------
ALTER TABLE core_ref_difficulty_level ADD COLUMN IF NOT EXISTS rank smallint;
ALTER TABLE core_ref_difficulty_sport ADD COLUMN IF NOT EXISTS rank smallint;
ALTER TABLE core_ref_rarity           ADD COLUMN IF NOT EXISTS rank smallint;
ALTER TABLE core_ref_visibility       ADD COLUMN IF NOT EXISTS rank smallint;

UPDATE core_ref_difficulty_level t SET rank = v.r
  FROM (VALUES ('difficulty_very_easy', 1), ('difficulty_easy', 2), ('difficulty_moderate', 3), ('difficulty_difficult', 4),
               ('difficulty_very_difficult', 5), ('difficulty_expert', 6), ('difficulty_extreme', 7)) AS v(icon, r)
 WHERE t.icon = v.icon AND t.rank IS NULL;

UPDATE core_ref_rarity t SET rank = v.r
  FROM (VALUES ('rarity_common', 1), ('rarity_uncommon', 2), ('rarity_rare', 3), ('rarity_epic', 4),
               ('rarity_legendary', 5), ('rarity_mythic', 6)) AS v(icon, r)
 WHERE t.icon = v.icon AND t.rank IS NULL;

UPDATE core_ref_visibility t SET rank = v.r
  FROM (VALUES ('visibility_excellent', 1), ('visibility_very_good', 2), ('visibility_good', 3), ('visibility_moderate', 4),
               ('visibility_poor', 5), ('visibility_low', 6), ('visibility_very_low', 7), ('visibility_whiteout', 8)) AS v(icon, r)
 WHERE t.icon = v.icon AND t.rank IS NULL;

-- difficulty_sport: the order of point_factor inside one sport type (equal point_factor = equal rank)
UPDATE core_ref_difficulty_sport t SET rank = d.r
  FROM (SELECT id, dense_rank() OVER (PARTITION BY sport_type_id ORDER BY point_factor) AS r
          FROM core_ref_difficulty_sport) d
 WHERE t.id = d.id AND t.rank IS NULL;

-- rows that were added by hand (other icon): the order of point_factor inside the table
UPDATE core_ref_difficulty_level t SET rank = d.r
  FROM (SELECT id, dense_rank() OVER (ORDER BY point_factor) AS r FROM core_ref_difficulty_level) d WHERE t.id = d.id AND t.rank IS NULL;
UPDATE core_ref_rarity t SET rank = d.r
  FROM (SELECT id, dense_rank() OVER (ORDER BY point_factor) AS r FROM core_ref_rarity) d WHERE t.id = d.id AND t.rank IS NULL;
UPDATE core_ref_visibility t SET rank = d.r
  FROM (SELECT id, dense_rank() OVER (ORDER BY point_factor) AS r FROM core_ref_visibility) d WHERE t.id = d.id AND t.rank IS NULL;

ALTER TABLE core_ref_difficulty_level ALTER COLUMN rank SET NOT NULL;
ALTER TABLE core_ref_difficulty_sport ALTER COLUMN rank SET NOT NULL;
ALTER TABLE core_ref_rarity           ALTER COLUMN rank SET NOT NULL;
ALTER TABLE core_ref_visibility       ALTER COLUMN rank SET NOT NULL;

COMMENT ON COLUMN core_ref_difficulty_level.rank IS 'Position of this value on the scale of its table. A higher number means harder, rarer or worse. Equal numbers are allowed (equivalent values). For difficulty_sport the scale is per sport_type_id: only grades of the same sport type can be compared. Used to find the hardest value, for example the difficulty of a route.';
COMMENT ON COLUMN core_ref_difficulty_sport.rank IS 'Position of this value on the scale of its table. A higher number means harder, rarer or worse. Equal numbers are allowed (equivalent values). For difficulty_sport the scale is per sport_type_id: only grades of the same sport type can be compared. Used to find the hardest value, for example the difficulty of a route.';
COMMENT ON COLUMN core_ref_rarity.rank IS 'Position of this value on the scale of its table. A higher number means harder, rarer or worse. Equal numbers are allowed (equivalent values). For difficulty_sport the scale is per sport_type_id: only grades of the same sport type can be compared. Used to find the hardest value, for example the difficulty of a route.';
COMMENT ON COLUMN core_ref_visibility.rank IS 'Position of this value on the scale of its table. A higher number means harder, rarer or worse. Equal numbers are allowed (equivalent values). For difficulty_sport the scale is per sport_type_id: only grades of the same sport type can be compared. Used to find the hardest value, for example the difficulty of a route.';

-- 2. route: classification may be empty (draft route without segments) ---------------------------------
ALTER TABLE explorer_agg_route ALTER COLUMN sport_type_id DROP NOT NULL;
ALTER TABLE explorer_agg_route ALTER COLUMN difficulty_level_id DROP NOT NULL;
ALTER TABLE explorer_agg_route ALTER COLUMN difficulty_sport_id DROP NOT NULL;

COMMENT ON COLUMN explorer_agg_route.sport_type_id IS 'FK to core_ref_sport_type. The primary sport activity for this route (e.g. hiking, trail running). NULL while the route has no segments (draft); set from the segments on the first save and never overwritten afterwards.';
COMMENT ON COLUMN explorer_agg_route.difficulty_level_id IS 'FK to core_ref_difficulty_level. General difficulty classification for this route. NULL while unknown; derived from the segment with the highest rank when empty.';
COMMENT ON COLUMN explorer_agg_route.difficulty_sport_id IS 'FK to core_ref_difficulty_sport. Sport-specific difficulty grading for this route. NULL while unknown; derived from the highest-ranked grade of the segments of the primary sport when empty.';

-- 3. segment_route: a used segment cannot be deleted; unique slot rows; one default per group ---------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM explorer_m2m_segment_route GROUP BY route_id, slot_position, segment_id HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'explorer_m2m_segment_route has duplicate (route_id, slot_position, segment_id) rows';
    END IF;
    IF EXISTS (SELECT 1 FROM explorer_m2m_segment_route WHERE is_default GROUP BY route_id, alt_group HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'explorer_m2m_segment_route has an alternative group with more than one default';
    END IF;
    IF EXISTS (SELECT 1 FROM explorer_m2m_route_journey GROUP BY journey_id, slot_position HAVING count(*) > 1) THEN
        RAISE EXCEPTION 'explorer_m2m_route_journey has two routes on the same day of a journey';
    END IF;
END $$;

ALTER TABLE explorer_m2m_segment_route DROP CONSTRAINT IF EXISTS explorer_m2m_segment_route_segment_id_fkey;
ALTER TABLE explorer_m2m_segment_route
    ADD CONSTRAINT explorer_m2m_segment_route_segment_id_fkey
    FOREIGN KEY (segment_id) REFERENCES explorer_agg_segment (id) ON DELETE RESTRICT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_segment_route_slot_segment') THEN
        ALTER TABLE explorer_m2m_segment_route
            ADD CONSTRAINT uq_segment_route_slot_segment UNIQUE (route_id, slot_position, segment_id);
    END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_segment_route_one_default
    ON explorer_m2m_segment_route (route_id, alt_group) WHERE is_default;
CREATE INDEX IF NOT EXISTS ix_segment_route_segment_id ON explorer_m2m_segment_route (segment_id);

COMMENT ON COLUMN explorer_m2m_segment_route.segment_id IS 'FK to explorer_agg_segment with RESTRICT delete: a segment that is used by a route cannot be deleted. The trail segment included in this route.';

-- 4. route_journey: a used route cannot be deleted; one route per day ----------------------------------
ALTER TABLE explorer_m2m_route_journey DROP CONSTRAINT IF EXISTS explorer_m2m_route_journey_route_id_fkey;
ALTER TABLE explorer_m2m_route_journey
    ADD CONSTRAINT explorer_m2m_route_journey_route_id_fkey
    FOREIGN KEY (route_id) REFERENCES explorer_agg_route (id) ON DELETE RESTRICT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_route_journey_day') THEN
        ALTER TABLE explorer_m2m_route_journey
            ADD CONSTRAINT uq_route_journey_day UNIQUE (journey_id, slot_position);
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_route_journey_route_id ON explorer_m2m_route_journey (route_id);

COMMENT ON COLUMN explorer_m2m_route_journey.route_id IS 'FK to explorer_agg_route with RESTRICT delete: a route that is used by a journey cannot be deleted. The planned route assigned to this day or stage of the journey.';

COMMIT;
