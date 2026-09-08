# Standard library
import logging

# Local application
from app.worker.celery_app import celery_app
from app.database import SyncSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task
def cleanup_orphaned_comments():
    # Celery task: delete comments that point to tracks/routes which no longer
    # exist.
    # Params: none.
    # Returns: a status dict ({"status": "done"}) once cleanup completes.
    # Use a synchronous session because Celery workers run outside the async
    # event loop.
    with SyncSessionLocal() as session:
        from sqlalchemy import text

        # Remove "track" comments whose referenced track row is gone.
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

        # Remove "route" comments whose referenced route row is gone.
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
