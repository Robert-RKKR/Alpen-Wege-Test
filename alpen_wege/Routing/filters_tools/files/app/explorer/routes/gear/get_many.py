from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, at_least, at_most, contains, equals, ids_query, number_query, one_of, page_params, search_query,
    sort_params, where_all,
)
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok_list
from app.explorer.schemas.gear import GearRead
from app.core.utils.scope import apply_scope

from ._router import router

M = ExplorerAggGear
SORT = {"name": M.name, "created_at": M.created_at, "weight_g": M.weight_g}


class GearFilters:
    def __init__(
        self,
        q: str | None = search_query("name or model"),
        company_id: list[UUID] | None = ids_query("Company"),
        gear_type_id: list[UUID] | None = ids_query("Gear type"),
        created_by: UUID | None = Query(None, description="Gear of this user."),
        weight_min: int | None = number_query("Weight in grams, at least."),
        weight_max: int | None = number_query("Weight in grams, at most."),
    ):
        self.q = q
        self.company_id = company_id
        self.gear_type_id = gear_type_id
        self.created_by = created_by
        self.weight_min = weight_min
        self.weight_max = weight_max

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl, M.model),
            one_of(M.company_id, self.company_id),
            one_of(M.gear_type_id, self.gear_type_id),
            equals(M.created_by, self.created_by),
            at_least(M.weight_g, self.weight_min),
            at_most(M.weight_g, self.weight_max),
        )


@router.get("", response_model=ApiResponse[list[GearRead]])
async def list_gear(
    access: AccessContext = Depends(resource_access("gear", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: GearFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
