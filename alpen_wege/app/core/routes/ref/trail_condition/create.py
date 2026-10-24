from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefTrailCondition
from app.core.schemas.ref import RefWithFactorCreate, RefWithFactorRead

from ._router import router


@router.post("", response_model=ApiResponse[RefWithFactorRead], status_code=status.HTTP_201_CREATED)
async def create_item(
    body: RefWithFactorCreate,
    access: AccessContext = Depends(resource_access("ref", "create")),
    db: AsyncSession = Depends(get_db),
):
    obj = CoreRefTrailCondition(**body.model_dump(exclude_unset=True), created_by=access.user.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, access.user.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj, code=201, message="Created")
