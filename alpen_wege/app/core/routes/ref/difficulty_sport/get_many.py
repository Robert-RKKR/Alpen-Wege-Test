from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, RankFilters, Sort, ids_query, number_query, one_of, page_params, search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefDifficultySport
from app.core.schemas.ref import DifficultySportRead

from ._router import router

M = CoreRefDifficultySport
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at, "point_factor": M.point_factor, "rank": M.rank}


class DifficultySportFilters(RankFilters):
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        created_by: UUID | None = Query(None, description="Rows created by this user."),
        rank_min: int | None = number_query("Rank, at least. Ranks only compare inside one sport type."),
        rank_max: int | None = number_query("Rank, at most."),
        sport_type_id: list[UUID] | None = ids_query("Sport type"),
    ):
        super().__init__(q, created_by, rank_min, rank_max)
        self.sport_type_id = sport_type_id

    def apply(self, stmt, model):
        return where_all(super().apply(stmt, model), one_of(model.sport_type_id, self.sport_type_id))


@router.get("", response_model=ApiResponse[list[DifficultySportRead]])
async def list_items(
    access: AccessContext = Depends(resource_access("ref", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: DifficultySportFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M), M)
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
