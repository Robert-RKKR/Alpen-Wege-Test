from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.core.models.models_ref import CoreRefRarity
from app.core.schemas.ref import RefRankedDetail

from ._router import router


@router.get("/{item_id}", response_model=ApiResponse[RefRankedDetail])
async def get_item(
    item_id: UUID,
    access: AccessContext = Depends(resource_access("ref", "read")),
    plan: ExpandPlan = Depends(expand_plan(RefRankedDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CoreRefRarity)
        .where(CoreRefRarity.id == item_id)
        .options(*plan.load_options(CoreRefRarity))
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="rarities not found")
    return ok(plan.render(obj, viewer=access.user))
