# Third-party
from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import Page, Sort, contains, page_params, search_query, sort_params, where_all
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.core.models.resource_type import CoreRefResourceType
from app.profile.schemas.access_policy import (
    ResourceTypeRead,
)
from app.profile.models import ProfileUsrUser

from ._router import router

M = CoreRefResourceType
SORT = {"key": M.key, "created_at": M.created_at}


class ResourceTypeFilters:
    def __init__(self, q: str | None = search_query("key")):
        self.q = q

    def apply(self, stmt):
        return where_all(stmt, contains(self.q, M.key))


@router.get("", response_model=ApiResponse[list[ResourceTypeRead]])
async def list_resource_types(
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "key", M.id)),
    filters: ResourceTypeFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
