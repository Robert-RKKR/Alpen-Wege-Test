# Third-party
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.management.models.settings import MgmtSettings
from app.management.schemas.settings import SettingDetail
from app.profile.models import ProfileUsrUser

from ._router import router
from ._shared import admin_only, get_row


@router.get("/{key}", response_model=ApiResponse[SettingDetail])
async def get_setting_route(
    key: str,
    _user: ProfileUsrUser = Depends(admin_only),
    plan: ExpandPlan = Depends(expand_plan(SettingDetail)),
    db: AsyncSession = Depends(get_db),
):
    row = await get_row(db, key, plan.load_options(MgmtSettings))
    return ok(plan.render(row, viewer=_user))
