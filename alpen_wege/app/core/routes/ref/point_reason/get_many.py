from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import NameFilters, Page, Sort, page_params, sort_params
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefPointReason
from app.core.schemas.ref import RefWithFactorRead

from ._router import router

M = CoreRefPointReason
SORT = {"name": M.name, "created_at": M.created_at, "updated_at": M.updated_at, "point_factor": M.point_factor}


@router.get("", response_model=ApiResponse[list[RefWithFactorRead]])
async def list_items(
    access: AccessContext = Depends(resource_access("ref", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: NameFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M), M)
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    result = await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))
    return ok_list(result.scalars().all(), total=total, limit=page.limit, offset=page.offset)
