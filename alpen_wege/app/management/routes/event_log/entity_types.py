# Third-party
from fastapi import Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.models.entity_type import MgmtRefEntityType
from app.management.schemas.event_log import (
    EntityTypeRead,
)
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("/entity-types", response_model=ApiResponse[list[EntityTypeRead]])
async def list_entity_types(
    module: str | None = Query(None, description="Filter by module (e.g. explorer, profile)"),
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MgmtRefEntityType).order_by(MgmtRefEntityType.module, MgmtRefEntityType.key)
    if module is not None:
        stmt = stmt.where(MgmtRefEntityType.module == module)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok(items)
