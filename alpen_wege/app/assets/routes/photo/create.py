from datetime import datetime

from fastapi import Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.assets.schemas.asset import PhotoRead
from app.assets.services.photo_storage import NotAnImage, delete_quietly, process_and_save
from app.config import get_settings
from app.core.dependencies import get_db
from app.core.schemas.geo import geojson_to_wkt
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.utils.event_logger import log_created
from app.profile.permissions import AccessContext, resource_access

from ._router import router


@router.post(
    "",
    response_model=ApiResponse[PhotoRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a photo",
    description=(
        "Multipart form with the image in `file` (JPEG, PNG or WebP, at most PHOTO_MAX_UPLOAD_MB). The image is checked, "
        "turned upright, shrunk to at most 2560 px and saved without its metadata. Position, altitude and capture time "
        "are read from EXIF when the form does not give them."
    ),
)
async def create_photo(
    file: UploadFile = File(..., description="JPEG, PNG or WebP image"),
    name: str | None = Form(None, max_length=255, description="Default: the file name."),
    name_de: str | None = Form(None),
    name_pl: str | None = Form(None),
    summary: str | None = Form(None, max_length=1000),
    summary_de: str | None = Form(None, max_length=1000),
    summary_pl: str | None = Form(None, max_length=1000),
    lon: float | None = Form(None, ge=-180, le=180),
    lat: float | None = Form(None, ge=-90, le=90),
    altitude_m: int | None = Form(None, ge=-500, le=9000),
    taken_at: datetime | None = Form(None),
    is_public: bool = Form(False),
    access: AccessContext = Depends(resource_access("photo", "create")),
    db: AsyncSession = Depends(get_db),
):
    if (lon is None) != (lat is None):
        raise AppError(422, "Give both lon and lat, or neither.")
    max_mb = get_settings().PHOTO_MAX_UPLOAD_MB
    try:
        stored = await run_in_threadpool(process_and_save, file.file, max_bytes=max_mb * 1024 * 1024)
    except OverflowError:
        raise AppError(413, f"File too large (maximum {max_mb} MB).")
    except NotAnImage:
        raise AppError(400, "Not a JPEG, PNG or WebP image.")

    if lon is None and stored.lon is not None:
        lon, lat = stored.lon, stored.lat
    try:
        photo = AssetAggPhoto(
            name=(name or file.filename or "photo")[:255],
            name_de=name_de or None, name_pl=name_pl or None,
            summary=summary or None, summary_de=summary_de or None, summary_pl=summary_pl or None,
            location=geojson_to_wkt({"type": "Point", "coordinates": [lon, lat]}, "POINT") if lon is not None else None,
            altitude_m=altitude_m if altitude_m is not None else stored.altitude_m,
            taken_at=taken_at or stored.taken_at,
            path=stored.relative_path,
            is_public=is_public,
            created_by=access.user.id,
        )
        db.add(photo)
        await db.flush()
        log_created(db, photo, access.user.id)
        await db.commit()
    except Exception:
        await run_in_threadpool(delete_quietly, stored.relative_path)
        raise
    await db.refresh(photo)
    return ok(photo, code=201, message="Created")
