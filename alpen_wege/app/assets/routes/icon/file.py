from typing import Literal
from uuid import UUID

from fastapi import Depends, Path, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import undefer

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.services.icon_files import PNG_MAX, PNG_MIN, icon_response
from app.core.dependencies import get_db
from app.core.utils.responses import AppError
from app.profile.permissions import AccessContext, check_object_access, resource_access

from ._router import router

FILE_RESPONSES = {200: {"content": {"image/svg+xml": {}, "image/png": {}}}}
FORMAT = Query("svg", description="`svg` (the stored picture) or `png` (drawn from it).")
SIZE = Query(64, ge=PNG_MIN, le=PNG_MAX, description=f"Width of the PNG in pixels, {PNG_MIN} to {PNG_MAX}. The height follows the shape. Only for `format=png`.")


@router.get(
    "/by-key/{key}/file",
    summary="The picture of an icon, found by its key",
    description="For example `by-key/flag_at/file` or `by-key/sport_hiking/file`. Works with the text that is still in the `icon` column of the reference tables.",
    responses=FILE_RESPONSES,
)
async def get_icon_file_by_key(
    request: Request,
    key: str = Path(..., max_length=100),
    format: Literal["svg", "png"] = FORMAT,
    size: int = SIZE,
    access: AccessContext = Depends(resource_access("icon", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AssetAggIcon).where(AssetAggIcon.key == key.strip().lower()).options(undefer(AssetAggIcon.svg))
    icon = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, icon, not_found_msg="Icon not found")
    return await icon_response(request, key=icon.key, svg=icon.svg, sha256=icon.sha256, fmt=format, size=size)


@router.get(
    "/{icon_id}/file",
    summary="The picture of an icon",
    description=(
        "`image/svg+xml` as stored, or `?format=png&size=64`. The answer carries an `ETag` (the SHA-256 of the SVG text; send "
        "it back in `If-None-Match` to get `304`) and headers that stop a script in the file from running."
    ),
    responses=FILE_RESPONSES,
)
async def get_icon_file(
    request: Request,
    icon_id: UUID,
    format: Literal["svg", "png"] = FORMAT,
    size: int = SIZE,
    access: AccessContext = Depends(resource_access("icon", "read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AssetAggIcon).where(AssetAggIcon.id == icon_id).options(undefer(AssetAggIcon.svg))
    icon = (await db.execute(stmt)).scalar_one_or_none()
    check_object_access(access, icon, not_found_msg="Icon not found")
    return await icon_response(request, key=icon.key, svg=icon.svg, sha256=icon.sha256, fmt=format, size=size)
