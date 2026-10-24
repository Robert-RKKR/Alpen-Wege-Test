# Standard library
import logging
import time
import uuid

# Third-party
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

# Local application
from app.database import SyncSessionLocal
from app.management.jobs import service
from app.management.jobs.events import publish_job_event, publish_progress
from app.management.jobs.outcome import GENERIC_FAILURE, TIMEOUT_FAILURE, interpret_result
from app.management.runtime_settings.service import get_setting_sync

logger = logging.getLogger(__name__)

_last_progress_sent: dict[str, float] = {}


def _to_uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def _run(fn) -> dict | None:
    # Run one job update in its own transaction, publish after the commit, never raise.
    try:
        with SyncSessionLocal() as session:
            row = fn(session)
            session.commit()
        if row is not None:
            publish_job_event(row)
        return row
    except Exception:
        logger.warning("Job update failed", exc_info=True)
        return None


class TrackedTask(Task):
    # Celery base class that keeps a mgmt_log_job row in step with the task. A task without a
    # job row (the UPDATEs match nothing) behaves exactly as before.
    #
    # job id = the keyword argument "job_id" (continuation tasks) or the task id (first task).
    job_stage: str | None = None  # stage set when this task starts (set through the task options)

    def _job_id(self, task_id, kwargs) -> uuid.UUID | None:
        return _to_uuid((kwargs or {}).get("job_id") or task_id)

    def before_start(self, task_id, args, kwargs):
        job_id = self._job_id(task_id, kwargs)
        if job_id is None:
            return
        first = str(job_id) == str(task_id)  # False for a continuation task (job_id in kwargs)
        row = _run(lambda s: service.mark_running(
            s, job_id, hostname=getattr(self.request, "hostname", None),
            stage=self.job_stage, first_task=first,
        ))
        if row is not None:
            self.request.job_id = str(job_id)
            self.request.job_user_id = row.get("user_id")

    def on_success(self, retval, task_id, args, kwargs):
        job_id = self._job_id(task_id, kwargs)
        if job_id is None:
            return
        action, info = interpret_result(retval)
        if action == "keep":
            return
        if action == "continue":
            if info.get("stage"):
                _run(lambda s: service.mark_progress(s, job_id, stage=info["stage"], progress=None))
            return
        _last_progress_sent.pop(str(job_id), None)
        if action == "failed":
            _run(lambda s: service.mark_failed(s, job_id, info["message"]))
        else:
            _run(lambda s: service.mark_succeeded(s, job_id, info["result"]))

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        job_id = self._job_id(task_id, kwargs)
        if job_id is not None:
            _run(lambda s: service.mark_queued_again(s, job_id, stage="retrying"))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        job_id = self._job_id(task_id, kwargs)
        if job_id is None:
            return
        _last_progress_sent.pop(str(job_id), None)
        message = TIMEOUT_FAILURE if isinstance(exc, SoftTimeLimitExceeded) else GENERIC_FAILURE
        _run(lambda s: service.mark_failed(s, job_id, message))


def report_progress(task, percent: int, stage: str | None = None, *, persist: bool = False) -> None:
    # Report progress from inside a tracked task (call as report_progress(self, 40, "parsing")).
    # persist=False: publish only, at most once per jobs.progress_min_interval_ms.
    # persist=True : also write stage and percent to the job row and publish the full job
    #                (use when the stage changes; a few times per job).
    # Never raises.
    job_id = getattr(task.request, "job_id", None)
    if not job_id:
        return
    try:
        if persist:
            parsed = uuid.UUID(job_id)
            _run(lambda s: service.mark_progress(s, parsed, stage=stage, progress=percent))
            return
        interval = get_setting_sync("jobs.progress_min_interval_ms") / 1000.0
        now = time.monotonic()
        if now - _last_progress_sent.get(job_id, 0.0) < interval:
            return
        _last_progress_sent[job_id] = now
        publish_progress(getattr(task.request, "job_user_id", None), job_id, stage, percent)
    except Exception:
        logger.warning("Could not report progress for job %s", job_id, exc_info=True)
