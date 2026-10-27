from uuid import UUID

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.expand import ExpandPlan, expand_plan
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryDetail

from ._router import router


@router.get("/{country_id}", response_model=ApiResponse[CountryDetail])
async def get_country(
    country_id: UUID,
    access: AccessContext = Depends(resource_access("country", "read")),
    plan: ExpandPlan = Depends(expand_plan(CountryDetail)),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(CompendiumCatCountry)
        .where(CompendiumCatCountry.id == country_id)
        .options(*plan.load_options(CompendiumCatCountry))
    )
    obj = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, obj, not_found_msg="Country not found")
    return ok(plan.render(obj, viewer=access.user))
