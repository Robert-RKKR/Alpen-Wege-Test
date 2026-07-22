from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.auth.schemas import RegisterRequest, TokenResponse
from app.auth.services.jwt import create_access_token
from app.auth.services.passwords import hash_password
from app.auth.models import AuthUserCredentials
from app.users.models import ProfileUsrUser
from app.config import get_settings

router = APIRouter()


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select

    existing = await db.execute(
        select(ProfileUsrUser).where(
            (ProfileUsrUser.email == body.email) | (ProfileUsrUser.username == body.username)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email or username already taken")

    user = ProfileUsrUser(
        email=body.email,
        username=body.username,
        first_name=body.first_name,
        last_name=body.last_name,
    )
    db.add(user)
    await db.flush()

    credentials = AuthUserCredentials(
        user_id=user.id,
        password_hash=hash_password(body.password),
        user_group="user",
    )
    db.add(credentials)
    await db.flush()

    settings = get_settings()
    token = create_access_token(user.id, credentials.user_group)
    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
