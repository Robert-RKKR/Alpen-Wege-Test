from uuid import UUID

from fastapi import Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.listing import Page, Sort, contains, equals, page_params, search_query, sort_params, where_all
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryRead
from app.core.utils.scope import apply_scope

from ._router import router

M = CompendiumCatCountry
SORT = {"name": M.name, "iso_code": M.iso_code, "created_at": M.created_at}


class CountryFilters:
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        iso_code: str | None = Query(None, min_length=2, max_length=3, description="ISO code, not case sensitive (AT, DE, ...)."),
        created_by: UUID | None = Query(None, description="Countries created by this user."),
    ):
        self.q = q
        self.iso_code = iso_code
        self.created_by = created_by

    def apply(self, stmt):
        return where_all(
            stmt,
            contains(self.q, M.name, M.name_de, M.name_pl),
            equals(func.upper(M.iso_code), self.iso_code.upper() if self.iso_code else None),
            equals(M.created_by, self.created_by),
        )


@router.get("", response_model=ApiResponse[list[CountryRead]])
async def list_countries(
    access: AccessContext = Depends(resource_access("country", "read")),
    page: Page = Depends(page_params()),
    sort: Sort = Depends(sort_params(SORT, "name", M.id)),
    filters: CountryFilters = Depends(),
    db: AsyncSession = Depends(get_db),
):
    base = filters.apply(apply_scope(select(M), M, access))
    total = (await db.execute(select(func.count()).select_from(base.subquery()))).scalar()
    stmt = sort.apply(base).limit(page.limit).offset(page.offset)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=page.limit, offset=page.offset)
