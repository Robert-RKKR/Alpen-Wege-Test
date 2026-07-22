from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.users.models import ProfileUsrUser
from app.auth.services.jwt import decode_token, is_token_blacklisted

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> ProfileUsrUser:
    try:
        payload = decode_token(token)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")

    jti = payload.get("jti")
    if not jti or await is_token_blacklisted(jti):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token has been revoked")

    user_id = UUID(payload["sub"])
    stmt = (
        select(ProfileUsrUser)
        .options(selectinload(ProfileUsrUser.credentials))
        .where(ProfileUsrUser.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")

    request.state.authenticated_user_id = user_id
    request.state.authenticated_user_group = user.credentials.user_group
    request.state.old_jti = jti
    request.state.old_token_exp = payload["exp"]

    return user


async def get_current_active_user(
    user: ProfileUsrUser = Depends(get_current_user),
) -> ProfileUsrUser:
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is deactivated")
    return user
