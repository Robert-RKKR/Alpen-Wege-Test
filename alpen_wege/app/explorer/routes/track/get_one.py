# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.schemas.track import (
    TrackDetail,
)

from ._router import router
from ._shared import ensure_visible, build_metrics


@router.get("/{track_id}", response_model=ApiResponse[TrackDetail])
async def get_track(
    track_id: UUID,
    access: AccessContext = Depends(resource_access("track", "read")),
    plan: ExpandPlan = Depends(expand_plan(TrackDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ExplorerAggTrack)
        .where(ExplorerAggTrack.id == track_id)
        .options(*plan.load_options(ExplorerAggTrack))
    )
    track = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, track, not_found_msg="Track not found")
    ensure_visible(access, track)

    geo_rec = None
    geo_perf = None
    if track.geo_record_id:
        geo_rec = await db.get(ExplorerSubGeoRecord, track.geo_record_id)
        if geo_rec and geo_rec.geo_performance_id:
            geo_perf = await db.get(
                ExplorerSubGeoPerformance, geo_rec.geo_performance_id
            )

    return ok(plan.render(track, viewer=access.user, metrics=build_metrics(geo_rec, geo_perf)))
