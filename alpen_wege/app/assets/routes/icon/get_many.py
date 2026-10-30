from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.schemas.asset import IconRead
from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, before, contains, equals, escape_like, moment_query, page_params, search_query, since, sort_params,
    where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import AccessContext, resource_access

from ._router import router

M = AssetAggIcon
SORT = {"key": M.key, "name": M.name, "created_at": M.created_at, "updated_at": M.updated_at}


class IconFilters:
    def __init__(
        self,
        q: str | None = search_query("key, name or summary in English, German or Polish"),
        key: str | None = Query(None, max_length=100, description="The icon with exactly this key (lower case; an upper-case value is compared in lower case)."),
        key_prefix: str | None = Query(None, max_length=100, description="Keys that start with this text, for example `flag_` for all flags or `sport_` for the sport symbols."),
        created_by: UUID | None = Query(None, description="Icons of this user."),
        created_from: moment_query("Created at or after this date or time.") = None,
        created_to: moment_query("Created before this date or time.") = None,
    ):
        self.q = q
        self.key = key
        self.key_prefix = key_prefix
        self.created_by = created_by
        self.created_from = created_from
        self.created_to = created_to

    def apply(self, stmt):
        prefix = self.key_prefix.strip().lower() if self.key_prefix and self.key_prefix.strip() else None
        return where_all(
            stmt,
            contains(self.q, M.key, M.name, M.name_de, M.name_pl, M.summary, M.summary_de, M.summary_pl),
            equals(M.key, self.key.strip().lower() if self.key else None),
            M.key.like(f"{escape_like(prefix)}%", escape="\\") if prefix else None,
            equals(M.created_by, self.created_by),
            since(M.created_at, self.created_from),
            before(M.created_at, self.created_to),
        )


@router.get(
    "",
    response_model=ApiResponse[list[IconRead]],
    description="The icons (flags, symbols) without their SVG text; the picture itself is `GET /assets/icons/{id}/file`.",
)
async def list_icons(
    access: AccessContext = Depends(resource_access("icon", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "key", M.id)),
    filters: IconFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(select(M))
    if access.scope == "own":
        base = base.where(M.created_by == access.user.id)
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    items = (await db.execute(sort.apply(base).limit(page.limit).offset(page.offset))).scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
