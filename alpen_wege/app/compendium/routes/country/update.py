from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.management.utils.event_logger import log_updated
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext, check_object_access
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryRead, CountryUpdate

from ._router import router


@router.patch("/{country_id}", response_model=ApiResponse[CountryRead])
async def update_country(
    country_id: UUID,
    body: CountryUpdate,
    access: AccessContext = Depends(resource_access("country", "update")),
    db: AsyncSession = Depends(get_db),
):
    obj = await db.get(CompendiumCatCountry, country_id)
    check_object_access(access, obj, not_found_msg="Country not found")
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    old_values = {f: getattr(obj, f) for f in data}
    for field, value in data.items():
        setattr(obj, field, value)
    log_updated(db, obj, old_values, data, access.user.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj)
