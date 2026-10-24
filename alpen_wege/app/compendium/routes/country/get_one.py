from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryRead

from ._router import router


@router.get("/{country_id}", response_model=ApiResponse[CountryRead])
async def get_country(
    country_id: UUID,
    access: AccessContext = Depends(resource_access("country", "read")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    check_object_access(access, obj, not_found_msg="Country not found")
    return ok(obj)
