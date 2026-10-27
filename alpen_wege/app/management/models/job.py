# Standard library
import uuid
from datetime import datetime

# Third-party
from sqlalchemy import (
    CheckConstraint,
    DDL,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    event,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Local application
from app.core.base import Base, TimestampMixin


class MgmtLogJob(Base, TimestampMixin):
    __tablename__ = "mgmt_log_job"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="ck_mgmt_log_job_status",
        ),
        CheckConstraint(
            "progress IS NULL OR progress BETWEEN 0 AND 100",
            name="ck_mgmt_log_job_progress",
        ),
        Index("ix_mgmt_log_job_user_created", "user_id", text("created_at DESC")),
        Index("ix_mgmt_log_job_subject", "subject_type", "subject_id"),
        Index("ix_mgmt_log_job_finished", "finished_at", postgresql_where=text("finished_at IS NOT NULL")),
        Index("ix_mgmt_log_job_active", "updated_at", postgresql_where=text("status IN ('queued', 'running')")),
        Index(
            "ux_mgmt_log_job_active_subject", "kind", "subject_type", "subject_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running') AND subject_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        server_default=func.gen_random_uuid(),
        comment="Job id. Also the Celery task id of the first task of the job (supplied by the application).",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profile_usr_user.id", ondelete="SET NULL"),
        nullable=True,
        comment="Owner. NULL for system or admin-script jobs, which only the management API shows.",
    )
    kind: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="What the job does, for example 'track.process'.",
    )
    task_name: Mapped[str] = mapped_column(
        String(128), nullable=False,
        comment="Celery task name of the first task.",
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="queued",
        comment="queued, running, succeeded, failed or cancelled. Terminal states are final.",
    )
    stage: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Machine name of the current step.",
    )
    progress: Mapped[int | None] = mapped_column(
        SmallInteger, nullable=True,
        comment="0 to 100, written when the stage or status changes (finer values only go through Redis).",
    )
    subject_type: Mapped[str | None] = mapped_column(
        String(64), nullable=True,
        comment="Type of the object the job is about, for example 'track'.",
    )
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        nullable=True,
        comment="Id of the object the job is about.",
    )
    result: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Small summary for the client. Never large data.",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Safe text for the user. Technical details are only in the worker log.",
    )
    attempts: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0",
        comment="Number of times the first task started.",
    )
    worker_hostname: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
        comment="Worker that ran the job last.",
    )
    request_id: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="HTTP request id that started the job (same value as mgmt_log_event.request_id).",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="First start of a worker.",
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
        comment="When the job reached a terminal state.",
    )

    user = relationship("ProfileUsrUser", foreign_keys=[user_id], lazy="raise", viewonly=True)


# Keeps updated_at current on every UPDATE (the stale-job check depends on it). Only runs when
# create_all creates the table; scripts/sql/management_x3_jobs.sql creates the same trigger.
event.listen(
    MgmtLogJob.__table__,
    "after_create",
    DDL(
        "CREATE TRIGGER trg_set_updated_at BEFORE UPDATE ON mgmt_log_job "
        "FOR EACH ROW EXECUTE FUNCTION moddatetime('updated_at')"
    ),
)
