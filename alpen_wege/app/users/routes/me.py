from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.users.schemas import UserRead, UserUpdate
from app.users.services import UserService

router = APIRouter()


def _user_to_read(user: ProfileUsrUser) -> UserRead:
    data = {
        "id": user.id,
        "email": user.email,
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "middle_name": user.middle_name,
        "gender": user.gender,
        "birth_date": user.birth_date,
        "height_cm": user.height_cm,
        "max_heart_rate": user.max_heart_rate,
        "resting_heart_rate": user.resting_heart_rate,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_active_at": user.last_active_at,
        "user_group": user.credentials.user_group if user.credentials else None,
    }
    return UserRead(**data)


@router.get("/me", response_model=UserRead)
async def get_me(current_user: ProfileUsrUser = Depends(get_current_active_user)):
    return _user_to_read(current_user)


@router.put("/me", response_model=UserRead)
async def update_me(
    body: UserUpdate,
    current_user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    updated = await service.update_profile(current_user, body.model_dump(exclude_unset=True))
    return _user_to_read(updated)
