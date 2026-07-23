# Standard library
from uuid import UUID

# Third-party
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.schemas import PaginatedResponse
from app.auth.permissions import require_groups
from app.users.models import ProfileUsrUser
from app.users.schemas import UserRead, AdminGroupUpdate
from app.users.services import UserService
from app.users.routes.me import _user_to_read

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[UserRead])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    is_active: bool | None = None,
    _admin: ProfileUsrUser = Depends(require_groups("admin")),
    db: AsyncSession = Depends(get_db),
):
    # List users (admin only) with pagination and an optional active filter.
    # Params:
    #   skip: number of records to skip (offset >= 0).
    #   limit: page size (1..200).
    #   is_active: optional filter on account active state.
    #   _admin: enforces that the caller is in the "admin" group (value unused).
    #   db: the async database session, injected by get_db.
    # Returns: a PaginatedResponse of UserRead items plus paging metadata.
    # Fetch the page of users and the total match count from the service.
    service = UserService(db)
    users, total = await service.list_users(skip, limit, is_active)
    # Serialize each ORM user and wrap with pagination metadata.
    return PaginatedResponse(
        items=[_user_to_read(u) for u in users],
        total=total,
        skip=skip,
        limit=limit,
    )


@router.get("/{user_id}", response_model=UserRead)
async def get_user(
    user_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("admin")),
    db: AsyncSession = Depends(get_db),
):
    # Fetch a single user by id (admin only).
    # Params:
    #   user_id: the target user's UUID (from the path).
    #   _admin: enforces "admin" group membership (value unused).
    #   db: the async database session, injected by get_db.
    # Returns: the user as a UserRead.
    # Raises: HTTPException 404 if no user with that id exists.
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _user_to_read(user)


@router.put("/{user_id}/activate", response_model=UserRead)
async def activate_user(
    user_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("admin")),
    db: AsyncSession = Depends(get_db),
):
    # Activate a user account (admin only).
    # Params:
    #   user_id: the target user's UUID (from the path).
    #   _admin: enforces "admin" group membership (value unused).
    #   db: the async database session, injected by get_db.
    # Returns: the updated user as a UserRead.
    # Raises: HTTPException 404 if no user with that id exists.
    # Set the account active flag to True via the service.
    service = UserService(db)
    user = await service.set_active(user_id, True)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _user_to_read(user)


@router.put("/{user_id}/deactivate", response_model=UserRead)
async def deactivate_user(
    user_id: UUID,
    _admin: ProfileUsrUser = Depends(require_groups("admin")),
    db: AsyncSession = Depends(get_db),
):
    # Deactivate a user account (admin only).
    # Params:
    #   user_id: the target user's UUID (from the path).
    #   _admin: enforces "admin" group membership (value unused).
    #   db: the async database session, injected by get_db.
    # Returns: the updated user as a UserRead.
    # Raises: HTTPException 404 if no user with that id exists.
    # Set the account active flag to False via the service.
    service = UserService(db)
    user = await service.set_active(user_id, False)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _user_to_read(user)


@router.put("/{user_id}/group", response_model=UserRead)
async def change_group(
    user_id: UUID,
    body: AdminGroupUpdate,
    _admin: ProfileUsrUser = Depends(require_groups("admin")),
    db: AsyncSession = Depends(get_db),
):
    # Change a user's authorization group (admin only).
    # Params:
    #   user_id: the target user's UUID (from the path).
    #   body: payload carrying the new group name (user_group).
    #   _admin: enforces "admin" group membership (value unused).
    #   db: the async database session, injected by get_db.
    # Returns: the updated user as a UserRead.
    # Raises: HTTPException 404 if the user (or their credentials) cannot be found.
    # Assign the new group via the service, which updates the credentials row.
    service = UserService(db)
    user = await service.set_group(user_id, body.user_group)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _user_to_read(user)
