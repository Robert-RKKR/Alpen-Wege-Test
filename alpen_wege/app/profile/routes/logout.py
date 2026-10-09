# Standard library
from datetime import datetime, timezone

# Third-party
from fastapi import APIRouter, Depends, Request, status

# Local application
from app.profile.dependencies import get_current_user
from app.core.utils.responses import ApiResponse, ok
from app.profile.services.jwt import blacklist_token
from app.profile.models import ProfileUsrUser

router = APIRouter()


@router.post("/logout", response_model=ApiResponse[None])
async def logout(
    request: Request,
    _current_user: ProfileUsrUser = Depends(get_current_user),
):
    # Log the caller out by revoking the access token used for this request.
    # Params:
    #   request: the current request; its state holds the token's id and
    # expiry.
    #   _current_user: the authenticated user (dependency enforces
    # authentication only).
    # Returns: nothing (HTTP 204 No Content).
    # Read the current token's id and expiry captured during authentication.
    jti = request.state.old_jti
    exp = request.state.old_token_exp
    # Blacklist the token for its remaining lifetime so it can't be reused.
    remaining = exp - int(datetime.now(timezone.utc).timestamp())
    if remaining > 0:
        await blacklist_token(jti, remaining)
    return ok(None, message="Logged out")
