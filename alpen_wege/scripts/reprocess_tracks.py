#!/usr/bin/env python
"""Reprocess tracks (enqueue via Celery).

Usage:
    python scripts/reprocess_tracks.py --track-id <uuid> --apply
    python scripts/reprocess_tracks.py --below-version 2 --apply
    python scripts/reprocess_tracks.py --below-version 2 --limit 50
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402
from app.database import SyncSessionLocal  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Reprocess tracks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--track-id", help="UUID of a single track")
    group.add_argument(
        "--below-version", type=int,
        help="Reprocess tracks with processor_version NULL or < N",
    )
    parser.add_argument("--limit", type=int, default=None, help="Max tracks to enqueue")
    parser.add_argument("--apply", action="store_true", help="Actually enqueue (default is dry run)")
    args = parser.parse_args()

    if args.track_id:
        track_ids = [args.track_id]
    else:
        params = {"version": args.below_version}
        limit_clause = ""
        if args.limit:
            limit_clause = " LIMIT :lim"
            params["lim"] = args.limit

        with SyncSessionLocal() as session:
            rows = session.execute(
                text(
                    "SELECT t.id FROM explorer_agg_track t "
                    "  JOIN explorer_sub_geo_record g ON g.id = t.geo_record_id "
                    " WHERE t.processing_status = 'ready' "
                    "   AND t.archived_at IS NULL "
                    "   AND (g.processor_version IS NULL OR g.processor_version < :version) "
                    " ORDER BY t.created_at"
                    + limit_clause
                ),
                params,
            ).fetchall()
        track_ids = [str(r[0]) for r in rows]

    logger.info("Found %d track(s) to reprocess", len(track_ids))

    if not args.apply:
        for tid in track_ids[:20]:
            logger.info("  %s", tid)
        if len(track_ids) > 20:
            logger.info("  ... and %d more", len(track_ids) - 20)
        logger.info("Dry run. Use --apply to enqueue.")
        return

    from uuid import UUID  # noqa: E402
    from app.explorer.services.dispatch import enqueue_reprocess_track  # noqa: E402
    from app.management.jobs import service as job_service  # noqa: E402
    from app.management.jobs.events import publish_job_event  # noqa: E402
    from app.management.jobs.kinds import JobKind, TASK_NAME  # noqa: E402
    from app.worker import model_registry  # noqa: E402,F401

    enqueued = 0
    for tid in track_ids:
        job = None
        try:
            with SyncSessionLocal() as session:
                job, created = job_service.get_or_create_active_job_sync(
                    session, user_id=None,  # system job: visible through /management/jobs only
                    kind=JobKind.TRACK_REPROCESS,
                    task_name=TASK_NAME[JobKind.TRACK_REPROCESS],
                    subject_type="track", subject_id=UUID(str(tid)),
                )
                session.commit()
            if not created:
                logger.info("Track %s already has an active reprocess job %s, skipped", tid, job["id"])
                continue
            publish_job_event(job)
            enqueue_reprocess_track(tid, job["id"])
            enqueued += 1
        except Exception:
            logger.warning("Failed to enqueue reprocess for track %s", tid)
            if job is not None:
                # do not leave a queued job behind: the next run would skip the track as "already active"
                with SyncSessionLocal() as session:
                    failed = job_service.mark_failed(session, job["id"], "The reprocess could not be queued.")
                    session.commit()
                if failed is not None:
                    publish_job_event(failed)

    logger.info("Enqueued %d / %d tracks", enqueued, len(track_ids))


if __name__ == "__main__":
    main()
