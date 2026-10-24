# Third-party
from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.schemas import RegisterRequest, TokenResponse
from app.profile.services.jwt import create_access_token
from app.profile.services.passwords import hash_password
from app.profile.models import ProfileUserCredentials, ProfileUsrUser
from app.config import get_settings

from ._router import router


@router.post(
    "/register",
    response_model=ApiResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Create a new user account plus credentials and return an access token.
    # Params:
    #   body: the registration payload (email, username, names, password).
    #   db: the async database session, injected by get_db.
    # Returns: a TokenResponse so the new user is logged in immediately (HTTP
    # 201).
    # Raises: HTTPException 409 if the email or username is already in use.
    from sqlalchemy import select

    # Reject the request if the email or username already belongs to another
    # account.
    existing = await db.execute(
        select(ProfileUsrUser).where(
            (ProfileUsrUser.email == body.email)
            | (ProfileUsrUser.username == body.username)
        )
    )
    if existing.scalar_one_or_none():
        raise AppError(
            status.HTTP_409_CONFLICT,
            "Registration conflict",
            error_message="An account with this email or username already exists.",
            error_errors=[{"field": "email/username", "code": "conflict", "message": "Already registered"}],
        )

    # Create the user row and flush so its generated id is available for
    # credentials.
    user = ProfileUsrUser(
        email=body.email,
        username=body.username,
        first_name=body.first_name,
        last_name=body.last_name,
    )
    db.add(user)
    await db.flush()

    # Store the hashed password and default "user" group in the credentials
    # table.
    credentials = ProfileUserCredentials(
        user_id=user.id,
        password_hash=hash_password(body.password),
        user_group="guest",
    )
    db.add(credentials)
    await db.flush()

    # Issue an access token so the caller is authenticated right after signup.
    settings = get_settings()
    token = create_access_token(user.id, credentials.user_group)
    return ok(
        TokenResponse(
            access_token=token,
            expires_in=settings.JWT_EXPIRE_MINUTES * 60,
        ),
        code=201,
        message="Registered",
    )
