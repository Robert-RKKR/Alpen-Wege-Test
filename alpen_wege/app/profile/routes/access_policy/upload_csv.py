# Third-party
from fastapi import Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, ok
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.profile.permissions import require_groups
from app.profile.services.access_cache import invalidate_policy_cache
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.models import ProfileUsrUser

from ._router import router


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import access policies from CSV",
    description=csv_upload_description(ProfileAccessPolicy),
)
async def upload_access_policy_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    admin: ProfileUsrUser = Depends(require_groups("administrator")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, ProfileAccessPolicy, admin.id, db)
    await invalidate_policy_cache()
    return ok(result, code=201, message="Import complete")
