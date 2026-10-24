# Standard library
import logging
from uuid import UUID

# Third-party
import redis as sync_redis
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import select, text, update

# Local application
from app.worker import model_registry  # noqa: F401
from app.config import get_settings
from app.database import SyncSessionLocal
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.models.models_sub.geo_record import ExplorerSubGeoRecord
from app.assets.models.models_agg.gpx import AssetAggGpx
from app.explorer.services.gpx.errors import GpxProcessingError
from app.explorer.services.gpx.pipeline import process_gpx_file
from app.explorer.services.gpx_storage import resolve_path
from app.explorer.services.track_persist import mark_failed, persist_processed_track
from app.explorer.services.dispatch import (
    enqueue_detect_pois,
    enqueue_process_track,
    request_stats_recompute,
)
from app.management.jobs import service as job_service
from app.management.jobs.events import publish_job_event
from app.management.jobs.kinds import JobKind, TASK_NAME
from app.management.jobs.tracked_task import TrackedTask, report_progress

logger = logging.getLogger(__name__)
settings = get_settings()


@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.process_gpx",
    job_stage="parsing",
    acks_late=True,
    soft_time_limit=600,
    time_limit=660,
    max_retries=3,
)
def process_track_gpx(self, track_id: str):
    track_id = UUID(track_id)

    with SyncSessionLocal() as session:
        result = session.execute(
            text(
                "UPDATE explorer_agg_track "
                "SET processing_status = 'processing', processing_error = NULL, "
                "    processing_started_at = now(), updated_at = now() "
                "WHERE id = :id AND processing_status = 'pending' "
                "  AND archived_at IS NULL "
                "RETURNING gpx_id"
            ),
            {"id": str(track_id)},
        )
        row = result.fetchone()
        session.commit()

    if row is None:
        with SyncSessionLocal() as session:
            state = session.execute(
                text(
                    "SELECT processing_status, archived_at IS NOT NULL "
                    "FROM explorer_agg_track WHERE id = :id"
                ),
                {"id": str(track_id)},
            ).first()
        status_now, archived = (state[0], state[1]) if state else (None, False)
        # TrackedTask.before_start sets request.job_id only if THIS execution moved the job from
        # queued to running. Then nobody else is working on it and the job must not stay running.
        owns_job = bool(getattr(self.request, "job_id", None))
        if owns_job and status_now != "processing":
            # archived: restore enqueues again with a new job; otherwise the track is already done
            reason = "archived" if archived else "already_processed"
            return {"track_id": str(track_id), "status": "skipped", "reason": reason}
        # another execution owns the track and the job: leave both alone
        return {"track_id": str(track_id), "status": "skipped", "job": "keep"}

    gpx_id = row[0]

    with SyncSessionLocal() as session:
        gpx = session.get(AssetAggGpx, gpx_id)
        if not gpx:
            mark_failed(session, track_id, "GPX asset record not found.")
            return {"track_id": str(track_id), "status": "failed"}
        gpx_path = str(resolve_path(gpx.path))

    try:
        processed = process_gpx_file(gpx_path)
    except GpxProcessingError as exc:
        with SyncSessionLocal() as session:
            mark_failed(session, track_id, exc.user_message)
        if exc.code == "file_missing":
            logger.error("GPX file missing for track %s: %s", track_id, gpx_path)
        return {"track_id": str(track_id), "status": "failed", "error": exc.code}
    except SoftTimeLimitExceeded:
        with SyncSessionLocal() as session:
            mark_failed(
                session, track_id,
                "Processing took too long. Please try a smaller file or contact support.",
            )
        return {"track_id": str(track_id), "status": "failed", "error": "timeout"}
    except Exception as exc:
        logger.exception("Unexpected error processing track %s", track_id)
        with SyncSessionLocal() as session:
            mark_failed(
                session, track_id,
                "Processing failed. Please try again or contact support.",
            )
        return {"track_id": str(track_id), "status": "failed", "error": "internal_error"}

    report_progress(self, 60, "saving", persist=True)

    try:
        with SyncSessionLocal() as session:
            track = session.execute(
                select(ExplorerAggTrack)
                .where(ExplorerAggTrack.id == track_id)
                .with_for_update()
            ).scalar_one_or_none()

            if not track or track.processing_status != "processing":
                return {"track_id": str(track_id), "status": "skipped", "job": "keep"}

            persist_processed_track(session, track, processed)
            owner_id = track.created_by
            session.commit()
    except Exception as exc:
        logger.exception("DB error persisting track %s", track_id)
        if self.request.retries >= (self.max_retries or 0):
            # last attempt: fail now, while the track is still 'processing' (mark_failed only
            # touches 'processing' rows), so the track and its job end with the same text
            with SyncSessionLocal() as session:
                mark_failed(
                    session, track_id,
                    "Processing failed after multiple attempts. Please contact support.",
                )
            return {"track_id": str(track_id), "status": "failed", "error": "max_retries"}
        try:
            with SyncSessionLocal() as session:
                session.execute(
                    update(ExplorerAggTrack)
                    .where(ExplorerAggTrack.id == track_id)
                    .values(processing_status="pending", processing_started_at=None)
                )
                session.commit()
            self.retry(countdown=30 * 2 ** self.request.retries, max_retries=3)
        except self.MaxRetriesExceededError:
            with SyncSessionLocal() as session:
                mark_failed(
                    session, track_id,
                    "Processing failed after multiple attempts. Please contact support.",
                )
            return {"track_id": str(track_id), "status": "failed", "error": "max_retries"}
        raise

    # hand the job to detect_pois (same job id as keyword argument); if that fails the job ends here
    continued = False
    try:
        enqueue_detect_pois(track_id, job_id=self.request.id)
        continued = True
    except Exception:
        logger.warning("Failed to enqueue detect_pois for track %s", track_id)

    try:
        request_stats_recompute(owner_id)
    except Exception:
        logger.warning("Failed to request stats recompute for user %s", owner_id)

    result = {
        "track_id": str(track_id),
        "status": "ready",
        "warnings": processed.warnings,
    }
    if continued:
        result.update({"job": "continue", "stage": "detecting_pois"})
    return result


@shared_task(name="tracks.reap_stuck")
def reap_stuck_tracks():
    _reap_stuck_processing()
    _reap_stuck_pending()


def _reap_stuck_processing():
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT id, created_by FROM explorer_agg_track "
                "WHERE processing_status = 'processing' "
                "  AND processing_started_at < now() - make_interval(mins => :mins)"
            ),
            {"mins": settings.STUCK_PROCESSING_MINUTES},
        ).fetchall()

    if not rows:
        return

    try:
        r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        r = None

    for tid, owner_id in rows:
        attempts = 0
        if r:
            try:
                key = f"track:attempts:{tid}"
                attempts = r.incr(key)
                r.expire(key, 86400)
            except Exception:
                pass

        job_event = None
        enqueue_job_id = None
        with SyncSessionLocal() as session:
            if attempts >= settings.STUCK_MAX_ATTEMPTS:
                message = "Processing was interrupted repeatedly. Please try again or contact support."
                updated = session.execute(
                    text(
                        "UPDATE explorer_agg_track "
                        "SET processing_status = 'failed', "
                        "    processing_error = :msg, "
                        "    processing_started_at = NULL, updated_at = now() "
                        "WHERE id = :id AND processing_status = 'processing' "
                        "  AND processing_started_at < now() - make_interval(mins => :mins)"
                    ),
                    {"id": str(tid), "msg": message, "mins": settings.STUCK_PROCESSING_MINUTES},
                )
                if updated.rowcount:
                    job_event = job_service.fail_active_job_for_subject(
                        session, kind=JobKind.TRACK_PROCESS, subject_type="track",
                        subject_id=tid, message=message,
                    )
                    logger.warning("Track %s failed after %d stuck attempts", tid, attempts)
            else:
                updated = session.execute(
                    text(
                        "UPDATE explorer_agg_track "
                        "SET processing_status = 'pending', "
                        "    processing_started_at = NULL, updated_at = now() "
                        "WHERE id = :id AND processing_status = 'processing' "
                        "  AND processing_started_at < now() - make_interval(mins => :mins)"
                    ),
                    {"id": str(tid), "mins": settings.STUCK_PROCESSING_MINUTES},
                )
                if updated.rowcount:
                    job, changed = job_service.requeue_or_create_job_sync(
                        session, user_id=owner_id, kind=JobKind.TRACK_PROCESS,
                        task_name=TASK_NAME[JobKind.TRACK_PROCESS],
                        subject_type="track", subject_id=tid,
                    )
                    enqueue_job_id = job["id"]
                    job_event = job if changed else None
            session.commit()

        # after the commit: publish and enqueue (the worker must see the track as pending)
        if job_event is not None:
            publish_job_event(job_event)
        if enqueue_job_id is not None:
            try:
                enqueue_process_track(tid, enqueue_job_id)
            except Exception:
                logger.warning("Failed to re-enqueue stuck track %s", tid)


@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.reprocess",
    job_stage="reprocessing",
    acks_late=True,
    soft_time_limit=600,
    time_limit=660,
)
def reprocess_track(self, track_id: str):
    track_id = UUID(track_id)

    with SyncSessionLocal() as session:
        session.execute(
            text(
                "SELECT pg_advisory_xact_lock(hashtextextended(:tid_text, 0))"
            ),
            {"tid_text": str(track_id)},
        )
        track = session.execute(
            select(ExplorerAggTrack)
            .where(ExplorerAggTrack.id == track_id)
            .with_for_update()
        ).scalar_one_or_none()

        if not track or track.processing_status != "ready":
            return {"track_id": str(track_id), "status": "skipped"}

        gpx = session.get(AssetAggGpx, track.gpx_id)
        if not gpx:
            logger.error("GPX asset not found for track %s", track_id)
            return {"track_id": str(track_id), "status": "failed"}
        gpx_path = str(resolve_path(gpx.path))

        existing_geo_record = None
        if track.geo_record_id:
            existing_geo_record = session.get(
                ExplorerSubGeoRecord, track.geo_record_id
            )

        try:
            processed = process_gpx_file(gpx_path)
        except GpxProcessingError as exc:
            logger.error(
                "Reprocess failed for track %s: %s", track_id, exc.user_message
            )
            return {
                "track_id": str(track_id), "status": "failed",
                "error": exc.code, "message": exc.user_message,
            }
        except Exception:
            logger.exception("Unexpected error reprocessing track %s", track_id)
            return {"track_id": str(track_id), "status": "failed", "error": "internal_error"}

        persist_processed_track(
            session, track, processed,
            existing_geo_record=existing_geo_record,
        )
        owner_id = track.created_by
        session.commit()

    continued = False
    try:
        enqueue_detect_pois(track_id, job_id=self.request.id)
        continued = True
    except Exception:
        logger.warning("Failed to enqueue detect_pois after reprocess for track %s", track_id)

    try:
        request_stats_recompute(owner_id)
    except Exception:
        logger.warning("Failed to request stats recompute after reprocess for user %s", owner_id)

    logger.info("Reprocessed track %s", track_id)
    result = {"track_id": str(track_id), "status": "ready"}
    if continued:
        result.update({"job": "continue", "stage": "detecting_pois"})
    return result


def _reap_stuck_pending():
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                "WITH due AS ("
                "  SELECT id FROM explorer_agg_track"
                "  WHERE processing_status = 'pending' AND archived_at IS NULL"
                "    AND updated_at < now() - make_interval(mins => :mins)"
                "  FOR UPDATE SKIP LOCKED"
                ") "
                "UPDATE explorer_agg_track t SET updated_at = now() "
                "FROM due WHERE t.id = due.id "
                "RETURNING t.id, t.created_by"
            ),
            {"mins": settings.STUCK_PENDING_MINUTES},
        ).fetchall()
        session.commit()

    for tid, owner_id in rows:
        try:
            with SyncSessionLocal() as session:
                job, changed = job_service.requeue_or_create_job_sync(
                    session, user_id=owner_id, kind=JobKind.TRACK_PROCESS,
                    task_name=TASK_NAME[JobKind.TRACK_PROCESS],
                    subject_type="track", subject_id=tid,
                )
                session.commit()
            if changed:
                publish_job_event(job)
            enqueue_process_track(tid, job["id"])
        except Exception:
            logger.warning("Failed to re-enqueue pending track %s", tid)
