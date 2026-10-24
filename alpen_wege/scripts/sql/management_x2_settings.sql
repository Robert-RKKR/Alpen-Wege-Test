-- Runtime settings table (X2). Idempotent, one transaction.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/management_x2_settings.sql
\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS moddatetime;

CREATE TABLE IF NOT EXISTS mgmt_settings (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    key              varchar(128) NOT NULL UNIQUE,
    value            jsonb        NOT NULL,
    value_type       varchar(16)  NOT NULL,
    default_value    jsonb        NOT NULL,
    min_value        numeric,
    max_value        numeric,
    category         varchar(32)  NOT NULL,
    description      text         NOT NULL,
    requires_restart boolean      NOT NULL DEFAULT false,
    updated_by       uuid REFERENCES profile_usr_user (id) ON DELETE SET NULL,
    created_at       timestamptz  NOT NULL DEFAULT now(),
    updated_at       timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT ck_mgmt_settings_value_type CHECK (value_type IN ('int', 'float', 'bool', 'string'))
);

DROP TRIGGER IF EXISTS trg_set_updated_at ON mgmt_settings;
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON mgmt_settings
    FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');

COMMIT;
