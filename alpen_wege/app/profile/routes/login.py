# Standard library
from datetime import datetime, timezone

# Third-party
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.schemas import LoginRequest, TokenResponse
from app.profile.services.jwt import create_access_token
from app.profile.services.passwords import verify_password
from app.profile.models import ProfileUserCredentials, ProfileUsrUser
from app.config import get_settings

router = APIRouter()


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    # Authenticate a user by email/password and issue an access token.
    # Params:
    #   body: the login request payload (email + password).
    #   db: the async database session, injected by get_db.
    # Returns: a TokenResponse containing the access token and its lifetime in
    # seconds.
    # Raises: HTTPException 401 for bad credentials, 403 if the account is
    # deactivated.
    # Look up the user by email, eager-loading their credentials for the check.
    stmt = (
        select(ProfileUsrUser)
        .options(selectinload(ProfileUsrUser.credentials))
        .where(ProfileUsrUser.email == body.email)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # Reject unknown users and wrong passwords with the same generic 401 (no
    # enumeration).
    if (
        not user
        or not user.credentials
        or not verify_password(body.password, user.credentials.password_hash)
    ):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid credentials"
        )

    # Valid credentials but a disabled account is forbidden, not unauthorized.
    if not user.is_active:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Account is deactivated"
        )

    # Record the successful login timestamp.
    user.credentials.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    # Mint and return the access token for the authenticated user.
    settings = get_settings()
    token = create_access_token(user.id, user.credentials.user_group)
    return ok(
        TokenResponse(
            access_token=token,
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        ),
        message="Login successful",
    )
