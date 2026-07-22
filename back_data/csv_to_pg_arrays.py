#!/usr/bin/env python3
"""Prepare a push_data CSV for COPY into its Postgres table:
- renames the "title" column to "name" (source CSVs use "title", tables use "name")
- drops any CSV columns that don't exist in the target table, warning on stderr
- rewrites JSON-style array fields into Postgres array literals (e.g. {"a","b"})
  for text[]/int[] columns
- rewrites the "bbox" column's [minLon,minLat,maxLon,maxLat] array into an
  EWKT polygon for its geometry(Polygon,4326) column

Usage: csv_to_pg_arrays.py <comma-separated-table-columns> < input.csv > output.csv
Writes the converted CSV (with header) to stdout; the caller reads the
first line back out to build the COPY column list.
"""
import csv
import json
import sys


def parse_json_array(value):
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    try:
        items = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    return items if isinstance(items, list) else None


def to_pg_array(items):
    def escape(item):
        text = str(item)
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    return "{" + ",".join(escape(item) for item in items) + "}"


def to_bbox_polygon(items):
    min_lon, min_lat, max_lon, max_lat = items
    ring = (
        f"{min_lon} {min_lat},{max_lon} {min_lat},"
        f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}"
    )
    return f"SRID=4326;POLYGON(({ring}))"


def convert_field(column, value):
    items = parse_json_array(value)
    if items is None:
        return value
    if column == "bbox":
        return to_bbox_polygon(items)
    return to_pg_array(items)


def main():
    if len(sys.argv) != 2:
        print("usage: csv_to_pg_arrays.py <comma-separated-table-columns>", file=sys.stderr)
        sys.exit(1)
    table_columns = set(sys.argv[1].split(","))

    reader = csv.reader(sys.stdin)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    raw_header = next(reader, None)
    if raw_header is None:
        return
    renamed_header = ["name" if c == "title" else c for c in raw_header]

    keep_indices = [i for i, c in enumerate(renamed_header) if c in table_columns]
    dropped = [c for c in renamed_header if c not in table_columns]
    if dropped:
        print(
            f"    WARNING: dropping CSV columns not present in table: {', '.join(dropped)}",
            file=sys.stderr,
        )

    kept_header = [renamed_header[i] for i in keep_indices]
    writer.writerow(kept_header)
    for row in reader:
        kept_row = [row[i] for i in keep_indices]
        writer.writerow(
            [convert_field(column, field) for column, field in zip(kept_header, kept_row)]
        )


if __name__ == "__main__":
    main()
