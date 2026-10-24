# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management import celery_info
from app.management.schemas.celery import (
    LiveTask,
)
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, cached, jobs_by_task_id


@router.get("/tasks/active", response_model=ApiResponse[list[LiveTask]])
async def celery_live_tasks(
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    live = await cached("live", celery_info.collect_live)
    jobs = await jobs_by_task_id(db, [t["task_id"] for t in live])
    return ok([{**t, "job": jobs.get(t["task_id"])} for t in live])
