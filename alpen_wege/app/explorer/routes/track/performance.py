# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.schemas.track import (
    TrackPerformance,
)

from ._router import router
from ._shared import ensure_visible


@router.get("/{track_id}/performance", response_model=ApiResponse[TrackPerformance])
async def get_track_performance(
    track_id: UUID,
    access: AccessContext = Depends(resource_access("track", "read")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
    check_object_access(access, track, not_found_msg="Track not found")
    ensure_visible(access, track)

    if not track.geo_record_id:
        raise AppError(404, "Performance data not available.")

    geo_rec = await db.get(ExplorerSubGeoRecord, track.geo_record_id)
    if not geo_rec or not geo_rec.geo_performance_id:
        raise AppError(404, "Performance data not available.")

    perf = await db.get(ExplorerSubGeoPerformance, geo_rec.geo_performance_id)
    if not perf:
        raise AppError(404, "Performance data not available.")

    return ok(TrackPerformance.model_validate(perf))
