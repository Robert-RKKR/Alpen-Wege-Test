from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok_list
from app.explorer.schemas.gear import GearRead
from app.core.utils.scope import apply_scope

from ._router import router


@router.get("", response_model=ApiResponse[list[GearRead]])
async def list_gear(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("gear", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(ExplorerAggGear)
    count_stmt = apply_scope(count_stmt, ExplorerAggGear, access)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ExplorerAggGear)
        .order_by(ExplorerAggGear.created_at.desc())
        .limit(limit).offset(offset)
    )
    stmt = apply_scope(stmt, ExplorerAggGear, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
