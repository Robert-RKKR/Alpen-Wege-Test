from fastapi import APIRouter, Depends

from app.auth.dependencies import get_current_active_user
from app.auth.schemas import TokenResponse
from app.auth.services.jwt import create_access_token
from app.users.models import ProfileUsrUser
from app.config import get_settings

router = APIRouter()


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    current_user: ProfileUsrUser = Depends(get_current_active_user),
):
    settings = get_settings()
    token = create_access_token(current_user.id, current_user.credentials.user_group)
    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
