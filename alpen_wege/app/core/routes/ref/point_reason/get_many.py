from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefPointReason
from app.core.schemas.ref import RefWithFactorRead

from ._router import router


@router.get("", response_model=ApiResponse[list[RefWithFactorRead]])
async def list_items(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("ref", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CoreRefPointReason)
    if access.scope == "own":
        count_stmt = count_stmt.where(CoreRefPointReason.created_by == access.user.id)
    total = (await db.execute(count_stmt)).scalar()

    stmt = select(CoreRefPointReason).order_by(CoreRefPointReason.name).limit(limit).offset(offset)
    if access.scope == "own":
        stmt = stmt.where(CoreRefPointReason.created_by == access.user.id)
    result = await db.execute(stmt)
    return ok_list(result.scalars().all(), total=total, limit=limit, offset=offset)
