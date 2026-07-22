from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, status

from app.auth.dependencies import get_current_user
from app.auth.services.jwt import blacklist_token
from app.users.models import ProfileUsrUser

router = APIRouter()


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    _current_user: ProfileUsrUser = Depends(get_current_user),
):
    jti = request.state.old_jti
    exp = request.state.old_token_exp
    remaining = exp - int(datetime.now(timezone.utc).timestamp())
    if remaining > 0:
        await blacklist_token(jti, remaining)
