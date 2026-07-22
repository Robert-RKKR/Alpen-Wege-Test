from fastapi import Depends, HTTPException, status

from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser


def require_groups(*allowed_groups: str):
    async def _check(
        current_user: ProfileUsrUser = Depends(get_current_active_user),
    ) -> ProfileUsrUser:
        if current_user.credentials.user_group not in allowed_groups:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_groups)}",
            )
        return current_user

    return _check
