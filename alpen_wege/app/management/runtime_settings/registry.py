# Standard library
import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SettingDef:
    key: str
    type: str  # 'int' | 'float' | 'bool' | 'string'
    default: Any
    category: str
    description: str
    min: float | None = None
    max: float | None = None
    requires_restart: bool = False


REGISTRY_LIST: tuple[SettingDef, ...] = (
    SettingDef("jobs.retention_days", "int", 30, "jobs",
               "Delete finished jobs older than this many days. 0 keeps them forever.", 0, 3650),
    SettingDef("jobs.stale_after_hours", "int", 24, "jobs",
               "Fail queued or running jobs that did not change for this many hours. 0 switches the check off.", 0, 720),
    SettingDef("jobs.progress_min_interval_ms", "int", 1000, "jobs",
               "Minimum time between two progress messages of one job.", 100, 60000),
    SettingDef("jobs.recent_finished_minutes", "int", 10, "jobs",
               "Jobs finished within this many minutes are included in the sync message of a WebSocket.", 0, 1440),
    SettingDef("events.retention_days", "int", 30, "events",
               "Delete event log entries older than this many days. 0 keeps them forever.", 0, 3650),
    SettingDef("ws.ticket_ttl_s", "int", 30, "ws",
               "Lifetime of a one-time WebSocket ticket in seconds.", 5, 300),
    SettingDef("ws.max_connections_per_user", "int", 5, "ws",
               "Open WebSockets allowed per user. Applies to new connections.", 1, 50),
    SettingDef("ws.max_lifetime_s", "int", 3600, "ws",
               "A WebSocket is closed after this many seconds and the client reconnects. Applies to new connections.", 60, 86400),
    SettingDef("celery.status_cache_s", "int", 5, "celery",
               "How long the Celery status answer is cached, in seconds. 0 switches the cache off.", 0, 60),
)

REGISTRY: dict[str, SettingDef] = {d.key: d for d in REGISTRY_LIST}


def validate_value(definition: SettingDef, value: Any) -> Any:
    # Check a value against the type and range of a setting.
    # Params:
    #   definition: the registry entry.
    #   value: the JSON value sent by the client or read from the database.
    # Returns: the normalised value.
    # Raises: ValueError with a short message for the client.
    if definition.type == "bool":
        if not isinstance(value, bool):
            raise ValueError("must be true or false")
        return value
    if definition.type == "string":
        if not isinstance(value, str):
            raise ValueError("must be text")
        if len(value) > 1000:
            raise ValueError("must be at most 1000 characters")
        return value
    if definition.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("must be a whole number")
    elif definition.type == "float":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("must be a number")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("must be a finite number")
    else:
        raise ValueError(f"unknown setting type {definition.type}")
    if definition.min is not None and value < definition.min:
        raise ValueError(f"must be at least {definition.min:g}")
    if definition.max is not None and value > definition.max:
        raise ValueError(f"must be at most {definition.max:g}")
    return value
