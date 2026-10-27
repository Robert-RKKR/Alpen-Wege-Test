# Standard library
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

# Third-party
from pydantic import BaseModel, ConfigDict, model_validator

from app.core.utils.expand import Link
from app.profile.schemas.user_read import ExpandedUser


class JobSubject(BaseModel):
    type: str
    id: UUID


class JobRead(BaseModel):
    # One shape for REST and WebSocket. Accepts an ORM object or a row mapping.
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    kind: str
    status: str
    stage: str | None = None
    progress: int | None = None
    subject: JobSubject | None = None
    result: dict | None = None
    error_message: str | None = None
    attempts: int = 0
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _build(cls, value):
        if isinstance(value, Mapping):
            get = value.get
        else:
            def get(name, default=None):
                return getattr(value, name, default)
        data = {name: get(name) for name in cls.model_fields if name != "subject"}
        subject_type, subject_id = get("subject_type"), get("subject_id")
        data["subject"] = {"type": subject_type, "id": subject_id} if subject_type and subject_id else None
        return data


class JobAdminRead(JobRead):
    user_id: UUID | None = None
    task_name: str
    worker_hostname: str | None = None
    request_id: str | None = None


class JobAdminDetail(JobAdminRead):
    user: ExpandedUser | None = Link()


class JobAccepted(BaseModel):
    job_id: UUID


class JobStats(BaseModel):
    by_status: dict[str, int]
    by_kind: dict[str, dict[str, int]]
    failed_last_24h: int
    oldest_queued_at: datetime | None = None
    avg_duration_s_by_kind: dict[str, float]
