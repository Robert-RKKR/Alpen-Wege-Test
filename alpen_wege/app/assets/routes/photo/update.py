from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.assets.schemas.asset import PhotoRead, PhotoUpdate
from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_updated
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.patch("/{photo_id}", response_model=ApiResponse[PhotoRead], description="Changes the details of a photo. The image itself cannot be replaced: upload a new photo.")
async def update_photo(
    photo_id: UUID,
    body: PhotoUpdate,
    access: AccessContext = Depends(resource_access("photo", "update")),
    db: AsyncSession = Depends(get_db),
):
    photo = await db.get(AssetAggPhoto, photo_id)
    check_object_access(access, photo, not_found_msg="Photo not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name", "") is None:
        changes.pop("name")
    old_values = {f: getattr(photo, f) for f in changes}
    if "location" in changes:
        changes["location"] = geojson_to_wkt(changes["location"], "POINT")
    for field, value in changes.items():
        setattr(photo, field, value)
    log_updated(db, photo, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(photo)
    return ok(photo)
