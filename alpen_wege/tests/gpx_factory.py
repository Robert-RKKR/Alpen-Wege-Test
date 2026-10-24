# Standard library
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path


def make_gpx(
    points,
    *,
    times=None,
    elevations=None,
    hr=None,
    tracks=1,
    route_only=False,
    waypoints=False,
    creator=None,
    sport_type=None,
):
    header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    header += '<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1"'
    header += ' xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1"'
    if creator:
        header += f' creator="{creator}"'
    header += ">\n"
    body = ""

    if waypoints:
        body += '  <wpt lat="47.0" lon="11.0"><name>WP1</name></wpt>\n'

    pts_per_track = len(points) // tracks if tracks > 0 else len(points)

    for t_idx in range(tracks):
        start = t_idx * pts_per_track
        end = start + pts_per_track if t_idx < tracks - 1 else len(points)
        chunk = points[start:end]
        chunk_times = times[start:end] if times else None
        chunk_eles = elevations[start:end] if elevations else None
        chunk_hr = hr[start:end] if hr else None

        if route_only:
            body += "  <rte>\n"
            for i, (lat, lon) in enumerate(chunk):
                body += f'    <rtept lat="{lat}" lon="{lon}">\n'
                if chunk_eles and i < len(chunk_eles) and chunk_eles[i] is not None:
                    body += f"      <ele>{chunk_eles[i]}</ele>\n"
                if chunk_times and i < len(chunk_times) and chunk_times[i] is not None:
                    body += f"      <time>{chunk_times[i].isoformat()}</time>\n"
                body += "    </rtept>\n"
            body += "  </rte>\n"
        else:
            body += "  <trk>\n"
            if sport_type:
                body += f"    <type>{sport_type}</type>\n"
            body += "    <trkseg>\n"
            for i, (lat, lon) in enumerate(chunk):
                body += f'      <trkpt lat="{lat}" lon="{lon}">\n'
                if chunk_eles and i < len(chunk_eles) and chunk_eles[i] is not None:
                    body += f"        <ele>{chunk_eles[i]}</ele>\n"
                if chunk_times and i < len(chunk_times) and chunk_times[i] is not None:
                    body += f"        <time>{chunk_times[i].isoformat()}</time>\n"
                if chunk_hr and i < len(chunk_hr) and chunk_hr[i] is not None:
                    body += "        <extensions>\n"
                    body += "          <gpxtpx:TrackPointExtension>\n"
                    body += f"            <gpxtpx:hr>{chunk_hr[i]}</gpxtpx:hr>\n"
                    body += "          </gpxtpx:TrackPointExtension>\n"
                    body += "        </extensions>\n"
                body += "      </trkpt>\n"
            body += "    </trkseg>\n"
            body += "  </trk>\n"

    footer = "</gpx>\n"
    return header + body + footer


def straight_line(n=100, start_lat=47.0, start_lon=11.0, step_m=10):
    dlat = step_m / 110540
    pts = [(start_lat + i * dlat, start_lon) for i in range(n)]
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    times = [t0 + timedelta(seconds=i * 3) for i in range(n)]
    eles = [1000.0] * n
    return pts, times, eles


def climb(n=200, gain=100, noise_std=0.5, seed=42):
    rng = random.Random(seed)
    dlat = 5 / 110540
    pts = [(47.0 + i * dlat, 11.0) for i in range(n)]
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    times = [t0 + timedelta(seconds=i * 5) for i in range(n)]
    base = [1000.0 + gain * i / (n - 1) for i in range(n)]
    eles = [e + rng.gauss(0, noise_std) for e in base]
    return pts, times, eles


def save_gpx(content: str, directory: str, name: str = "test.gpx") -> str:
    path = Path(directory) / name
    path.write_text(content, encoding="utf-8")
    return str(path)
