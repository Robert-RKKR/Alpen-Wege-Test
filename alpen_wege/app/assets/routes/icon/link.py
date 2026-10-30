from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.schemas.asset import IconLinkResult
from app.assets.services.icon_link import link_icons
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import AccessContext, resource_access

from ._router import router


@router.post(
    "/link",
    response_model=ApiResponse[IconLinkResult],
    summary="Link rows to their icons by key",
    description=(
        "Sets `icon_id` on every row that has none yet and whose icon text (the 19 reference tables and the resource types: the old `icon` column in lower case), "
        "ISO code (countries: the icon `flag_<iso code>`, for example `flag_at`) or ISO 3166-2 code (regions: `flag_ch_zh`) matches the **key** of an icon. "
        "The API version of `scripts/sql/icons_link.sql`. A link that is already set is never changed, so it can be run again after every import. "
        "The answer says how many rows were linked per table and how many still have no icon (no icon with their key exists yet). "
        "`dry_run=true` counts without saving. Needs the update permission on reference data (administrator by default). "
        "These bulk updates are not written to the event log one by one."
    ),
)
async def link_icons_by_key(
    dry_run: bool = Query(False, description="Count what would be linked but save nothing."),
    access: AccessContext = Depends(resource_access("ref", "update")),
    db: AsyncSession = Depends(get_db),
):
    linked, empty = await link_icons(db)
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return ok(IconLinkResult(dry_run=dry_run, linked=linked, still_without_icon=empty), message="Dry run complete" if dry_run else "Linked")
