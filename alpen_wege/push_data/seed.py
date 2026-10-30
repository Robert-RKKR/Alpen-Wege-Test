#!/usr/bin/env python3
"""
Seed the database from CSV files in push_data/.

Run inside the API container:
    sudo docker exec alpen-api python /app/push_data/seed.py

Creates a seed user, then loads all 22 CSV files in FK-dependency order.
The core_ref_* files name their icon by id, so the icons must be loaded first (scripts/seed_icons.py --csv).
Handles WKB hex geometry, title→name column rename, and bbox JSON arrays.
Idempotent: re-running skips already-inserted rows via ON CONFLICT.
"""
import csv
import json
import struct
import sys
from pathlib import Path

import bcrypt
import psycopg2

import os

DB_DSN = os.environ.get(
    "SEED_DB_DSN",
    "dbname=alpenwege user=alpenwege password=alpenwege host=localhost port=5433",
)
SEED_USER_ID = "3cd01bcd-4b7a-43dc-9cf6-e709815783cc"
SEED_EMAIL = "seed@alpenwege.dev"
SEED_USERNAME = "seed_admin"
SEED_PASSWORD = "SeedPass123!"
DATA_DIR = Path(__file__).parent

LOAD_ORDER = [
    "core_ref_sport_type",
    "core_ref_achievement_category",
    "core_ref_achievement_scope",
    "core_ref_achievement_type",
    "core_ref_company",
    "core_ref_compendium_type",
    "core_ref_difficulty_level",
    "core_ref_gear_type",
    "core_ref_point_reason",
    "core_ref_post_type",
    "core_ref_rarity",
    "core_ref_region_type",
    "core_ref_schedule_status",
    "core_ref_snow_condition",
    "core_ref_trail_condition",
    "core_ref_visibility",
    "core_ref_waypoint_type",
    "core_ref_weather_condition",
    "core_ref_difficulty_sport",
    "compendium_cat_country",
    "compendium_cat_region",
    "compendium_cat_poi",
]

TITLE_TO_NAME = {
    "compendium_cat_country",
    "compendium_cat_region",
    "compendium_cat_poi",
}


def wkb_hex_to_ewkt(hex_str):
    raw = bytes.fromhex(hex_str)
    bo = "<" if raw[0] == 1 else ">"
    wkb_type = struct.unpack(f"{bo}I", raw[1:5])[0]
    has_srid = bool(wkb_type & 0x20000000)
    geom_type = wkb_type & 0xFF
    offset = 5
    srid = 4326
    if has_srid:
        srid = struct.unpack(f"{bo}I", raw[5:9])[0]
        offset = 9
    if geom_type == 1:
        x, y = struct.unpack(f"{bo}dd", raw[offset : offset + 16])
        return f"SRID={srid};POINT({x} {y})"
    raise ValueError(f"Unsupported WKB geometry type {geom_type}")


def bbox_to_ewkt(bbox_json):
    a = json.loads(bbox_json)
    return (
        f"SRID=4326;POLYGON(({a[0]} {a[1]},{a[2]} {a[1]},"
        f"{a[2]} {a[3]},{a[0]} {a[3]},{a[0]} {a[1]}))"
    )


def get_col_info(cur, table):
    cur.execute(
        "SELECT column_name, data_type, udt_name"
        " FROM information_schema.columns WHERE table_name = %s",
        (table,),
    )
    return {
        name: ("array" if dt == "ARRAY" else "geo" if udt == "geometry" else "scalar")
        for name, dt, udt in cur.fetchall()
    }


def coerce_val(raw, kind):
    if raw is None or raw.strip() == "":
        return None
    raw = raw.strip()
    if kind == "geo":
        if raw.startswith("["):
            return bbox_to_ewkt(raw)
        if raw.upper().startswith(("POINT", "POLYGON", "SRID")):
            return raw
        return wkb_hex_to_ewkt(raw)
    if kind == "array":
        if raw.startswith("["):
            return json.loads(raw)
        return [v.strip() for v in raw.split("|") if v.strip()]
    return raw


def ensure_seed_user(cur):
    cur.execute("SELECT 1 FROM profile_usr_user WHERE id = %s", (SEED_USER_ID,))
    if cur.fetchone():
        print("  Seed user already exists")
    else:
        cur.execute(
            "INSERT INTO profile_usr_user"
            " (id, email, username, first_name, last_name)"
            " VALUES (%s, %s, %s, %s, %s)",
            (SEED_USER_ID, SEED_EMAIL, SEED_USERNAME, "Seed", "Admin"),
        )
        pw_hash = bcrypt.hashpw(SEED_PASSWORD.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO profile_user_credentials"
            " (user_id, password_hash, user_group)"
            " VALUES (%s, %s, 'administrator')",
            (SEED_USER_ID, pw_hash),
        )
        print(f"  Created seed user: {SEED_EMAIL} / {SEED_PASSWORD}")
    cur.connection.commit()


def _flush_batch(cur, sql, batch_rows):
    inserted = 0
    errors = []
    for row_no, vals in batch_rows:
        try:
            cur.execute("SAVEPOINT sp")
            cur.execute(sql, vals)
            inserted += 1
        except Exception as e:
            err_msg = str(e).split("\n")[0]
            errors.append(f"row {row_no}: {err_msg}")
            cur.execute("ROLLBACK TO SAVEPOINT sp")
    cur.connection.commit()
    return inserted, errors


def load_table(cur, table):
    csv_path = DATA_DIR / f"{table}.csv"
    if not csv_path.exists():
        print(f"  {table}: no CSV — skip")
        return

    col_info = get_col_info(cur, table)
    if not col_info:
        print(f"  {table}: table missing in DB — skip")
        return

    rename = table in TITLE_TO_NAME

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        mapping = []
        for h in reader.fieldnames:
            db = "name" if (rename and h == "title") else h
            if db in col_info:
                mapping.append((h, db))

        db_cols = [m[1] for m in mapping]
        placeholders = ", ".join(
            "ST_GeomFromEWKT(%s)" if col_info[c] == "geo" else "%s" for c in db_cols
        )
        sql = (
            f"INSERT INTO {table} ({', '.join(db_cols)})"
            f" VALUES ({placeholders})"
            f" ON CONFLICT (id) DO NOTHING"
        )

        BATCH = 500
        inserted = 0
        errors = []
        batch_rows = []
        for row_no, row in enumerate(reader, 2):
            vals = [coerce_val(row.get(h), col_info[db]) for h, db in mapping]
            batch_rows.append((row_no, vals))
            if len(batch_rows) >= BATCH:
                ins, errs = _flush_batch(cur, sql, batch_rows)
                inserted += ins
                errors.extend(errs)
                batch_rows = []
        if batch_rows:
            ins, errs = _flush_batch(cur, sql, batch_rows)
            inserted += ins
            errors.extend(errs)
    msg = f"  {table}: {inserted} inserted"
    if errors:
        msg += f", {len(errors)} errors"
    print(msg)
    for e in errors[:5]:
        print(f"    {e}")
    if len(errors) > 5:
        print(f"    ... +{len(errors) - 5} more")


def require_icons(cur):
    # the core_ref_* rows name their icon by id (icon_id is required); without the icons every row would be refused
    cur.execute("SELECT count(*) FROM asset_agg_icon")
    if cur.fetchone()[0] == 0:
        print("ERROR: asset_agg_icon is empty. Load the icons first:")
        print("  python scripts/seed_icons.py --csv Routing/icons_import/icons_import.csv")
        sys.exit(1)


def main():
    print("Connecting to PostgreSQL ...")
    try:
        conn = psycopg2.connect(DB_DSN)
    except psycopg2.OperationalError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    cur = conn.cursor()
    require_icons(cur)

    print("\n1) Seed user")
    ensure_seed_user(cur)

    print(f"\n2) Loading {len(LOAD_ORDER)} tables ...")
    for t in LOAD_ORDER:
        load_table(cur, t)

    print("\n3) Marking transport and parking types as non-collectable ...")
    non_collectable = (
        "Bus Stop", "Train Station", "Tram", "Cable Car Station",
        "Gondola Station", "Chair Lift", "Funicular Station", "Rack Railway",
        "Mountain Railway", "Ferry Crossing", "Multi transport station",
        "Multi transport station (Bus/Cable Car)",
        "Multi transport station (Tram/Bus)", "Parking", "Lake Harbor",
        "Helipad",
    )
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name = 'core_ref_compendium_type' AND column_name = 'is_collectable'"
    )
    if cur.fetchone():
        placeholders = ", ".join(["%s"] * len(non_collectable))
        cur.execute(
            f"UPDATE core_ref_compendium_type SET is_collectable = false "
            f"WHERE name IN ({placeholders})",
            non_collectable,
        )
        conn.commit()
        print(f"  Set {cur.rowcount} types to non-collectable")
    else:
        print("  is_collectable column not present yet — skipped")

    cur.close()
    conn.close()
    print("\nDone!")
    print(f"\nLogin credentials: {SEED_EMAIL} / {SEED_PASSWORD}")


if __name__ == "__main__":
    main()
