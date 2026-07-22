from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.users.models import ProfileUsrUser
from app.auth.models import AuthUserCredentials


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, user_id: UUID) -> ProfileUsrUser | None:
        stmt = (
            select(ProfileUsrUser)
            .options(selectinload(ProfileUsrUser.credentials))
            .where(ProfileUsrUser.id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_profile(self, user: ProfileUsrUser, data: dict) -> ProfileUsrUser:
        for key, value in data.items():
            if value is not None:
                setattr(user, key, value)
        await self.db.flush()
        return user

    async def list_users(
        self, skip: int = 0, limit: int = 50, is_active: bool | None = None
    ) -> tuple[list[ProfileUsrUser], int]:
        stmt = select(ProfileUsrUser).options(selectinload(ProfileUsrUser.credentials))
        count_stmt = select(func.count()).select_from(ProfileUsrUser)

        if is_active is not None:
            stmt = stmt.where(ProfileUsrUser.is_active == is_active)
            count_stmt = count_stmt.where(ProfileUsrUser.is_active == is_active)

        total = (await self.db.execute(count_stmt)).scalar() or 0
        stmt = stmt.offset(skip).limit(limit).order_by(ProfileUsrUser.created_at.desc())
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())
        return users, total

    async def set_active(self, user_id: UUID, is_active: bool) -> ProfileUsrUser | None:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        user.is_active = is_active
        await self.db.flush()
        return user

    async def set_group(self, user_id: UUID, user_group: str) -> ProfileUsrUser | None:
        user = await self.get_by_id(user_id)
        if not user or not user.credentials:
            return None
        user.credentials.user_group = user_group
        await self.db.flush()
        return user
