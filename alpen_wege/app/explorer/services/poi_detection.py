# Standard library
import logging
from dataclasses import dataclass, field
from uuid import UUID

# Third-party
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

# Local application
from app.config import get_settings
from app.explorer.services.gpx.matching import nearest_visit
from app.explorer.services.gpx.pipeline import load_clean_segments
from app.explorer.services.gpx_storage import resolve_path

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class DetectionReport:
    status: str = "ok"
    start_poi_set: bool = False
    end_poi_set: bool = False
    visits_added: int = 0
    cards_added: int = 0
    affected_user_ids: set[UUID] = field(default_factory=set)


@dataclass
class RescanBatch:
    visits_added: int = 0
    cards_added: int = 0
    tracks_scanned: int = 0
    last_track_id: UUID | None = None
    affected_user_ids: set[UUID] = field(default_factory=set)


@dataclass
class RescanReport:
    cards_granted: int = 0
    affected_user_ids: set[UUID] = field(default_factory=set)


def detect_for_track(
    session, track_id, *, radius_m=None, require_timestamps=None,
) -> DetectionReport:
    if radius_m is None:
        radius_m = settings.POI_COLLECT_RADIUS_M
    if require_timestamps is None:
        require_timestamps = settings.POI_DETECTION_REQUIRES_TIMESTAMPS
    tolerance_m = settings.ROUTE_SIMPLIFY_TOLERANCE_M

    report = DetectionReport()

    row = session.execute(
        text(
            "SELECT t.id, t.processing_status, t.archived_at, t.recorded_at, "
            "       t.created_at, t.created_by, t.geo_record_id, t.start_poi_id, "
            "       t.end_poi_id, gpx.path "
            "  FROM explorer_agg_track t "
            "  JOIN asset_agg_gpx gpx ON gpx.id = t.gpx_id "
            " WHERE t.id = :tid"
        ),
        {"tid": str(track_id)},
    ).one_or_none()

    if row is None:
        report.status = "not_found"
        return report

    if row.archived_at is not None or row.processing_status != "ready":
        report.status = "skipped"
        return report

    owner_id = row.created_by
    geo_record_id = row.geo_record_id

    if row.start_poi_id is None:
        session.execute(
            text(
                "UPDATE explorer_agg_track t "
                "   SET start_poi_id = ("
                "       SELECT poi.id FROM compendium_cat_poi poi, "
                "              explorer_sub_geo_record g "
                "        WHERE g.id = t.geo_record_id "
                "          AND ST_DWithin(poi.location::geography, "
                "              g.start_location::geography, :r) "
                "        ORDER BY ST_Distance(poi.location::geography, "
                "              g.start_location::geography) LIMIT 1) "
                " WHERE t.id = :tid AND t.start_poi_id IS NULL"
            ),
            {"tid": str(track_id), "r": radius_m},
        )
        report.start_poi_set = True

    if row.end_poi_id is None:
        session.execute(
            text(
                "UPDATE explorer_agg_track t "
                "   SET end_poi_id = ("
                "       SELECT poi.id FROM compendium_cat_poi poi, "
                "              explorer_sub_geo_record g "
                "        WHERE g.id = t.geo_record_id "
                "          AND ST_DWithin(poi.location::geography, "
                "              g.end_location::geography, :r) "
                "        ORDER BY ST_Distance(poi.location::geography, "
                "              g.end_location::geography) LIMIT 1) "
                " WHERE t.id = :tid AND t.end_poi_id IS NULL"
            ),
            {"tid": str(track_id), "r": radius_m},
        )
        report.end_poi_set = True

    if require_timestamps and row.recorded_at is None:
        return report

    hits = session.execute(
        text(
            "SELECT poi.id, ST_X(poi.location) AS lon, ST_Y(poi.location) AS lat "
            "  FROM explorer_sub_geo_record g "
            "  JOIN compendium_cat_poi poi "
            "    ON ST_DWithin(poi.location::geography, g.route, :radius_plus) "
            "  JOIN core_ref_compendium_type ct "
            "    ON ct.id = poi.compendium_type_id AND ct.is_collectable "
            " WHERE g.id = :gid"
        ),
        {"gid": str(geo_record_id), "radius_plus": radius_m + tolerance_m},
    ).fetchall()

    if not hits:
        return report

    gpx_path = str(resolve_path(row.path))
    cleaned = load_clean_segments(gpx_path)

    visit_time_fallback = row.recorded_at or row.created_at

    verified = []
    for hit in hits:
        nv = nearest_visit(cleaned, hit.lat, hit.lon)
        if nv.distance_m <= radius_m:
            visit_time = nv.time or visit_time_fallback
            verified.append((hit.id, nv.along_track_m, visit_time))

    verified.sort(key=lambda v: v[1])

    for slot, (poi_id, along_m, visit_time) in enumerate(verified):
        r1 = session.execute(
            text(
                "INSERT INTO explorer_m2m_track_poi "
                "  (track_id, poi_id, slot_position, distance_m, created_by) "
                "VALUES (:tid, :pid, :slot, :dist, :owner) "
                "ON CONFLICT ON CONSTRAINT uq_explorer_m2m_track_poi_track_poi "
                "DO NOTHING RETURNING id"
            ),
            {
                "tid": str(track_id),
                "pid": str(poi_id),
                "slot": slot,
                "dist": int(along_m),
                "owner": str(owner_id),
            },
        )

        r2 = session.execute(
            text(
                "INSERT INTO profile_m2m_user_poi "
                "  (user_id, poi_id, track_id, collected_at) "
                "VALUES (:uid, :pid, :tid, :cat) "
                "ON CONFLICT ON CONSTRAINT uq_profile_m2m_user_poi_visit "
                "DO NOTHING RETURNING id"
            ),
            {
                "uid": str(owner_id),
                "pid": str(poi_id),
                "tid": str(track_id),
                "cat": visit_time,
            },
        )
        if r2.fetchone():
            report.visits_added += 1
            report.affected_user_ids.add(UUID(str(owner_id)))

        cr = session.execute(
            text(
                "INSERT INTO profile_m2m_user_card (user_id, card_id, collected_at, track_id) "
                "SELECT :uid, c.id, :cat, :tid "
                "  FROM compendium_cat_card c "
                " WHERE c.poi_id = :pid "
                "ON CONFLICT (user_id, card_id) DO NOTHING "
                "RETURNING id"
            ),
            {
                "uid": str(owner_id),
                "pid": str(poi_id),
                "tid": str(track_id),
                "cat": visit_time,
            },
        )
        report.cards_added += cr.rowcount

    return report


def rescan_poi_batch(
    session, poi_id, *, radius_m=None, require_timestamps=None,
    after_track_id=None, batch_size=200,
) -> RescanBatch:
    if radius_m is None:
        radius_m = settings.POI_COLLECT_RADIUS_M
    if require_timestamps is None:
        require_timestamps = settings.POI_DETECTION_REQUIRES_TIMESTAMPS
    tolerance_m = settings.ROUTE_SIMPLIFY_TOLERANCE_M

    result = RescanBatch()

    collectable = session.execute(
        text(
            "SELECT 1 FROM compendium_cat_poi p "
            "  JOIN core_ref_compendium_type t ON t.id = p.compendium_type_id "
            " WHERE p.id = :pid AND t.is_collectable"
        ),
        {"pid": str(poi_id)},
    ).one_or_none()

    if not collectable:
        return result

    params = {
        "poi_id": str(poi_id),
        "radius_plus": radius_m + tolerance_m,
        "require_ts": require_timestamps,
        "batch_size": batch_size,
    }
    after_clause = ""
    if after_track_id:
        after_clause = "AND t.id > :after_tid"
        params["after_tid"] = str(after_track_id)

    tracks = session.execute(
        text(
            f"SELECT t.id AS track_id, t.created_by, t.recorded_at, t.created_at, gpx.path "
            f"  FROM compendium_cat_poi poi "
            f"  JOIN explorer_sub_geo_record g "
            f"    ON ST_DWithin(g.route, poi.location::geography, :radius_plus) "
            f"  JOIN explorer_agg_track t ON t.geo_record_id = g.id "
            f"  JOIN asset_agg_gpx gpx ON gpx.id = t.gpx_id "
            f" WHERE poi.id = :poi_id AND t.archived_at IS NULL "
            f"   AND t.processing_status = 'ready' "
            f"   AND (t.recorded_at IS NOT NULL OR NOT :require_ts) "
            f"   {after_clause} "
            f" ORDER BY t.id LIMIT :batch_size"
        ),
        params,
    ).fetchall()

    poi_row = session.execute(
        text("SELECT ST_X(location) AS lon, ST_Y(location) AS lat FROM compendium_cat_poi WHERE id = :pid"),
        {"pid": str(poi_id)},
    ).one()

    for track in tracks:
        result.tracks_scanned += 1
        result.last_track_id = track.track_id

        gpx_path = str(resolve_path(track.path))
        cleaned = load_clean_segments(gpx_path)
        nv = nearest_visit(cleaned, poi_row.lat, poi_row.lon)
        if nv.distance_m > radius_m:
            continue

        visit_time = nv.time or track.recorded_at or track.created_at
        owner_id = track.created_by

        session.execute(
            text(
                "INSERT INTO explorer_m2m_track_poi "
                "  (track_id, poi_id, slot_position, distance_m, created_by) "
                "VALUES (:tid, :pid, "
                "  coalesce((SELECT max(slot_position) + 1 FROM explorer_m2m_track_poi "
                "    WHERE track_id = :tid), 0), "
                "  :dist, :owner) "
                "ON CONFLICT ON CONSTRAINT uq_explorer_m2m_track_poi_track_poi "
                "DO NOTHING"
            ),
            {
                "tid": str(track.track_id),
                "pid": str(poi_id),
                "dist": int(nv.along_track_m),
                "owner": str(owner_id),
            },
        )

        r2 = session.execute(
            text(
                "INSERT INTO profile_m2m_user_poi "
                "  (user_id, poi_id, track_id, collected_at) "
                "VALUES (:uid, :pid, :tid, :cat) "
                "ON CONFLICT ON CONSTRAINT uq_profile_m2m_user_poi_visit "
                "DO NOTHING RETURNING id"
            ),
            {
                "uid": str(owner_id),
                "pid": str(poi_id),
                "tid": str(track.track_id),
                "cat": visit_time,
            },
        )
        if r2.fetchone():
            result.visits_added += 1
            result.affected_user_ids.add(UUID(str(owner_id)))

        cr = session.execute(
            text(
                "INSERT INTO profile_m2m_user_card (user_id, card_id, collected_at, track_id) "
                "SELECT :uid, c.id, :cat, :tid "
                "  FROM compendium_cat_card c "
                " WHERE c.poi_id = :pid "
                "ON CONFLICT (user_id, card_id) DO NOTHING "
                "RETURNING id"
            ),
            {
                "uid": str(owner_id),
                "pid": str(poi_id),
                "tid": str(track.track_id),
                "cat": visit_time,
            },
        )
        result.cards_added += cr.rowcount

    if not tracks:
        result.last_track_id = None

    return result


def rescan_card(session, card_id) -> RescanReport:
    report = RescanReport()

    cr = session.execute(
        text(
            "INSERT INTO profile_m2m_user_card (user_id, card_id, collected_at, track_id) "
            "SELECT DISTINCT ON (v.user_id) v.user_id, c.id, v.collected_at, v.track_id "
            "  FROM compendium_cat_card c "
            "  JOIN compendium_cat_poi p ON p.id = c.poi_id "
            "  JOIN core_ref_compendium_type t ON t.id = p.compendium_type_id AND t.is_collectable "
            "  JOIN profile_m2m_user_poi v ON v.poi_id = c.poi_id "
            " WHERE c.id = :card_id "
            " ORDER BY v.user_id, v.collected_at ASC "
            "ON CONFLICT (user_id, card_id) DO NOTHING "
            "RETURNING user_id"
        ),
        {"card_id": str(card_id)},
    )

    for row in cr:
        report.cards_granted += 1
        report.affected_user_ids.add(UUID(str(row.user_id)))

    return report
