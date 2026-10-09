# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.dependencies import get_current_active_user
from app.profile.models import ProfileUsrUser
from app.profile.schemas import UserRead, UserUpdate
from app.profile.services import UserService

router = APIRouter()


def _user_to_read(user: ProfileUsrUser) -> UserRead:
    # Map a ProfileUsrUser ORM object to its public UserRead schema.
    # Params:
    #   user: the user ORM instance (its credentials relationship may be loaded
    # or None).
    # Returns: a UserRead populated from the user's fields, with user_group
    # from credentials.
    # Copy the exposed fields; user_group is pulled from credentials when
    # present.
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
        "user_group": user.credentials.user_group
        if user.credentials
        else None,
    }
    return UserRead(**data)


@router.get("/me", response_model=ApiResponse[UserRead])
async def get_me(
    current_user: ProfileUsrUser = Depends(get_current_active_user),
):
    return ok(_user_to_read(current_user))


@router.put("/me", response_model=ApiResponse[UserRead])
async def update_me(
    body: UserUpdate,
    current_user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    service = UserService(db)
    updated = await service.update_profile(
        current_user, body.model_dump(exclude_unset=True)
    )
    return ok(_user_to_read(updated), message="Updated")
