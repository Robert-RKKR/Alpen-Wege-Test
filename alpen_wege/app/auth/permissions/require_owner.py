# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, HTTPException, status

# Local application
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser


def require_owner_or_groups(target_user_id: UUID, *allowed_groups: str):
    # Build a dependency allowing access only to the resource owner or privileged groups.
    # Params:
    #   target_user_id: the id of the user who owns the resource being accessed.
    #   allowed_groups: group names (e.g. "admin") that may bypass the ownership check.
    # Returns: an async dependency callable that yields the user if authorized.
    async def _check(
        current_user: ProfileUsrUser = Depends(get_current_active_user),
    ) -> ProfileUsrUser:
        # Inner dependency: allow the owner, or any user in a privileged group.
        # Params:
        #   current_user: the authenticated, active user, injected by the dependency.
        # Returns: the same user when they own the resource or are privileged.
        # Raises: HTTPException 403 when the user is neither the owner nor privileged.
        # Owner check: is the caller acting on their own resource?
        is_self = current_user.id == target_user_id
        # Privilege check: does the caller belong to an allowed override group?
        is_privileged = current_user.credentials.user_group in allowed_groups
        # Deny only when the caller is neither the owner nor privileged.
        if not is_self and not is_privileged:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot access another user's resource",
            )
        return current_user

    return _check
