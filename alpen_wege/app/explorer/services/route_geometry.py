# Standard library
from dataclasses import dataclass
from uuid import UUID


@dataclass
class GeoPart:
    # The map data of one segment of a route, as stored (always from the start of the segment to its end)
    slot: int
    segment_id: UUID
    is_reversed: bool
    geojson: dict | None
    elevation_graph: list | None
    distance_m: int | None


def lines_of(geojson: dict | None) -> list[list[list[float]]]:
    # a GeoJSON LineString or MultiLineString as a list of lines (each a list of [lon, lat])
    if not geojson:
        return []
    kind = geojson.get("type")
    if kind == "LineString":
        return [geojson["coordinates"]]
    if kind == "MultiLineString":
        return list(geojson["coordinates"])
    return []


def walked(lines: list, is_reversed: bool) -> list:
    # the lines in the direction in which the route walks them: backwards means the lines in reverse order, each reversed
    if not is_reversed:
        return [list(line) for line in lines]
    return [list(reversed(line)) for line in reversed(lines)]


def line_geojson(lines: list) -> dict | None:
    if not lines:
        return None
    if len(lines) == 1:
        return {"type": "LineString", "coordinates": lines[0]}
    return {"type": "MultiLineString", "coordinates": lines}


def segment_length(part: GeoPart) -> float:
    # the length that a segment adds to the profile of the route: its distance, else the end of its own graph
    if part.distance_m is not None:
        return float(part.distance_m)
    if part.elevation_graph:
        return float(part.elevation_graph[-1][0])
    return 0.0


def walked_graph(part: GeoPart) -> list[list[float]]:
    # the [distance, elevation] pairs of one segment in walking direction, distances from the start of that segment
    graph = part.elevation_graph or []
    if not part.is_reversed:
        return [[float(d), float(e)] for d, e in graph]
    length = segment_length(part)
    return [[max(0.0, length - float(d)), float(e)] for d, e in reversed(graph)]


def combined_profile(parts: list[GeoPart]) -> list[list[float]] | None:
    # One elevation profile for the default segments in slot order: each segment's distances start where the one before
    # it ended; a reversed segment is mirrored. None when fewer than 2 points have an elevation.
    out: list[list[float]] = []
    offset = 0.0
    for part in sorted(parts, key=lambda p: p.slot):
        for d, e in walked_graph(part):
            out.append([round(offset + d, 1), round(e, 1)])
        offset += segment_length(part)
    return out if len(out) >= 2 else None


def route_lines(parts: list[GeoPart]) -> list[list[list[float]]]:
    # the lines of all given segments, in slot order, each in walking direction
    lines: list = []
    for part in sorted(parts, key=lambda p: p.slot):
        lines.extend(walked(lines_of(part.geojson), part.is_reversed))
    return lines
