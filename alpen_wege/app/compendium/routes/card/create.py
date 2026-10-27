from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.schemas.card import CardCreate, CardRead

from ._router import router
from ._shared import EAGER, queue_render_quietly


@router.post("", response_model=ApiResponse[CardRead], status_code=status.HTTP_201_CREATED)
async def create_card(
    body: CardCreate,
    access: AccessContext = Depends(resource_access("card", "create")),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumCatCard(**body.model_dump(exclude_unset=True), created_by=access.user.id)
    db.add(obj)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "Card number already used.", error_errors=[{"field": "body.card_number", "message": "already used"}])
    log_created(db, obj, access.user.id)
    await db.commit()
    await queue_render_quietly(db, obj.id, access.user.id)
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == obj.id)
        .options(*EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")
