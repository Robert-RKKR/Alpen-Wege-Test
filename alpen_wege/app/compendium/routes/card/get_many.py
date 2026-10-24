from fastapi import Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.schemas.card import CardRead
from app.core.utils.scope import apply_scope

from ._router import router
from ._shared import EAGER


@router.get("", response_model=ApiResponse[list[CardRead]])
async def list_cards(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("card", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatCard)
    count_stmt = apply_scope(count_stmt, CompendiumCatCard, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatCard).options(*EAGER).order_by(CompendiumCatCard.name).limit(limit).offset(offset)
    stmt = apply_scope(stmt, CompendiumCatCard, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)
