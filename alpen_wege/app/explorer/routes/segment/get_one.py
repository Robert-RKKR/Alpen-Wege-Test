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
from app.explorer.models.models_agg.segment import ExplorerAggSegment
from app.explorer.schemas.segment import SegmentDetail
from app.explorer.services.segment_view import computed_of, geo_info

from ._router import router


@router.get("/{segment_id}", response_model=ApiResponse[SegmentDetail])
async def get_segment(
    segment_id: UUID,
    access: AccessContext = Depends(resource_access("segment", "read")),
    plan: ExpandPlan = Depends(expand_plan(SegmentDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ExplorerAggSegment).where(ExplorerAggSegment.id == segment_id).options(*plan.load_options(ExplorerAggSegment))
    segment = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, segment, not_found_msg="Segment not found")
    info = await geo_info(db, [segment.geo_record_id])
    return ok(plan.render(segment, viewer=access.user, **computed_of(info.get(segment.geo_record_id))))
