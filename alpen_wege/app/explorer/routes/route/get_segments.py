# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.schemas.route import RouteSegmentItem
from app.explorer.services.route_view import item_dict, route_links, segment_facts

from ._router import router


@router.get("/{route_id}/segments", response_model=ApiResponse[list[RouteSegmentItem]])
async def get_route_segments(
    route_id: UUID,
    access: AccessContext = Depends(resource_access("route", "read")),
    db: AsyncSession = Depends(get_db),
):
    # The segment rows in slot order, the default of a slot first
    route = await db.get(ExplorerAggRoute, route_id)
    check_object_access(access, route, not_found_msg="Route not found")
    links = await route_links(db, route.id)
    facts = await segment_facts(db, [l.segment_id for l in links])
    ordered = sorted(links, key=lambda l: (l.slot_position, not l.is_default))
    return ok([item_dict(l, facts[l.segment_id]) for l in ordered])
