from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.core.models.models_ref import CoreRefCompany
from app.core.schemas.ref import RefBaseDetail

from ._router import router


@router.get("/{item_id}", response_model=ApiResponse[RefBaseDetail])
async def get_item(
    item_id: UUID,
    access: AccessContext = Depends(resource_access("ref", "read")),
    plan: ExpandPlan = Depends(expand_plan(RefBaseDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CoreRefCompany)
        .where(CoreRefCompany.id == item_id)
        .options(*plan.load_options(CoreRefCompany))
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="companies not found")
    return ok(plan.render(obj, viewer=access.user))
