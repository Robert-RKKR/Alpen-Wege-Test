# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.runtime_settings.registry import REGISTRY
from app.management.schemas.settings import SettingRead
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, get_row, apply


@router.post("/{key}/reset", response_model=ApiResponse[SettingRead])
async def reset_setting(
    key: str,
    admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = await get_row(db, key)
    return ok(await apply(db, row, REGISTRY[key].default, admin), message="Reset to default")
