# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, before, contains, equals, page_params, search_query, since, sort_params, where_all, moment_query,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser, ProfileUserCredentials
from app.profile.schemas import UserRead


from ._router import router
from ._shared import user_to_read

M = ProfileUsrUser
C = ProfileUserCredentials
SORT = {
    "created_at": M.created_at,
    "username": M.username,
    "last_active_at": M.last_active_at,
}


class UserFilters:
    def __init__(
        self,
        q: str | None = search_query("username, e-mail, first name or last name"),
        is_active: bool | None = Query(None, description="Only active (true) or only deactivated (false) users."),
        user_group: str | None = Query(
            None, pattern="^(administrator|editor|viewer|guest)?$", description="administrator, editor, viewer or guest."
        ),
        created_from: moment_query("Created at or after this date or time.") = None,
        created_to: moment_query("Created before this date or time.") = None,
    ):
        self.q = q
        self.is_active = is_active
        self.user_group = user_group
        self.created_from = created_from
        self.created_to = created_to

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.username, M.email, M.first_name, M.last_name),
            equals(M.is_active, self.is_active),
            equals(C.user_group, self.user_group),
            since(M.created_at, self.created_from),
            before(M.created_at, self.created_to),
        )


@router.get("/", response_model=ApiResponse[list[UserRead]])
async def list_users(
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    page: Page = Depends(page_params(offset_alias="skip")),   # the users list has always called the offset skip
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: UserFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M).outerjoin(C, C.user_id == M.id))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base.options(selectinload(M.credentials))).limit(page.limit).offset(page.offset)
    users = (await db.execute(stmt)).scalars().all()
    items = [user_to_read(u) for u in users]
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
