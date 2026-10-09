# Third-party
from fastapi import APIRouter, Depends

# Local application
from app.profile.dependencies import get_current_active_user
from app.core.utils.responses import ApiResponse, ok
from app.profile.schemas import TokenResponse
from app.profile.services.jwt import create_access_token
from app.profile.models import ProfileUsrUser
from app.config import get_settings

router = APIRouter()


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token(
    current_user: ProfileUsrUser = Depends(get_current_active_user),
):
    # Issue a fresh access token for the already-authenticated caller.
    # Params:
    #   current_user: the authenticated, active user, injected by the
    # dependency.
    # Returns: a TokenResponse with a new access token and its lifetime in
    # seconds.
    # Mint a new token carrying the user's id and group.
    settings = get_settings()
    token = create_access_token(
        current_user.id, current_user.credentials.user_group
    )
    return ok(
        TokenResponse(
            access_token=token,
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        ),
        message="Token refreshed",
    )
