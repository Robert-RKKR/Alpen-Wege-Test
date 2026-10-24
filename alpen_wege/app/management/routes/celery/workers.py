# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.management import celery_info
from app.management.schemas.celery import (
    WorkerInfo,
)
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, cached


@router.get("/workers", response_model=ApiResponse[list[WorkerInfo]])
async def celery_workers(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await cached("workers", celery_info.collect_workers))
