# Third-party
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.dependencies import get_db
from app.core.utils.responses import ApiResponse, AppError, ok
from app.management.models.settings import MgmtSettings
from app.management.runtime_settings.registry import REGISTRY, validate_value
from app.management.runtime_settings.service import invalidate
from app.management.schemas.settings import SettingRead, SettingUpdate
from app.management.utils.event_logger import log_updated
from app.profile.models import ProfileUsrUser
from app.profile.permissions import require_groups

router = APIRouter(prefix="/settings", tags=["Management - Settings"])
admin_only = require_groups("administrator")


async def _get_row(db: AsyncSession, key: str) -> MgmtSettings:
    definition = REGISTRY.get(key)
    row = (await db.execute(select(MgmtSettings).where(MgmtSettings.key == key))).scalar_one_or_none()
    if definition is None or row is None:
        raise AppError(404, "Not found", error_message="No setting exists with this key.")
    return row


async def _apply(db: AsyncSession, row: MgmtSettings, value, admin: ProfileUsrUser) -> MgmtSettings:
    old_values = {"value": row.value}
    row.value = value
    row.updated_by = admin.id
    log_updated(db, row, old_values, {"value": value}, admin.id)
    await db.commit()
    await db.refresh(row)
    invalidate()
    return row


@router.get("", response_model=ApiResponse[list[SettingRead]])
async def list_settings(
    category: str | None = None,
    _user: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MgmtSettings).order_by(MgmtSettings.category, MgmtSettings.key)
    if category is not None:
        stmt = stmt.where(MgmtSettings.category == category)
    return ok((await db.execute(stmt)).scalars().all())


@router.get("/{key}", response_model=ApiResponse[SettingRead])
async def get_setting_route(
    key: str,
    _user: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    return ok(await _get_row(db, key))


@router.patch("/{key}", response_model=ApiResponse[SettingRead])
async def update_setting(
    key: str,
    body: SettingUpdate,
    admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(db, key)
    try:
        value = validate_value(REGISTRY[key], body.value)
    except ValueError as exc:
        raise AppError(
            422, "Validation failed",
            error_message=f"{key}: {exc}",
            error_errors=[{"field": "value", "code": "invalid_value", "message": str(exc)}],
        )
    return ok(await _apply(db, row, value, admin), message="Updated")


@router.post("/{key}/reset", response_model=ApiResponse[SettingRead])
async def reset_setting(
    key: str,
    admin: ProfileUsrUser = Depends(admin_only),
    db: AsyncSession = Depends(get_db),
):
    row = await _get_row(db, key)
    return ok(await _apply(db, row, REGISTRY[key].default, admin), message="Reset to default")
