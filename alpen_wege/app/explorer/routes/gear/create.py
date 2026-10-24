from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.profile.permissions import resource_access, AccessContext
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.core.utils.responses import ApiResponse, ok
from app.explorer.schemas.gear import GearCreate, GearRead

from ._router import router


@router.post("", response_model=ApiResponse[GearRead], status_code=status.HTTP_201_CREATED)
async def create_gear(
    body: GearCreate,
    access: AccessContext = Depends(resource_access("gear", "create")),
    db: AsyncSession = Depends(get_db),
):
    gear = ExplorerAggGear(
        **body.model_dump(exclude_unset=True),
        created_by=access.user.id,
    )
    db.add(gear)
    await db.flush()
    log_created(db, gear, access.user.id)
    await db.commit()
    await db.refresh(gear)
    return ok(gear, code=201, message="Created")
