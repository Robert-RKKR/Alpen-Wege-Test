# Standard library
import logging
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.services.dispatch import (
    enqueue_detect_pois,
    enqueue_process_track,
    request_stats_recompute,
)
from app.management.jobs.events import publish_job_event_async
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.service import get_or_create_active_job

from ._router import router

logger = logging.getLogger(__name__)


@router.post("/{track_id}/restore", response_model=ApiResponse[None])
async def restore_track(
    track_id: UUID,
    access: AccessContext = Depends(resource_access("track", "update")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
    check_object_access(access, track, not_found_msg="Track not found")

    if track.archived_at is not None:
        old_values = {"archived_at": track.archived_at}
        track.archived_at = None
        log_updated(
            db, track, old_values, {"archived_at": None}, access.user.id
        )
        await db.commit()

        try:
            await run_in_threadpool(request_stats_recompute, track.created_by)
        except Exception:
            logger.warning("Failed to request stats recompute after restore")

        if track.processing_status == "pending":
            try:
                job, created = await get_or_create_active_job(
                    db, user_id=track.created_by, kind=JobKind.TRACK_PROCESS,
                    task_name=TASK_NAME[JobKind.TRACK_PROCESS],
                    subject_type="track", subject_id=track.id,
                )
                await db.commit()
                if created:
                    await publish_job_event_async(job)
                await run_in_threadpool(enqueue_process_track, track.id, job["id"])
            except Exception:
                logger.warning("Failed to enqueue processing after restore of track %s", track.id)
        elif track.processing_status == "ready":
            try:
                await run_in_threadpool(enqueue_detect_pois, track.id)
            except Exception:
                pass

    return ok(None, message="Restored")
