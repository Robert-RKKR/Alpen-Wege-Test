# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import PAGE_100_MAX_500, Page, Sort, before, equals, page_params, since, sort_params, where_all, moment_query
from app.core.utils.responses import ApiResponse, AppError, ok_list
from app.management.jobs.kinds import JOB_STATUSES
from app.management.models.job import MgmtLogJob
from app.management.schemas.job import JobRead
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser

from ._router import router

M = MgmtLogJob
SORT = {"created_at": M.created_at, "finished_at": M.finished_at, "status": M.status}


class MyJobFilters:
    def __init__(
        self,
        status: str | None = Query(None, description="queued, running, succeeded, failed or cancelled."),
        kind: str | None = Query(None, description="Kind of job: track.process, track.reprocess, poi.rescan, card.rescan or demo."),
        subject_type: str | None = Query(None, description="Type of the object the job works on, for example track."),
        subject_id: UUID | None = Query(None, description="The object the job works on."),
        active: bool = Query(False, description="true: only queued and running jobs."),
        created_from: moment_query("Created at or after this date or time.") = None,
        created_to: moment_query("Created before this date or time.") = None,
    ):
        if status and status not in JOB_STATUSES:
            raise AppError(422, f"Invalid status: {status}")
        self.status = status
        self.kind = kind
        self.subject_type = subject_type
        self.subject_id = subject_id
        self.active = active
        self.created_from = created_from
        self.created_to = created_to

    def apply(self, stmt):
        return where_all(
            stmt,
            equals(M.status, self.status),
            equals(M.kind, self.kind),
            equals(M.subject_type, self.subject_type),
            equals(M.subject_id, self.subject_id),
            M.status.in_(("queued", "running")) if self.active else None,
            since(M.created_at, self.created_from),
            before(M.created_at, self.created_to),
        )


@router.get("", response_model=ApiResponse[list[JobRead]])
async def list_my_jobs(
    user: ProfileUsrUser = Depends(get_current_active_user),
    page: Page = Depends(page_params(PAGE_100_MAX_500)),
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: MyJobFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M).where(M.user_id == user.id))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))).scalars().all()
    return ok_list(rows, total=total, limit=page.limit, offset=page.offset)
