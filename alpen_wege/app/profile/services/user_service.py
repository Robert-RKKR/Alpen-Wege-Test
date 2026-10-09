# Standard library
from uuid import UUID

# Third-party
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Local application
from app.profile.models import ProfileUsrUser, ProfileUserCredentials


class UserService:
    # Data-access/service layer for user records, wrapping an async DB session.
    def __init__(self, db: AsyncSession):
        # Store the database session used by all methods on this service.
        # Params:
        #   db: the async database session for the current request/unit of
        # work.
        self.db = db

    async def get_by_id(self, user_id: UUID) -> ProfileUsrUser | None:
        # Fetch a single user by primary key, with credentials eager-loaded.
        # Params:
        #   user_id: the user's UUID.
        # Returns: the matching ProfileUsrUser, or None if no user exists.
        stmt = (
            select(ProfileUsrUser)
            .options(selectinload(ProfileUsrUser.credentials))
            .where(ProfileUsrUser.id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_profile(
        self, user: ProfileUsrUser, data: dict
    ) -> ProfileUsrUser:
        # Apply a partial update to a user's profile fields.
        # Params:
        #   user: the user instance to modify.
        #   data: mapping of field name -> new value; None values are skipped.
        # Returns: the updated (flushed) user instance.
        # Only overwrite attributes whose provided value is not None.
        for key, value in data.items():
            if value is not None:
                setattr(user, key, value)
        # Flush so changes are sent to the DB within the current transaction.
        await self.db.flush()
        return user

    async def list_users(
        self, skip: int = 0, limit: int = 1000, is_active: bool | None = None
    ) -> tuple[list[ProfileUsrUser], int]:
        stmt = select(ProfileUsrUser).options(
            selectinload(ProfileUsrUser.credentials)
        )
        count_stmt = select(func.count()).select_from(ProfileUsrUser)

        if is_active is not None:
            stmt = stmt.where(ProfileUsrUser.is_active == is_active)
            count_stmt = count_stmt.where(
                ProfileUsrUser.is_active == is_active
            )

        total = (await self.db.execute(count_stmt)).scalar() or 0
        stmt = stmt.offset(skip).limit(limit).order_by(ProfileUsrUser.created_at.desc())
        result = await self.db.execute(stmt)
        users = list(result.scalars().all())
        return users, total

    async def set_active(
        self, user_id: UUID, is_active: bool
    ) -> ProfileUsrUser | None:
        # Activate or deactivate a user account.
        # Params:
        #   user_id: the user's UUID.
        #   is_active: the desired active state.
        # Returns: the updated user, or None if no such user exists.
        user = await self.get_by_id(user_id)
        if not user:
            return None
        user.is_active = is_active
        await self.db.flush()
        return user

    async def set_group(
        self, user_id: UUID, user_group: str
    ) -> ProfileUsrUser | None:
        # Change a user's authorization group.
        # Params:
        #   user_id: the user's UUID.
        #   user_group: the new group name to assign.
        # Returns: the updated user, or None if the user or their credentials
        # are missing.
        user = await self.get_by_id(user_id)
        # The group lives on the credentials row, so both must exist.
        if not user or not user.credentials:
            return None
        user.credentials.user_group = user_group
        await self.db.flush()
        return user
