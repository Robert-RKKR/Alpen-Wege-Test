from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.core.utils.responses import ApiResponse, ok, ok_list
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.schemas.card import CardCreate, CardRead, CardUpdate

router = APIRouter(prefix="/cards", tags=["Compendium - Card"])

_EAGER = [
    selectinload(CompendiumCatCard.rarity),
    selectinload(CompendiumCatCard.compendium_type),
    selectinload(CompendiumCatCard.poi),
]


def _apply_scope(stmt, model, access: AccessContext):
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)
        )
    return stmt


@router.get("", response_model=ApiResponse[list[CardRead]])
async def list_cards(
    limit: int = 1000,
    offset: int = 0,
    access: AccessContext = Depends(resource_access("card", "read")),
    db: AsyncSession = Depends(get_db),
):
    count_stmt = select(func.count()).select_from(CompendiumCatCard)
    count_stmt = _apply_scope(count_stmt, CompendiumCatCard, access)
    total = (await db.execute(count_stmt)).scalar()
    stmt = select(CompendiumCatCard).options(*_EAGER).order_by(CompendiumCatCard.name).limit(limit).offset(offset)
    stmt = _apply_scope(stmt, CompendiumCatCard, access)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return ok_list(items, total=total, limit=limit, offset=offset)


@router.post("", response_model=ApiResponse[CardRead], status_code=status.HTTP_201_CREATED)
async def create_card(
    body: CardCreate,
    access: AccessContext = Depends(resource_access("card", "create")),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumCatCard(**body.model_dump(exclude_unset=True), created_by=access.user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one(), code=201, message="Created")


@router.get("/{card_id}", response_model=ApiResponse[CardRead])
async def get_card(
    card_id: UUID,
    access: AccessContext = Depends(resource_access("card", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == card_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Card not found")
    return ok(obj)


@router.patch("/{card_id}", response_model=ApiResponse[CardRead])
async def update_card(
    card_id: UUID,
    body: CardUpdate,
    access: AccessContext = Depends(resource_access("card", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCard, card_id)
    check_object_access(access, obj, not_found_msg="Card not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == card_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return ok(result.scalar_one())


@router.delete("/{card_id}", response_model=ApiResponse[None])
async def delete_card(
    card_id: UUID,
    access: AccessContext = Depends(resource_access("card", "delete")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCard, card_id)
    check_object_access(access, obj, not_found_msg="Card not found")
    await db.delete(obj)
    await db.commit()
    return ok(None, message="Deleted")


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import cards from CSV",
    description=csv_upload_description(CompendiumCatCard),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("card", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CompendiumCatCard, access.user.id, db)
    return ok(result, code=201, message="Import complete")
