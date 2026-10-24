-- Management move (X1): core_log_event -> mgmt_log_event, core_ref_entity_type -> mgmt_ref_entity_type.
-- Idempotent, one transaction. Run with api and worker STOPPED:
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/management_x1_move.sql
\set ON_ERROR_STOP on
BEGIN;

-- 0. Remember row count and highest seq of the event log (checked at the end)
CREATE TEMP TABLE _x1_before (n bigint, max_seq bigint) ON COMMIT DROP;
DO $$
BEGIN
    IF to_regclass('public.core_log_event') IS NOT NULL THEN
        INSERT INTO _x1_before SELECT count(*), coalesce(max(seq), 0) FROM core_log_event;
    ELSIF to_regclass('public.mgmt_log_event') IS NOT NULL THEN
        INSERT INTO _x1_before SELECT count(*), coalesce(max(seq), 0) FROM mgmt_log_event;
    ELSE
        RAISE EXCEPTION 'Neither core_log_event nor mgmt_log_event exists';
    END IF;
END $$;

-- 1. Rename the tables
DO $$
BEGIN
    IF to_regclass('public.core_ref_entity_type') IS NOT NULL THEN
        IF to_regclass('public.mgmt_ref_entity_type') IS NOT NULL THEN
            RAISE EXCEPTION 'Both core_ref_entity_type and mgmt_ref_entity_type exist; drop the empty mgmt table first';
        END IF;
        ALTER TABLE core_ref_entity_type RENAME TO mgmt_ref_entity_type;
    END IF;
    IF to_regclass('public.core_log_event') IS NOT NULL THEN
        IF to_regclass('public.mgmt_log_event') IS NOT NULL THEN
            RAISE EXCEPTION 'Both core_log_event and mgmt_log_event exist; drop the empty mgmt table first';
        END IF;
        ALTER TABLE core_log_event RENAME TO mgmt_log_event;
    END IF;
END $$;

-- 2. Rename constraints (this also renames the index behind a primary key or unique constraint)
DO $$
DECLARE r record; new_name text;
BEGIN
    FOR r IN
        SELECT c.conrelid::regclass::text AS tbl, c.conname
          FROM pg_constraint c
         WHERE c.conrelid IN ('public.mgmt_log_event'::regclass, 'public.mgmt_ref_entity_type'::regclass)
           AND c.conname ~ 'core_(log_event|ref_entity_type)'
    LOOP
        new_name := regexp_replace(r.conname, 'core_(log_event|ref_entity_type)', 'mgmt_\1');
        EXECUTE format('ALTER TABLE %s RENAME CONSTRAINT %I TO %I', r.tbl, r.conname, new_name);
        RAISE NOTICE 'constraint % -> %', r.conname, new_name;
    END LOOP;
END $$;

-- 3. Rename the remaining indexes
DO $$
DECLARE r record; new_name text;
BEGIN
    FOR r IN
        SELECT i.indexname
          FROM pg_indexes i
         WHERE i.schemaname = 'public'
           AND i.tablename IN ('mgmt_log_event', 'mgmt_ref_entity_type')
           AND i.indexname ~ 'core_(log_event|ref_entity_type)'
    LOOP
        new_name := regexp_replace(r.indexname, 'core_(log_event|ref_entity_type)', 'mgmt_\1');
        EXECUTE format('ALTER INDEX public.%I RENAME TO %I', r.indexname, new_name);
        RAISE NOTICE 'index % -> %', r.indexname, new_name;
    END LOOP;
END $$;

-- 4. Rename the identity sequence of mgmt_log_event.seq (cosmetic: a failure only prints a notice)
DO $$
DECLARE r record; new_name text;
BEGIN
    FOR r IN
        SELECT sequencename FROM pg_sequences
         WHERE schemaname = 'public' AND sequencename ~ '^core_log_event'
    LOOP
        new_name := regexp_replace(r.sequencename, '^core_log_event', 'mgmt_log_event');
        BEGIN
            EXECUTE format('ALTER SEQUENCE public.%I RENAME TO %I', r.sequencename, new_name);
            RAISE NOTICE 'sequence % -> %', r.sequencename, new_name;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'sequence % not renamed: %', r.sequencename, SQLERRM;
        END;
    END LOOP;
END $$;

-- 5. The entity type rows follow their tables (the seed does not update key, module or display_name)
UPDATE mgmt_ref_entity_type
   SET key = 'mgmt_log_event', module = 'mgmt', display_name = 'Event'
 WHERE key = 'core_log_event'
   AND NOT EXISTS (SELECT 1 FROM mgmt_ref_entity_type WHERE key = 'mgmt_log_event');
UPDATE mgmt_ref_entity_type
   SET key = 'mgmt_ref_entity_type', module = 'mgmt', display_name = 'Entity Type'
 WHERE key = 'core_ref_entity_type'
   AND NOT EXISTS (SELECT 1 FROM mgmt_ref_entity_type WHERE key = 'mgmt_ref_entity_type');

-- 6. Index for the retention job (X6)
CREATE INDEX IF NOT EXISTS ix_mgmt_log_event_changed_at ON mgmt_log_event (changed_at);

-- 7. Verification: nothing lost, nothing left behind
DO $$
DECLARE b record; a record; left_over int;
BEGIN
    SELECT * INTO b FROM _x1_before;
    SELECT count(*) AS n, coalesce(max(seq), 0) AS max_seq INTO a FROM mgmt_log_event;
    IF a.n <> b.n OR a.max_seq <> b.max_seq THEN
        RAISE EXCEPTION 'Event log changed: before % rows / max seq %, after % rows / max seq %',
            b.n, b.max_seq, a.n, a.max_seq;
    END IF;
    SELECT count(*) INTO left_over FROM pg_class
     WHERE relname ~ 'core_(log_event|ref_entity_type)' AND relkind <> 'S';
    IF left_over > 0 THEN
        RAISE EXCEPTION '% objects are still named core_log_event / core_ref_entity_type', left_over;
    END IF;
    RAISE NOTICE 'OK: % events, max seq %', a.n, a.max_seq;
END $$;

COMMIT;
