#!/usr/bin/env python
"""Start a demo job (a worker task that sleeps and reports progress).

Usage (inside the api container):
    python scripts/demo_job.py --user-id <uuid> --seconds 8          # job of a user
    python scripts/demo_job.py --seconds 8 --fail                    # system job, task fails
"""
import argparse
import sys
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SyncSessionLocal  # noqa: E402
from app.management.jobs.events import publish_job_event  # noqa: E402
from app.management.jobs.kinds import JobKind, TASK_NAME  # noqa: E402
from app.management.jobs.service import create_job_sync  # noqa: E402
from app.worker import model_registry  # noqa: E402,F401
from app.worker.celery_app import celery_app  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Start a demo job")
    parser.add_argument("--user-id", help="owner of the job (omit for a system job)")
    parser.add_argument("--seconds", type=int, default=10)
    parser.add_argument("--fail", action="store_true")
    args = parser.parse_args()

    with SyncSessionLocal() as session:
        job = create_job_sync(
            session,
            user_id=UUID(args.user_id) if args.user_id else None,
            kind=JobKind.DEMO,
            task_name=TASK_NAME[JobKind.DEMO],
        )
        session.commit()
    publish_job_event(job)
    celery_app.send_task(
        TASK_NAME[JobKind.DEMO], args=[args.seconds, args.fail],
        task_id=str(job["id"]), ignore_result=True,
    )
    print(job["id"])


if __name__ == "__main__":
    main()
