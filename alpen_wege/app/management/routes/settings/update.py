# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.runtime_settings.registry import REGISTRY, validate_value
from app.management.schemas.settings import SettingRead, SettingUpdate
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, get_row, apply


@router.patch("/{key}", response_model=ApiResponse[SettingRead])
async def update_setting(
    key: str,
    body: SettingUpdate,
    admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = await get_row(db, key)
    try:
        value = validate_value(REGISTRY[key], body.value)
    except ValueError as exc:
        raise AppError(
            422, "Validation failed",
            error_message=f"{key}: {exc}",
            error_errors=[{"field": "value", "code": "invalid_value", "message": str(exc)}],
        )
    return ok(await apply(db, row, value, admin), message="Updated")
