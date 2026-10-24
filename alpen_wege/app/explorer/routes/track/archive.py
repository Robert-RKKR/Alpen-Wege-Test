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
    request_stats_recompute,
)

from ._router import router

logger = logging.getLogger(__name__)


@router.delete("/{track_id}", response_model=ApiResponse[None])
async def archive_track(
    track_id: UUID,
    access: AccessContext = Depends(resource_access("track", "delete")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
    check_object_access(access, track, not_found_msg="Track not found")

    if track.archived_at is None:
        from datetime import datetime, timezone

        old_values = {"archived_at": None}
        track.archived_at = datetime.now(timezone.utc)
        log_updated(
            db, track, old_values, {"archived_at": track.archived_at}, access.user.id
        )
        await db.commit()

        try:
            await run_in_threadpool(request_stats_recompute, track.created_by)
        except Exception:
            logger.warning("Failed to request stats recompute after archive")

    return ok(None, message="Archived")
