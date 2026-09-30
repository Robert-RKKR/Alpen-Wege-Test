from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.schemas.post import PostCreate, PostRead, PostUpdate

router = APIRouter(prefix="/posts", tags=["posts"])

_EAGER = [
    selectinload(CompendiumCatPost.post_type),
]


@router.get("", response_model=list[PostRead])
async def list_posts(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CompendiumCatPost).options(*_EAGER).order_by(CompendiumCatPost.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumCatPost(**body.model_dump(exclude_unset=True), created_by=user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get("/{post_id}", response_model=PostRead)
async def get_post(
    post_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == post_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    return obj


@router.patch("/{post_id}", response_model=PostRead)
async def update_post(
    post_id: UUID,
    body: PostUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPost, post_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == post_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_post(
    post_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPost, post_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Post not found")
    await db.delete(obj)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import posts from CSV",
    description=csv_upload_description(CompendiumCatPost),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, CompendiumCatPost, user.id, db)
