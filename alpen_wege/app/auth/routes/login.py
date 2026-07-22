from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.auth.schemas import LoginRequest, TokenResponse
from app.auth.services.jwt import create_access_token
from app.auth.services.passwords import verify_password
from app.auth.models import AuthUserCredentials
from app.users.models import ProfileUsrUser
from app.config import get_settings

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ProfileUsrUser)
        .options(selectinload(ProfileUsrUser.credentials))
        .where(ProfileUsrUser.email == body.email)
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if not user or not user.credentials or not verify_password(body.password, user.credentials.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is deactivated")

    user.credentials.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    settings = get_settings()
    token = create_access_token(user.id, user.credentials.user_group)
    return TokenResponse(
        access_token=token,
        expires_in=settings.JWT_EXPIRE_MINUTES * 60,
    )
