from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.schemas.post import PostCreate, PostRead, PostUpdate

router = APIRouter(prefix="/posts", tags=["Compendium - Post"])

_EAGER = [
    selectinload(CompendiumCatPost.post_type),
]


def _apply_scope(stmt, model, access: AccessContext):
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)
        )
    return stmt


@router.get("", response_model=ApiResponse[list[PostRead]])
async def list_posts(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("post", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatPost)
    count_stmt = _apply_scope(count_stmt, CompendiumCatPost, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatPost).options(*_EAGER).order_by(CompendiumCatPost.name).limit(limit).offset(offset)
    stmt = _apply_scope(stmt, CompendiumCatPost, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[PostRead], status_code=status.HTTP_201_CREATED)
async def create_post(
    body: PostCreate,
    access: AccessContext = Depends(resource_access("post", "create")),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumCatPost(**body.model_dump(exclude_unset=True), created_by=access.user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")


@router.get("/{post_id}", response_model=ApiResponse[PostRead])
async def get_post(
    post_id: UUID,
    access: AccessContext = Depends(resource_access("post", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == post_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Post not found")
    return ok(obj)


@router.patch("/{post_id}", response_model=ApiResponse[PostRead])
async def update_post(
    post_id: UUID,
    body: PostUpdate,
    access: AccessContext = Depends(resource_access("post", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPost, post_id)
    check_object_access(access, obj, not_found_msg="Post not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumCatPost)
        .where(CompendiumCatPost.id == post_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())


@router.delete("/{post_id}", response_model=ApiResponse[None])
async def delete_post(
    post_id: UUID,
    access: AccessContext = Depends(resource_access("post", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatPost, post_id)
    check_object_access(access, obj, not_found_msg="Post not found")
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import posts from CSV",
    description=csv_upload_description(CompendiumCatPost),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("post", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CompendiumCatPost, access.user.id, db)
    return ok(result, code=201, message="Import complete")
