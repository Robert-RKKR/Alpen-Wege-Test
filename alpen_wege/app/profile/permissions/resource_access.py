# Standard library
from dataclasses import dataclass

# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import AppError
from app.profile.dependencies import get_current_active_user
from app.profile.services.access_cache import get_policy_scope
from app.profile.models import ProfileUsrUser


@dataclass
class AccessContext:
    user: ProfileUsrUser
    scope: str  # "own" | "public" | "all"


def resource_access(resource_key: str, action: str):
    async def _check(
        user: ProfileUsrUser = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> AccessContext:
        scope = await get_policy_scope(
            user.credentials.user_group,
            resource_key,
            action,
            db,
        )
        if scope is None:
            raise AppError(
                status.HTTP_403_FORBIDDEN,
                "Access denied",
                error_message=f"Your role does not have {action} permission on this resource.",
            )
        return AccessContext(user=user, scope=scope)

    return _check


def check_object_access(access: AccessContext, obj, *, not_found_msg: str = "Not found"):
    if obj is None:
        raise AppError(
            status.HTTP_404_NOT_FOUND,
            "Not found",
            error_message=f"The requested {not_found_msg.lower().replace(' not found', '')} does not exist or you do not have access to it.",
        )
    if access.scope == "all":
        return
    created_by = getattr(obj, "created_by", None)
    if created_by is not None and created_by == access.user.id:
        return
    if access.scope == "public" and getattr(obj, "is_public", False):
        return
    raise AppError(
        status.HTTP_404_NOT_FOUND,
        "Not found",
        error_message=f"The requested {not_found_msg.lower().replace(' not found', '')} does not exist or you do not have access to it.",
    )
