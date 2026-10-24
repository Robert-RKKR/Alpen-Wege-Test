# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.schemas.track import (
    TrackRead,
)

from ._router import router
from ._shared import ensure_visible, build_metrics


@router.get("/{track_id}", response_model=ApiResponse[TrackRead])
async def get_track(
    track_id: UUID,
    access: AccessContext = Depends(resource_access("track", "read")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
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

    result = TrackRead(
        id=track.id,
        name=track.name,
        name_de=track.name_de,
        name_pl=track.name_pl,
        summary=track.summary,
        summary_de=track.summary_de,
        summary_pl=track.summary_pl,
        description=track.description,
        description_de=track.description_de,
        description_pl=track.description_pl,
        is_public=track.is_public,
        processing_status=track.processing_status,
        processing_error=track.processing_error,
        processing_warnings=track.processing_warnings,
        processed_at=track.processed_at,
        recorded_at=track.recorded_at,
        archived_at=track.archived_at,
        sport_type_id=track.sport_type_id,
        difficulty_level_id=track.difficulty_level_id,
        difficulty_sport_id=track.difficulty_sport_id,
        start_poi_id=track.start_poi_id,
        end_poi_id=track.end_poi_id,
        geo_record_id=track.geo_record_id,
        gpx_id=track.gpx_id,
        created_at=track.created_at,
        updated_at=track.updated_at,
        created_by=track.created_by,
        metrics=build_metrics(geo_rec, geo_perf),
    )
    return ok(result)
