# Standard library
import math

# Third-party
import numpy as np
from shapely.geometry import LineString

# Local application
from .cleaning import haversine
from .limits import GpxLimits
from .models import CleanedGpx, GpxPoint


def _to_local(seg: list[GpxPoint]) -> tuple[np.ndarray, float, float]:
    lats = np.array([p.lat for p in seg])
    lons = np.array([p.lon for p in seg])
    lat0 = float(np.mean(lats))
    lon0 = float(np.mean(lons))
    x = (lons - lon0) * math.cos(math.radians(lat0)) * 111320
    y = (lats - lat0) * 110540
    return np.column_stack([x, y]), lon0, lat0


def _from_local(
    coords: np.ndarray, lon0: float, lat0: float,
) -> list[tuple[float, float]]:
    lons = coords[:, 0] / (math.cos(math.radians(lat0)) * 111320) + lon0
    lats = coords[:, 1] / 110540 + lat0
    return list(zip(lons.tolist(), lats.tolist()))


def _simplify_segment(
    seg: list[GpxPoint], tolerance_m: float,
) -> list[tuple[float, float]]:
    if len(seg) < 2:
        return [(seg[0].lon, seg[0].lat)] if seg else []
    local, lon0, lat0 = _to_local(seg)
    ls = LineString(local)
    simplified = ls.simplify(tolerance_m, preserve_topology=False)
    return _from_local(np.array(simplified.coords), lon0, lat0)


def build_geojson(
    cleaned: CleanedGpx, limits: GpxLimits,
) -> tuple[dict, set[str]]:
    warnings: set[str] = set()
    decimals = limits.geojson_coord_decimals
    max_pts = limits.geojson_max_points

    lo, hi = 0.0, 5000.0
    best_coords = None
    best_total = None
    for _ in range(12):
        mid = (lo + hi) / 2
        coords = [_simplify_segment(s, mid) for s in cleaned.segments]
        total = sum(len(c) for c in coords)
        if total <= max_pts:
            hi = mid
            best_coords = coords
            best_total = total
        else:
            lo = mid

    if best_coords is None:
        best_coords = [_simplify_segment(s, hi) for s in cleaned.segments]
        best_total = sum(len(c) for c in best_coords)

    if best_total > max_pts:
        lengths = [(sum(
            haversine(c[i][1], c[i][0], c[i + 1][1], c[i + 1][0])
            for i in range(len(c) - 1)
        ), idx) for idx, c in enumerate(best_coords)]
        lengths.sort(reverse=True)
        keep = set()
        running = 0
        for length, idx in lengths:
            pts_count = len(best_coords[idx])
            if running + pts_count <= max_pts:
                keep.add(idx)
                running += pts_count
        best_coords = [c for idx, c in enumerate(best_coords) if idx in keep]
        warnings.add("geometry_truncated")

    rounded = []
    for coords in best_coords:
        seg_rounded = []
        for lon, lat in coords:
            pt = [round(lon, decimals), round(lat, decimals)]
            if seg_rounded and seg_rounded[-1] == pt:
                continue
            seg_rounded.append(pt)
        if len(seg_rounded) >= 2:
            rounded.append(seg_rounded)

    if len(rounded) == 1:
        geojson = {"type": "LineString", "coordinates": rounded[0]}
    else:
        geojson = {"type": "MultiLineString", "coordinates": rounded}

    return geojson, warnings


def build_elevation_graph(
    cleaned: CleanedGpx, limits: GpxLimits,
) -> list | None:
    from .metrics import _median_filter

    series: list[tuple[float, float]] = []
    global_dist = 0.0

    for seg in cleaned.segments:
        cum = np.zeros(len(seg))
        for i in range(1, len(seg)):
            cum[i] = cum[i - 1] + haversine(
                seg[i - 1].lat, seg[i - 1].lon, seg[i].lat, seg[i].lon
            )
        eles = np.array([p.ele if p.ele is not None else np.nan for p in seg])
        has_ele = ~np.isnan(eles)
        if has_ele.sum() >= 2:
            filtered = _median_filter(eles[has_ele], limits.elevation_median_window)
            cum_at_ele = cum[has_ele]
            for d, e in zip(cum_at_ele, filtered):
                series.append((global_dist + d, e))
        global_dist += float(cum[-1]) if len(cum) > 0 else 0

    if len(series) < 2:
        return None

    dists = np.array([s[0] for s in series])
    vals = np.array([s[1] for s in series])
    n = min(limits.graph_max_points, len(series))
    target = np.linspace(dists[0], dists[-1], n)
    interp = np.interp(target, dists, vals)

    result = []
    for d, v in zip(target, interp):
        if np.isnan(v) or np.isinf(v):
            continue
        result.append([round(float(d), 1), round(float(v), 1)])
    return result if len(result) >= 2 else None


def build_route_ewkt(cleaned: CleanedGpx, limits: GpxLimits) -> str:
    lines = []
    for seg in cleaned.segments:
        coords = _simplify_segment(seg, limits.route_simplify_tolerance_m)
        if len(coords) >= 2:
            coord_str = ",".join(
                f"{round(lon, 6)} {round(lat, 6)}" for lon, lat in coords
            )
            lines.append(f"({coord_str})")
    return f"SRID=4326;MULTILINESTRING({','.join(lines)})"
