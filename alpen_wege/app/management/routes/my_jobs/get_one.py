# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.models.job import MgmtLogJob
from app.management.schemas.job import JobRead
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("/{job_id}", response_model=ApiResponse[JobRead])
async def get_my_job(
    job_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    job = await db.get(MgmtLogJob, job_id)
    if job is None or job.user_id != user.id:
        # Same answer for "not found" and "not yours"
        raise AppError(404, "Not found", error_message="The job does not exist or you do not have access to it.")
    return ok(job)
