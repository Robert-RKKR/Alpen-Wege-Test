# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import require_groups
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import (
    AccessPolicyRead,
)
from app.profile.models import ProfileUsrUser

from ._router import router


@router.get("/{item_id}", response_model=ApiResponse[AccessPolicyRead])
async def get_access_policy(
    item_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(ProfileAccessPolicy, item_id)
    if not obj:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message="No access policy exists with the given ID.",
        )
    return ok(obj)
