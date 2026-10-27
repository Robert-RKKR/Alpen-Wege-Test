# Third-party
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.utils.responses import AppError
from app.explorer.models.models_agg.journey import ExplorerAggJourney
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.models.models_m2m.route_journey import ExplorerM2mRouteJourney
from app.explorer.models.models_m2m.segment_route import ExplorerM2mSegmentRoute
from app.profile.services.access_cache import get_policy_scope

# Who may see and use what, and who uses what. The routes (segments, routes, journeys) call these helpers; the pure
# rule is `visible`, the same rule as check_object_access.


def visible(scope: str | None, user_id, created_by, is_public: bool) -> bool:
    if scope is None:
        return False
    if scope == "all":
        return True
    if created_by == user_id:
        return True
    return scope == "public" and bool(is_public)


async def scope_of(db: AsyncSession, user, resource_key: str, action: str) -> str | None:
    # The scope of the user's role for a resource and action (own, public, all) or None without permission
    return await get_policy_scope(user.credentials.user_group, resource_key, action, db)


async def routes_using_segment(db: AsyncSession, segment_id) -> list:
    # the distinct routes that contain the segment: (id, name, created_by, is_public)
    stmt = (
        select(ExplorerAggRoute.id, ExplorerAggRoute.name, ExplorerAggRoute.created_by, ExplorerAggRoute.is_public)
        .join(ExplorerM2mSegmentRoute, ExplorerM2mSegmentRoute.route_id == ExplorerAggRoute.id)
        .where(ExplorerM2mSegmentRoute.segment_id == segment_id)
        .distinct()
        .order_by(ExplorerAggRoute.name)
    )
    return list((await db.execute(stmt)).all())


async def journeys_using_route(db: AsyncSession, route_id) -> list:
    # the distinct journeys that contain the route: (id, name, created_by, is_public)
    stmt = (
        select(ExplorerAggJourney.id, ExplorerAggJourney.name, ExplorerAggJourney.created_by, ExplorerAggJourney.is_public)
        .join(ExplorerM2mRouteJourney, ExplorerM2mRouteJourney.journey_id == ExplorerAggJourney.id)
        .where(ExplorerM2mRouteJourney.route_id == route_id)
        .distinct()
        .order_by(ExplorerAggJourney.name)
    )
    return list((await db.execute(stmt)).all())


async def usage_count(db: AsyncSession, model, column, value) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(column == value))).scalar_one()


def in_use_error(what: str, used_by: str, users: list, viewer_scope: str | None, viewer_id) -> AppError:
    # 409 for a delete of something that is used. The answer has the number of users and the names of only those that the
    # caller may see (a private route of somebody else is counted, never named).
    seen = [u for u in users if visible(viewer_scope, viewer_id, u.created_by, u.is_public)]
    names = [u.name for u in seen][:20]
    hidden = len(users) - len(seen)
    text = f"This {what} is used by {len(users)} {used_by}(s) and cannot be deleted."
    if names:
        text += " Visible to you: " + ", ".join(names) + (f" and {hidden} more" if hidden else "") + "."
    elif hidden:
        text += " You cannot see them."
    return AppError(
        409,
        "Conflict",
        error_message=text,
        error_errors=[{"field": None, "code": "in_use", "message": text}],
    )


def not_private_error(what: str, used_by: str, count: int) -> AppError:
    text = (f"This {what} is used by {count} {used_by}(s) of other users or by public {used_by}s, "
            f"so it cannot be made private.")
    return AppError(409, "Conflict", error_message=text, error_errors=[{"field": "is_public", "code": "in_use", "message": text}])


def must_stay_public(users: list, owner_id) -> int:
    # how many of the users force the thing to stay public: another user's, or any public one
    return sum(1 for u in users if u.created_by != owner_id or u.is_public)
