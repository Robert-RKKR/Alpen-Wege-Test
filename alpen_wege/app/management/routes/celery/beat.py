# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.management import celery_info
from app.management.schemas.celery import (
    BeatEntry,
)
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only


@router.get("/beat", response_model=ApiResponse[list[BeatEntry]])
async def celery_beat(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(celery_info.collect_beat())
