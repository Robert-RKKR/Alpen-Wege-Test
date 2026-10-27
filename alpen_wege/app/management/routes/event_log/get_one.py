# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.management.models.event_log import MgmtLogEvent
from app.management.schemas.event_log import (
    EventLogDetail,
)
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("/{log_id}", response_model=ApiResponse[EventLogDetail])
async def get_event_log(
    log_id: UUID,
    _user: ProfileUsrUser = Depends(require_groups("administrator")),
    plan: ExpandPlan = Depends(expand_plan(EventLogDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(MgmtLogEvent)
        .options(*plan.load_options(MgmtLogEvent))
        .where(MgmtLogEvent.id == log_id)
    )
    result = await db.execute(stmt)
    entry = result.scalar_one_or_none()
    if entry is None:
        raise AppError(404, "Not found", error_message="Event log entry not found.")
    return ok(plan.render(entry, viewer=_user))
