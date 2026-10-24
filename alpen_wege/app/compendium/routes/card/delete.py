from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_deleted
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.card import CompendiumCatCard

from ._router import router


@router.delete("/{card_id}", response_model=ApiResponse[None])
async def delete_card(
    card_id: UUID,
    access: AccessContext = Depends(resource_access("card", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCard, card_id)
    check_object_access(access, obj, not_found_msg="Card not found")
    log_deleted(db, obj, access.user.id)
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")
