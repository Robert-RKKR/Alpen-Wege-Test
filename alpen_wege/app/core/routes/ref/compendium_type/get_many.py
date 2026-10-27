from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    NameFilters, Page, Sort, equals, page_params, search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefCompendiumType
from app.core.schemas.ref import CompendiumTypeRead

from ._router import router

M = CoreRefCompendiumType
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at, "point_factor": M.point_factor}


class CompendiumTypeFilters(NameFilters):
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        created_by: UUID | None = Query(None, description="Rows created by this user."),
        is_collectable: bool | None = Query(None, description="Only the types that can be collected (true) or not (false)."),
    ):
        super().__init__(q, created_by)
        self.is_collectable = is_collectable

    def apply(self, stmt, model):
        return where_all(super().apply(stmt, model), equals(model.is_collectable, self.is_collectable))


@router.get("", response_model=ApiResponse[list[CompendiumTypeRead]])
async def list_items(
    access: AccessContext = Depends(resource_access("ref", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: CompendiumTypeFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M), M)
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
