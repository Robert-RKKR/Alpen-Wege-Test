# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.schemas.job import JobAdminRead
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, T


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
