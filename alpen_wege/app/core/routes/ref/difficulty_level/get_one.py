from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.core.models.models_ref import CoreRefDifficultyLevel
from app.core.schemas.ref import RefWithFactorRead

from ._router import router


@router.get("/{item_id}", response_model=ApiResponse[RefWithFactorRead])
async def get_item(
    item_id: UUID,
    access: AccessContext = Depends(resource_access("ref", "read")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CoreRefDifficultyLevel, item_id)
    check_object_access(access, obj, not_found_msg="difficulty-levels not found")
    return ok(obj)
