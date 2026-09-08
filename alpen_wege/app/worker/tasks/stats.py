# Standard library
import logging
from datetime import datetime, timedelta, timezone

# Local application
from app.worker.celery_app import celery_app
from app.database import SyncSessionLocal

logger = logging.getLogger(__name__)


@celery_app.task
def log_active_users():
    # Celery task: count and log users active within the last hour.
    # Params: none.
    # Returns: a dict {"active_users": <count>}.
    # Synchronous session: Celery workers run outside the async event loop.
    with SyncSessionLocal() as session:
        from sqlalchemy import text

        # Count users whose last_active_at falls within the past hour.
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        result = session.execute(
            text(
                "SELECT count(*) FROM profile_usr_user "
                "WHERE last_active_at > :since"
            ),
            {"since": one_hour_ago},
        )
        count = result.scalar()
        logger.info("Active users in the last hour: %d", count)

    return {"active_users": count}


@celery_app.task
def aggregate_user_statistics(user_id: str):
    # Celery task: recompute and upsert lifetime activity totals for one user.
    # Params:
    #   user_id: the user's id whose statistics should be aggregated.
    # Returns: a dict {"user_id": ..., "status": "done"}.
    # Synchronous session: Celery workers run outside the async event loop.
    with SyncSessionLocal() as session:
        from sqlalchemy import text

        # Aggregate counts/distance/elevation/time across the user's tracks.
        result = session.execute(
            text(
                """
                SELECT
                    count(*) as total_activities,
                    coalesce(sum(gr.distance_m), 0) as total_distance_m,
                    coalesce(sum(gr.elevation_gain_m), 0) as total_elevation_m,
                    coalesce(sum(gp.total_time_s), 0) as total_time_s
                FROM explorer_agg_track t
                LEFT JOIN explorer_sub_geo_record gr ON t.geo_record_id = gr.id
                LEFT JOIN explorer_sub_geo_performance gp
                    ON gr.geo_performance_id = gp.id
                WHERE t.created_by = :uid
                """
            ),
            {"uid": user_id},
        )
        row = result.one()

        # Upsert the aggregated totals into the "all"-scope statistics row.
        session.execute(
            text(
                """
                INSERT INTO profile_sub_statistic
                    (user_id, scope, total_distance_m, total_elevation_m,
                     total_activities, total_time_s)
                VALUES (:uid, 'all', :dist, :elev, :acts, :time)
                ON CONFLICT (user_id, scope, scope_year, scope_month)
                DO UPDATE SET
                    total_distance_m = EXCLUDED.total_distance_m,
                    total_elevation_m = EXCLUDED.total_elevation_m,
                    total_activities = EXCLUDED.total_activities,
                    total_time_s = EXCLUDED.total_time_s
                """
            ),
            {
                "uid": user_id,
                "dist": row.total_distance_m,
                "elev": row.total_elevation_m,
                "acts": row.total_activities,
                "time": row.total_time_s,
            },
        )
        session.commit()

    logger.info("Aggregated statistics for user %s", user_id)
    return {"user_id": user_id, "status": "done"}
