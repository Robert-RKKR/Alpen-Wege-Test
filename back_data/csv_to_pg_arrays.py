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

# Standard library
import csv
import json
import sys


def parse_json_array(value):
    # Try to interpret a CSV cell as a JSON array.
    # Params:
    #   value: the raw cell string.
    # Returns: the parsed list if the value is a valid JSON array, else None.
    # Quick reject: must be bracket-delimited to be a candidate array.
    stripped = value.strip()
    if not (stripped.startswith("[") and stripped.endswith("]")):
        return None
    # Attempt a real JSON parse; malformed input is treated as "not an array".
    try:
        items = json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        return None
    # Only accept actual lists.
    return items if isinstance(items, list) else None


def to_pg_array(items):
    # Render a Python list as a PostgreSQL array literal, e.g. {"a","b"}.
    # Params:
    #   items: the list of values to encode.
    # Returns: a string containing the Postgres array literal.
    def escape(item):
        # Quote and backslash-escape a single element for the array literal.
        text = str(item)
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'

    # Join the escaped elements inside curly braces.
    return "{" + ",".join(escape(item) for item in items) + "}"


def to_bbox_polygon(items):
    # Convert a [minLon, minLat, maxLon, maxLat] bbox into an EWKT polygon.
    # Params:
    #   items: a 4-element list of bounding-box coordinates.
    # Returns: an EWKT string (SRID=4326;POLYGON((...))) for a geometry column.
    # Unpack the bounding box corners.
    min_lon, min_lat, max_lon, max_lat = items
    # Build the closed ring: BL -> BR -> TR -> TL -> back to BL.
    ring = (
        f"{min_lon} {min_lat},{max_lon} {min_lat},"
        f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}"
    )
    return f"SRID=4326;POLYGON(({ring}))"


def convert_field(column, value):
    # Convert a single CSV field to its Postgres representation if it's an array.
    # Params:
    #   column: the target column name (special-cased for "bbox").
    #   value: the raw CSV cell value.
    # Returns: the converted value, or the original value if it's not a JSON array.
    # Non-array values pass through unchanged.
    items = parse_json_array(value)
    if items is None:
        return value
    # The bbox column becomes a polygon; every other array becomes a PG array literal.
    if column == "bbox":
        return to_bbox_polygon(items)
    return to_pg_array(items)


def main():
    # CLI entry point: transform a push_data CSV on stdin into COPY-ready CSV on stdout.
    # Params: none (reads sys.argv and stdin) — argv[1] is the target table's columns.
    # Returns: nothing; writes the converted CSV to stdout and warnings to stderr.
    # Require exactly one argument: the comma-separated list of table columns.
    if len(sys.argv) != 2:
        print(
            "usage: csv_to_pg_arrays.py <comma-separated-table-columns>",
            file=sys.stderr,
        )
        sys.exit(1)
    table_columns = set(sys.argv[1].split(","))

    # Stream CSV in from stdin and out to stdout with normalized line endings.
    reader = csv.reader(sys.stdin)
    writer = csv.writer(sys.stdout, lineterminator="\n")

    # Read the header; an empty input file is a no-op.
    raw_header = next(reader, None)
    if raw_header is None:
        return
    # Source CSVs use "title" where tables use "name" — rename to match.
    renamed_header = ["name" if c == "title" else c for c in raw_header]

    # Keep only columns that exist in the target table; warn about any dropped ones.
    keep_indices = [i for i, c in enumerate(renamed_header) if c in table_columns]
    dropped = [c for c in renamed_header if c not in table_columns]
    if dropped:
        print(
            f"    WARNING: dropping CSV columns not present in table: {', '.join(dropped)}",
            file=sys.stderr,
        )

    # Emit the filtered header, then convert and emit each data row.
    kept_header = [renamed_header[i] for i in keep_indices]
    writer.writerow(kept_header)
    for row in reader:
        kept_row = [row[i] for i in keep_indices]
        writer.writerow(
            [
                convert_field(column, field)
                for column, field in zip(kept_header, kept_row)
            ]
        )


if __name__ == "__main__":
    main()
