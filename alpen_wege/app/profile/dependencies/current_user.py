# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import AppError
from app.profile.models import ProfileUsrUser
from app.profile.services.jwt import decode_token, is_token_blacklisted

# OAuth2 bearer scheme; extracts the token from the Authorization header.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


async def get_current_user(
    request: Request,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> ProfileUsrUser:
    # FastAPI dependency that resolves the authenticated user from a bearer
    # token.
    # Params:
    #   request: the current request; its state is populated for the refresh
    # middleware.
    #   token: the bearer access token, injected by the OAuth2 scheme.
    #   db: the async database session, injected by get_db.
    # Returns: the ProfileUsrUser matching the token's subject.
    # Raises: HTTPException 401 if the token is invalid, revoked, or the user
    # is missing.
    # Decode/verify the token; invalid or expired tokens are rejected as 401.
    try:
        payload = decode_token(token)
    except ValueError:
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication failed",
            error_message="The access token is invalid, expired, or malformed. Please log in again.",
        )

    # Reject tokens that have been explicitly revoked (e.g. logout / rotation).
    jti = payload.get("jti")
    if not jti or await is_token_blacklisted(jti):
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication failed",
            error_message="This session has been revoked. Please log in again to get a new token.",
        )

    # Load the user (and their credentials) named by the token subject claim.
    user_id = UUID(payload["sub"])
    stmt = (
        select(ProfileUsrUser)
        .options(selectinload(ProfileUsrUser.credentials))
        .where(ProfileUsrUser.id == user_id)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # A token referencing a deleted/credential-less user is treated as
    # unauthorized.
    if not user or not user.credentials:
        raise AppError(
            status.HTTP_401_UNAUTHORIZED,
            "Authentication failed",
            error_message="The account associated with this token no longer exists.",
        )

    # Stash identity/token details on request.state so TokenRefreshMiddleware
    # can rotate.
    request.state.authenticated_user_id = user_id
    request.state.authenticated_user_group = user.credentials.user_group
    request.state.old_jti = jti
    request.state.old_token_exp = payload["exp"]

    return user


async def get_current_active_user(
    user: ProfileUsrUser = Depends(get_current_user),
) -> ProfileUsrUser:
    # Dependency that additionally requires the authenticated user to be
    # active.
    # Params:
    #   user: the authenticated user, injected by get_current_user.
    # Returns: the same user when the account is active.
    # Raises: HTTPException 403 if the account has been deactivated.
    if not user.is_active:
        raise AppError(
            status.HTTP_403_FORBIDDEN,
            "Account suspended",
            error_message="Your account has been deactivated. Contact an administrator to restore access.",
        )
    return user
