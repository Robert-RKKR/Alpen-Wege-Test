# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok_list
from app.management.jobs.kinds import JOB_STATUSES
from app.management.models.job import MgmtLogJob
from app.management.schemas.job import JobRead
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("", response_model=ApiResponse[list[JobRead]])
async def list_my_jobs(
    limit: int = 100,
    offset: int = 0,
    status: str | None = None,
    kind: str | None = None,
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    active: bool = False,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 500))
    if status is not None and status not in JOB_STATUSES:
        raise AppError(422, f"Invalid status: {status}")

    base = select(MgmtLogJob).where(MgmtLogJob.user_id == user.id)
    if status:
        base = base.where(MgmtLogJob.status == status)
    if active:
        base = base.where(MgmtLogJob.status.in_(("queued", "running")))
    if kind:
        base = base.where(MgmtLogJob.kind == kind)
    if subject_type:
        base = base.where(MgmtLogJob.subject_type == subject_type)
    if subject_id:
        base = base.where(MgmtLogJob.subject_id == subject_id)

    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(
        base.order_by(MgmtLogJob.created_at.desc()).limit(limit).offset(offset)
    )).scalars().all()
    return ok_list(rows, total=total, limit=limit, offset=offset)
