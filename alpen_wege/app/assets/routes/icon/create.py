import re

from fastapi import Depends, File, Form, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.schemas.asset import ICON_KEY_PATTERN, IconRead
from app.assets.services.icon_upload import key_from_filename, read_clean_svg
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.utils.event_logger import log_created
from app.profile.permissions import AccessContext, resource_access

from ._router import router
from ._shared import key_taken


@router.post(
    "",
    response_model=ApiResponse[IconRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload an icon",
    description=(
        "Multipart form with the SVG in `file` (at most ICON_MAX_UPLOAD_KB, default 300 KB). The file is cleaned before it "
        "is stored: script, `<style>`, `<foreignObject>`, animation, external links and foreign namespaces are removed and "
        "listed in `response_details.removed`. `key` (lower-case letters, digits and `_ . -`) is the name the reference "
        "tables, countries and regions are linked by; default: the file name. `409` when the key exists."
    ),
)
async def create_icon(
    file: UploadFile = File(..., description="SVG file"),
    key: str | None = Form(None, max_length=100, description="Default: the file name in lower case, for example Flag AT.svg -> flag_at."),
    name: str | None = Form(None, max_length=255, description="Default: the file name."),
    name_de: str | None = Form(None),
    name_pl: str | None = Form(None),
    summary: str | None = Form(None, max_length=1000),
    summary_de: str | None = Form(None, max_length=1000),
    summary_pl: str | None = Form(None, max_length=1000),
    access: AccessContext = Depends(resource_access("icon", "create")),
    db: AsyncSession = Depends(get_db),
):
    icon_key = (key or "").strip().lower() or key_from_filename(file.filename)
    if not re.fullmatch(ICON_KEY_PATTERN, icon_key):
        raise AppError(
            422, "Validation failed",
            error_message="The key must be 1 to 100 characters: lower-case letters, digits and _ . - only.",
            error_errors=[{"field": "key", "code": "invalid_key", "message": "Give a key (lower-case letters, digits, _ . -)."}],
        )
    if (await db.execute(select(AssetAggIcon.id).where(AssetAggIcon.key == icon_key))).first():
        raise key_taken()
    clean = await read_clean_svg(file)

    icon = AssetAggIcon(
        key=icon_key,
        name=(name or (file.filename or icon_key).rsplit("/", 1)[-1].rsplit("\\", 1)[-1])[:255],
        name_de=name_de or None, name_pl=name_pl or None,
        summary=summary or None, summary_de=summary_de or None, summary_pl=summary_pl or None,
        svg=clean.svg, sha256=clean.sha256,
        created_by=access.user.id,
    )
    db.add(icon)
    try:
        await db.flush()
        log_created(db, icon, access.user.id)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise key_taken()
    await db.refresh(icon)
    result = ok(icon, code=201, message="Created")
    result["response_details"] = {"removed": list(clean.removed)}
    return result
