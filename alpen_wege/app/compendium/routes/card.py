from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.schemas.card import CardCreate, CardRead, CardUpdate

router = APIRouter(prefix="/cards", tags=["cards"])

_EAGER = [
    selectinload(CompendiumCatCard.rarity),
    selectinload(CompendiumCatCard.compendium_type),
    selectinload(CompendiumCatCard.poi),
]


@router.get("", response_model=list[CardRead])
async def list_cards(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(CompendiumCatCard).options(*_EAGER).order_by(CompendiumCatCard.name)
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=CardRead, status_code=status.HTTP_201_CREATED)
async def create_card(
    body: CardCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = CompendiumCatCard(**body.model_dump(exclude_unset=True), created_by=user.id)
    db.add(obj)
    await db.commit()
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == obj.id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.get("/{card_id}", response_model=CardRead)
async def get_card(
    card_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == card_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    return obj


@router.patch("/{card_id}", response_model=CardRead)
async def update_card(
    card_id: UUID,
    body: CardUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCard, card_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    stmt = (
        select(CompendiumCatCard)
        .where(CompendiumCatCard.id == card_id)
        .options(*_EAGER)
    )
    result = await db.execute(stmt)
    return result.scalar_one()


@router.delete("/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_card(
    card_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCard, card_id)
    if not obj:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Card not found")
    await db.delete(obj)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import cards from CSV",
    description=csv_upload_description(CompendiumCatCard),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, CompendiumCatCard, user.id, db)
