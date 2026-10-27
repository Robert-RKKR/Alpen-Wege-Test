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
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.schemas.route import RouteDetail

from ._router import router
from ._shared import detail


@router.get("/{route_id}", response_model=ApiResponse[RouteDetail])
async def get_route(
    route_id: UUID,
    access: AccessContext = Depends(resource_access("route", "read")),
    plan: ExpandPlan = Depends(expand_plan(RouteDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ExplorerAggRoute).where(ExplorerAggRoute.id == route_id).options(*plan.load_options(ExplorerAggRoute))
    route = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, route, not_found_msg="Route not found")
    return ok(await detail(db, route, access.user, plan))
