# Standard library
import math
from dataclasses import dataclass
from datetime import datetime

# Third-party
import numpy as np

# Local application
from .cleaning import haversine, haversine_vec
from .models import CleanedGpx


@dataclass
class NearestVisit:
    distance_m: float
    along_track_m: float
    time: datetime | None


def nearest_visit(
    cleaned: CleanedGpx, lat: float, lon: float,
) -> NearestVisit:
    best_dist = math.inf
    best_seg_idx = 0
    best_pt_idx = 0

    for si, seg in enumerate(cleaned.segments):
        lats = np.array([p.lat for p in seg])
        lons = np.array([p.lon for p in seg])
        dists = haversine_vec(
            np.full(len(seg), lat), np.full(len(seg), lon), lats, lons
        )
        idx = int(np.argmin(dists))
        if dists[idx] < best_dist:
            best_dist = dists[idx]
            best_seg_idx = si
            best_pt_idx = idx

    seg = cleaned.segments[best_seg_idx]
    best_on_line_dist = best_dist
    best_along = _along_track(cleaned, best_seg_idx, best_pt_idx)
    best_time_result = None

    for di in [-1, 0]:
        a_idx = best_pt_idx + di
        b_idx = best_pt_idx + di + 1
        if a_idx < 0 or b_idx >= len(seg):
            continue
        a = seg[a_idx]
        b = seg[b_idx]
        proj_dist, t_param = _project_to_edge(lat, lon, a, b)
        if proj_dist < best_on_line_dist:
            best_on_line_dist = proj_dist
            seg_along = _along_track(cleaned, best_seg_idx, a_idx)
            edge_len = haversine(a.lat, a.lon, b.lat, b.lon)
            best_along = seg_along + edge_len * t_param
            if a.time is not None and b.time is not None:
                dt = (b.time - a.time).total_seconds()
                best_time_result = a.time + __import__(
                    "datetime"
                ).timedelta(seconds=dt * t_param)
            else:
                best_time_result = None

    if best_time_result is None:
        best_time_result = _nearest_timed(seg, best_pt_idx)

    return NearestVisit(
        distance_m=best_on_line_dist,
        along_track_m=best_along,
        time=best_time_result,
    )


def _along_track(cleaned: CleanedGpx, seg_idx: int, pt_idx: int) -> float:
    dist = 0.0
    for si in range(seg_idx):
        seg = cleaned.segments[si]
        for i in range(1, len(seg)):
            dist += haversine(
                seg[i - 1].lat, seg[i - 1].lon, seg[i].lat, seg[i].lon
            )
    seg = cleaned.segments[seg_idx]
    for i in range(1, min(pt_idx + 1, len(seg))):
        dist += haversine(
            seg[i - 1].lat, seg[i - 1].lon, seg[i].lat, seg[i].lon
        )
    return dist


def _project_to_edge(
    lat: float, lon: float, a, b,
) -> tuple[float, float]:
    lat0 = (a.lat + b.lat) / 2
    cos_lat = math.cos(math.radians(lat0))
    ax = (a.lon - a.lon) * cos_lat * 111320
    ay = (a.lat - a.lat) * 110540
    bx = (b.lon - a.lon) * cos_lat * 111320
    by = (b.lat - a.lat) * 110540
    px = (lon - a.lon) * cos_lat * 111320
    py = (lat - a.lat) * 110540

    dx, dy = bx - ax, by - ay
    len_sq = dx * dx + dy * dy
    if len_sq == 0:
        return haversine(lat, lon, a.lat, a.lon), 0.0

    t = max(0, min(1, (px * dx + py * dy) / len_sq))
    cx = ax + t * dx
    cy = ay + t * dy
    dist = math.sqrt((px - cx) ** 2 + (py - cy) ** 2)
    return dist, t


def _nearest_timed(seg, pt_idx) -> datetime | None:
    for offset in range(len(seg)):
        for idx in [pt_idx - offset, pt_idx + offset]:
            if 0 <= idx < len(seg) and seg[idx].time is not None:
                return seg[idx].time
    return None
