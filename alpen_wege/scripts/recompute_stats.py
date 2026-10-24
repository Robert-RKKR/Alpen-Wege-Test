#!/usr/bin/env python
"""Recompute user statistics directly (no Celery).

Usage:
    python scripts/recompute_stats.py --user-id <uuid>
    python scripts/recompute_stats.py --all
"""
import argparse
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

sys.path.insert(0, ".")

from app.database import SyncSessionLocal  # noqa: E402
from app.explorer.services.track_statistics import recompute_user_statistics  # noqa: E402
from sqlalchemy import text  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Recompute user statistics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--user-id", help="UUID of a single user")
    group.add_argument("--all", action="store_true", help="Recompute for all users")
    args = parser.parse_args()

    if args.user_id:
        user_ids = [args.user_id]
    else:
        with SyncSessionLocal() as session:
            rows = session.execute(
                text("SELECT DISTINCT id FROM profile_usr_user ORDER BY id")
            ).fetchall()
        user_ids = [str(r[0]) for r in rows]
        logger.info("Found %d users", len(user_ids))

    total = 0
    for uid in user_ids:
        with SyncSessionLocal() as session:
            counts = recompute_user_statistics(session, uid)
            session.commit()
        logger.info("User %s: %s", uid, counts)
        total += 1

    logger.info("Done. Recomputed statistics for %d user(s).", total)


if __name__ == "__main__":
    main()
