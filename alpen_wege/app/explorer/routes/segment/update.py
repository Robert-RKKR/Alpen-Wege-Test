# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_updated
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.schemas.segment import SegmentRead, SegmentUpdate
from app.explorer.services.segment_persist import ensure_poi_near, ensure_refs
from app.explorer.services.segment_view import geo_info, read_dict
from app.explorer.services.visibility import must_stay_public, not_private_error, routes_using_segment

from ._router import router


@router.patch("/{segment_id}", response_model=ApiResponse[SegmentRead])
async def update_segment(
    segment_id: UUID,
    body: SegmentUpdate,
    access: AccessContext = Depends(resource_access("segment", "update")),
    db: AsyncSession = Depends(get_db),
):
    # Metadata only: the geometry of a segment never changes (draw a new segment instead).
    segment = await db.get(ExplorerAggSegment, segment_id)
    check_object_access(access, segment, not_found_msg="Segment not found")
    await db.refresh(segment, with_for_update=True)       # after the access check: a stranger cannot lock it; a save of a route waits for us
    changes = body.model_dump(exclude_unset=True)
    await ensure_refs(db, changes)
    if changes.get("start_poi_id") or changes.get("end_poi_id"):
        here = (await geo_info(db, [segment.geo_record_id])).get(segment.geo_record_id)
        if changes.get("start_poi_id"):
            await ensure_poi_near(db, "start_poi_id", changes["start_poi_id"], here.start_lon, here.start_lat)
        if changes.get("end_poi_id"):
            await ensure_poi_near(db, "end_poi_id", changes["end_poi_id"], here.end_lon, here.end_lat)
    if segment.is_public and changes.get("is_public") is False:
        # a segment that a route of another user or a public route uses has to stay visible
        count = must_stay_public(await routes_using_segment(db, segment.id), segment.created_by)
        if count:
            raise not_private_error("segment", "route", count)
    old_values = {f: getattr(segment, f) for f in changes}
    for field, value in changes.items():
        setattr(segment, field, value)
    if changes:
        segment.updated_at = func.now()
    log_updated(db, segment, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(segment)
    info = await geo_info(db, [segment.geo_record_id])
    return ok(read_dict(segment, info.get(segment.geo_record_id)))
