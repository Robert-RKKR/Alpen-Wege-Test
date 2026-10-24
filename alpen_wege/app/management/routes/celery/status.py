# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.management import celery_info
from app.management.schemas.celery import (
    CeleryStatus,
)
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, cached


@router.get("/status", response_model=ApiResponse[CeleryStatus])
async def celery_status(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await cached("status", celery_info.collect_status))
