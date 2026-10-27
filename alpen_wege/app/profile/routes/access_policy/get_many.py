# Third-party
from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.listing import Page, Sort, equals, page_params, sort_params, where_all
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.core.models.resource_type import CoreRefResourceType
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    AccessPolicyReadWithKey,
)
from app.profile.models import ProfileUsrUser

from ._router import router

M = ProfileAccessPolicy
R = CoreRefResourceType
SORT = {"group": M.user_group, "resource_key": R.key, "action": M.action}


class AccessPolicyFilters:
    def __init__(
        self,
        group: str | None = Query(
            None, pattern="^(administrator|editor|viewer|guest)?$", description="administrator, editor, viewer or guest."
        ),
        resource_key: str | None = Query(None, description="Resource key, for example poi or track."),
        action: str | None = Query(None, pattern="^(create|read|update|delete)?$", description="create, read, update or delete."),
        scope: str | None = Query(None, pattern="^(own|public|all)?$", description="own, public or all."),
    ):
        self.group = group
        self.resource_key = resource_key
        self.action = action
        self.scope = scope

    def apply(self, stmt):
        return where_all(
            stmt,
            equals(M.user_group, self.group),
            equals(R.key, self.resource_key),
            equals(M.action, self.action),
            equals(M.scope, self.scope),
        )


@router.get("", response_model=ApiResponse[list[AccessPolicyReadWithKey]])
async def list_access_policies(
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "group", (R.key, M.action, M.id))),   # the old order: group, key, action
    filters: AccessPolicyFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M).join(R))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    rows = result.scalars().all()

    items = []
    for row in rows:
        data = {
            "id": row.id,
            "user_group": row.user_group,
            "resource_type_id": row.resource_type_id,
            "action": row.action,
            "scope": row.scope,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "resource_key": row.resource_type.key if row.resource_type else None,
        }
        items.append(AccessPolicyReadWithKey(**data))

    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
