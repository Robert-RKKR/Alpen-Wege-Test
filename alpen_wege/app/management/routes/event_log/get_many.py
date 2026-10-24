# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

# Local application
from app.core.dependencies import get_db
from app.management.models.entity_type import MgmtRefEntityType
from app.management.models.event_log import MgmtLogEvent
from app.management.schemas.event_log import (
    EventLogRead,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("", response_model=ApiResponse[list[EventLogRead]])
async def list_event_logs(
    limit: int = 100,
    offset: int = 0,
    entity_type: str | None = Query(None, description="Filter by entity type key (table name)"),
    entity_id: UUID | None = Query(None),
    action: str | None = Query(None),
    changed_by: UUID | None = Query(None),
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    filters = []
    if entity_type is not None:
        sub = select(MgmtRefEntityType.id).where(MgmtRefEntityType.key == entity_type)
        filters.append(MgmtLogEvent.entity_type_id.in_(sub))
    if entity_id is not None:
        filters.append(MgmtLogEvent.entity_id == entity_id)
    if action is not None:
        filters.append(MgmtLogEvent.action == action)
    if changed_by is not None:
        filters.append(MgmtLogEvent.changed_by == changed_by)

    count_stmt = select(func.count()).select_from(MgmtLogEvent)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(MgmtLogEvent)
        .options(joinedload(MgmtLogEvent.entity_type))
        .order_by(MgmtLogEvent.changed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    for f in filters:
        stmt = stmt.where(f)
    result = await db.execute(stmt)
    items = result.scalars().unique().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
