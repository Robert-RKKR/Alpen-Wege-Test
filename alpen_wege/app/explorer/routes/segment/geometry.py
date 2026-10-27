# Standard library
import json
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
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.schemas.segment import SegmentGeometry

from ._router import router


@router.get("/{segment_id}/geometry", response_model=ApiResponse[SegmentGeometry])
async def get_segment_geometry(
    segment_id: UUID,
    access: AccessContext = Depends(resource_access("segment", "read")),
    db: AsyncSession = Depends(get_db),
):
    segment = await db.get(ExplorerAggSegment, segment_id)
    check_object_access(access, segment, not_found_msg="Segment not found")
    row = (await db.execute(
        select(
            ExplorerSubGeoRecord.geojson,
            ExplorerSubGeoRecord.elevation_graph,
            ST_AsGeoJSON(ExplorerSubGeoRecord.start_location).label("start_geojson"),
            ST_AsGeoJSON(ExplorerSubGeoRecord.end_location).label("end_geojson"),
        ).where(ExplorerSubGeoRecord.id == segment.geo_record_id)
    )).one_or_none()
    if row is None:
        raise AppError(404, "Geometry not found.")
    return ok(SegmentGeometry(
        geojson=row.geojson,
        elevation_graph=row.elevation_graph,
        start_location=json.loads(row.start_geojson) if row.start_geojson else None,
        end_location=json.loads(row.end_geojson) if row.end_geojson else None,
    ))
