# Standard library
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

# Local application
from app.management.schemas.job import JobAdminRead, JobRead

NOW = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)


def _row(**extra):
    base = dict(
        id=uuid.uuid4(), kind="track.process", status="running", stage="parsing", progress=None,
        subject_type="track", subject_id=uuid.uuid4(), result=None, error_message=None, attempts=1,
        created_at=NOW, started_at=NOW, finished_at=None, updated_at=NOW,
        user_id=uuid.uuid4(), task_name="tracks.process_gpx", worker_hostname="w1", request_id="r",
    )
    base.update(extra)
    return base


def test_from_mapping_builds_subject_and_hides_internal_fields():
    job = JobRead.model_validate(_row())
    dumped = job.model_dump(mode="json")
    assert dumped["subject"]["type"] == "track"
    assert "user_id" not in dumped and "task_name" not in dumped


def test_from_object_and_no_subject():
    job = JobRead.model_validate(SimpleNamespace(**_row(subject_type=None, subject_id=None)))
    assert job.subject is None


def test_admin_shape_has_extra_fields():
    job = JobAdminRead.model_validate(_row())
    assert job.task_name == "tracks.process_gpx" and job.worker_hostname == "w1"
