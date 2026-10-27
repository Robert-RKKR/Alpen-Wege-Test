from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.schemas.card import CardDetail

from ._router import router


@router.get("/{card_id}", response_model=ApiResponse[CardDetail])
async def get_card(
    card_id: UUID,
    access: AccessContext = Depends(resource_access("card", "read")),
    plan: ExpandPlan = Depends(expand_plan(CardDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == card_id)
        .options(*plan.load_options(CompendiumCatCard))
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Card not found")
    return ok(plan.render(obj, viewer=access.user))
