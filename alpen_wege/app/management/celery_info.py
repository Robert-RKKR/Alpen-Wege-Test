# Standard library
import logging
from datetime import datetime, timezone

# Third-party
import redis as sync_redis

# Local application
from app.config import get_settings
from app.management.jobs.kinds import CHAIN_TASKS, TRACKED_TASKS
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _epoch_to_iso(value) -> str | None:
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError):
        return None


# ------------------------------------------------------------------ pure shaping (tested)

def shape_workers(stats: dict | None, queues: dict | None, registered: dict | None) -> list[dict]:
    stats, queues, registered = stats or {}, queues or {}, registered or {}
    out = []
    for name in sorted(set(stats) | set(queues) | set(registered)):
        s = stats.get(name) or {}
        pool = s.get("pool") or {}
        out.append({
            "hostname": name,
            "pid": s.get("pid"),
            "uptime_s": s.get("uptime"),
            "concurrency": pool.get("max-concurrency"),
            "queues": sorted(q["name"] for q in (queues.get(name) or []) if q.get("name")),
            "tasks_executed": dict(s.get("total") or {}),
            "registered_tasks": len(registered.get(name) or []),
        })
    return out


def shape_live(active: dict | None, reserved: dict | None, scheduled: dict | None) -> list[dict]:
    # Task arguments are deliberately dropped here.
    items = []
    for state, data in (("active", active), ("reserved", reserved), ("scheduled", scheduled)):
        for worker, tasks in (data or {}).items():
            for task in tasks or []:
                request = (task.get("request") if state == "scheduled" else task) or {}
                if not request.get("id"):
                    continue
                items.append({
                    "task_id": request["id"],
                    "name": request.get("name"),
                    "worker": worker,
                    "state": state,
                    "started_at": _epoch_to_iso(request.get("time_start")) if state == "active" else None,
                    "eta": task.get("eta") if state == "scheduled" else None,
                })
    return items


def shape_registered(registered: dict | None) -> list[dict]:
    names = sorted({n for tasks in (registered or {}).values() for n in (tasks or []) if not n.startswith("celery.")})
    return [
        {"name": n, "tracked": n in TRACKED_TASKS or n in CHAIN_TASKS, "job_kind": TRACKED_TASKS.get(n)}
        for n in names
    ]


def overall_state(broker_ok: bool, workers_online: int) -> str:
    if not broker_ok:
        return "down"
    return "ok" if workers_online > 0 else "no_workers"


# ------------------------------------------------------------------ blocking collectors

def _redis_ok(url: str) -> bool:
    client = None
    try:
        client = sync_redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        return bool(client.ping())
    except Exception:
        return False
    finally:
        if client is not None:
            client.close()


def _queue_length() -> int | None:
    client = None
    try:
        client = sync_redis.from_url(get_settings().CELERY_BROKER_URL, socket_connect_timeout=2, socket_timeout=2)
        return int(client.llen(celery_app.conf.task_default_queue or "celery"))
    except Exception:
        return None
    finally:
        if client is not None:
            client.close()


def _online_workers(timeout: float) -> list[str]:
    try:
        return sorted((celery_app.control.inspect(timeout=timeout).ping() or {}).keys())
    except Exception:
        logger.warning("Celery ping failed", exc_info=True)
        return []


def _inspector(workers: list[str], timeout: float):
    return celery_app.control.inspect(destination=workers, timeout=timeout, limit=len(workers))


def collect_status(timeout: float = 1.0) -> dict:
    settings = get_settings()
    broker_ok = _redis_ok(settings.CELERY_BROKER_URL)
    backend_ok = _redis_ok(settings.CELERY_RESULT_BACKEND)
    workers = _online_workers(timeout) if broker_ok else []
    active = reserved = scheduled = 0
    if workers:
        insp = _inspector(workers, timeout)
        active = sum(len(v) for v in (insp.active() or {}).values())
        reserved = sum(len(v) for v in (insp.reserved() or {}).values())
        scheduled = sum(len(v) for v in (insp.scheduled() or {}).values())
    return {
        "state": overall_state(broker_ok, len(workers)),
        "broker_reachable": broker_ok,
        "result_backend_reachable": backend_ok,
        "workers_online": len(workers),
        "workers": workers,
        "queue_length": _queue_length() if broker_ok else None,
        "active_tasks": active,
        "reserved_tasks": reserved,
        "scheduled_tasks": scheduled,
        "beat_entries": len(celery_app.conf.beat_schedule or {}),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def collect_workers(timeout: float = 1.0) -> list[dict]:
    workers = _online_workers(timeout)
    if not workers:
        return []
    insp = _inspector(workers, timeout)
    return shape_workers(insp.stats(), insp.active_queues(), insp.registered())


def collect_registered(timeout: float = 1.0) -> list[dict]:
    workers = _online_workers(timeout)
    if not workers:
        return []
    return shape_registered(_inspector(workers, timeout).registered())


def collect_live(timeout: float = 1.0) -> list[dict]:
    workers = _online_workers(timeout)
    if not workers:
        return []
    insp = _inspector(workers, timeout)
    return shape_live(insp.active(), insp.reserved(), insp.scheduled())


def collect_beat() -> list[dict]:
    now = datetime.now(timezone.utc)
    entries = []
    for name, entry in sorted((celery_app.conf.beat_schedule or {}).items()):
        schedule = entry.get("schedule")
        try:
            next_run = (now + schedule.remaining_estimate(now)).isoformat()
        except Exception:
            next_run = None
        entries.append({
            "name": name,
            "task": entry.get("task"),
            "schedule": getattr(schedule, "human_readable", None) or str(schedule),
            "next_run_at": next_run,
        })
    return entries
