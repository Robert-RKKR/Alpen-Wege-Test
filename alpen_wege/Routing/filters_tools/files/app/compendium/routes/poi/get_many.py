from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, at_least, at_most, before, bbox_condition, contains, equals, ids_query, near_condition, number_query,
    one_of, page_params, search_query, since, sort_params, where_all, moment_query,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.schemas.poi import PoiRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER

M = CompendiumCatPoi
SORT = {"name": M.name, "altitude_m": M.altitude_m, "created_at": M.created_at, "updated_at": M.updated_at}


class PoiFilters:
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        compendium_type_id: list[UUID] | None = ids_query("POI type"),
        main_region_id: list[UUID] | None = ids_query("Main region"),
        created_by: UUID | None = Query(None, description="POIs created by this user."),
        altitude_min: int | None = number_query("Altitude in metres, at least."),
        altitude_max: int | None = number_query("Altitude in metres, at most."),
        created_from: moment_query("Created at or after this date or time.") = None,
        created_to: moment_query("Created before this date or time.") = None,
        bbox: str | None = Query(None, description="Inside a box: min_lon,min_lat,max_lon,max_lat (west, south, east, north)."),
        near: str | None = Query(None, description="Around a point: lon,lat. Use radius_m for the distance."),
        radius_m: int | None = Query(None, description="Distance around near in metres. Default 5000, at most 100000."),
    ):
        self.q = q
        self.compendium_type_id = compendium_type_id
        self.main_region_id = main_region_id
        self.created_by = created_by
        self.altitude_min = altitude_min
        self.altitude_max = altitude_max
        self.created_from = created_from
        self.created_to = created_to
        self.bbox = bbox
        self.near = near
        self.radius_m = radius_m

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            one_of(M.compendium_type_id, self.compendium_type_id),
            one_of(M.main_region_id, self.main_region_id),
            equals(M.created_by, self.created_by),
            at_least(M.altitude_m, self.altitude_min),
            at_most(M.altitude_m, self.altitude_max),
            since(M.created_at, self.created_from),
            before(M.created_at, self.created_to),
            bbox_condition(M.location, self.bbox),
            near_condition(M.location, self.near, self.radius_m),
        )


@router.get("", response_model=ApiResponse[list[PoiRead]])
async def list_pois(
    access: AccessContext = Depends(resource_access("poi", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: PoiFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    stmt = sort.apply(base.options(*EAGER)).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
