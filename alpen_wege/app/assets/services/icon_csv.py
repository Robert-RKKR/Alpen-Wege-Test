"""Creating many icons from one CSV (columns key and svg, optional name, name_de, name_pl, summary, summary_de, summary_pl).

Used by POST /assets/icons/upload-csv and by scripts/seed_icons.py --csv, so the API and the script do exactly the same:
parse_csv_text -> prepare_rows (every SVG is cleaned like an upload; wrong rows are named by row number) -> save_icons.
"""
# Standard library
import csv
import io
import re
import uuid
from dataclasses import dataclass, field

# Third-party
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Local application
from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.services.icon_svg import InvalidSvg, clean_svg
from app.management.utils.event_logger import log_created, log_updated

KEY_RE = re.compile(r"^[a-z0-9_.-]{1,100}$")
TEXT_FIELDS = ("name", "name_de", "name_pl", "summary", "summary_de", "summary_pl")
# A seeded icon gets an id that depends only on its key, so a seed CSV can name it by id on every database.
ICON_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://alpenwege.dev/asset_agg_icon")
CHUNK = 500


def icon_id(key: str) -> uuid.UUID:
    return uuid.uuid5(ICON_NAMESPACE, key)


def parse_csv_text(text: str, max_rows: int | None = None) -> list[dict]:
    # rows of the import CSV; the SVG text can be long. ValueError (a sentence for the caller) when the file cannot be used.
    csv.field_size_limit(10_000_000)
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    names = [n.strip() for n in (reader.fieldnames or [])]
    missing = [c for c in ("key", "svg") if c not in names]
    if missing:
        raise ValueError(f"the CSV needs the column(s): {', '.join(missing)} (found: {', '.join(names) or 'none'})")
    rows = []
    try:
        for row in reader:
            rows.append({k.strip(): (v or "") for k, v in row.items() if k})
            if max_rows is not None and len(rows) > max_rows:
                raise ValueError(f"more than {max_rows} rows; split the file")
    except csv.Error as exc:
        raise ValueError(f"not a readable CSV: {exc}")
    if not rows:
        raise ValueError("the CSV has a header but no rows")
    return rows


def prepare_rows(rows: list[dict]):
    # (prepared icons, rejected [(label, reason)], notes [(key, what the cleaner removed)])
    prepared, rejected, notes, seen = [], [], [], set()
    for i, row in enumerate(rows, start=2):
        key = row["key"].strip().lower()
        label = f"row {i} ({key or 'no key'})"
        if not KEY_RE.match(key):
            rejected.append((label, "the key must be lower-case letters, digits and _ . - (1 to 100 characters)"))
            continue
        if key in seen:
            rejected.append((label, "the key is in the file twice"))
            continue
        seen.add(key)
        try:
            c = clean_svg(row["svg"].encode("utf-8"))
        except InvalidSvg as exc:
            rejected.append((label, str(exc)))
            continue
        if c.removed:
            notes.append((key, ", ".join(c.removed)))
        item = {f: (row.get(f) or "").strip() or None for f in TEXT_FIELDS}
        item.update(key=key, name=item["name"] or key, svg=c.svg, sha=c.sha256)
        prepared.append(item)
    return prepared, rejected, notes


@dataclass
class SaveResult:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    keys: dict = field(default_factory=dict)      # key -> "inserted" | "updated" | "unchanged"


async def save_icons(db: AsyncSession, prepared: list[dict], user_id, *, update: bool) -> SaveResult:
    # Adds the icons to the session (the caller commits). An existing key is left alone, or replaced (svg and every text field)
    # when update is true. The id of a new icon comes from its key; if that id is taken by an icon with another key (the key was
    # renamed) a random one is used.
    result = SaveResult()
    existing: dict[str, AssetAggIcon] = {}
    keys = [p["key"] for p in prepared]
    for i in range(0, len(keys), CHUNK):
        rows = await db.execute(select(AssetAggIcon).where(AssetAggIcon.key.in_(keys[i:i + CHUNK])))
        existing.update({icon.key: icon for icon in rows.scalars()})
    wanted = {p["key"]: icon_id(p["key"]) for p in prepared if p["key"] not in existing}
    taken: set = set()
    ids = list(wanted.values())
    for i in range(0, len(ids), CHUNK):
        taken |= set((await db.execute(select(AssetAggIcon.id).where(AssetAggIcon.id.in_(ids[i:i + CHUNK])))).scalars())
    for p in prepared:
        icon = existing.get(p["key"])
        if icon is None:
            new_id = wanted[p["key"]] if wanted[p["key"]] not in taken else uuid.uuid4()
            icon = AssetAggIcon(id=new_id, key=p["key"], svg=p["svg"], sha256=p["sha"], created_by=user_id, **{f: p[f] for f in TEXT_FIELDS})
            db.add(icon)
            log_created(db, icon, user_id)
            result.inserted += 1
            result.keys[p["key"]] = "inserted"
            continue
        changes = {f: p[f] for f in TEXT_FIELDS if getattr(icon, f) != p[f]}
        if icon.sha256 != p["sha"]:
            changes.update(svg=p["svg"], sha256=p["sha"])
        if not update or not changes:
            result.unchanged += 1
            result.keys[p["key"]] = "unchanged"
            continue
        old_values = {f: getattr(icon, f) for f in changes if f != "svg"}        # the SVG text is never read for the log
        for f, value in changes.items():
            setattr(icon, f, value)
        log_updated(db, icon, old_values, changes, user_id)
        result.updated += 1
        result.keys[p["key"]] = "updated"
    return result
