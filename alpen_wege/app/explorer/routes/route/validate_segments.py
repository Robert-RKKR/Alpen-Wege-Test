# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.config import get_settings
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.schemas.route import ValidateRouteSegments, ValidationReport
from app.explorer.services.continuity import EndPoint, SlotItem, validate
from app.explorer.services.route_view import RowSpec, segment_facts, slot_item
from app.explorer.services.visibility import scope_of, visible

from ._router import router

settings = get_settings()


def _point(pair) -> EndPoint:
    lon, lat = pair
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise AppError(422, "A point is outside longitude -180..180 / latitude -90..90.")
    return EndPoint(lon, lat)


@router.post("/{route_id}/segments/validate", response_model=ApiResponse[ValidationReport])
async def validate_route_segments(
    route_id: UUID,
    body: ValidateRouteSegments,
    access: AccessContext = Depends(resource_access("route", "read")),
    db: AsyncSession = Depends(get_db),
):
    # The same checks as the save, without saving: for the editor while the user is still drawing. Saved segments by id;
    # a drawing that is not saved yet by its first and last point.
    route = await db.get(ExplorerAggRoute, route_id)
    check_object_access(access, route, not_found_msg="Route not found")
    saved_ids = [it.segment_id for it in body.segments if it.segment_id is not None]
    facts = {}
    if saved_ids:
        scope = await scope_of(db, access.user, "segment", "read")
        facts = await segment_facts(db, saved_ids)
        missing = [str(i) for i in set(saved_ids) if i not in facts or not visible(scope, access.user.id, facts[i].segment.created_by, facts[i].segment.is_public)]
        if missing:
            raise AppError(404, "Not found", error_message="Segment not found or not visible to you: " + ", ".join(sorted(missing)))
    items = []
    for i, it in enumerate(body.segments):
        if it.segment_id is not None:
            items.append(slot_item(RowSpec(it.slot_position, it.alt_group, it.is_default, it.is_reversed), facts[it.segment_id]))
        else:
            items.append(SlotItem(f"item {i}", it.slot_position, it.is_default, it.is_reversed, _point(it.start), _point(it.end), it.alt_group))
    return ok(validate(items, settings.CONTINUITY_THRESHOLD_M, settings.ROUTE_MAX_SEGMENTS).as_dict())
