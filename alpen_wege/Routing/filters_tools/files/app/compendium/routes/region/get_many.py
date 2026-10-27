from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, bbox_condition, contains, equals, ids_query, one_of, page_params, search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.schemas.region import RegionRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER

M = CompendiumCatRegion
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at}


class RegionFilters:
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        country_id: list[UUID] | None = ids_query("Country"),
        region_type_id: list[UUID] | None = ids_query("Region type"),
        parent_id: UUID | None = Query(None, description="Direct sub-regions of this region."),
        created_by: UUID | None = Query(None, description="Regions created by this user."),
        bbox: str | None = Query(None, description="Regions whose area touches a box: min_lon,min_lat,max_lon,max_lat (west, south, east, north)."),
    ):
        self.q = q
        self.country_id = country_id
        self.region_type_id = region_type_id
        self.parent_id = parent_id
        self.created_by = created_by
        self.bbox = bbox

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            one_of(M.country_id, self.country_id),
            one_of(M.region_type_id, self.region_type_id),
            equals(M.parent_id, self.parent_id),
            equals(M.created_by, self.created_by),
            bbox_condition(M.bbox, self.bbox),
        )


@router.get("", response_model=ApiResponse[list[RegionRead]])
async def list_regions(
    access: AccessContext = Depends(resource_access("region", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: RegionFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    stmt = sort.apply(base.options(*EAGER)).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
