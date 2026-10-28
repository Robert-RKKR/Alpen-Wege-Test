from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.core.utils.responses import AppError
from app.explorer.services.visibility import scope_of, visible


async def check_photo_link(db: AsyncSession, user, photo_id: UUID | None) -> None:
    # A record may only point at a photo its editor may read; otherwise anyone who can read the record (or its card
    # graphic) would see a private photo of somebody else. Unknown and unreadable photos get the same 422.
    if photo_id is None:
        return
    photo = await db.get(AssetAggPhoto, photo_id)
    scope = await scope_of(db, user, "photo", "read")
    if photo is None or not visible(scope, user.id, photo.created_by, photo.is_public):
        raise AppError(
            422,
            "Validation failed",
            error_message="main_photo_id: the photo does not exist or you may not use it.",
            error_errors=[{"field": "main_photo_id", "code": "photo_not_usable",
                           "message": "The photo does not exist or you may not use it."}],
        )


def csv_photo_check(db: AsyncSession, user):
    # row_check for import_csv: a row may only name a photo the importer may read
    async def _check(data: dict) -> None:
        try:
            await check_photo_link(db, user, data.get("main_photo_id"))
        except AppError:
            raise ValueError("main_photo_id: the photo does not exist or you may not use it")
    return _check
