# Local application
from app.management.celery_info import overall_state, shape_live, shape_registered, shape_workers


def test_shape_live_drops_arguments_and_handles_scheduled():
    active = {"w1": [{"id": "a", "name": "mgmt.demo_job", "args": "(8,)", "kwargs": "{}", "time_start": 1790000000.0}]}
    scheduled = {"w1": [{"eta": "2026-10-23T08:00:00+00:00", "request": {"id": "s", "name": "stats.recompute_user", "args": "('u',)"}}]}
    items = shape_live(active, None, scheduled)
    assert [i["task_id"] for i in items] == ["a", "s"]
    assert all("args" not in i and "kwargs" not in i for i in items)
    assert items[0]["state"] == "active" and items[0]["started_at"] is not None
    assert items[1]["state"] == "scheduled" and items[1]["eta"] is not None


def test_shape_workers_and_registered():
    workers = shape_workers(
        {"w1": {"pid": 7, "uptime": 120, "pool": {"max-concurrency": 4}, "total": {"mgmt.demo_job": 2}}},
        {"w1": [{"name": "celery"}]},
        {"w1": ["tracks.process_gpx", "celery.ping"]},
    )
    assert workers[0]["concurrency"] == 4 and workers[0]["queues"] == ["celery"] and workers[0]["registered_tasks"] == 2
    names = {t["name"]: t for t in shape_registered({"w1": ["tracks.process_gpx", "stats.recompute_user", "celery.ping"]})}
    assert "celery.ping" not in names
    assert names["tracks.process_gpx"]["tracked"] is True and names["tracks.process_gpx"]["job_kind"] == "track.process"
    assert names["stats.recompute_user"]["tracked"] is False


def test_overall_state():
    assert overall_state(False, 3) == "down"
    assert overall_state(True, 0) == "no_workers"
    assert overall_state(True, 1) == "ok"
