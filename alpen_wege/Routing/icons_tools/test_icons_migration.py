"""End-to-end test of the icons step 1 migration (the repo's scripts/sql/icons_*.sql and scripts/seed_icons.py) on a real
PostgreSQL with the REAL seed data (push_data/*.csv: 643 reference rows, 250 countries, 1,570 regions) and the REAL flag files.

The "old live database" is rebuilt from the CSV files with the columns that matter here (stub tables, no PostGIS columns).
Tests run in file order and share one throw-away database that the fixture creates and drops.

Run (needs psycopg2, pytest, and the packages of requirements.txt because seed_icons.py imports the app):
    MIG_PG_URI=postgresql://postgres@localhost:5433/postgres MIG_PG_BIN=/path/to/postgres/bin ALPEN_DIR=/path/to/alpen_wege \
    python -m pytest test_icons_migration.py -q -p no:cacheprovider
The server must have the moddatetime extension (every Postgres image of this project has it).
"""
import contextlib
import csv
import glob
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras
import psycopg2.errors
import pytest

psycopg2.extras.register_uuid()

ALPEN = Path(os.environ.get("ALPEN_DIR", "."))
HERE = ALPEN / "scripts" / "sql"          # the SQL scripts live here
PUSH = ALPEN / "push_data"
FLAGS = ALPEN / "app/compendium/cards/flags"
BIN = Path(os.environ["MIG_PG_BIN"])
SERVER_URI = os.environ["MIG_PG_URI"]

REF_TABLES = [
    "core_ref_resource_type", "core_ref_achievement_category", "core_ref_achievement_scope", "core_ref_achievement_type",
    "core_ref_company", "core_ref_compendium_type", "core_ref_difficulty_level", "core_ref_difficulty_sport",
    "core_ref_gear_type", "core_ref_point_reason", "core_ref_post_type", "core_ref_rarity", "core_ref_region_type",
    "core_ref_schedule_status", "core_ref_snow_condition", "core_ref_sport_type", "core_ref_trail_condition",
    "core_ref_visibility", "core_ref_waypoint_type", "core_ref_weather_condition",
]
ALL22 = REF_TABLES + ["compendium_cat_country", "compendium_cat_region"]
RESOURCE_TYPES = [("gear", "backpack"), ("journey", "map"), ("route", "route"), ("segment", "timeline"), ("track", "satellite"),
                  ("trip", "flight"), ("poi", "place"), ("country", "flag"), ("region", "terrain"), ("card", "style"),
                  ("post", "article"), ("poi_region", "link"), ("photo", "photo_camera"), ("gpx", "gps_fixed"),
                  ("achievement", "emoji_events"), ("ref", "list")]


class _Server:
    def __init__(self, uri):
        self._uri = uri

    def get_uri(self):
        return self._uri


@pytest.fixture(scope="module")
def pg():
    name = "icons_migration_test"
    admin = psycopg2.connect(SERVER_URI)
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name}")
        cur.execute(f"CREATE DATABASE {name}")
    uri = re.sub(r"/[^/?]*(\?|$)", rf"/{name}\1", SERVER_URI, count=1)
    yield _Server(uri)
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {name} WITH (FORCE)")
    admin.close()


def conn(pg):
    c = psycopg2.connect(pg.get_uri())
    c.autocommit = True
    return c


@contextlib.contextmanager
def cursor(pg):
    # one autocommit connection per block; closed explicitly (psycopg2's "with connection" would wrap a transaction)
    c = conn(pg)
    try:
        with c.cursor() as cur:
            yield cur
    finally:
        c.close()


def sql_file(pg, name, check=True):
    r = subprocess.run([str(BIN / "psql"), pg.get_uri(), "-X", "-f", str(HERE / name)], capture_output=True, text=True)
    if check:
        assert r.returncode == 0, r.stderr
    return r


def one(pg, q, args=None):
    with cursor(pg) as cur:
        cur.execute(q, args)
        return cur.fetchone()[0]


def dump_schema(pg):
    out = subprocess.check_output([str(BIN / "pg_dump"), "-s", "--no-owner", pg.get_uri()], text=True)
    return "\n".join(l for l in out.splitlines() if not l.startswith(("--", "SET ", "\\restrict", "\\unrestrict")) and l.strip())


# ------------------------------------------------------------------------------ the old live database
def test_00_build_old_database(pg):
    c = conn(pg)
    cur = c.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS moddatetime")
    cur.execute("CREATE TABLE profile_usr_user (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email text UNIQUE NOT NULL)")
    admin = uuid.uuid4()
    cur.execute("INSERT INTO profile_usr_user (id, email) VALUES (%s, 'admin@alpenwege.dev')", (admin,))
    base = ("id uuid PRIMARY KEY DEFAULT gen_random_uuid(), created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), created_by uuid NOT NULL REFERENCES profile_usr_user (id), "
            "name text, name_de text, name_pl text, color text NOT NULL, icon text NOT NULL")
    n = 0
    for t in REF_TABLES:
        cur.execute(f"CREATE TABLE {t} ({base})")
        if t == "core_ref_resource_type":
            rows = [(str(uuid.uuid4()), admin, k, "#9E9E9E", i) for k, i in RESOURCE_TYPES]
        else:
            with open(PUSH / f"{t}.csv", encoding="utf-8-sig") as f:
                rows = [(r["id"], admin, r["name"], r["color"], r["icon"]) for r in csv.DictReader(f)]
        for r in rows:
            cur.execute(f"INSERT INTO {t} (id, created_by, name, color, icon) VALUES (%s, %s, %s, %s, %s)", r)
        n += len(rows)
    assert n == 643 + len(RESOURCE_TYPES), n

    cur.execute(f"CREATE TABLE compendium_cat_country ({base.replace('name text,', 'name text UNIQUE,').replace('color text NOT NULL, icon text NOT NULL', 'iso_code text NOT NULL UNIQUE')})")
    with open(PUSH / "compendium_cat_country.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cur.execute("INSERT INTO compendium_cat_country (id, created_by, name, iso_code) VALUES (%s, %s, %s, %s)",
                        (r["id"], admin, r["title"], r["iso_code"]))
    cur.execute(f"CREATE TABLE compendium_cat_region ({base.replace('color text NOT NULL, icon text NOT NULL', 'iso_code text, country_id uuid NOT NULL REFERENCES compendium_cat_country (id)')})")
    with open(PUSH / "compendium_cat_region.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            cur.execute("INSERT INTO compendium_cat_region (id, created_by, name, iso_code, country_id) VALUES (%s, %s, %s, %s, %s)",
                        (r["id"], admin, r["title"], r["iso_code"], r["country_id"]))
    assert one(pg, "SELECT count(*) FROM compendium_cat_country") == 250
    assert one(pg, "SELECT count(*) FROM compendium_cat_region") == 1570


def test_01_preflight_finds_no_problem(pg):
    r = sql_file(pg, "icons_preflight.sql")
    assert "PROBLEM" not in r.stdout, r.stdout
    assert "NOTE    icon texts that differ only in case: Ship / ship" in r.stdout, r.stdout     # a real finding in the seed data
    assert r.stdout.count("OK      table exists") == 22
    assert "distinct icon texts in the 20 reference tables" in r.stdout


def test_02_preflight_detects_problems(pg):
    c = conn(pg)
    cur = c.cursor()
    cur.execute("INSERT INTO core_ref_rarity (created_by, name, color, icon) SELECT id, 'bad', '#000000', 'has space!' FROM profile_usr_user")
    r = sql_file(pg, "icons_preflight.sql")
    assert "PROBLEM icon text is not a valid key: core_ref_rarity / has space!" in r.stdout
    cur.execute("DELETE FROM core_ref_rarity WHERE icon = 'has space!'")


# ------------------------------------------------------------------------------ step 1 DDL
def test_03_ddl_creates_everything(pg):
    before = {t: one(pg, f"SELECT md5(string_agg(id::text || icon, ',' ORDER BY id)) FROM {t}") for t in REF_TABLES}
    sql_file(pg, "icons_ddl.sql")
    assert one(pg, "SELECT count(*) FROM asset_agg_icon") == 0
    with cursor(pg) as cur:
        cur.execute("SELECT table_name FROM information_schema.columns WHERE column_name = 'icon_id' AND data_type = 'uuid'")
        assert sorted(r[0] for r in cur.fetchall()) == sorted(ALL22)
        cur.execute("""SELECT conrelid::regclass::text, confdeltype FROM pg_constraint
                        WHERE contype = 'f' AND confrelid = 'asset_agg_icon'::regclass AND conrelid <> 'asset_agg_icon'::regclass""")
        fks = cur.fetchall()
        assert len(fks) == 22 and all(d == "r" for _, d in fks), fks          # r = RESTRICT
        cur.execute("""SELECT count(*) FROM pg_indexes WHERE indexname LIKE 'ix\\_%\\_icon\\_id' ESCAPE '\\'""")
        assert cur.fetchone()[0] == 22
        cur.execute("SELECT conname FROM pg_constraint WHERE conrelid = 'asset_agg_icon'::regclass AND contype = 'f'")
        assert [r[0] for r in cur.fetchall()] == ["asset_agg_icon_created_by_fkey"]
    # the old text column and its data are untouched
    after = {t: one(pg, f"SELECT md5(string_agg(id::text || icon, ',' ORDER BY id)) FROM {t}") for t in REF_TABLES}
    assert before == after
    # every new column carries a comment
    assert one(pg, """SELECT count(*) FROM pg_description d JOIN pg_attribute a ON a.attrelid = d.objoid AND a.attnum = d.objsubid
                       WHERE a.attname = 'icon_id' AND d.description LIKE 'FK to asset_agg_icon%'""") == 22


def test_04_ddl_is_idempotent(pg):
    first = dump_schema(pg)
    sql_file(pg, "icons_ddl.sql")
    assert dump_schema(pg) == first


def test_05_old_application_code_still_works(pg):
    # the previous version knows no icon_id: its INSERTs and UPDATEs must keep working
    with cursor(pg) as cur:
        cur.execute("INSERT INTO core_ref_rarity (created_by, name, color, icon) SELECT id, 'old app', '#111111', 'rarity_old' FROM profile_usr_user")
        cur.execute("UPDATE core_ref_rarity SET color = '#222222' WHERE name = 'old app'")
        cur.execute("INSERT INTO compendium_cat_country (created_by, name, iso_code) SELECT id, 'Oldland', 'ZZ' FROM profile_usr_user")
        cur.execute("DELETE FROM core_ref_rarity WHERE name = 'old app'")
        cur.execute("DELETE FROM compendium_cat_country WHERE iso_code = 'ZZ'")


def test_06_table_rules(pg):
    admin = one(pg, "SELECT id FROM profile_usr_user")
    ins = "INSERT INTO asset_agg_icon (created_by, name, key, svg, sha256) VALUES (%s, 'x', %s, %s, %s)"
    good_svg, sha = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>', "a" * 64
    for key, svg, h in [("has space", good_svg, sha), ("UpperCase", good_svg, sha), ("", good_svg, sha), ("k" * 101, good_svg, sha),
                        ("k1", "<html/>", sha), ("k2", " <svg/>", sha), ("k3", good_svg, "XYZ"),
                        ("k4", '<svg viewBox="0 0 1 1">' + "x" * 1048576 + "</svg>", sha)]:
        with cursor(pg) as cur, pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(ins, (admin, key, svg, h))
    with cursor(pg) as cur:
        cur.execute(ins, (admin, "ok_key", good_svg, sha))
        with pytest.raises(psycopg2.errors.UniqueViolation):
            cur.execute(ins, (admin, "ok_key", good_svg, sha))
    with cursor(pg) as cur, pytest.raises(psycopg2.errors.ForeignKeyViolation):
        cur.execute(ins, (str(uuid.uuid4()), "other", good_svg, sha))
    # updated_at follows every UPDATE
    with cursor(pg) as cur:
        cur.execute("SELECT updated_at FROM asset_agg_icon WHERE key = 'ok_key'")
        t1 = cur.fetchone()[0]
        cur.execute("SELECT pg_sleep(0.05)")
        cur.execute("UPDATE asset_agg_icon SET summary = 's' WHERE key = 'ok_key'")
        cur.execute("SELECT updated_at FROM asset_agg_icon WHERE key = 'ok_key'")
        assert cur.fetchone()[0] > t1
        cur.execute("DELETE FROM asset_agg_icon WHERE key = 'ok_key'")


# ------------------------------------------------------------------------------ seeding flags
def run_seed(pg, *args):
    env = dict(os.environ, SEED_DB_DSN=pg.get_uri(), PYTHONPATH=str(ALPEN), PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, str(ALPEN / "scripts" / "seed_icons.py"), *args], capture_output=True, text=True, env=env)


def test_07_seed_flags(pg):
    a = ["--dir", str(FLAGS), "--prefix", "flag_", "--dash-to-underscore", "--name-template", "Flag {STEM}"]
    r = run_seed(pg, *a, "--dry-run")
    assert r.returncode == 0 and one(pg, "SELECT count(*) FROM asset_agg_icon") == 0, r.stdout + r.stderr
    r = run_seed(pg, *a)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "270 files: 270 accepted (270 new, 0 updated, 0 unchanged), 0 rejected" in r.stdout, r.stdout
    assert one(pg, "SELECT count(*) FROM asset_agg_icon WHERE key LIKE 'flag\\_%'") == 270
    assert one(pg, "SELECT name FROM asset_agg_icon WHERE key = 'flag_gb_eng'") == "Flag GB-ENG"
    # the id depends only on the key (same on every database; step 2 seed files can name icons by id)
    assert str(one(pg, "SELECT id FROM asset_agg_icon WHERE key = 'flag_at'")) == "%s" % uuid.uuid5(uuid.uuid5(uuid.NAMESPACE_URL, "https://alpenwege.dev/asset_agg_icon"), "flag_at")
    assert one(pg, "SELECT count(*) FROM asset_agg_icon WHERE key = 'flag_at' AND sha256 = encode(sha256(convert_to(svg, 'UTF8')), 'hex')") == 1
    r = run_seed(pg, *a)                                  # second run changes nothing
    assert "0 new, 0 updated, 270 unchanged" in r.stdout, r.stdout
    r = run_seed(pg, *a, "--update")
    assert "0 new, 0 updated, 270 unchanged" in r.stdout, r.stdout


def test_08_seed_rejects_bad_file_but_loads_the_rest(pg, tmp_path):
    (tmp_path / "good.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z" onclick="x()"/><script>1</script></svg>')
    (tmp_path / "bad.svg").write_text('<html><script>alert(1)</script></html>')
    (tmp_path / "bomb.svg").write_text('<!DOCTYPE s [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><text>&a;</text></svg>')
    r = run_seed(pg, "--dir", str(tmp_path))
    assert r.returncode == 1 and "1 accepted" in r.stdout and "2 rejected" in r.stdout, r.stdout
    svg = one(pg, "SELECT svg FROM asset_agg_icon WHERE key = 'good'")
    assert "script" not in svg and "onclick" not in svg and "<path" in svg
    assert one(pg, "SELECT count(*) FROM asset_agg_icon WHERE key IN ('bad', 'bomb')") == 0
    with cursor(pg) as cur:
        cur.execute("DELETE FROM asset_agg_icon WHERE key = 'good'")


# ------------------------------------------------------------------------------ linking
def link(pg):
    r = sql_file(pg, "icons_link.sql")
    return r.stderr          # RAISE NOTICE goes to stderr


def test_09_link_countries_regions_and_reference_tables(pg, tmp_path_factory):
    out = link(pg)
    assert re.search(r"compendium_cat_country\s*:\s*250 linked now,\s*0 still", out), out
    assert re.search(r"compendium_cat_region\s*:\s*0 linked now,\s*1570 still", out), out      # no region icons loaded yet
    assert re.search(r"core_ref_sport_type\s*:\s*0 linked now", out), out                       # no reference icons loaded yet
    assert one(pg, "SELECT count(*) FROM compendium_cat_country c JOIN asset_agg_icon i ON i.id = c.icon_id WHERE i.key = 'flag_' || lower(c.iso_code)") == 250

    # load artwork for a canton, a municipality and EVERY existing icon text of the reference tables (synthetic svg)
    texts = set()
    for t in REF_TABLES:
        with cursor(pg) as cur:
            cur.execute(f"SELECT DISTINCT icon FROM {t}")
            texts |= {r[0] for r in cur.fetchall()}
    folder = tmp_path_factory.mktemp("synthetic_icons")
    for tx in texts | {"flag_ch_zh", "flag_ch_zh_ak"}:
        (folder / f"{tx}.svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24H0z"/><!-- {tx} --></svg>')
    r = run_seed(pg, "--dir", str(folder))
    assert r.returncode == 0 and f"{len(texts) + 2} accepted" in r.stdout, r.stdout

    # one reference row is already linked by hand to another icon: the script must leave it alone
    with cursor(pg) as cur:
        cur.execute("UPDATE core_ref_rarity SET icon_id = (SELECT id FROM asset_agg_icon WHERE key = 'flag_at') WHERE icon = (SELECT icon FROM core_ref_rarity ORDER BY id LIMIT 1)")
    out = link(pg)
    assert re.search(r"compendium_cat_region\s*:\s*2 linked now,\s*1568 still", out), out
    for t in REF_TABLES:
        n = one(pg, f"SELECT count(*) FROM {t} WHERE icon_id IS NULL")
        assert n == (0 if t != "core_ref_rarity" else 0), (t, n)
    assert one(pg, "SELECT count(*) FROM core_ref_rarity r JOIN asset_agg_icon i ON i.id = r.icon_id WHERE i.key = 'flag_at'") == 1   # manual link kept
    assert one(pg, "SELECT count(*) FROM compendium_cat_region g JOIN asset_agg_icon i ON i.id = g.icon_id WHERE g.iso_code = 'CH-ZH' AND i.key = 'flag_ch_zh'") == 1
    assert one(pg, "SELECT count(*) FROM compendium_cat_region g JOIN asset_agg_icon i ON i.id = g.icon_id WHERE g.iso_code = 'CH-ZH-AK' AND i.key = 'flag_ch_zh_ak'") == 1
    out = link(pg)                                       # idempotent: nothing left to link
    assert len(re.findall(r":\s*0 linked now", out)) == 22, out


def test_10_used_icon_cannot_be_deleted_unused_can(pg):
    with cursor(pg) as cur:
        with pytest.raises(psycopg2.errors.ForeignKeyViolation):
            cur.execute("DELETE FROM asset_agg_icon WHERE key = 'flag_at'")
        cur.execute("DELETE FROM asset_agg_icon WHERE key = 'flag_xx'")                 # a flag nobody uses
        assert cur.rowcount == 1


# ------------------------------------------------------------------------------ rollback
def test_11_rollback_restores_the_old_schema(pg):
    old = {t: one(pg, f"SELECT md5(string_agg(id::text || icon, ',' ORDER BY id)) FROM {t}") for t in REF_TABLES}
    sql_file(pg, "icons_rollback.sql")
    assert one(pg, "SELECT to_regclass('asset_agg_icon') IS NULL")
    assert one(pg, "SELECT count(*) FROM information_schema.columns WHERE column_name = 'icon_id'") == 0
    assert old == {t: one(pg, f"SELECT md5(string_agg(id::text || icon, ',' ORDER BY id)) FROM {t}") for t in REF_TABLES}
    sql_file(pg, "icons_rollback.sql")                                                   # also idempotent


def test_12_schema_after_rollback_equals_schema_before_ddl_and_ddl_works_again(pg):
    after_rollback = dump_schema(pg)
    sql_file(pg, "icons_ddl.sql")
    with_icons = dump_schema(pg)
    sql_file(pg, "icons_rollback.sql")
    assert dump_schema(pg) == after_rollback
    assert with_icons != after_rollback and "asset_agg_icon" in with_icons
    sql_file(pg, "icons_ddl.sql")
    assert dump_schema(pg) == with_icons
