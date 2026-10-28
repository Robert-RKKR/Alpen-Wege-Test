from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.gpx import AssetAggGpx
from app.assets.schemas.asset import GpxRead
from app.core.dependencies import get_db
from app.core.utils.listing import (
    Page, Sort, before, contains, equals, moment_query, page_params, search_query, since, sort_params, where_all,
)
from app.core.utils.responses import ApiResponse, ok_list
from app.core.utils.scope import apply_scope
from app.profile.permissions import AccessContext, resource_access

from ._router import router

M = AssetAggGpx
SORT = {"name": M.name, "size_bytes": M.size_bytes, "created_at": M.created_at}


class GpxFilters:
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        created_by: UUID | None = Query(None, description="GPX files of this user."),
        is_public: bool | None = Query(None, description="Only public (true) or only private (false) files."),
        sha256: str | None = Query(None, min_length=64, max_length=64, description="Files with this SHA-256 (duplicates)."),
        created_from: moment_query("Created at or after this date or time.") = None,
        created_to: moment_query("Created before this date or time.") = None,
    ):
        self.q = q
        self.created_by = created_by
        self.is_public = is_public
        self.sha256 = sha256.lower() if sha256 else None
        self.created_from = created_from
        self.created_to = created_to

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            equals(M.created_by, self.created_by),
            equals(M.is_public, self.is_public),
            equals(M.sha256, self.sha256),
            since(M.created_at, self.created_from),
            before(M.created_at, self.created_to),
        )


@router.get("", response_model=ApiResponse[list[GpxRead]])
async def list_gpx(
    access: AccessContext = Depends(resource_access("gpx", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "-created_at", M.id)),
    filters: GpxFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    stmt = sort.apply(base).limit(page.limit).offset(page.offset)
    items = (await db.execute(stmt)).scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
