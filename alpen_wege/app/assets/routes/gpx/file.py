from uuid import UUID

from fastapi import Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.gpx import AssetAggGpx
from app.core.dependencies import get_db
from app.core.utils.responses import AppError
from app.explorer.services.gpx_storage import resolve_path
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.get("/{gpx_id}/file", summary="Download the GPX file", responses={200: {"content": {"application/gpx+xml": {}}}})
async def get_gpx_file(
    gpx_id: UUID,
    access: AccessContext = Depends(resource_access("gpx", "read")),
    db: AsyncSession = Depends(get_db),
):
    gpx = await db.get(AssetAggGpx, gpx_id)
    check_object_access(access, gpx, not_found_msg="GPX file not found")
    try:
        path = resolve_path(gpx.path)
    except ValueError:
        path = None
    if path is None or not path.is_file():
        raise AppError(404, "GPX file not found")
    return FileResponse(
        path, media_type="application/gpx+xml", filename=f"{gpx.id}.gpx",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
