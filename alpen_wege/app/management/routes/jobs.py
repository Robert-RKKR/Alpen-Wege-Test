# Standard library
from datetime import datetime, timedelta, timezone
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok, ok_list
from app.management.jobs.kinds import JOB_STATUSES
from app.management.models.job import MgmtLogJob
from app.management.schemas.job import JobAdminRead, JobStats
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups

router = APIRouter(prefix="/jobs", tags=["Management - Jobs"])
admin_only = require_groups("administrator")
T = MgmtLogJob


@router.get("", response_model=ApiResponse[list[JobAdminRead]])
async def list_all_jobs(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    kind: str | None = None,
    user_id: UUID | None = None,
    task_name: str | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    active: bool = False,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    if status is not None and status not in JOB_STATUSES:
        raise AppError(422, f"Invalid status: {status}")
    base = select(T)
    for condition, value in (
        (T.status == status, status), (T.kind == kind, kind), (T.user_id == user_id, user_id),
        (T.task_name == task_name, task_name), (T.subject_type == subject_type, subject_type),
        (T.subject_id == subject_id, subject_id), (T.created_at >= created_from, created_from),
        (T.created_at < created_to, created_to),
    ):
        if value is not None:
            base = base.where(condition)
    if active:
        base = base.where(T.status.in_(("queued", "running")))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(base.order_by(T.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return ok_list(rows, total=total, limit=limit, offset=offset)


# declared before "/{job_id}" on purpose: "stats" must not be parsed as a job id
@router.get("/stats", response_model=ApiResponse[JobStats])
async def job_stats(
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    by_status: dict[str, int] = {}
    by_kind: dict[str, dict[str, int]] = {}
    for kind, status, n in (await db.execute(select(T.kind, T.status, func.count()).group_by(T.kind, T.status))).all():
        by_status[status] = by_status.get(status, 0) + n
        by_kind.setdefault(kind, {})[status] = n
    failed_24h = (await db.execute(
        select(func.count()).where(T.status == "failed", T.finished_at > now - timedelta(hours=24))
    )).scalar_one()
    oldest = (await db.execute(select(func.min(T.created_at)).where(T.status == "queued"))).scalar_one()
    avg_rows = (await db.execute(
        select(T.kind, func.avg(func.extract("epoch", T.finished_at - T.started_at)))
        .where(T.status == "succeeded", T.started_at.isnot(None), T.finished_at > now - timedelta(days=7))
        .group_by(T.kind)
    )).all()
    return ok(JobStats(
        by_status=by_status, by_kind=by_kind, failed_last_24h=failed_24h, oldest_queued_at=oldest,
        avg_duration_s_by_kind={k: round(float(v), 2) for k, v in avg_rows if v is not None},
    ))


@router.get("/{job_id}", response_model=ApiResponse[JobAdminRead])
async def get_any_job(
    job_id: UUID,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(T, job_id)
    if job is None:
        raise AppError(404, "Not found", error_message="No job exists with this id.")
    return ok(job)
