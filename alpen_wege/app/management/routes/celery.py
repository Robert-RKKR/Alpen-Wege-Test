# Standard library
import json
import uuid

# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management import celery_info
from app.management.models.job import MgmtLogJob
from app.management.runtime_settings.service import get_setting
from app.management.schemas.celery import (
    BeatEntry, CeleryStatus, LiveTask, RegisteredTask, TaskDetail, WorkerInfo,
)
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups
from app.redis import get_redis_pool

router = APIRouter(prefix="/celery", tags=["Management - Celery"])
admin_only = require_groups("administrator")


async def _cached(key: str, collector):
    # Run a blocking collector in a threadpool; cache the JSON answer in Redis.
    ttl = await get_setting("celery.status_cache_s")
    redis = get_redis_pool()
    if ttl > 0:
        raw = await redis.get(f"aw:celery:{key}")
        if raw:
            return json.loads(raw)
    data = await run_in_threadpool(collector)
    if ttl > 0:
        await redis.set(f"aw:celery:{key}", json.dumps(data), ex=ttl)
    return data


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


async def _jobs_by_task_id(db: AsyncSession, task_ids: list[str]) -> dict[str, MgmtLogJob]:
    ids = [u for u in (_uuid_or_none(t) for t in task_ids) if u]
    if not ids:
        return {}
    rows = (await db.execute(select(MgmtLogJob).where(MgmtLogJob.id.in_(ids)))).scalars().all()
    return {str(r.id): r for r in rows}


@router.get("/status", response_model=ApiResponse[CeleryStatus])
async def celery_status(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await _cached("status", celery_info.collect_status))


@router.get("/workers", response_model=ApiResponse[list[WorkerInfo]])
async def celery_workers(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await _cached("workers", celery_info.collect_workers))


# "/tasks/registered" and "/tasks/active" are declared before "/tasks/{task_id}" on purpose
@router.get("/tasks/registered", response_model=ApiResponse[list[RegisteredTask]])
async def celery_registered(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(await _cached("registered", celery_info.collect_registered))


@router.get("/tasks/active", response_model=ApiResponse[list[LiveTask]])
async def celery_live_tasks(
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    live = await _cached("live", celery_info.collect_live)
    jobs = await _jobs_by_task_id(db, [t["task_id"] for t in live])
    return ok([{**t, "job": jobs.get(t["task_id"])} for t in live])


@router.get("/tasks/{task_id}", response_model=ApiResponse[TaskDetail])
async def celery_task_detail(
    task_id: str,
    _admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    live = {t["task_id"]: t for t in await _cached("live", celery_info.collect_live)}.get(task_id)
    job = (await _jobs_by_task_id(db, [task_id])).get(task_id)
    if live is None and job is None:
        raise AppError(404, "Not found", error_message="No job and no live task with this id.")
    return ok({
        "task_id": task_id,
        "job": job,
        "live_state": live["state"] if live else "unknown",
        "worker": live["worker"] if live else None,
        "started_at": live["started_at"] if live else None,
    })


@router.get("/beat", response_model=ApiResponse[list[BeatEntry]])
async def celery_beat(_admin: ProfileUsrUser = Depends(admin_only)):
    return ok(celery_info.collect_beat())
