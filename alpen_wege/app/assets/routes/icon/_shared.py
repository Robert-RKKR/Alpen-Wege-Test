from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.responses import AppError
from app.profile.services.access_cache import get_policy_scope


def key_taken() -> AppError:
    return AppError(
        409, "Duplicate entry",
        error_message="An icon with this key already exists.",
        error_errors=[{"field": "key", "code": "conflict", "message": "Key already in use"}],
    )


async def require_policy(db: AsyncSession, user, resource_key: str, action: str) -> None:
    # A route that needs a second permission besides the one of its dependency (the CSV import with update=true or link=true).
    if await get_policy_scope(user.credentials.user_group, resource_key, action, db) is None:
        raise AppError(403, "Access denied", error_message=f"Your role does not have {action} permission on {resource_key}, which this option needs.")
