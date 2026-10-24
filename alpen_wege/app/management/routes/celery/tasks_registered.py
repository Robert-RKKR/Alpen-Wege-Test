# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.management import celery_info
from app.management.schemas.celery import (
    RegisteredTask,
)
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, cached


@router.get("/tasks/registered", response_model=ApiResponse[list[RegisteredTask]])
async def celery_registered(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await cached("registered", celery_info.collect_registered))
