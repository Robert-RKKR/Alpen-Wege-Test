# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_created
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.schemas.route import RouteCreate, RouteDetail
from app.explorer.services.segment_persist import ensure_refs

from ._router import router
from ._shared import detail, write_plan_conditions


@router.post("", response_model=ApiResponse[RouteDetail], status_code=status.HTTP_201_CREATED)
async def create_route(
    body: RouteCreate,
    access: AccessContext = Depends(resource_access("route", "create")),
    db: AsyncSession = Depends(get_db),
):
    # Creates the route itself (a draft without segments). The segments come with PUT /routes/{id}/segments.
    data = body.model_dump(exclude={"plan_conditions"})
    await ensure_refs(db, data)
    route = ExplorerAggRoute(**data, created_by=access.user.id)
    db.add(route)
    await db.flush()
    await write_plan_conditions(db, route, body.plan_conditions.model_dump(exclude_unset=True) if body.plan_conditions else None)
    log_created(db, route, access.user.id)
    await db.commit()
    await db.refresh(route)
    return ok(await detail(db, route, access.user, links=[], facts={}), code=201, message="Created")
