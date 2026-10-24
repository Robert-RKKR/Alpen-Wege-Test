# Standard library
import logging
from uuid import UUID

# Third-party
from fastapi import Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.services.dispatch import (
    enqueue_process_track,
)
from app.management.jobs.events import publish_job_event_async
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.service import get_or_create_active_job
from app.management.schemas.job import JobAccepted
from app.core.utils.api_paths import job_url

from ._router import router

logger = logging.getLogger(__name__)


@router.post(
    "/{track_id}/reprocess",
    response_model=ApiResponse[JobAccepted],
    status_code=status.HTTP_202_ACCEPTED,
)
async def reprocess_track(
    track_id: UUID,
    response: Response,
    access: AccessContext = Depends(resource_access("track", "update")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
    check_object_access(access, track, not_found_msg="Track not found")

    if track.processing_status != "failed":
        raise AppError(409, "Only failed tracks can be reprocessed.")

    track.processing_status = "pending"
    track.processing_error = None
    track.processing_started_at = None
    # the failed attempt's job is terminal, so this creates a new job and keeps the old one as history
    job, created = await get_or_create_active_job(
        db, user_id=track.created_by, kind=JobKind.TRACK_PROCESS,
        task_name=TASK_NAME[JobKind.TRACK_PROCESS],
        subject_type="track", subject_id=track.id,
    )
    await db.commit()
    if created:
        await publish_job_event_async(job)

    try:
        await run_in_threadpool(enqueue_process_track, track.id, job["id"])
    except Exception:
        logger.warning("Failed to enqueue reprocess for track %s", track.id)

    # GET /management/my-jobs/{id} is owner-only: Location is only useful to the owner. An administrator
    # reprocessing someone else's track reads the job through /management/jobs/{id}.
    if track.created_by == access.user.id:
        response.headers["Location"] = job_url(job["id"])
    return ok(JobAccepted(job_id=job["id"]), code=202, message="Reprocessing queued")
