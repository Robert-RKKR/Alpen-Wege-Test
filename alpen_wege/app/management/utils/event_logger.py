# Standard library
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime

# Third-party
from geoalchemy2.elements import WKBElement
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.core.base import Base
from app.core.utils.responses import request_id_ctx

SKIP_FIELDS = frozenset({"id", "created_at", "updated_at", "created_by"})


@dataclass(frozen=True, slots=True)
class _EntityMeta:
    entity_type_id: uuid.UUID
    tracking_mode: str
    ignore_fields: frozenset[str] = field(default_factory=frozenset)


_entity_cache: dict[str, _EntityMeta] = {}


def _serialize_value(val):
    if val is None:
        return None
    if isinstance(val, uuid.UUID):
        return str(val)
    if isinstance(val, datetime):
        return val.isoformat()
    if isinstance(val, date):
        return val.isoformat()
    if isinstance(val, WKBElement):
        return None
    if isinstance(val, (list, tuple)):
        return [_serialize_value(v) for v in val]
    if isinstance(val, dict):
        return {k: _serialize_value(v) for k, v in val.items()}
    if isinstance(val, (str, int, float, bool)):
        return val
    return str(val)


def _snapshot_fields(instance, ignore: frozenset[str] = frozenset()) -> dict:
    # ignore: the entity type's ignore_fields; such a field is not read at all (asset_agg_icon.svg is a deferred column
    # of up to 300 KB that must neither be loaded for the log nor copied into it)
    mapper = inspect(type(instance))
    data = {}
    for col in mapper.columns:
        key = col.key
        if key in SKIP_FIELDS or key in ignore:
            continue
        data[key] = _serialize_value(getattr(instance, key, None))
    return data


def _changes_snapshot(changes: dict[str, tuple]) -> dict:
    return {
        key: {
            "old": _serialize_value(old),
            "new": _serialize_value(new),
        }
        for key, (old, new) in changes.items()
    }


async def load_entity_type_cache(session: AsyncSession) -> None:
    from app.management.models.entity_type import MgmtRefEntityType

    stmt = select(MgmtRefEntityType).where(MgmtRefEntityType.tracking_mode != "none")
    result = await session.execute(stmt)
    rows = result.scalars().all()
    _entity_cache.clear()
    for row in rows:
        _entity_cache[row.key] = _EntityMeta(
            entity_type_id=row.id,
            tracking_mode=row.tracking_mode,
            ignore_fields=frozenset(row.ignore_fields) if row.ignore_fields else frozenset(),
        )


def _get_meta_and_pk(instance):
    table = getattr(instance, "__tablename__", None)
    meta = _entity_cache.get(table)
    if meta is None:
        return None, None
    pk = inspect(instance).mapper.primary_key_from_instance(instance)
    if not pk or pk[0] is None:
        return None, None
    return meta, pk[0]


def log_created(db, instance, user_id: uuid.UUID) -> None:
    from app.management.models.event_log import MgmtLogEvent

    meta, entity_id = _get_meta_and_pk(instance)
    if meta is None:
        return
    db.add(MgmtLogEvent(
        entity_type_id=meta.entity_type_id,
        entity_id=entity_id,
        action="created",
        snapshot=_snapshot_fields(instance, meta.ignore_fields),
        changed_by=user_id,
        request_id=request_id_ctx.get("") or None,
    ))


def log_updated(
    db, instance, old_values: dict, changes: dict, user_id: uuid.UUID,
) -> None:
    from app.management.models.event_log import MgmtLogEvent

    meta, entity_id = _get_meta_and_pk(instance)
    if meta is None:
        return
    skip = SKIP_FIELDS | meta.ignore_fields
    diff = {}
    for field_name in changes:
        if field_name in skip:
            continue
        old = _serialize_value(old_values.get(field_name))
        new = _serialize_value(changes[field_name])
        if old != new:
            diff[field_name] = (old_values.get(field_name), changes[field_name])
    if not diff:
        return
    db.add(MgmtLogEvent(
        entity_type_id=meta.entity_type_id,
        entity_id=entity_id,
        action="updated",
        snapshot=_changes_snapshot(diff),
        changed_by=user_id,
        request_id=request_id_ctx.get("") or None,
    ))


def log_deleted(db, instance, user_id: uuid.UUID) -> None:
    from app.management.models.event_log import MgmtLogEvent

    meta, entity_id = _get_meta_and_pk(instance)
    if meta is None:
        return
    db.add(MgmtLogEvent(
        entity_type_id=meta.entity_type_id,
        entity_id=entity_id,
        action="deleted",
        snapshot=_snapshot_fields(instance, meta.ignore_fields),
        changed_by=user_id,
        request_id=request_id_ctx.get("") or None,
    ))
