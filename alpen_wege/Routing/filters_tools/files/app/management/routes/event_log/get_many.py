# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import PAGE_100, Page, Sort, before, equals, page_params, since, sort_params, where_all, moment_query
from app.management.models.entity_type import MgmtRefEntityType
from app.management.models.event_log import MgmtLogEvent
from app.management.schemas.event_log import (
    EventLogRead,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser

from ._router import router

M = MgmtLogEvent
SORT = {"changed_at": M.changed_at, "seq": M.seq}


class EventLogFilters:
    def __init__(
        self,
        entity_type: str | None = Query(None, description="Filter by entity type key (table name)"),
        entity_id: UUID | None = Query(None, description="The object the entry is about."),
        action: str | None = Query(None, description="created, updated or deleted."),
        changed_by: UUID | None = Query(None, description="The user who made the change."),
        changed_from: moment_query("Changed at or after this date or time.") = None,
        changed_to: moment_query("Changed before this date or time.") = None,
    ):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.action = action
        self.changed_by = changed_by
        self.changed_from = changed_from
        self.changed_to = changed_to

    def apply(self, stmt):
        entity_type_ids = None
        if self.entity_type:
            entity_type_ids = M.entity_type_id.in_(select(MgmtRefEntityType.id).where(MgmtRefEntityType.key == self.entity_type))
        return where_all(
            stmt,
            entity_type_ids,
            equals(M.entity_id, self.entity_id),
            equals(M.action, self.action),
            equals(M.changed_by, self.changed_by),
            since(M.changed_at, self.changed_from),
            before(M.changed_at, self.changed_to),
        )


@router.get("", response_model=ApiResponse[list[EventLogRead]])
async def list_event_logs(
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    page: Page = Depends(page_params(PAGE_100)),
    sort: Sort = Depends(sort_params(SORT, "-changed_at", M.id)),
    filters: EventLogFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base.options(joinedload(M.entity_type))).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().unique().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
