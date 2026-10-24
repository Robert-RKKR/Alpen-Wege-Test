#!/usr/bin/env python
"""Rescan POIs / cards against existing tracks.

Usage:
    python scripts/rescan_pois.py --poi-id <uuid>             # dry run
    python scripts/rescan_pois.py --poi-id <uuid> --apply     # commit
    python scripts/rescan_pois.py --card-id <uuid> --apply
    python scripts/rescan_pois.py --all --apply
    python scripts/rescan_pois.py --all --radius 75           # custom radius
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402
from app.database import SyncSessionLocal  # noqa: E402
from app.explorer.services.poi_detection import (  # noqa: E402
    rescan_card,
    rescan_poi_batch,
)


def main():
    parser = argparse.ArgumentParser(description="Rescan POIs against tracks")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--poi-id", help="UUID of a single POI")
    group.add_argument("--card-id", help="UUID of a single card")
    group.add_argument("--all", action="store_true", help="All collectable POIs")
    parser.add_argument("--apply", action="store_true", help="Commit (default is dry run)")
    parser.add_argument("--radius", type=float, default=None, help="Override POI_COLLECT_RADIUS_M")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    if args.card_id:
        _do_card(args.card_id, apply=args.apply)
    elif args.poi_id:
        _do_poi(args.poi_id, apply=args.apply, radius=args.radius, batch_size=args.batch_size)
    else:
        _do_all(apply=args.apply, radius=args.radius, batch_size=args.batch_size)


def _do_card(card_id: str, *, apply: bool):
    with SyncSessionLocal() as session:
        report = rescan_card(session, card_id)
        if apply:
            session.commit()
            logger.info("Applied: granted %d cards to %d users", report.cards_granted, len(report.affected_user_ids))
        else:
            session.rollback()
            logger.info("Dry run: would grant %d cards to %d users", report.cards_granted, len(report.affected_user_ids))


def _do_poi(poi_id: str, *, apply: bool, radius, batch_size: int):
    total_visits = 0
    total_cards = 0
    total_tracks = 0
    after = None

    while True:
        with SyncSessionLocal() as session:
            batch = rescan_poi_batch(
                session, poi_id,
                radius_m=radius,
                after_track_id=after,
                batch_size=batch_size,
            )
            if apply:
                session.commit()
            else:
                session.rollback()

        total_visits += batch.visits_added
        total_cards += batch.cards_added
        total_tracks += batch.tracks_scanned

        if batch.last_track_id is None:
            break
        after = batch.last_track_id

    verb = "Added" if apply else "Would add"
    logger.info(
        "%s %d visits and %d cards across %d tracks",
        verb, total_visits, total_cards, total_tracks,
    )


def _do_all(*, apply: bool, radius, batch_size: int):
    with SyncSessionLocal() as session:
        rows = session.execute(
            text(
                "SELECT p.id FROM compendium_cat_poi p "
                "  JOIN core_ref_compendium_type t ON t.id = p.compendium_type_id "
                " WHERE t.is_collectable ORDER BY p.id"
            )
        ).fetchall()

    logger.info("Found %d collectable POIs", len(rows))
    grand_visits = 0
    grand_cards = 0
    grand_tracks = 0

    for i, (poi_id,) in enumerate(rows, 1):
        total_visits = 0
        total_cards = 0
        total_tracks = 0
        after = None

        while True:
            with SyncSessionLocal() as session:
                batch = rescan_poi_batch(
                    session, poi_id,
                    radius_m=radius,
                    after_track_id=after,
                    batch_size=batch_size,
                )
                if apply:
                    session.commit()
                else:
                    session.rollback()

            total_visits += batch.visits_added
            total_cards += batch.cards_added
            total_tracks += batch.tracks_scanned

            if batch.last_track_id is None:
                break
            after = batch.last_track_id

        grand_visits += total_visits
        grand_cards += total_cards
        grand_tracks += total_tracks

        if total_visits or total_cards:
            logger.info(
                "  [%d/%d] POI %s: visits=%d cards=%d tracks=%d",
                i, len(rows), poi_id, total_visits, total_cards, total_tracks,
            )

    verb = "Added" if apply else "Would add"
    logger.info(
        "%s %d visits and %d cards across %d tracks for %d POIs",
        verb, grand_visits, grand_cards, grand_tracks, len(rows),
    )


if __name__ == "__main__":
    main()
