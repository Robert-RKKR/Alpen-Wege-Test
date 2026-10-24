# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.schemas.settings import SettingRead
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, get_row


@router.get("/{key}", response_model=ApiResponse[SettingRead])
async def get_setting_route(
    key: str,
    _user: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return ok(await get_row(db, key))
