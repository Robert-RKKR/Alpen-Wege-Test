from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

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
    service = UserService(db)
    users, total = await service.list_users(skip, limit, is_active)
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
    service = UserService(db)
    user = await service.set_group(user_id, body.user_group)
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    return _user_to_read(user)
