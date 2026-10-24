# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from geoalchemy2.functions import ST_AsGeoJSON
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.models.models_sub.geo_performance import ExplorerSubGeoPerformance
from app.explorer.schemas.track import (
    TrackGeometry,
)

from ._router import router
from ._shared import ensure_visible


@router.get("/{track_id}/geometry", response_model=ApiResponse[TrackGeometry])
async def get_track_geometry(
    track_id: UUID,
    access: AccessContext = Depends(resource_access("track", "read")),
    db: AsyncSession = Depends(get_db),
):
    track = await db.get(ExplorerAggTrack, track_id)
    check_object_access(access, track, not_found_msg="Track not found")
    ensure_visible(access, track)

    if track.processing_status != "ready" or not track.geo_record_id:
        raise AppError(404, "Geometry not available yet.")

    stmt = select(
        ExplorerSubGeoRecord.geojson,
        ExplorerSubGeoRecord.elevation_graph,
        ExplorerSubGeoRecord.geo_performance_id,
        ST_AsGeoJSON(ExplorerSubGeoRecord.start_location).label("start_geojson"),
        ST_AsGeoJSON(ExplorerSubGeoRecord.end_location).label("end_geojson"),
    ).where(ExplorerSubGeoRecord.id == track.geo_record_id)
    row = (await db.execute(stmt)).one_or_none()

    if not row:
        raise AppError(404, "Geometry not found.")

    import json as json_mod

    heart_graph = None
    speed_pattern = None
    if row.geo_performance_id:
        perf = await db.get(ExplorerSubGeoPerformance, row.geo_performance_id)
        if perf:
            heart_graph = perf.heart_graph
            speed_pattern = perf.speed_pattern

    start_loc = json_mod.loads(row.start_geojson) if row.start_geojson else None
    end_loc = json_mod.loads(row.end_geojson) if row.end_geojson else None

    result = TrackGeometry(
        geojson=row.geojson,
        elevation_graph=row.elevation_graph,
        heart_graph=heart_graph,
        speed_pattern=speed_pattern,
        start_location=start_loc,
        end_location=end_loc,
    )
    return ok(result)
