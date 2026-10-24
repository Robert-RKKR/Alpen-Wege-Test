from fastapi import Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db
from app.core.utils.csv_import import CsvImportResult, csv_upload_description, import_csv
from app.core.utils.responses import ApiResponse, ok
from app.profile.permissions import resource_access, AccessContext
from app.core.models.models_ref import CoreRefDifficultyLevel

from ._router import router


@router.post(
    "/upload-csv",
    response_model=ApiResponse[CsvImportResult],
    summary="Import difficulty-levels from CSV",
    description=csv_upload_description(CoreRefDifficultyLevel),
)
async def upload_csv(
    file: UploadFile = File(..., description="CSV file with header row"),
    access: AccessContext = Depends(resource_access("ref", "create")),
    db: AsyncSession = Depends(get_db),
):
    result = await import_csv(file, CoreRefDifficultyLevel, access.user.id, db)
    return ok(result, code=201, message="Import complete")
