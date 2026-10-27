# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_deleted
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.explorer.services.visibility import in_use_error, routes_using_segment, scope_of

from ._router import router


@router.delete("/{segment_id}", response_model=ApiResponse[None])
async def delete_segment(
    segment_id: UUID,
    access: AccessContext = Depends(resource_access("segment", "delete")),
    db: AsyncSession = Depends(get_db),
):
    segment = await db.get(ExplorerAggSegment, segment_id)
    check_object_access(access, segment, not_found_msg="Segment not found")
    user_id = access.user.id                                                    # read now: a rollback expires the user object
    route_scope = await scope_of(db, access.user, "route", "read")
    await db.refresh(segment, with_for_update=True)
    users = await routes_using_segment(db, segment.id)
    if users:
        # 409: a used segment stays (the database says the same with a foreign key that restricts the delete)
        raise in_use_error("segment", "route", users, route_scope, user_id)
    geo_record_id = segment.geo_record_id
    log_deleted(db, segment, user_id)
    try:
        await db.delete(segment)
        await db.flush()
        geo = await db.get(ExplorerSubGeoRecord, geo_record_id)
        if geo is not None:
            await db.delete(geo)
        await db.commit()
    except IntegrityError:
        # a route took the segment between the check and the delete
        await db.rollback()
        users = await routes_using_segment(db, segment_id)
        raise in_use_error("segment", "route", users, route_scope, user_id)
    return ok(None, message="Deleted")
