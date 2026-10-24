# Third-party
from fastapi import Depends

# Local application
from app.core.utils.responses import ApiResponse, ok
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead


from ._router import router
from ._shared import user_to_read


@router.get("/me", response_model=ApiResponse[UserRead])
async def get_me(
    current_user: ProfileUsrUser = Depends(get_current_active_user),
):
    return ok(user_to_read(current_user))
