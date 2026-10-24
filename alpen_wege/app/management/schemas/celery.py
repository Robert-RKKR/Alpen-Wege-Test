# Standard library
from datetime import datetime

# Third-party
from pydantic import BaseModel

# Local application
from app.management.schemas.job import JobAdminRead


class CeleryStatus(BaseModel):
    state: str  # ok | no_workers | down
    broker_reachable: bool
    result_backend_reachable: bool
    workers_online: int
    workers: list[str]
    queue_length: int | None = None
    active_tasks: int
    reserved_tasks: int
    scheduled_tasks: int
    beat_entries: int
    checked_at: datetime


class WorkerInfo(BaseModel):
    hostname: str
    pid: int | None = None
    uptime_s: int | None = None
    concurrency: int | None = None
    queues: list[str]
    tasks_executed: dict[str, int]
    registered_tasks: int


class RegisteredTask(BaseModel):
    name: str
    tracked: bool
    job_kind: str | None = None


class LiveTask(BaseModel):
    task_id: str
    name: str | None = None
    worker: str
    state: str  # active | reserved | scheduled
    started_at: datetime | None = None
    eta: str | None = None
    job: JobAdminRead | None = None


class TaskDetail(BaseModel):
    task_id: str
    job: JobAdminRead | None = None
    live_state: str  # active | reserved | scheduled | unknown (not on any worker right now)
    worker: str | None = None
    started_at: datetime | None = None


class BeatEntry(BaseModel):
    name: str
    task: str | None = None
    schedule: str
    next_run_at: datetime | None = None
