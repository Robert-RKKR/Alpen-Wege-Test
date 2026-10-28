from uuid import UUID

from fastapi import Depends
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.assets.services.photo_storage import MEDIA_TYPES, resolve_path
from app.core.dependencies import get_db
from app.core.utils.responses import AppError
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.get(
    "/{photo_id}/file",
    summary="The image file",
    responses={200: {"content": {mime: {} for mime in MEDIA_TYPES.values()}}},
)
async def get_photo_file(
    photo_id: UUID,
    access: AccessContext = Depends(resource_access("photo", "read")),
    db: AsyncSession = Depends(get_db),
):
    photo = await db.get(AssetAggPhoto, photo_id)
    check_object_access(access, photo, not_found_msg="Photo not found")
    ext = photo.path.rsplit(".", 1)[-1].lower()
    try:
        path = resolve_path(photo.path)
    except ValueError:
        path = None
    if path is None or ext not in MEDIA_TYPES or not path.is_file():
        raise AppError(404, "Photo file not found")
    return FileResponse(
        path, media_type=MEDIA_TYPES[ext], filename=f"{photo.id}.{ext}", content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
