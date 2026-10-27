# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse
from app.profile.permissions import resource_access, AccessContext
from app.explorer.schemas.segment import SegmentCreated, SegmentFromTrack
from app.explorer.services import segment_build
from app.explorer.services.segment_persist import segment_fields
from app.explorer.services.track_source import clip_source_path
from app.explorer.services.segment_http import build

from ._router import router
from ._shared import finish_create


@router.post("/from-track", response_model=ApiResponse[SegmentCreated], status_code=status.HTTP_201_CREATED)
async def create_segment_from_track(
    body: SegmentFromTrack,
    access: AccessContext = Depends(resource_access("segment", "create")),
    db: AsyncSession = Depends(get_db),
):
    # A segment from a part of one of the caller's own recorded tracks. The new GPX has no time and no heart rate.
    path = await clip_source_path(db, access.user, body.track_id)
    processed = await build(segment_build.from_track_file, path, body.start_distance_m, body.end_distance_m)
    return await finish_create(db, access.user, processed, segment_fields(body))
