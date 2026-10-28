import csv
import io
import json
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKTElement
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession


# ------------------------------------------------------------------
# Swagger response model
# ------------------------------------------------------------------

class CsvImportResult(BaseModel):
    inserted: int
    errors: list[str] = []


# ------------------------------------------------------------------
# Dynamic Swagger description builder
# ------------------------------------------------------------------

def _col_type_label(col) -> str:
    if isinstance(col.type, Geometry):
        geo = getattr(col.type, "geometry_type", "GEOMETRY")
        return f"WKT {geo}"
    try:
        ptype = col.type.python_type
    except NotImplementedError:
        return "text"
    return {
        uuid.UUID: "UUID",
        int: "integer",
        float: "float",
        bool: "boolean",
        datetime: "ISO datetime",
        str: "text",
        list: "array (pipe `a|b` or JSON)",
    }.get(ptype, "text")


def csv_upload_description(model) -> str:
    mapper = sa_inspect(model)
    lines = [
        "Upload a **CSV** file to bulk-insert rows.  ",
        "The first row must be the header with column names.\n",
        "| Column | Type | Required | Notes |",
        "|--------|------|----------|-------|",
    ]
    for col in mapper.columns:
        name = col.key
        ctype = _col_type_label(col)
        if col.primary_key and col.server_default:
            req, note = "no", "auto-generated UUID if omitted"
        elif col.key == "created_by":
            req, note = "no", "defaults to authenticated user"
        elif col.key in ("created_at", "updated_at") and col.server_default:
            req, note = "no", "auto-generated timestamp"
        elif col.nullable or col.server_default is not None:
            req, note = "no", ""
        else:
            req, note = "**yes**", ""

        if isinstance(col.type, Geometry):
            geo = getattr(col.type, "geometry_type", "").upper()
            if geo == "POINT":
                note = (note + "; " if note else "") + (
                    f"WKT e.g. `POINT(13.37 47.27)` — "
                    f"or use `{name}_lon` + `{name}_lat` columns instead"
                )
            else:
                note = (note + "; " if note else "") + (
                    f"WKT e.g. `POLYGON((lon1 lat1, …))`"
                )

        lines.append(f"| `{name}` | {ctype} | {req} | {note} |")

    lines.append("")
    lines.append("**Array columns** accept pipe-separated `a|b|c` or JSON `[\"a\",\"b\"]`.")
    return "\n".join(lines)


# ------------------------------------------------------------------
# Type coercion
# ------------------------------------------------------------------

def _coerce(raw: str | None, col_type):
    if raw is None or raw.strip() == "":
        return None

    raw = raw.strip()

    if isinstance(col_type, Geometry):
        return WKTElement(raw, srid=getattr(col_type, "srid", 4326) or 4326)

    try:
        ptype = col_type.python_type
    except NotImplementedError:
        return raw

    if ptype is uuid.UUID:
        return uuid.UUID(raw)
    if ptype is int:
        return int(raw)
    if ptype is float:
        return float(raw)
    if ptype is bool:
        return raw.lower() in ("true", "1", "yes", "t")
    if ptype is datetime:
        return datetime.fromisoformat(raw)
    if ptype is list:
        if raw.startswith("["):
            return json.loads(raw)
        return [v.strip() for v in raw.split("|") if v.strip()]
    return raw


# ------------------------------------------------------------------
# CSV import
# ------------------------------------------------------------------

def _required_columns(mapper) -> list[str]:
    # NOT NULL columns that nothing fills in by itself (no database default, no Python default, not created_by)
    return [
        c.key for c in mapper.columns
        if not c.nullable and not c.primary_key and c.server_default is None and c.default is None and c.key != "created_by"
    ]


async def import_csv(
    file,
    model,
    user_id: uuid.UUID,
    db: AsyncSession,
    *,
    row_check=None,
) -> dict:
    """Parse a CSV upload and bulk-insert rows into *model*'s table.

    Returns ``{"inserted": N, "errors": [...]}``. row_check(data) is awaited for every parsed row and raises
    ValueError to reject it (for example a link to something the caller may not use).
    """
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    mapper = sa_inspect(model)
    col_map = {c.key: c for c in mapper.columns}

    point_geo = {
        k
        for k, c in col_map.items()
        if isinstance(c.type, Geometry)
        and getattr(c.type, "geometry_type", "").upper() == "POINT"
    }

    required = _required_columns(mapper)
    headers = {(h or "").strip() for h in (reader.fieldnames or [])}
    missing_headers = [
        k for k in required
        if k not in headers and not (k in point_geo and {f"{k}_lon", f"{k}_lat"} <= headers)
    ]
    if missing_headers:
        # without these columns every row would fail in the database (500); say it once, clearly, and insert nothing
        return {"inserted": 0, "errors": [f"missing required column(s) in the header: {', '.join(missing_headers)}"]}

    objects = []
    errors: list[str] = []
    for row_idx, row in enumerate(reader, start=2):
        try:
            data: dict = {}
            skip: set = set()

            for geo_key in point_geo:
                lon_h = f"{geo_key}_lon"
                lat_h = f"{geo_key}_lat"
                if lon_h in row and lat_h in row:
                    lon_v = (row[lon_h] or "").strip()
                    lat_v = (row[lat_h] or "").strip()
                    if lon_v and lat_v:
                        data[geo_key] = WKTElement(
                            f"POINT({lon_v} {lat_v})", srid=4326
                        )
                        skip.update({lon_h, lat_h})

            for header, value in row.items():
                header = header.strip()
                if header in skip or header not in col_map or header in data:
                    continue
                data[header] = _coerce(value, col_map[header].type)

            if "created_by" in col_map and "created_by" not in data:
                data["created_by"] = user_id

            empty = [k for k in required if data.get(k) is None]
            if empty:
                raise ValueError(f"missing value for {', '.join(empty)}")
            if row_check is not None:
                await row_check(data)

            objects.append(model(**data))
        except Exception as exc:
            errors.append(f"row {row_idx}: {exc}")

    if objects:
        db.add_all(objects)
        await db.commit()

    return {"inserted": len(objects), "errors": errors}
