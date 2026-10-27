# Third-party
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.utils.expand import ExpandPlan
from app.core.utils.responses import AppError, ok
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.models.models_sub.plan_conditions import ExplorerSubPlanConditions
from app.explorer.schemas.route import RouteDetail
from app.explorer.services.route_view import route_extras


async def write_plan_conditions(db: AsyncSession, route: ExplorerAggRoute, changes: dict | None) -> None:
    # The plan conditions of a route are its own row: created when first sent, afterwards only the sent fields change
    if not changes:
        return
    if route.plan_condition_id is None:
        row = ExplorerSubPlanConditions(**changes)
        db.add(row)
        await db.flush()
        route.plan_condition_id = row.id
        return
    row = await db.get(ExplorerSubPlanConditions, route.plan_condition_id)
    for field, value in changes.items():
        setattr(row, field, value)


async def detail(db: AsyncSession, route: ExplorerAggRoute, user, plan: ExpandPlan | None = None, links=None, facts=None, **more) -> dict:
    # The RouteDetail of a route as a dict (the links are only ids unless the plan asks for them)
    plan = plan or ExpandPlan.parse(RouteDetail, None)
    extras = await route_extras(db, route, links, facts)
    extras.update(more)
    return plan.render(route, viewer=user, **extras)


def issue_errors(issues) -> list[dict]:
    # continuity issues in the error format of the API
    return [{"field": "segments", "code": i.kind, "message": i.message} for i in issues]


def invalid_route(issues) -> AppError:
    text = f"The segments do not form a valid route ({len(issues)} problem(s)). Check error_errors, or send validation: \"warn\" to save anyway."
    return AppError(422, "Validation failed", error_message=text, error_errors=issue_errors(issues))
