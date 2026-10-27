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
from app.management.schemas.job import JobAdminRead
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, T

SORT = {"created_at": T.created_at, "finished_at": T.finished_at, "status": T.status}


class JobFilters:
    def __init__(
        self,
        status: str | None = Query(None, description="queued, running, succeeded, failed or cancelled."),
        kind: str | None = Query(None, description="Kind of job: track.process, track.reprocess, poi.rescan, card.rescan or demo."),
        user_id: UUID | None = Query(None, description="Jobs of this user."),
        task_name: str | None = Query(None, description="Name of the Celery task, for example tracks.process_gpx."),
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
        self.user_id = user_id
        self.task_name = task_name
        self.subject_type = subject_type
        self.subject_id = subject_id
        self.active = active
        self.created_from = created_from
        self.created_to = created_to

    def apply(self, stmt):
        return where_all(
            stmt,
            equals(T.status, self.status),
            equals(T.kind, self.kind),
            equals(T.user_id, self.user_id),
            equals(T.task_name, self.task_name),
            equals(T.subject_type, self.subject_type),
            equals(T.subject_id, self.subject_id),
            T.status.in_(("queued", "running")) if self.active else None,
            since(T.created_at, self.created_from),
            before(T.created_at, self.created_to),
        )


@router.get("", response_model=ApiResponse[list[JobAdminRead]])
async def list_all_jobs(
    _admin: ProfileUsrUser = Depends(admin_only),
    page: Page = Depends(page_params(PAGE_100_MAX_500)),
    sort: Sort = Depends(sort_params(SORT, "-created_at", T.id)),
    filters: JobFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(T))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))).scalars().all()
    return ok_list(rows, total=total, limit=page.limit, offset=page.offset)
