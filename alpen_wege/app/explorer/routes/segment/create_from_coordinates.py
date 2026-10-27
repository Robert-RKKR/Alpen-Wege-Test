# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse
from app.profile.permissions import resource_access, AccessContext
from app.explorer.schemas.segment import SegmentCreated, SegmentFromCoordinates
from app.explorer.services import segment_build
from app.explorer.services.segment_persist import segment_fields
from app.explorer.services.segment_http import build

from ._router import router
from ._shared import finish_create


@router.post("/from-coordinates", response_model=ApiResponse[SegmentCreated], status_code=status.HTTP_201_CREATED)
async def create_segment_from_coordinates(
    body: SegmentFromCoordinates,
    access: AccessContext = Depends(resource_access("segment", "create")),
    db: AsyncSession = Depends(get_db),
):
    # A segment from points drawn on a map: [[lon, lat, ele?], ...] (the schema limits the number of points)
    processed = await build(segment_build.from_coordinates, body.coordinates)
    return await finish_create(db, access.user, processed, segment_fields(body))
