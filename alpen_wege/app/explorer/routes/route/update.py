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
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.schemas.route import RouteDetail, RouteUpdate
from app.explorer.services.route_rules import publish_own_segments
from app.explorer.services.route_view import route_links, segment_facts
from app.explorer.services.segment_persist import ensure_refs
from app.explorer.services.visibility import journeys_using_route, must_stay_public, not_private_error

from ._router import router
from ._shared import detail, write_plan_conditions


@router.patch("/{route_id}", response_model=ApiResponse[RouteDetail])
async def update_route(
    route_id: UUID,
    body: RouteUpdate,
    access: AccessContext = Depends(resource_access("route", "update")),
    db: AsyncSession = Depends(get_db),
):
    # Metadata, classification (sport and difficulty by hand) and plan conditions. The segments are changed with
    # PUT /routes/{id}/segments.
    route = await db.get(ExplorerAggRoute, route_id)
    check_object_access(access, route, not_found_msg="Route not found")
    await db.refresh(route, with_for_update=True)       # the same lock as the segment save: the two cannot run at the same time
    changes = body.model_dump(exclude_unset=True)
    conditions = changes.pop("plan_conditions", None)
    await ensure_refs(db, changes)
    if route.is_public and changes.get("is_public") is False:
        # a route that a journey of another user or a public journey uses has to stay visible
        count = must_stay_public(await journeys_using_route(db, route.id), route.created_by)
        if count:
            raise not_private_error("route", "journey", count)
    if not route.is_public and changes.get("is_public") is True:
        # publishing a route publishes its own segments (a public route must not show private ones)
        links = await route_links(db, route.id)
        for segment in publish_own_segments(route, await segment_facts(db, [l.segment_id for l in links], lock=True)):
            log_updated(db, segment, {"is_public": False}, {"is_public": True}, access.user.id)
    old_values = {f: getattr(route, f) for f in changes}
    for field, value in changes.items():
        setattr(route, field, value)
    await write_plan_conditions(db, route, conditions)
    if changes or conditions:
        route.updated_at = func.now()
    log_updated(db, route, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(route)
    return ok(await detail(db, route, access.user))
