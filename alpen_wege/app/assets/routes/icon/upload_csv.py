from fastapi import Depends, File, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.assets.schemas.asset import IconImportResult
from app.assets.services.icon_csv import parse_csv_text, prepare_rows, save_icons
from app.assets.services.icon_link import link_icons
from app.config import get_settings
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.profile.permissions import AccessContext, resource_access

from ._router import router
from ._shared import require_policy

MAX_LISTED = 200      # errors and notes shown in the answer


def _listed(items: list[str]) -> list[str]:
    return items[:MAX_LISTED] + ([f"... and {len(items) - MAX_LISTED} more"] if len(items) > MAX_LISTED else [])


@router.post(
    "/upload-csv",
    response_model=ApiResponse[IconImportResult],
    summary="Create many icons from one CSV file",
    description=(
        "Multipart form with a CSV in `file` (UTF-8, comma separated, the first row is the header; at most ICON_CSV_MAX_UPLOAD_MB, default 5 MB, and "
        "ICON_CSV_MAX_ROWS, default 2000 rows). Columns: `key` and `svg` (required), `name`, `name_de`, `name_pl`, `summary`, `summary_de`, `summary_pl` "
        "(optional; `name` defaults to the key). `scripts/make_icon_set.py` makes such a file (`icons_import.csv`). Every SVG is cleaned like an upload "
        "(what was taken out is in `notes`); a wrong row (bad key, key twice, not an SVG) is skipped and named in `errors`, the other rows are used.\n\n"
        "- `dry_run=true`: everything is checked and counted, nothing is saved. Use it first.\n"
        "- `update=true`: an icon whose key exists is replaced (SVG and names) when it differs; without it, existing icons are left alone (`unchanged`). Needs the update permission on icons.\n"
        "- `link=true` (default): afterwards every country and region without a flag whose ISO code (countries, flag_xx) or ISO 3166-2 code "
        "(regions) matches the key of an icon gets its `icon_id`, as `POST /assets/icons/link` does. Needs the update permission on reference data; use `link=false` to skip it.\n\n"
        "Administrator only by default. The answer says how many icons were created, replaced, left alone and rejected, and what was linked."
    ),
)
async def upload_icons_csv(
    file: UploadFile = File(..., description="CSV file with the columns key, svg and optional name, name_de, name_pl, summary, summary_de, summary_pl"),
    dry_run: bool = Query(False, description="Check and count everything but save nothing."),
    update: bool = Query(False, description="Replace icons whose key exists (SVG and names) when they differ."),
    link: bool = Query(True, description="Afterwards set icon_id on the countries and regions whose ISO code matches the key of an icon."),
    access: AccessContext = Depends(resource_access("icon", "create")),
    db: AsyncSession = Depends(get_db),
):
    settings = get_settings()
    limit = settings.ICON_CSV_MAX_UPLOAD_MB * 1024 * 1024
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(413, f"File too large (maximum {settings.ICON_CSV_MAX_UPLOAD_MB} MB).")
    try:
        rows = parse_csv_text(raw.decode("utf-8-sig"), settings.ICON_CSV_MAX_ROWS)
    except UnicodeDecodeError:
        raise AppError(400, "Not a usable CSV file: it must be UTF-8 (in Excel: Save As, CSV UTF-8).")
    except ValueError as exc:
        raise AppError(400, f"Not a usable CSV file: {exc}.")
    if update:
        await require_policy(db, access.user, "icon", "update")
    if link:
        await require_policy(db, access.user, "ref", "update")

    prepared, rejected, notes = await run_in_threadpool(prepare_rows, rows)        # cleaning is CPU work
    saved = await save_icons(db, prepared, access.user.id, update=update)
    linked = empty = None
    if link and prepared:
        linked, empty = await link_icons(db)
    elif link:
        linked, empty = {}, {}
    try:
        if dry_run:
            await db.rollback()          # the counts above are real; nothing stays
        else:
            await db.commit()
    except IntegrityError:
        await db.rollback()
        raise AppError(409, "Conflict", error_message="An icon was created at the same time (same key or id). Run the import again.")
    result = IconImportResult(
        dry_run=dry_run, inserted=saved.inserted, updated=saved.updated, unchanged=saved.unchanged, rejected=len(rejected),
        errors=_listed([f"{label}: {why}" for label, why in rejected]), notes=_listed([f"{key}: removed {what}" for key, what in notes]),
        linked=linked, still_without_icon=empty,
    )
    return ok(result, code=200 if dry_run else 201, message="Dry run complete" if dry_run else "Import complete")
