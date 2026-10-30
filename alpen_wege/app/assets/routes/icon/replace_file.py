from uuid import UUID

from fastapi import Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.schemas.asset import IconRead
from app.assets.services.icon_upload import read_clean_svg
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.management.utils.event_logger import log_updated
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router


@router.put(
    "/{icon_id}/file",
    response_model=ApiResponse[IconRead],
    summary="Replace the SVG of an icon",
    description=(
        "Multipart form with the new SVG in `file` (cleaned like an upload; what was removed is in `response_details.removed`). "
        "The id, the key and every link stay; every row that uses the icon shows the new picture."
    ),
)
async def replace_icon_file(
    icon_id: UUID,
    file: UploadFile = File(..., description="SVG file"),
    access: AccessContext = Depends(resource_access("icon", "update")),
    db: AsyncSession = Depends(get_db),
):
    icon = await db.get(AssetAggIcon, icon_id)
    check_object_access(access, icon, not_found_msg="Icon not found")
    clean = await read_clean_svg(file)
    old_sha = icon.sha256
    icon.svg = clean.svg
    icon.sha256 = clean.sha256
    log_updated(db, icon, {"sha256": old_sha}, {"sha256": clean.sha256}, access.user.id)   # the SVG text itself is not logged
    await db.commit()
    await db.refresh(icon)
    result = ok(icon)
    result["response_details"] = {"removed": list(clean.removed)}
    return result
