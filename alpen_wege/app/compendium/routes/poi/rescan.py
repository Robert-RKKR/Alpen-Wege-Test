from uuid import UUID

from fastapi import Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.redis import get_redis_pool
from app.explorer.services.dispatch import enqueue_rescan_poi
from app.management.jobs.events import publish_job_event_async
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.service import create_job, fail_active_jobs_for_subject, fail_job
from app.management.schemas.job import JobAccepted
from app.core.utils.api_paths import job_url

from ._router import router


@router.post(
    "/{poi_id}/rescan",
    response_model=ApiResponse[JobAccepted],
    status_code=status.HTTP_202_ACCEPTED,
)
async def rescan_poi(
    poi_id: UUID,
    response: Response,
    access: AccessContext = Depends(resource_access("poi", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPoi, poi_id)
    check_object_access(access, obj, not_found_msg="POI not found")

    from app.config import get_settings
    settings = get_settings()

    redis = get_redis_pool()
    lock_key = f"rescan:poi:{poi_id}"
    locked = await redis.set(lock_key, "1", nx=True, ex=settings.RESCAN_LOCK_SECONDS)
    if not locked:
        raise AppError(409, "Rescan already queued.")

    try:
        # We hold the lock, so no rescan of this POI can be running: a leftover active job
        # (hard-killed task, lost message) must not block this one through the unique index.
        leftovers = await fail_active_jobs_for_subject(
            db, kind=JobKind.POI_RESCAN, subject_type="poi", subject_id=poi_id,
            message="The rescan did not finish.",
        )
        job = await create_job(
            db, user_id=access.user.id, kind=JobKind.POI_RESCAN,
            task_name=TASK_NAME[JobKind.POI_RESCAN],
            subject_type="poi", subject_id=poi_id,
        )
        await db.commit()
    except Exception:
        await redis.delete(lock_key)
        raise AppError(503, "Failed to create the rescan job.")

    for leftover in leftovers:
        await publish_job_event_async(leftover)
    await publish_job_event_async(job)
    try:
        await run_in_threadpool(enqueue_rescan_poi, poi_id, job["id"])
    except Exception:
        await redis.delete(lock_key)
        failed = await fail_job(db, job["id"], "The rescan could not be queued.")
        await db.commit()
        if failed is not None:
            await publish_job_event_async(failed)
        raise AppError(503, "Failed to enqueue rescan.")

    response.headers["Location"] = job_url(job["id"])
    return ok(JobAccepted(job_id=job["id"]), code=202, message="Rescan queued")
