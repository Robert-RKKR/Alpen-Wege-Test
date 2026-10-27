# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.schemas.job import JobAdminDetail
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, T


@router.get("/{job_id}", response_model=ApiResponse[JobAdminDetail])
async def get_any_job(
    job_id: UUID,
    _admin: ProfileUsrUser = Depends(admin_only),
    plan: ExpandPlan = Depends(expand_plan(JobAdminDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(T).where(T.id == job_id).options(*plan.load_options(T))
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise AppError(404, "Not found", error_message="No job exists with this id.")
    # JobRead builds "subject" from subject_type and subject_id
    return ok(plan.render(job, viewer=_admin, subject=None, subject_type=job.subject_type, subject_id=job.subject_id))
