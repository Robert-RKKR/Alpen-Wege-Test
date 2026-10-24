# Standard library
import uuid
from typing import Any

# Third-party
from sqlalchemy import func, null, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Local application
from app.core.utils.responses import request_id_ctx
from app.management.models.job import MgmtLogJob

ACTIVE = ("queued", "running")
_T = MgmtLogJob.__table__


def _first(result) -> dict | None:
    row = result.mappings().first()
    return dict(row) if row is not None else None


def _insert(user_id, kind, task_name, subject_type, subject_id):
    return pg_insert(_T).values(
        id=uuid.uuid4(), user_id=user_id, kind=kind, task_name=task_name, status="queued",
        subject_type=subject_type, subject_id=subject_id,
        request_id=request_id_ctx.get("") or None,
    )


def _insert_if_free(user_id, kind, task_name, subject_type, subject_id):
    # ON CONFLICT DO NOTHING without a target: the only unique rule that can fire here is
    # ux_mgmt_log_job_active_subject (the primary key is a fresh uuid). No predicate to keep in sync.
    return _insert(user_id, kind, task_name, subject_type, subject_id).on_conflict_do_nothing().returning(*_T.c)


def _active_for(kind, subject_type, subject_id):
    return select(_T).where(
        _T.c.kind == kind, _T.c.subject_type == subject_type,
        _T.c.subject_id == subject_id, _T.c.status.in_(ACTIVE),
    )


def _active_update(job_id):
    return update(_T).where(_T.c.id == job_id, _T.c.status.in_(ACTIVE))


# ---------------------------------------------------------------- async (API routes)

async def create_job(db, *, user_id, kind, task_name, subject_type=None, subject_id=None) -> dict:
    # Insert a queued job (flush only; the caller commits). Returns the row as a dict.
    # Raises IntegrityError if an active job already exists for the same (kind, subject).
    result = await db.execute(_insert(user_id, kind, task_name, subject_type, subject_id).returning(*_T.c))
    return dict(result.mappings().one())


async def get_or_create_active_job(db, *, user_id, kind, task_name, subject_type, subject_id) -> tuple[dict, bool]:
    # Return (job, created). Reuses the queued or running job of this (kind, subject).
    for _ in range(3):
        row = _first(await db.execute(_insert_if_free(user_id, kind, task_name, subject_type, subject_id)))
        if row is not None:
            return row, True
        existing = _first(await db.execute(_active_for(kind, subject_type, subject_id)))
        if existing is not None:
            return existing, False
    raise RuntimeError("Could not create or find an active job")


async def fail_job(db, job_id, message: str) -> dict | None:
    # For routes that could not enqueue the task: the job must not hang in 'queued'.
    # Flush only; the caller commits (and publishes the returned row). None if it was not active.
    result = await db.execute(
        update(_T).where(_T.c.id == job_id, _T.c.status.in_(ACTIVE)).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    )
    return _first(result)


async def fail_active_jobs_for_subject(db, *, kind, subject_type, subject_id, message: str) -> list[dict]:
    # Fail every queued or running job of this (kind, subject). Used by routes that hold a lock
    # proving no run can be in progress (rescan), so a leftover job cannot block the new one.
    # Flush only; the caller commits and publishes the returned rows.
    result = await db.execute(
        update(_T).where(
            _T.c.kind == kind, _T.c.subject_type == subject_type,
            _T.c.subject_id == subject_id, _T.c.status.in_(ACTIVE),
        ).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    )
    return [dict(r) for r in result.mappings().all()]


# ---------------------------------------------------------------- sync (worker, reaper, scripts)

def create_job_sync(session, *, user_id, kind, task_name, subject_type=None, subject_id=None) -> dict:
    result = session.execute(_insert(user_id, kind, task_name, subject_type, subject_id).returning(*_T.c))
    return dict(result.mappings().one())


def get_or_create_active_job_sync(session, *, user_id, kind, task_name, subject_type, subject_id) -> tuple[dict, bool]:
    for _ in range(3):
        row = _first(session.execute(_insert_if_free(user_id, kind, task_name, subject_type, subject_id)))
        if row is not None:
            return row, True
        existing = _first(session.execute(_active_for(kind, subject_type, subject_id)))
        if existing is not None:
            return existing, False
    raise RuntimeError("Could not create or find an active job")


def requeue_or_create_job_sync(session, *, user_id, kind, task_name, subject_type, subject_id) -> tuple[dict, bool]:
    # For the reaper: reuse the active job of the subject (a running one goes back to queued)
    # or create a new one. Returns (job, changed); changed is True if the job was created or
    # moved back to queued (publish an event only then). The caller enqueues with task_id = job["id"].
    job, created = get_or_create_active_job_sync(
        session, user_id=user_id, kind=kind, task_name=task_name,
        subject_type=subject_type, subject_id=subject_id,
    )
    if created:
        return job, True
    if job["status"] == "running":
        requeued = mark_queued_again(session, job["id"], stage="requeued")
        return (requeued or job), requeued is not None
    return job, False


def mark_running(
    session, job_id, *, hostname: str | None = None, stage: str | None = None, first_task: bool = True,
) -> dict | None:
    # first_task=True : the first task of a job. Only a *queued* job is started, so a duplicate
    #                   delivery (or a skipped run) cannot bump `attempts` or reset the stage of a
    #                   run in progress. Retries and the reaper move the job back to queued first.
    # first_task=False: a continuation task (detect_pois): the job is running, keep it running.
    values: dict[str, Any] = {
        "status": "running",
        "started_at": func.coalesce(_T.c.started_at, func.now()),
    }
    if first_task:
        values["attempts"] = _T.c.attempts + 1
    if hostname:
        values["worker_hostname"] = hostname[:128]
    if stage:
        values["stage"] = stage
    if first_task:
        stmt = update(_T).where(_T.c.id == job_id, _T.c.status == "queued")
    else:
        stmt = _active_update(job_id)
    return _first(session.execute(stmt.values(**values).returning(*_T.c)))


def mark_progress(session, job_id, *, stage: str | None, progress: int | None) -> dict | None:
    values: dict[str, Any] = {}
    if stage is not None:
        values["stage"] = stage
    if progress is not None:
        values["progress"] = max(0, min(100, int(progress)))
    if not values:
        return None
    return _first(session.execute(_active_update(job_id).values(**values).returning(*_T.c)))


def mark_succeeded(session, job_id, result: dict | None) -> dict | None:
    return _first(session.execute(
        _active_update(job_id).values(
            status="succeeded", progress=100, stage="done",
            result=result if result is not None else null(),  # SQL NULL, not JSON null
            error_message=None, finished_at=func.now(),
        ).returning(*_T.c)
    ))


def mark_failed(session, job_id, message: str) -> dict | None:
    return _first(session.execute(
        _active_update(job_id).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    ))


def mark_queued_again(session, job_id, *, stage: str | None = None) -> dict | None:
    values: dict[str, Any] = {"status": "queued"}
    if stage:
        values["stage"] = stage
    return _first(session.execute(_active_update(job_id).values(**values).returning(*_T.c)))


def fail_active_job_for_subject(session, *, kind, subject_type, subject_id, message: str) -> dict | None:
    # Used by domain code that fails the subject itself (mark_failed, reaper) so the job follows.
    return _first(session.execute(
        update(_T).where(
            _T.c.kind == kind, _T.c.subject_type == subject_type,
            _T.c.subject_id == subject_id, _T.c.status.in_(ACTIVE),
        ).values(
            status="failed", error_message=(message or "")[:2000], finished_at=func.now(),
        ).returning(*_T.c)
    ))


def fail_stale_jobs(session, hours: int) -> list[dict]:
    result = session.execute(
        update(_T).where(
            _T.c.status.in_(ACTIVE),
            _T.c.updated_at < func.now() - func.make_interval(0, 0, 0, 0, hours),
        ).values(
            status="failed", error_message="The job did not finish in time.", finished_at=func.now(),
        ).returning(*_T.c)
    )
    return [dict(r) for r in result.mappings().all()]
