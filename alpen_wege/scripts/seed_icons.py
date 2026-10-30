#!/usr/bin/env python3
"""
Load icons into asset_agg_icon, from a folder of SVG files or from a CSV file that carries the SVG text.

Every graphic goes through the same cleaner as the upload route (app.assets.services.icon_svg.clean_svg), so the database never holds
a file as it came. The key of an icon is the file name without .svg (folder) or the column `key` (CSV); keys are lower case.

Folder (flags: the 270 files of the card renderer):
    python scripts/seed_icons.py --dir app/compendium/cards/flags --prefix flag_ --dash-to-underscore --name-template "Flag {STEM}"
CSV (the icons of the reference tables, made by scripts/make_icon_set.py):
    python scripts/seed_icons.py --csv icons_import.csv
    columns: key, svg (required); name, name_de, name_pl, summary, summary_de, summary_pl (optional; name defaults to the key)

Idempotent: an existing key is left alone unless --update is given (then the svg is replaced when the cleaned text differs; in CSV mode
the names and summaries are replaced too). --dry-run checks and cleans every row and prints the result without touching the database.
Run inside the API container:  sudo docker exec alpen-api python /app/scripts/seed_icons.py --csv /app/icons_import.csv
Afterwards run scripts/sql/icons_link.sql: it sets icon_id on every row whose old icon text matches an icon key.
Exit code 0 = every row was accepted, 1 = at least one was rejected (the others are still loaded).
"""
import argparse
import os
import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # the repo root, so that `app` can be imported
from app.assets.services.icon_csv import ICON_NAMESPACE, KEY_RE, TEXT_FIELDS, icon_id, parse_csv_text, prepare_rows  # noqa: E402,F401  the same code as the API
from app.assets.services.icon_svg import InvalidSvg, clean_svg  # noqa: E402  the same cleaner as the upload route

_DEFAULT_DSN = "dbname=alpenwege user=alpenwege password=alpenwege host=localhost port=5433"
_DOCKER_DSN = "dbname=alpenwege user=alpenwege password=alpenwege host=postgres port=5432"
DB_DSN = os.environ.get("SEED_DB_DSN") or (_DOCKER_DSN if os.environ.get("DATABASE_URL_SYNC") else _DEFAULT_DSN)


def read_csv_rows(path):
    # rows of the import CSV (UTF-8, with or without the BOM that Excel writes)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return parse_csv_text(fh.read())


prepare_csv_rows = prepare_rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--dir", help="folder with .svg files (not searched recursively)")
    source.add_argument("--csv", help="CSV file with the columns key, svg and optional names (see above)")
    ap.add_argument("--prefix", default="", help="--dir: added in front of every key, for example flag_")
    ap.add_argument("--dash-to-underscore", action="store_true", help="--dir: gb-eng.svg -> gb_eng (for flags)")
    ap.add_argument("--name-template", default="{stem}", help="--dir: name of the icon; {stem} = file name, {STEM} = upper case")
    ap.add_argument("--update", action="store_true", help="replace an existing key when it differs")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--admin-email", default="admin@alpenwege.dev", help="created_by of new icons")
    a = ap.parse_args()

    notes = []
    if a.csv:
        try:
            rows = read_csv_rows(a.csv)
        except (OSError, ValueError) as exc:
            print(f"cannot read {a.csv}: {exc}")
            return 1
        total = len(rows)
        prepared, rejected, notes = prepare_csv_rows(rows)
        fields = ("svg", "sha256") + TEXT_FIELDS
    else:
        files = sorted(Path(a.dir).glob("*.svg"))
        if not files:
            print(f"no .svg files in {a.dir}")
            return 1
        total = len(files)
        prepared, rejected = [], []
        for f in files:
            stem = f.stem
            key = (a.prefix + (stem.replace("-", "_") if a.dash_to_underscore else stem)).lower()   # keys are lower case
            try:
                c = clean_svg(f.read_bytes())
            except InvalidSvg as exc:
                rejected.append((f.name, str(exc)))
                continue
            prepared.append({"key": key, "name": a.name_template.format(stem=stem, STEM=stem.upper()), "svg": c.svg, "sha": c.sha256,
                             **{f_: None for f_ in TEXT_FIELDS if f_ != "name"}})
        fields = ("svg", "sha256")

    inserted = unchanged = updated = 0
    if not a.dry_run:
        conn = psycopg2.connect(DB_DSN)
        cur = conn.cursor()
        cur.execute("SELECT id FROM profile_usr_user WHERE email = %s", (a.admin_email,))
        row = cur.fetchone()
        if not row:
            print(f"user {a.admin_email} not found")
            return 1
        admin_id = row[0]
        for item in prepared:
            cur.execute(f"SELECT {', '.join(fields)} FROM asset_agg_icon WHERE key = %s", (item["key"],))
            old = cur.fetchone()
            values = {"svg": item["svg"], "sha256": item["sha"], **{f: item[f] for f in TEXT_FIELDS}}
            if old is None:
                cur.execute("INSERT INTO asset_agg_icon (id, created_by, key, svg, sha256, name, name_de, name_pl, summary, summary_de, summary_pl) "
                            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                            (str(icon_id(item["key"])), admin_id, item["key"], item["svg"], item["sha"], item["name"], item["name_de"], item["name_pl"],
                             item["summary"], item["summary_de"], item["summary_pl"]))
                inserted += 1
            elif a.update and tuple(old) != tuple(values[f] for f in fields):
                cur.execute(f"UPDATE asset_agg_icon SET {', '.join(f + ' = %s' for f in fields)} WHERE key = %s",
                            (*[values[f] for f in fields], item["key"]))
                updated += 1
            else:
                unchanged += 1
        conn.commit()
        cur.close()
        conn.close()

    unit = "rows" if a.csv else "files"
    print(f"{total} {unit}: {len(prepared)} accepted ({'dry run' if a.dry_run else f'{inserted} new, {updated} updated, {unchanged} unchanged'}), {len(rejected)} rejected")
    for key, what in notes:
        print(f"  NOTE {key}: the cleaner removed {what}")
    for name, why in rejected:
        print(f"  REJECTED {name}: {why}")
    return 1 if rejected else 0


if __name__ == "__main__":
    sys.exit(main())
