# Standard library
from datetime import datetime
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok_list
from app.management.jobs.kinds import JOB_STATUSES
from app.management.schemas.job import JobAdminRead
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, T


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
