from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.core.models.models_ref import CoreRefDifficultyLevel
from app.core.schemas.ref import RefWithFactorRead, RefWithFactorUpdate

from ._router import router


@router.patch("/{item_id}", response_model=ApiResponse[RefWithFactorRead])
async def update_item(
    item_id: UUID,
    body: RefWithFactorUpdate,
    access: AccessContext = Depends(resource_access("ref", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CoreRefDifficultyLevel, item_id)
    check_object_access(access, obj, not_found_msg="difficulty-levels not found")
    changes = body.model_dump(exclude_unset=True)
    old_values = {f: getattr(obj, f) for f in changes}
    for field, value in changes.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj)
