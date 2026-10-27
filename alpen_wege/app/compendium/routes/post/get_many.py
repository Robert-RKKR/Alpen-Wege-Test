from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, contains, equals, ids_query, one_of, page_params, search_query, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.schemas.post import PostRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER

M = CompendiumCatPost
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at}


class PostFilters:
    def __init__(
        self,
        q: str | None = search_query("title in English, German or Polish"),
        post_type_id: list[UUID] | None = ids_query("Post type"),
        created_by: UUID | None = Query(None, description="Posts created by this user."),
    ):
        self.q = q
        self.post_type_id = post_type_id
        self.created_by = created_by

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            one_of(M.post_type_id, self.post_type_id),
            equals(M.created_by, self.created_by),
        )


@router.get("", response_model=ApiResponse[list[PostRead]])
async def list_posts(
    access: AccessContext = Depends(resource_access("post", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: PostFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    stmt = sort.apply(base.options(*EAGER)).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
