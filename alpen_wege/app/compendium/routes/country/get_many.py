from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryRead
from app.core.utils.scope import apply_scope

from ._router import router


@router.get("", response_model=ApiResponse[list[CountryRead]])
async def list_countries(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("country", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatCountry)
    count_stmt = apply_scope(count_stmt, CompendiumCatCountry, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatCountry).order_by(CompendiumCatCountry.name).limit(limit).offset(offset)
    stmt = apply_scope(stmt, CompendiumCatCountry, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
