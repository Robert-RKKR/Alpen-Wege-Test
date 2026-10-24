# Standard library
import logging

# Third-party
from fastapi import Depends, File, Form, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.config import get_settings
from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.assets.models.models_agg.gpx import AssetAggGpx
from app.explorer.schemas.track import (
    TrackCreated,
)
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.xml_guard import check_gpx_root
from app.explorer.services.gpx_storage import (
    UploadTooLarge,
    delete_quietly,
    save_upload,
)
from app.explorer.services.dispatch import (
    enqueue_process_track,
)
from app.management.jobs.events import publish_job_event_async
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.service import create_job
from app.core.utils.api_paths import job_url

from ._router import router

logger = logging.getLogger(__name__)
settings = get_settings()


@router.post("", response_model=ApiResponse[TrackCreated], status_code=status.HTTP_202_ACCEPTED)
async def create_track(
    response: Response,
    name: str = Form(..., min_length=1, max_length=255),
    gpx_file: UploadFile = File(...),
    summary: str | None = Form(None, max_length=1000),
    description: str | None = Form(None, max_length=10000),
    is_public: bool = Form(False),
    access: AccessContext = Depends(resource_access("track", "create")),
    db: AsyncSession = Depends(get_db),
):
    filename = gpx_file.filename or ""
    if not filename.lower().endswith(".gpx"):
        raise AppError(400, "Only .gpx files are accepted.")

    try:
        await run_in_threadpool(check_gpx_root, gpx_file.file)
        gpx_file.file.seek(0)
    except GpxProcessingError:
        raise AppError(400, "Not a valid GPX file.")

    max_bytes = settings.GPX_MAX_UPLOAD_MB * 1024 * 1024
    try:
        stored = await run_in_threadpool(save_upload, gpx_file.file, max_bytes=max_bytes)
    except UploadTooLarge:
        raise AppError(413, f"File too large (maximum {settings.GPX_MAX_UPLOAD_MB} MB).")

    relative_path = stored.relative_path
    try:
        dup_stmt = (
            select(ExplorerAggTrack.id)
            .join(AssetAggGpx, AssetAggGpx.id == ExplorerAggTrack.gpx_id)
            .where(
                ExplorerAggTrack.created_by == access.user.id,
                ExplorerAggTrack.archived_at.is_(None),
                AssetAggGpx.sha256 == stored.sha256,
            )
            .order_by(ExplorerAggTrack.created_at.desc())
            .limit(1)
        )
        dup_result = await db.execute(dup_stmt)
        duplicate_of = dup_result.scalar_one_or_none()

        gpx = AssetAggGpx(
            name=filename[:255],
            path=relative_path,
            sha256=stored.sha256,
            size_bytes=stored.size_bytes,
            created_by=access.user.id,
            is_public=False,
        )
        db.add(gpx)
        await db.flush()

        track = ExplorerAggTrack(
            name=name,
            summary=summary or None,
            description=description or None,
            is_public=is_public,
            gpx_id=gpx.id,
            processing_status="pending",
            created_by=access.user.id,
        )
        db.add(track)
        await db.flush()
        log_created(db, track, access.user.id)
        job = await create_job(
            db, user_id=access.user.id, kind=JobKind.TRACK_PROCESS,
            task_name=TASK_NAME[JobKind.TRACK_PROCESS],
            subject_type="track", subject_id=track.id,
        )
        await db.commit()
    except Exception:
        await run_in_threadpool(delete_quietly, relative_path)
        raise

    await publish_job_event_async(job)
    try:
        await run_in_threadpool(enqueue_process_track, track.id, job["id"])
    except Exception:
        # the track stays pending and its job queued; the reaper enqueues it again
        logger.warning("Failed to enqueue processing for track %s", track.id)

    response.headers["Location"] = job_url(job["id"])
    result = TrackCreated(
        id=track.id,
        name=track.name,
        processing_status=track.processing_status,
        created_at=track.created_at,
        duplicate_of_track_id=duplicate_of,
        job_id=job["id"],
    )
    return ok(result, code=202, message="Accepted")
