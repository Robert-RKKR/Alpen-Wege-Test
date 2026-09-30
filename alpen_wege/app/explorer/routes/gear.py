from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.auth.dependencies import get_current_active_user
from app.users.models import ProfileUsrUser
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.explorer.schemas.gear import GearCreate, GearRead, GearUpdate

router = APIRouter(prefix="/gear", tags=["gear"])


@router.get("", response_model=list[GearRead])
async def list_gear(
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ExplorerAggGear)
        .where(ExplorerAggGear.created_by == user.id)
        .order_by(ExplorerAggGear.created_at.desc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=GearRead, status_code=status.HTTP_201_CREATED)
async def create_gear(
    body: GearCreate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    gear = ExplorerAggGear(
        **body.model_dump(exclude_unset=True),
        created_by=user.id,
    )
    db.add(gear)
    await db.commit()
    await db.refresh(gear)
    return gear


@router.get("/{gear_id}", response_model=GearRead)
async def get_gear(
    gear_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    if not gear or gear.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gear not found")
    return gear


@router.patch("/{gear_id}", response_model=GearRead)
async def update_gear(
    gear_id: UUID,
    body: GearUpdate,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    if not gear or gear.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gear not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(gear, field, value)
    await db.commit()
    await db.refresh(gear)
    return gear


@router.delete("/{gear_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gear(
    gear_id: UUID,
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    gear = await db.get(ExplorerAggGear, gear_id)
    if not gear or gear.created_by != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gear not found")
    await db.delete(gear)
    await db.commit()


@router.post(
    "/upload-csv",
    response_model=CsvImportResult,
    summary="Import gear from CSV",
    description=csv_upload_description(ExplorerAggGear),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    user: ProfileUsrUser = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await import_csv(file, ExplorerAggGear, user.id, db)
