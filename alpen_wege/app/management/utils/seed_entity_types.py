# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.base import Base
from app.management.models.entity_type import MgmtRefEntityType

NONE_TABLES = frozenset({
    "mgmt_ref_entity_type",
    "mgmt_log_event",
    "mgmt_log_job",
    "profile_user_credentials",
    "explorer_sub_geo_record",
    "explorer_sub_geo_performance",
    "spatial_ref_sys",
})

IGNORE_FIELDS_MAP: dict[str, list[str]] = {
    "profile_usr_user": ["last_active_at", "updated_at"],
}


def _derive_module(table_name: str) -> str:
    return table_name.split("_", 1)[0]


def _derive_display_name(table_name: str) -> str:
    parts = table_name.split("_")
    skip = {"agg", "sub", "m2m", "cat", "ref", "usr", "log"}
    filtered = [p for p in parts[1:] if p.lower() not in skip]
    if not filtered:
        filtered = parts[1:]
    return " ".join(w.capitalize() for w in filtered)


def _tracking_mode(table_name: str) -> str:
    if table_name in NONE_TABLES:
        return "none"
    return "all"


async def seed_entity_types(session: AsyncSession) -> None:
    result = await session.execute(select(MgmtRefEntityType))
    existing = {row.key: row for row in result.scalars().all()}

    table_names = sorted(Base.metadata.tables.keys())
    dirty = False

    for table_name in table_names:
        expected_mode = _tracking_mode(table_name)
        expected_ignore = IGNORE_FIELDS_MAP.get(table_name)

        row = existing.get(table_name)
        if row is None:
            session.add(MgmtRefEntityType(
                key=table_name,
                display_name=_derive_display_name(table_name),
                module=_derive_module(table_name),
                tracking_mode=expected_mode,
                ignore_fields=expected_ignore,
            ))
            dirty = True
        else:
            if row.tracking_mode != expected_mode:
                row.tracking_mode = expected_mode
                dirty = True
            if row.ignore_fields != expected_ignore:
                row.ignore_fields = expected_ignore
                dirty = True

    if dirty:
        await session.commit()
