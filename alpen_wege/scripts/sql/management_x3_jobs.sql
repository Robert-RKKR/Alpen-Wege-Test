-- Job log table (X3). Idempotent, one transaction.
--   sudo docker exec -i alpen-postgres psql -U alpenwege -d alpenwege < scripts/sql/management_x3_jobs.sql
\set ON_ERROR_STOP on
BEGIN;

CREATE EXTENSION IF NOT EXISTS moddatetime;

CREATE TABLE IF NOT EXISTS mgmt_log_job (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),   -- the app always supplies it (= Celery task id)
    user_id         uuid REFERENCES profile_usr_user (id) ON DELETE SET NULL,
    kind            varchar(64)  NOT NULL,
    task_name       varchar(128) NOT NULL,
    status          varchar(16)  NOT NULL DEFAULT 'queued',
    stage           varchar(64),
    progress        smallint,
    subject_type    varchar(64),
    subject_id      uuid,
    result          jsonb,
    error_message   text,
    attempts        smallint     NOT NULL DEFAULT 0,
    worker_hostname varchar(128),
    request_id      text,
    created_at      timestamptz  NOT NULL DEFAULT now(),
    started_at      timestamptz,
    finished_at     timestamptz,
    updated_at      timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT ck_mgmt_log_job_status
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')),
    CONSTRAINT ck_mgmt_log_job_progress
        CHECK (progress IS NULL OR progress BETWEEN 0 AND 100)
);

CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_user_created ON mgmt_log_job (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_subject ON mgmt_log_job (subject_type, subject_id);
CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_finished ON mgmt_log_job (finished_at) WHERE finished_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_mgmt_log_job_active ON mgmt_log_job (updated_at) WHERE status IN ('queued', 'running');
-- one active job per (kind, subject): reaper, restore and reprocess reuse it, races are settled here
CREATE UNIQUE INDEX IF NOT EXISTS ux_mgmt_log_job_active_subject
    ON mgmt_log_job (kind, subject_type, subject_id)
    WHERE status IN ('queued', 'running') AND subject_id IS NOT NULL;

DROP TRIGGER IF EXISTS trg_set_updated_at ON mgmt_log_job;
CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON mgmt_log_job
    FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at');

COMMIT;
