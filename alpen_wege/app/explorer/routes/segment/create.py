# Standard library
from uuid import UUID

# Third-party
from fastapi import Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

# Local application
from app.config import get_settings
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError
from app.profile.permissions import resource_access, AccessContext
from app.explorer.schemas.segment import SegmentCreated
from app.explorer.services import segment_build
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.xml_guard import check_gpx_root
from app.explorer.services.gpx_storage import UploadTooLarge, delete_quietly, resolve_path, save_upload
from app.explorer.services.segment_http import build

from ._router import router
from ._shared import finish_create

settings = get_settings()


@router.post("", response_model=ApiResponse[SegmentCreated], status_code=status.HTTP_201_CREATED)
async def create_segment(
    name: str = Form(..., min_length=1, max_length=255),
    gpx_file: UploadFile = File(...),
    sport_type_id: UUID = Form(...),
    summary: str | None = Form(None, max_length=1000),
    description: str | None = Form(None, max_length=10000),
    difficulty_level_id: UUID | None = Form(None),
    difficulty_sport_id: UUID | None = Form(None),
    is_public: bool = Form(False),
    access: AccessContext = Depends(resource_access("segment", "create")),
    db: AsyncSession = Depends(get_db),
):
    # A segment from a GPX file: the file is read, time, heart rate and cadence are dropped, the geometry is kept, and the
    # file itself is deleted again (a segment stores no GPX file).
    if not (gpx_file.filename or "").lower().endswith(".gpx"):
        raise AppError(400, "Only .gpx files are accepted.")
    try:
        await run_in_threadpool(check_gpx_root, gpx_file.file)
        gpx_file.file.seek(0)
    except GpxProcessingError:
        raise AppError(400, "Not a valid GPX file.")
    max_bytes = settings.SEGMENT_GPX_MAX_UPLOAD_MB * 1024 * 1024
    try:
        stored = await run_in_threadpool(save_upload, gpx_file.file, max_bytes=max_bytes)
    except UploadTooLarge:
        raise AppError(413, f"File too large (maximum {settings.SEGMENT_GPX_MAX_UPLOAD_MB} MB for a segment).")
    try:
        processed = await build(segment_build.from_gpx_file, resolve_path(stored.relative_path))
    finally:
        await run_in_threadpool(delete_quietly, stored.relative_path)
    fields = {
        "name": name, "summary": summary or None, "description": description or None, "sport_type_id": sport_type_id,
        "difficulty_level_id": difficulty_level_id, "difficulty_sport_id": difficulty_sport_id, "is_public": is_public,
    }
    return await finish_create(db, access.user, processed, fields)
