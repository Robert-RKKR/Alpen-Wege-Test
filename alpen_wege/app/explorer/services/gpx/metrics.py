# Standard library
import math

# Third-party
import numpy as np

# Local application
from .cleaning import haversine
from .limits import GpxLimits
from .models import CleanedGpx, GeoMetrics, GpxPoint, PerfMetrics


def geometry_metrics(cleaned: CleanedGpx, limits: GpxLimits) -> GeoMetrics:
    total_distance = 0.0
    total_gain = 0.0
    total_loss = 0.0
    highest = -math.inf
    lowest = math.inf
    first_ele = None
    total_points = 0
    all_grades = []
    all_grade_weights = []

    for seg in cleaned.segments:
        seg_dist, seg_cum = _segment_distances(seg)
        total_distance += seg_dist
        total_points += len(seg)

        eles = np.array([p.ele if p.ele is not None else np.nan for p in seg])
        has_ele = ~np.isnan(eles)

        if has_ele.sum() >= 1:
            filtered = _median_filter(
                eles[has_ele], limits.elevation_median_window
            )
            local_max = float(np.max(filtered))
            local_min = float(np.min(filtered))
            if local_max > highest:
                highest = local_max
            if local_min < lowest:
                lowest = local_min
            if first_ele is None:
                first_ele = float(filtered[0])

        if has_ele.sum() >= 2:
            filtered = _median_filter(
                eles[has_ele], limits.elevation_median_window
            )
            gain, loss = _hysteresis(filtered, limits.elevation_threshold_m)
            total_gain += gain
            total_loss += loss

            cum_at_ele = seg_cum[has_ele]
            grades, weights = _windowed_grade(
                filtered, cum_at_ele, limits.grade_window_m
            )
            if len(grades):
                all_grades.extend(grades)
                all_grade_weights.extend(weights)

    has_elevation = highest > -math.inf
    avg_grade = None
    highest_grade = None
    if all_grades:
        g = np.array(all_grades)
        w = np.array(all_grade_weights)
        total_w = w.sum()
        if total_w > 0:
            avg_grade = float(np.sum(np.abs(g) * w) / total_w)
        highest_grade = float(max(0, np.max(g)))

    first_seg = cleaned.segments[0]
    last_seg = cleaned.segments[-1]

    return GeoMetrics(
        distance_m=int(round(total_distance)),
        elevation_gain_m=int(round(total_gain)) if has_elevation else None,
        elevation_loss_m=int(round(total_loss)) if has_elevation else None,
        highest_elevation_m=int(round(highest)) if has_elevation else None,
        lowest_elevation_m=int(round(lowest)) if has_elevation else None,
        elevation=int(round(first_ele)) if first_ele is not None else None,
        avg_grade=avg_grade,
        highest_grade=highest_grade,
        total_points=total_points,
        start_lat=first_seg[0].lat,
        start_lon=first_seg[0].lon,
        end_lat=last_seg[-1].lat,
        end_lon=last_seg[-1].lon,
    )


def performance_metrics(
    cleaned: CleanedGpx, geo: GeoMetrics, limits: GpxLimits,
) -> PerfMetrics | None:
    has_timed_seg = False
    for seg in cleaned.segments:
        timed = [p for p in seg if p.time is not None]
        if len(timed) >= 2:
            has_timed_seg = True
            break
    if not has_timed_seg:
        return None

    first_time = None
    last_time = None
    total_time = 0.0
    moving_time = 0.0
    moving_dist = 0.0
    timed_dist = 0.0
    ascent_time = 0.0
    ascent_dist = 0.0
    descent_time = 0.0
    descent_dist = 0.0
    interval_speeds: list[float] = []
    ascent_speeds: list[float] = []
    descent_speeds: list[float] = []
    hr_samples: list[int] = []
    speed_dist_series: list[tuple[float, float]] = []
    hr_dist_series: list[tuple[float, float]] = []
    global_dist = 0.0

    for seg in cleaned.segments:
        eles = np.array([p.ele if p.ele is not None else np.nan for p in seg])
        has_ele = ~np.isnan(eles)

        seg_cum = np.zeros(len(seg))
        for i in range(1, len(seg)):
            d = haversine(seg[i - 1].lat, seg[i - 1].lon, seg[i].lat, seg[i].lon)
            seg_cum[i] = seg_cum[i - 1] + d

        grade_arr = np.full(len(seg), np.nan)
        if has_ele.sum() >= 2:
            filtered = _median_filter(eles[has_ele], limits.elevation_median_window)
            ele_full = np.full(len(seg), np.nan)
            ele_full[has_ele] = filtered
            cum_at_ele = seg_cum[has_ele]
            for i in range(len(seg)):
                if np.isnan(ele_full[i]):
                    continue
                idx_in_ele = int(np.searchsorted(cum_at_ele, seg_cum[i], side="right"))
                if idx_in_ele < len(cum_at_ele):
                    dx = cum_at_ele[idx_in_ele] - seg_cum[i]
                    if dx > 0:
                        de = filtered[idx_in_ele] - ele_full[i]
                        grade_arr[i] = np.clip(de / dx * 100, -100, 100)

        timed_pts = [(i, seg[i]) for i in range(len(seg)) if seg[i].time is not None]
        if len(timed_pts) >= 2:
            seg_first = timed_pts[0][1].time
            seg_last = timed_pts[-1][1].time
            if first_time is None or seg_first < first_time:
                first_time = seg_first
            if last_time is None or seg_last > last_time:
                last_time = seg_last
            total_time += (seg_last - seg_first).total_seconds()

            for k in range(1, len(timed_pts)):
                idx_prev, p_prev = timed_pts[k - 1]
                idx_cur, p_cur = timed_pts[k]
                dt = (p_cur.time - p_prev.time).total_seconds()
                if dt <= 0:
                    continue
                d = seg_cum[idx_cur] - seg_cum[idx_prev]
                timed_dist += d
                v = d / dt
                speed_kmh = v * 3.6

                interval_speeds.append(speed_kmh)
                mid_dist = global_dist + (seg_cum[idx_prev] + seg_cum[idx_cur]) / 2
                speed_dist_series.append((mid_dist, speed_kmh))

                is_moving = v >= limits.moving_speed_ms
                if is_moving:
                    moving_time += dt
                    moving_dist += d

                g = grade_arr[idx_prev]
                if is_moving and not np.isnan(g):
                    if g > 3:
                        ascent_time += dt
                        ascent_dist += d
                        ascent_speeds.append(speed_kmh)
                    elif g < -3:
                        descent_time += dt
                        descent_dist += d
                        descent_speeds.append(speed_kmh)

        for i, p in enumerate(seg):
            if p.hr is not None:
                hr_samples.append(p.hr)
                hr_dist_series.append((global_dist + seg_cum[i], float(p.hr)))

        global_dist += seg_cum[-1] if len(seg_cum) > 0 else 0

    stop_time = max(0, total_time - moving_time)
    moving_ratio = moving_time / total_time if total_time > 0 else 0.0
    avg_speed = (timed_dist / total_time * 3.6) if total_time > 0 else None
    moving_avg = (moving_dist / moving_time * 3.6) if moving_time > 0 else None
    ascent_avg = (ascent_dist / ascent_time * 3.6) if ascent_time > 0 else None
    descent_avg = (descent_dist / descent_time * 3.6) if descent_time > 0 else None

    max_speed = _rolling_median_max(interval_speeds) if interval_speeds else None
    max_ascent = _rolling_median_max(ascent_speeds) if ascent_speeds else None
    max_descent = _rolling_median_max(descent_speeds) if descent_speeds else None

    avg_hr = int(round(np.mean(hr_samples))) if hr_samples else None
    max_hr = max(hr_samples) if hr_samples else None
    min_hr = min(hr_samples) if hr_samples else None

    heart_graph = _make_graph(hr_dist_series, limits.graph_max_points, int_y=True)
    speed_pat = _make_graph(speed_dist_series, limits.graph_max_points, int_y=False)

    return PerfMetrics(
        started_at=first_time,
        ended_at=last_time,
        total_time_s=int(round(total_time)),
        moving_time_s=int(round(moving_time)),
        stop_time_s=int(round(stop_time)),
        moving_ratio=round(moving_ratio, 4),
        avg_speed_kmh=round(avg_speed, 2) if avg_speed is not None else None,
        moving_avg_speed_kmh=round(moving_avg, 2) if moving_avg is not None else None,
        ascent_avg_speed_kmh=round(ascent_avg, 2) if ascent_avg is not None else None,
        descent_avg_speed_kmh=round(descent_avg, 2) if descent_avg is not None else None,
        max_speed_kmh=round(max_speed, 2) if max_speed is not None else None,
        max_ascent_speed_kmh=round(max_ascent, 2) if max_ascent is not None else None,
        max_descent_speed_kmh=round(max_descent, 2) if max_descent is not None else None,
        avg_heart_rate=avg_hr,
        max_heart_rate=max_hr,
        min_heart_rate=min_hr,
        heart_graph=heart_graph,
        speed_pattern=speed_pat,
    )


def _segment_distances(seg: list[GpxPoint]) -> tuple[float, np.ndarray]:
    cum = np.zeros(len(seg))
    for i in range(1, len(seg)):
        cum[i] = cum[i - 1] + haversine(
            seg[i - 1].lat, seg[i - 1].lon, seg[i].lat, seg[i].lon
        )
    return float(cum[-1]) if len(cum) > 0 else 0.0, cum


def _median_filter(arr: np.ndarray, window: int) -> np.ndarray:
    if window <= 1 or len(arr) <= 1:
        return arr.copy()
    n = len(arr)
    half = window // 2
    out = np.empty(n)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        out[i] = np.median(arr[lo:hi])
    return out


def _hysteresis(eles: np.ndarray, threshold: float) -> tuple[float, float]:
    gain = 0.0
    loss = 0.0
    ref = eles[0]
    for e in eles[1:]:
        d = e - ref
        if d >= threshold:
            gain += d
            ref = e
        elif d <= -threshold:
            loss += -d
            ref = e
    return gain, loss


def _windowed_grade(
    eles: np.ndarray, cum: np.ndarray, window_m: float,
) -> tuple[list[float], list[float]]:
    grades = []
    weights = []
    n = len(eles)
    for i in range(n - 1):
        j = int(np.searchsorted(cum, cum[i] + window_m, side="left"))
        if j >= n:
            j = n - 1
        dx = cum[j] - cum[i]
        if dx <= 0:
            continue
        grade = (eles[j] - eles[i]) / dx * 100
        grade = max(-100, min(100, grade))
        step_d = cum[i + 1] - cum[i] if i + 1 < n else 0
        grades.append(grade)
        weights.append(step_d)
    return grades, weights


def _rolling_median_max(speeds: list[float]) -> float | None:
    if not speeds:
        return None
    arr = np.array(speeds)
    if len(arr) < 3:
        return float(np.max(arr))
    medians = np.array([
        np.median(arr[max(0, i - 1):i + 2]) for i in range(len(arr))
    ])
    return float(np.max(medians))


def _make_graph(
    series: list[tuple[float, float]], max_points: int, *, int_y: bool,
) -> list | None:
    if len(series) < 2:
        return None
    dists = np.array([s[0] for s in series])
    vals = np.array([s[1] for s in series])
    n = min(max_points, len(series))
    target = np.linspace(dists[0], dists[-1], n)
    interp = np.interp(target, dists, vals)
    result = []
    for d, v in zip(target, interp):
        if np.isnan(v) or np.isinf(v):
            continue
        if int_y:
            result.append([round(float(d), 1), int(round(float(v)))])
        else:
            result.append([round(float(d), 1), round(float(v), 1)])
    return result if len(result) >= 2 else None
