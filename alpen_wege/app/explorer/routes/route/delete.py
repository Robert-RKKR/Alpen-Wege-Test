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
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.models.models_sub.plan_conditions import ExplorerSubPlanConditions
from app.explorer.services.visibility import in_use_error, journeys_using_route, scope_of

from ._router import router


@router.delete("/{route_id}", response_model=ApiResponse[None])
async def delete_route(
    route_id: UUID,
    access: AccessContext = Depends(resource_access("route", "delete")),
    db: AsyncSession = Depends(get_db),
):
    # The segment rows of the route go with it (the segments themselves stay). A route that a journey uses is not deleted.
    route = await db.get(ExplorerAggRoute, route_id)
    check_object_access(access, route, not_found_msg="Route not found")
    user_id = access.user.id                                                    # read now: a rollback expires the user object
    journey_scope = await scope_of(db, access.user, "journey", "read")
    await db.refresh(route, with_for_update=True)
    users = await journeys_using_route(db, route.id)
    if users:
        raise in_use_error("route", "journey", users, journey_scope, user_id)
    conditions_id = route.plan_condition_id
    log_deleted(db, route, user_id)
    try:
        await db.delete(route)
        await db.flush()
        conditions = await db.get(ExplorerSubPlanConditions, conditions_id) if conditions_id else None
        if conditions is not None:
            await db.delete(conditions)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        users = await journeys_using_route(db, route_id)
        raise in_use_error("route", "journey", users, journey_scope, user_id)
    return ok(None, message="Deleted")
