# Standard library
import logging

# Third-party
from sqlalchemy import text

logger = logging.getLogger(__name__)

_UPSERT_COLUMNS = (
    "total_activities, total_distance_m, total_elevation_m, total_elevation_loss_m, "
    "total_time_s, total_moving_time_s, active_days, "
    "max_elevation_m, longest_track_m, longest_track_id"
)

_ON_CONFLICT = (
    "ON CONFLICT ON CONSTRAINT uq_profile_sub_statistic_bucket DO UPDATE SET "
    "total_activities = EXCLUDED.total_activities, "
    "total_distance_m = EXCLUDED.total_distance_m, "
    "total_elevation_m = EXCLUDED.total_elevation_m, "
    "total_elevation_loss_m = EXCLUDED.total_elevation_loss_m, "
    "total_time_s = EXCLUDED.total_time_s, "
    "total_moving_time_s = EXCLUDED.total_moving_time_s, "
    "active_days = EXCLUDED.active_days, "
    "max_elevation_m = EXCLUDED.max_elevation_m, "
    "longest_track_m = EXCLUDED.longest_track_m, "
    "longest_track_id = EXCLUDED.longest_track_id, "
    "updated_at = now()"
)

_SRC_CTE = """
WITH src AS (
    SELECT t.id, t.sport_type_id,
           gr.distance_m, gr.elevation_gain_m, gr.elevation_loss_m,
           gr.highest_elevation_m,
           gp.total_time_s, gp.moving_time_s,
           (t.recorded_at AT TIME ZONE 'UTC') AS rec_utc,
           EXTRACT(YEAR  FROM t.recorded_at AT TIME ZONE 'UTC')::int AS y,
           EXTRACT(MONTH FROM t.recorded_at AT TIME ZONE 'UTC')::int AS m
      FROM explorer_agg_track t
      JOIN explorer_sub_geo_record gr ON gr.id = t.geo_record_id
      LEFT JOIN explorer_sub_geo_performance gp ON gp.id = gr.geo_performance_id
     WHERE t.created_by = :uid AND t.archived_at IS NULL
       AND t.processing_status = 'ready'
)
"""

_ALL_SQL = _SRC_CTE + f"""
INSERT INTO profile_sub_statistic
    (user_id, sport_type_id, scope, scope_year, scope_month, {_UPSERT_COLUMNS})
SELECT :uid, sport_type_id, 'all', NULL, NULL,
       count(*),
       coalesce(sum(distance_m), 0), coalesce(sum(elevation_gain_m), 0),
       coalesce(sum(elevation_loss_m), 0),
       coalesce(sum(total_time_s), 0), coalesce(sum(moving_time_s), 0),
       count(DISTINCT rec_utc::date),
       max(highest_elevation_m), max(distance_m),
       (array_agg(id ORDER BY distance_m DESC NULLS LAST))[1]
  FROM src
 GROUP BY GROUPING SETS ((), (sport_type_id))
HAVING GROUPING(sport_type_id) = 1 OR sport_type_id IS NOT NULL
{_ON_CONFLICT}
"""

_YEAR_SQL = _SRC_CTE + f"""
INSERT INTO profile_sub_statistic
    (user_id, sport_type_id, scope, scope_year, scope_month, {_UPSERT_COLUMNS})
SELECT :uid, sport_type_id, 'year', y, NULL,
       count(*),
       coalesce(sum(distance_m), 0), coalesce(sum(elevation_gain_m), 0),
       coalesce(sum(elevation_loss_m), 0),
       coalesce(sum(total_time_s), 0), coalesce(sum(moving_time_s), 0),
       count(DISTINCT rec_utc::date),
       max(highest_elevation_m), max(distance_m),
       (array_agg(id ORDER BY distance_m DESC NULLS LAST))[1]
  FROM src
 WHERE rec_utc IS NOT NULL
 GROUP BY GROUPING SETS ((y), (y, sport_type_id))
HAVING GROUPING(sport_type_id) = 1 OR sport_type_id IS NOT NULL
{_ON_CONFLICT}
"""

_MONTH_SQL = _SRC_CTE + f"""
INSERT INTO profile_sub_statistic
    (user_id, sport_type_id, scope, scope_year, scope_month, {_UPSERT_COLUMNS})
SELECT :uid, sport_type_id, 'month', y, m,
       count(*),
       coalesce(sum(distance_m), 0), coalesce(sum(elevation_gain_m), 0),
       coalesce(sum(elevation_loss_m), 0),
       coalesce(sum(total_time_s), 0), coalesce(sum(moving_time_s), 0),
       count(DISTINCT rec_utc::date),
       max(highest_elevation_m), max(distance_m),
       (array_agg(id ORDER BY distance_m DESC NULLS LAST))[1]
  FROM src
 WHERE rec_utc IS NOT NULL
 GROUP BY GROUPING SETS ((y, m), (y, m, sport_type_id))
HAVING GROUPING(sport_type_id) = 1 OR sport_type_id IS NOT NULL
{_ON_CONFLICT}
"""

_POI_ALL_SQL = """
UPDATE profile_sub_statistic s SET unique_pois_count = v.n, updated_at = now()
  FROM (SELECT count(DISTINCT poi_id) AS n
          FROM profile_m2m_user_poi WHERE user_id = :uid) v
 WHERE s.user_id = :uid AND s.scope = 'all' AND s.sport_type_id IS NULL
"""

_POI_YEAR_SQL = """
UPDATE profile_sub_statistic s
   SET unique_pois_count = coalesce(v.n, 0), updated_at = now()
  FROM (SELECT EXTRACT(YEAR FROM collected_at AT TIME ZONE 'UTC')::int AS y,
               count(DISTINCT poi_id) AS n
          FROM profile_m2m_user_poi WHERE user_id = :uid
         GROUP BY y) v
 WHERE s.user_id = :uid AND s.scope = 'year'
   AND s.scope_year = v.y AND s.sport_type_id IS NULL
"""

_POI_MONTH_SQL = """
UPDATE profile_sub_statistic s
   SET unique_pois_count = coalesce(v.n, 0), updated_at = now()
  FROM (SELECT EXTRACT(YEAR  FROM collected_at AT TIME ZONE 'UTC')::int AS y,
               EXTRACT(MONTH FROM collected_at AT TIME ZONE 'UTC')::int AS m,
               count(DISTINCT poi_id) AS n
          FROM profile_m2m_user_poi WHERE user_id = :uid
         GROUP BY y, m) v
 WHERE s.user_id = :uid AND s.scope = 'month'
   AND s.scope_year = v.y AND s.scope_month = v.m
   AND s.sport_type_id IS NULL
"""

_ZERO_SQL = """
UPDATE profile_sub_statistic
   SET total_activities = 0, total_distance_m = 0,
       total_elevation_m = 0, total_elevation_loss_m = 0,
       total_time_s = 0, total_moving_time_s = 0,
       active_days = 0, unique_pois_count = 0,
       max_elevation_m = NULL, longest_track_m = NULL, longest_track_id = NULL,
       updated_at = now()
 WHERE user_id = :uid
"""


def recompute_user_statistics(session, user_id) -> dict:
    uid = str(user_id)

    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:uid_text, 0))"),
        {"uid_text": uid},
    )

    session.execute(text(_ZERO_SQL), {"uid": uid})

    r_all = session.execute(text(_ALL_SQL), {"uid": uid})
    r_year = session.execute(text(_YEAR_SQL), {"uid": uid})
    r_month = session.execute(text(_MONTH_SQL), {"uid": uid})

    session.execute(text(_POI_ALL_SQL), {"uid": uid})
    session.execute(text(_POI_YEAR_SQL), {"uid": uid})
    session.execute(text(_POI_MONTH_SQL), {"uid": uid})

    counts = {
        "all_rows": r_all.rowcount,
        "year_rows": r_year.rowcount,
        "month_rows": r_month.rowcount,
    }
    logger.info(
        "Recomputed statistics for user %s: %s",
        uid, counts,
    )
    return counts
