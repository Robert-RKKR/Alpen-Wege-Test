from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import Page, Sort, equals, page_params, sort_params, where_all
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.poi_region import PoiRegionRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER

M = CompendiumM2mPoiRegion
SORT = {"slot_position": M.slot_position, "created_at": M.created_at}


class PoiRegionFilters:
    def __init__(
        self,
        poi_id: UUID | None = Query(None, description="Links of this POI."),
        region_id: UUID | None = Query(None, description="Links of this region."),
        created_by: UUID | None = Query(None, description="Links created by this user."),
    ):
        self.poi_id = poi_id
        self.region_id = region_id
        self.created_by = created_by

    def apply(self, stmt):
        return where_all(
            stmt,
            equals(M.poi_id, self.poi_id),
            equals(M.region_id, self.region_id),
            equals(M.created_by, self.created_by),
        )


@router.get("", response_model=ApiResponse[list[PoiRegionRead]])
async def list_poi_regions(
    access: AccessContext = Depends(resource_access("poi_region", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "slot_position", M.id)),
    filters: PoiRegionFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    stmt = sort.apply(base.options(*EAGER)).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
