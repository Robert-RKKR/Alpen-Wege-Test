from uuid import UUID

from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser


def require_owner_or_groups(target_user_id: UUID, *allowed_groups: str):
    async def _check(
        current_user: ProfileUsrUser = Depends(get_current_active_user),
    ) -> ProfileUsrUser:
        is_self = current_user.id == target_user_id
        is_privileged = current_user.credentials.user_group in allowed_groups
        if not is_self and not is_privileged:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another user's resource",
            )
        return current_user

    return _check
