# Third-party
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.models.settings import MgmtSettings
from app.management.schemas.settings import SettingRead
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only


@router.get("", response_model=ApiResponse[list[SettingRead]])
async def list_settings(
    category: str | None = None,
    _user: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MgmtSettings).order_by(MgmtSettings.category, MgmtSettings.key)
    if category is not None:
        stmt = stmt.where(MgmtSettings.category == category)
    return ok((await db.execute(stmt)).scalars().all())
