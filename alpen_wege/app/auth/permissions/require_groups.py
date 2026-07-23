# Third-party
from fastapi import Depends, HTTPException, status

# Local application
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser


def require_groups(*allowed_groups: str):
    # Build a FastAPI dependency that restricts a route to specific user groups.
    # Params:
    #   allowed_groups: one or more group names permitted to access the route.
    # Returns: an async dependency callable that yields the user if authorized.
    async def _check(
        current_user: ProfileUsrUser = Depends(get_current_active_user),
    ) -> ProfileUsrUser:
        # Inner dependency: verify the authenticated user's group is allowed.
        # Params:
        #   current_user: the authenticated, active user, injected by the dependency.
        # Returns: the same user when their group is in allowed_groups.
        # Raises: HTTPException 403 if the user's group is not permitted.
        # Deny access when the user's group is not among the allowed ones.
        if current_user.credentials.user_group not in allowed_groups:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of: {', '.join(allowed_groups)}",
            )
        return current_user

    return _check
