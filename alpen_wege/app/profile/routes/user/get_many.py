# Third-party
from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok_list
from app.profile.permissions import require_groups
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead
from app.profile.services import UserService


from ._router import router
from ._shared import user_to_read


@router.get("/", response_model=ApiResponse[list[UserRead]])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1),
    is_active: bool | None = None,
    _admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    users, total = await service.list_users(skip, limit, is_active)
    items = [user_to_read(u) for u in users]
    return ok_list(items, total=total, limit=limit, offset=skip)
