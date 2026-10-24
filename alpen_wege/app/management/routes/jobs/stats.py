# Standard library
from datetime import datetime, timedelta, timezone

# Third-party
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.schemas.job import JobStats
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, T


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
