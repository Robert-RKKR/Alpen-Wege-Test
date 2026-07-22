import logging

from app.worker.celery_app import celery_app
from app.database import SyncSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task
def cleanup_orphaned_comments():
    with SyncSessionLocal() as session:
        from sqlalchemy import text

        result = session.execute(
            text(
                """
                DELETE FROM social_sub_comment
                WHERE entity_type = 'track'
                  AND entity_id NOT IN (SELECT id FROM explorer_agg_track)
                """
            )
        )
        deleted = result.rowcount
        session.commit()
        logger.info("Cleaned up %d orphaned track comments", deleted)

        result = session.execute(
            text(
                """
                DELETE FROM social_sub_comment
                WHERE entity_type = 'route'
                  AND entity_id NOT IN (SELECT id FROM explorer_agg_route)
                """
            )
        )
        deleted = result.rowcount
        session.commit()
        logger.info("Cleaned up %d orphaned route comments", deleted)

    return {"status": "done"}
