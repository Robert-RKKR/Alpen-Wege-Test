#!/usr/bin/env python3
"""
Initialize the database with users, resource types, and access policies.

Run inside the API container:
    sudo docker exec alpen-api python /app/scripts/init_seed.py

Or locally (requires psycopg2 and bcrypt):
    python scripts/init_seed.py

Idempotent: safe to re-run. Existing users are skipped, resource types use
ON CONFLICT, and access policies are rebuilt from scratch each run.
"""
import os
import sys
import uuid

import bcrypt
import psycopg2

_DEFAULT_DSN = "dbname=alpenwege user=alpenwege password=alpenwege host=localhost port=5433"
_DOCKER_DSN = "dbname=alpenwege user=alpenwege password=alpenwege host=postgres port=5432"

DB_DSN = os.environ.get("SEED_DB_DSN")
if not DB_DSN:
    DB_DSN = _DOCKER_DSN if os.environ.get("DATABASE_URL_SYNC") else _DEFAULT_DSN

PASSWORD = "!Password@5005"

USERS = [
    {
        "email": "admin@alpenwege.dev",
        "username": "admin",
        "first_name": "Admin",
        "last_name": "User",
        "group": "administrator",
    },
    {
        "email": "editor@alpenwege.dev",
        "username": "editor",
        "first_name": "Editor",
        "last_name": "User",
        "group": "editor",
    },
    {
        "email": "viewer@alpenwege.dev",
        "username": "viewer",
        "first_name": "Viewer",
        "last_name": "User",
        "group": "viewer",
    },
    {
        "email": "guest@alpenwege.dev",
        "username": "guest",
        "first_name": "Guest",
        "last_name": "User",
        "group": "guest",
    },
]

RESOURCE_TYPES = [
    ("gear", "Gear", "#4CAF50", "backpack"),
    ("journey", "Journey", "#2196F3", "map"),
    ("route", "Route", "#FF9800", "route"),
    ("segment", "Segment", "#9C27B0", "timeline"),
    ("track", "Track", "#F44336", "satellite"),
    ("trip", "Trip", "#00BCD4", "flight"),
    ("poi", "Point of Interest", "#E91E63", "place"),
    ("country", "Country", "#3F51B5", "flag"),
    ("region", "Region", "#009688", "terrain"),
    ("card", "Card", "#FF5722", "style"),
    ("post", "Post", "#795548", "article"),
    ("poi_region", "POI Region", "#607D8B", "link"),
    ("photo", "Photo", "#8BC34A", "photo_camera"),
    ("gpx", "GPX", "#CDDC39", "gps_fixed"),
    ("achievement", "Achievement", "#FFC107", "emoji_events"),
    ("ref", "Reference Data", "#9E9E9E", "list"),
]

EXPLORER_KEYS = {"gear", "journey", "route", "segment", "track", "trip"}
COMPENDIUM_KEYS = {"poi", "country", "region", "card", "post", "poi_region"}
ASSET_KEYS = {"photo", "gpx"}
ACHIEVEMENT_KEYS = {"achievement"}
REF_KEYS = {"ref"}

ALL_KEYS = EXPLORER_KEYS | COMPENDIUM_KEYS | ASSET_KEYS | ACHIEVEMENT_KEYS | REF_KEYS

ACTIONS = ["create", "read", "update", "delete"]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def migrate_constraints(cur):
    """Drop old CHECK constraints and create new ones with updated group values."""
    OLD_TO_NEW = {"admin": "administrator", "user": "viewer"}

    for table, constraint in [
        ("profile_user_credentials", "ck_profile_user_credentials_user_group"),
        ("profile_access_policy", "ck_profile_access_policy_user_group"),
    ]:
        cur.execute(
            "SELECT 1 FROM information_schema.table_constraints "
            "WHERE constraint_name = %s AND table_name = %s",
            (constraint, table),
        )
        if cur.fetchone():
            cur.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
            for old_val, new_val in OLD_TO_NEW.items():
                cur.execute(
                    f"UPDATE {table} SET user_group = %s WHERE user_group = %s",
                    (new_val, old_val),
                )
            cur.execute(
                f"ALTER TABLE {table} ADD CONSTRAINT {constraint} "
                f"CHECK (user_group IN ('administrator', 'viewer', 'guest', 'editor'))"
            )
            print(f"  Migrated {constraint}")
        else:
            print(f"  {constraint}: already migrated or not found")

    cur.connection.commit()


def ensure_user(cur, email, username, first_name, last_name, group, pw_hash):
    """Create a user + credentials if the email doesn't already exist. Returns user id."""
    cur.execute(
        "SELECT id FROM profile_usr_user WHERE email = %s", (email,)
    )
    row = cur.fetchone()
    if row:
        user_id = row[0]
        cur.execute(
            "UPDATE profile_user_credentials SET user_group = %s WHERE user_id = %s",
            (group, user_id),
        )
        print(f"  {email}: exists (id={user_id}), group updated to '{group}'")
        return user_id

    user_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO profile_usr_user (id, email, username, first_name, last_name) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, email, username, first_name, last_name),
    )
    cur.execute(
        "INSERT INTO profile_user_credentials (user_id, password_hash, user_group) "
        "VALUES (%s, %s, %s)",
        (user_id, pw_hash, group),
    )
    print(f"  {email}: created (group='{group}')")
    return user_id


def seed_resource_types(cur, admin_id):
    """Insert resource types, skipping existing keys."""
    inserted = 0
    for key, name, color, icon in RESOURCE_TYPES:
        cur.execute(
            "INSERT INTO core_ref_resource_type (id, key, name, color, icon, created_by) "
            "VALUES (%s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (key) DO NOTHING",
            (str(uuid.uuid4()), key, name, color, icon, admin_id),
        )
        if cur.rowcount > 0:
            inserted += 1
    cur.connection.commit()
    print(f"  {inserted} new resource types inserted ({len(RESOURCE_TYPES)} total defined)")


def build_policies():
    """Build the full access policy matrix."""
    policies = []

    def add(group, keys, actions_scopes):
        for key in keys:
            for action, scope in actions_scopes:
                policies.append((group, key, action, scope))

    # Administrator: full access on everything
    add("administrator", ALL_KEYS, [(a, "all") for a in ACTIONS])

    # Guest: read-only
    add("guest", EXPLORER_KEYS | ASSET_KEYS | ACHIEVEMENT_KEYS, [("read", "public")])
    add("guest", COMPENDIUM_KEYS | REF_KEYS, [("read", "all")])

    # Viewer: Guest + own CRUD on explorer/asset/achievement
    add("viewer", EXPLORER_KEYS | ASSET_KEYS | ACHIEVEMENT_KEYS, [
        ("create", "own"), ("read", "public"), ("update", "own"), ("delete", "own"),
    ])
    add("viewer", COMPENDIUM_KEYS | REF_KEYS, [("read", "all")])

    # Editor: Viewer + own CRUD on compendium
    add("editor", EXPLORER_KEYS | ASSET_KEYS | ACHIEVEMENT_KEYS, [
        ("create", "own"), ("read", "public"), ("update", "own"), ("delete", "own"),
    ])
    add("editor", COMPENDIUM_KEYS, [
        ("create", "own"), ("read", "all"), ("update", "own"), ("delete", "own"),
    ])
    add("editor", REF_KEYS, [("read", "all")])

    return policies


def seed_access_policies(cur):
    """Rebuild the full access policy matrix from scratch."""
    cur.execute("DELETE FROM profile_access_policy")
    deleted = cur.rowcount
    if deleted:
        print(f"  Cleared {deleted} existing policy rows")

    cur.execute("SELECT id, key FROM core_ref_resource_type")
    key_to_id = {row[1]: row[0] for row in cur.fetchall()}

    policies = build_policies()
    inserted = 0
    errors = []
    for group, key, action, scope in policies:
        rt_id = key_to_id.get(key)
        if not rt_id:
            errors.append(f"Resource type '{key}' not found in DB")
            continue
        cur.execute(
            "INSERT INTO profile_access_policy (id, user_group, resource_type_id, action, scope) "
            "VALUES (%s, %s, %s, %s, %s)",
            (str(uuid.uuid4()), group, rt_id, action, scope),
        )
        inserted += 1

    cur.connection.commit()
    print(f"  {inserted} policy rows inserted")
    for e in errors:
        print(f"    ERROR: {e}")


def main():
    print("Connecting to PostgreSQL ...")
    try:
        conn = psycopg2.connect(DB_DSN)
    except psycopg2.OperationalError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    cur = conn.cursor()

    print("\n1) Migrate user_group CHECK constraints")
    migrate_constraints(cur)

    print("\n2) Create users")
    pw_hash = hash_password(PASSWORD)
    admin_id = None
    for u in USERS:
        uid = ensure_user(
            cur, u["email"], u["username"], u["first_name"], u["last_name"],
            u["group"], pw_hash,
        )
        if u["group"] == "administrator":
            admin_id = uid
    conn.commit()

    print("\n3) Seed resource types")
    seed_resource_types(cur, admin_id)

    print("\n4) Seed access policies")
    seed_access_policies(cur)

    cur.close()
    conn.close()
    print("\nDone!")
    print(f"\nLogin credentials (all users): password = {PASSWORD}")
    for u in USERS:
        print(f"  {u['email']} ({u['group']})")


if __name__ == "__main__":
    main()
