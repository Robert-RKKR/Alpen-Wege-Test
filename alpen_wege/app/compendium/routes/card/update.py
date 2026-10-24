from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.schemas.card import CardRead, CardUpdate

from ._router import router
from ._shared import EAGER


@router.patch("/{card_id}", response_model=ApiResponse[CardRead])
async def update_card(
    card_id: UUID,
    body: CardUpdate,
    access: AccessContext = Depends(resource_access("card", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCard, card_id)
    check_object_access(access, obj, not_found_msg="Card not found")
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(obj, f) for f in changes}
    for field, value in changes.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, changes, access.user.id)
    await db.commit()
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == card_id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())
