# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management import celery_info
from app.management.schemas.celery import (
    TaskDetail,
)
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, cached, jobs_by_task_id


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskDetail])
async def celery_task_detail(
    task_id: str,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    live = {t["task_id"]: t for t in await cached("live", celery_info.collect_live)}.get(task_id)
    job = (await jobs_by_task_id(db, [task_id])).get(task_id)
    if live is None and job is None:
        raise AppError(404, "Not found", error_message="No job and no live task with this id.")
    return ok({
        "task_id": task_id,
        "job": job,
        "live_state": live["state"] if live else "unknown",
        "worker": live["worker"] if live else None,
        "started_at": live["started_at"] if live else None,
    })
