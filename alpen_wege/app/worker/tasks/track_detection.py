# Standard library
import logging
from uuid import UUID

# Third-party
import redis as sync_redis
from celery import shared_task

# Local application
from app.worker import model_registry  # noqa: F401
from app.config import get_settings
from app.database import SyncSessionLocal
from app.explorer.services.poi_detection import (
    detect_for_track,
    rescan_card as _rescan_card,
    rescan_poi_batch,
)
from app.explorer.services.dispatch import request_stats_recompute
from app.management.jobs.tracked_task import TrackedTask

logger = logging.getLogger(__name__)
settings = get_settings()


@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.detect_pois",
    job_stage="detecting_pois",
    acks_late=True,
    soft_time_limit=300,
    time_limit=330,
)
def detect_pois(self, track_id: str, job_id: str | None = None):
    # job_id: the job this task continues (read by TrackedTask from the keyword arguments).
    track_id = UUID(track_id)

    with SyncSessionLocal() as session:
        report = detect_for_track(
            session, track_id,
            radius_m=settings.POI_COLLECT_RADIUS_M,
            require_timestamps=settings.POI_DETECTION_REQUIRES_TIMESTAMPS,
        )
        session.commit()

    for uid in report.affected_user_ids:
        try:
            request_stats_recompute(uid)
        except Exception:
            logger.warning("Failed to request stats recompute for user %s", uid)

    logger.info(
        "detect_pois track=%s: visits=%d cards=%d start=%s end=%s",
        track_id, report.visits_added, report.cards_added,
        report.start_poi_set, report.end_poi_set,
    )
    return {
        "track_id": str(track_id),
        "status": report.status,
        "visits_added": report.visits_added,
        "cards_added": report.cards_added,
    }


@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.rescan_poi",
    job_stage="scanning",
    acks_late=True,
    soft_time_limit=1800,
    time_limit=1860,
)
def rescan_poi(self, poi_id: str):
    poi_uuid = UUID(poi_id)
    lock_key = f"rescan:poi:{poi_id}"

    try:
        total_visits = 0
        total_cards = 0
        total_tracks = 0
        all_affected: set[UUID] = set()
        after_track_id = None

        while True:
            with SyncSessionLocal() as session:
                batch = rescan_poi_batch(
                    session, poi_uuid,
                    radius_m=settings.POI_COLLECT_RADIUS_M,
                    require_timestamps=settings.POI_DETECTION_REQUIRES_TIMESTAMPS,
                    after_track_id=after_track_id,
                    batch_size=200,
                )
                session.commit()

            total_visits += batch.visits_added
            total_cards += batch.cards_added
            total_tracks += batch.tracks_scanned
            all_affected.update(batch.affected_user_ids)

            if batch.last_track_id is None:
                break
            after_track_id = batch.last_track_id

        for uid in all_affected:
            try:
                request_stats_recompute(uid)
            except Exception:
                logger.warning("Failed to request stats recompute for user %s", uid)

        logger.info(
            "rescan_poi poi=%s: tracks=%d visits=%d cards=%d users=%d",
            poi_id, total_tracks, total_visits, total_cards, len(all_affected),
        )
        return {
            "status": "done",
            "poi_id": poi_id,
            "tracks_scanned": total_tracks,
            "visits_added": total_visits,
            "cards_added": total_cards,
        }
    finally:
        try:
            r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.delete(lock_key)
        except Exception:
            logger.warning("Could not delete rescan lock %s", lock_key)


@shared_task(
    bind=True,
    base=TrackedTask,
    name="tracks.rescan_card",
    job_stage="scanning",
    acks_late=True,
    soft_time_limit=120,
    time_limit=150,
)
def rescan_card(self, card_id: str):
    lock_key = f"rescan:card:{card_id}"

    try:
        with SyncSessionLocal() as session:
            report = _rescan_card(session, card_id)
            session.commit()

        for uid in report.affected_user_ids:
            try:
                request_stats_recompute(uid)
            except Exception:
                logger.warning("Failed to request stats recompute for user %s", uid)

        logger.info(
            "rescan_card card=%s: granted=%d users=%d",
            card_id, report.cards_granted, len(report.affected_user_ids),
        )
        return {
            "status": "done",
            "card_id": card_id,
            "cards_granted": report.cards_granted,
        }
    finally:
        try:
            r = sync_redis.from_url(settings.REDIS_URL, decode_responses=True)
            r.delete(lock_key)
        except Exception:
            logger.warning("Could not delete rescan lock %s", lock_key)
