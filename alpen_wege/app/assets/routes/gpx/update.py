from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.gpx import AssetAggGpx
from app.assets.schemas.asset import GpxRead, GpxUpdate
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_updated
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.patch("/{gpx_id}", response_model=ApiResponse[GpxRead], description="Changes the name, summary or visibility. The file itself cannot be replaced.")
async def update_gpx(
    gpx_id: UUID,
    body: GpxUpdate,
    access: AccessContext = Depends(resource_access("gpx", "update")),
    db: AsyncSession = Depends(get_db),
):
    gpx = await db.get(AssetAggGpx, gpx_id)
    check_object_access(access, gpx, not_found_msg="GPX file not found")
    changes = body.model_dump(exclude_unset=True)
    if changes.get("name", "") is None:
        changes.pop("name")
    old_values = {f: getattr(gpx, f) for f in changes}
    for field, value in changes.items():
        setattr(gpx, field, value)
    log_updated(db, gpx, old_values, changes, access.user.id)
    await db.commit()
    await db.refresh(gpx)
    return ok(gpx)
