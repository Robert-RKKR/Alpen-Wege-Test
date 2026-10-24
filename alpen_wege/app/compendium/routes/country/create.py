from fastapi import Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.management.utils.event_logger import log_created
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.schemas.country import CountryCreate, CountryRead

from ._router import router


@router.post("", response_model=ApiResponse[CountryRead], status_code=status.HTTP_201_CREATED)
async def create_country(
    body: CountryCreate,
    access: AccessContext = Depends(resource_access("country", "create")),
    db: AsyncSession = Depends(get_db),
):
    data = body.model_dump(exclude_unset=True)
    if "location" in data:
        data["location"] = geojson_to_wkt(data["location"], "POINT")
    obj = CompendiumCatCountry(**data, created_by=access.user.id)
    db.add(obj)
    await db.flush()
    log_created(db, obj, access.user.id)
    await db.commit()
    await db.refresh(obj)
    return ok(obj, code=201, message="Created")
