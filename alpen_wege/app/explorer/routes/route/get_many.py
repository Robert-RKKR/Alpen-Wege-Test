# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, at_least, at_most, contains, equals, ids_query, number_query, one_of, page_params, search_query,
    sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.core.utils.scope import apply_scope
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.route import ExplorerAggRoute
from app.explorer.schemas.route import RouteRead

from ._router import router

M = ExplorerAggRoute
SORT = {
    "name": M.name,
    "created_at": M.created_at,
    "updated_at": M.updated_at,
    "agg_distance_m": M.agg_distance_m,
    "agg_elevation_gain_m": M.agg_elevation_gain_m,
    "rating_avg": M.rating_avg,
}


class RouteFilters:
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        sport_type_id: list[UUID] | None = ids_query("Sport type"),
        difficulty_level_id: list[UUID] | None = ids_query("Difficulty level"),
        difficulty_sport_id: list[UUID] | None = ids_query("Sport difficulty"),
        created_by: UUID | None = Query(None, description="Routes of this user (use your own id for 'my routes')."),
        is_public: bool | None = Query(None, description="Only public (true) or only private (false) routes."),
        distance_min: int | None = number_query("Total distance in metres, at least."),
        distance_max: int | None = number_query("Total distance in metres, at most."),
        elevation_gain_min: int | None = number_query("Total ascent in metres, at least."),
        elevation_gain_max: int | None = number_query("Total ascent in metres, at most."),
    ):
        self.q = q
        self.sport_type_id = sport_type_id
        self.difficulty_level_id = difficulty_level_id
        self.difficulty_sport_id = difficulty_sport_id
        self.created_by = created_by
        self.is_public = is_public
        self.distance_min = distance_min
        self.distance_max = distance_max
        self.elevation_gain_min = elevation_gain_min
        self.elevation_gain_max = elevation_gain_max

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            one_of(M.sport_type_id, self.sport_type_id),
            one_of(M.difficulty_level_id, self.difficulty_level_id),
            one_of(M.difficulty_sport_id, self.difficulty_sport_id),
            equals(M.created_by, self.created_by),
            equals(M.is_public, self.is_public),
            at_least(M.agg_distance_m, self.distance_min),
            at_most(M.agg_distance_m, self.distance_max),
            at_least(M.agg_elevation_gain_m, self.elevation_gain_min),
            at_most(M.agg_elevation_gain_m, self.elevation_gain_max),
        )


@router.get("", response_model=ApiResponse[list[RouteRead]])
async def list_routes(
    access: AccessContext = Depends(resource_access("route", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: RouteFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
