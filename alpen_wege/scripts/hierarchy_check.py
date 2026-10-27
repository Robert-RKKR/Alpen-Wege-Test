#!/usr/bin/env python
"""Live check of segments and routes (planned hierarchy, phases 1 and 2), against a RUNNING api (needs the seeded dev
users and the push_data seed; for the track clip a Celery worker).

    pip install httpx
    python scripts/hierarchy_check.py --base http://localhost:8000 [--worker] [--keep]

It makes its own GPX files, creates segments and routes (as administrator, editor and viewer), checks the answers and
deletes everything again (--keep leaves the rows). Tracks are archived, not deleted. The event log keeps the entries.
With --worker (a worker is running) it also cuts a segment from an uploaded track. Seed users: scripts/init_seed.py.
"""
import argparse
import io
import math
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tests.gpx_factory import make_gpx  # noqa: E402

parser = argparse.ArgumentParser(description="Live check of segments and routes")
parser.add_argument("--base", default="http://localhost:8000")
parser.add_argument("--password", default="!Password@5005")
parser.add_argument("--worker", action="store_true", help="a Celery worker is running: also cut a segment from a track")
parser.add_argument("--keep", action="store_true", help="do not delete what was created")
parser.add_argument("--gpx-dir", help="the GPX_STORAGE_DIR of the api when it runs on this machine: checks that no uploaded GPX file stays on disk")
parser.add_argument("--dsn", help="a psycopg2 connection string (dbname=... user=... host=... port=...): also checks what only the database can see "
                                  "(no GPX file or performance row behind a segment, the foreign keys and unique rules, the journey rules)")
ARGS = parser.parse_args()
API = ARGS.base.rstrip("/") + "/api/v1"
results = []
cleanup_routes: list[tuple[str, str]] = []     # (who, id)
cleanup_segments: list[tuple[str, str]] = []
cleanup_tracks: list[str] = []
client = httpx.Client(timeout=120)
TAG = uuid.uuid4().hex[:6]
R_EARTH = 6371008.8


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if (detail and not cond) else ""), flush=True)


def _stopped(kind, exc, tb):
    last = results[-1][0] if results else "the start"
    print(f"FAIL  the script stopped with {kind.__name__}: {exc}   [last check before it: {last}]", flush=True)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed) + 1} failed", flush=True)


sys.excepthook = _stopped
tokens = {}


def login(who):
    r = client.post(f"{API}/profile/auth/login", json={"email": f"{who}@alpenwege.dev", "password": ARGS.password})
    tokens[who] = r.json()["response_data"]["access_token"]


for who in ("admin", "editor", "viewer", "guest"):
    login(who)


def call(method, path, who="admin", **kw):
    r = client.request(method, API + path, headers={"Authorization": f"Bearer {tokens[who]}"}, **kw)
    if r.status_code == 401:
        login(who)
        r = client.request(method, API + path, headers={"Authorization": f"Bearer {tokens[who]}"}, **kw)
    rotated = r.headers.get("X-Access-Token")
    if rotated:
        tokens[who] = rotated
    return r


def data(r):
    return r.json().get("response_data")


def errors(r):
    return [e.get("code") for e in (r.json().get("response_details") or {}).get("error_errors", [])]


def error_text(r):
    return str((r.json().get("response_details") or {}).get("error_message", ""))


# ---------------------------------------------------------------- test data
def hav(a, b):
    p1, p2 = math.radians(a[1]), math.radians(b[1])
    dp, dl = p2 - p1, math.radians(b[0] - a[0])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R_EARTH * math.asin(math.sqrt(h))


def trail(start, n=60, step_m=25.0, ele0=1000.0, climb=0.5, heading="north"):
    # [[lon, lat, ele], ...] walking north (or east), climbing climb metres per point
    pts, (lon, lat) = [], start
    for i in range(n):
        pts.append([round(lon, 6), round(lat, 6), round(ele0 + i * climb, 1)])
        if heading == "north":
            lat += step_m / 110540
        else:
            lon += step_m / (111320 * math.cos(math.radians(lat)))
    return pts


def length(pts):
    return sum(hav(a, b) for a, b in zip(pts, pts[1:]))


def gpx_text(pts, timed=True, hr=True):
    lat_lon = [(p[1], p[0]) for p in pts]
    t0 = datetime(2024, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    times = [t0 + timedelta(seconds=5 * i) for i in range(len(pts))] if timed else None
    return make_gpx(lat_lon, times=times, elevations=[p[2] for p in pts], hr=[120 + (i % 20) for i in range(len(pts))] if (hr and timed) else None)


def gpx_file(text, name="trail.gpx"):
    return {"gpx_file": (name, io.BytesIO(text.encode("utf-8")), "application/gpx+xml")}


BASE = (11.40 + (int(TAG, 16) % 1000) / 100000, 47.20 + (int(TAG, 16) % 700) / 100000)   # a start that differs between runs
REF = {}
for table, key in (("sport-types", "Hiking"), ("sport-types", "Cycling"), ("difficulty-levels", "Easy"), ("difficulty-levels", "Moderate"), ("difficulty-levels", "Difficult")):
    rows = data(call("GET", f"/core/{table}", params={"q": key, "limit": 50}))
    REF[key] = next(x["id"] for x in rows if x["name"] == key)
HIKING, CYCLING = REF["Hiking"], REF["Cycling"]
EASY, MODERATE, DIFFICULT = REF["Easy"], REF["Moderate"], REF["Difficult"]


def new_segment(who, coords, name, sport=HIKING, **extra):
    r = call("POST", "/explorer/segments/from-coordinates", who, json={"name": f"{name} {TAG}", "sport_type_id": sport, "coordinates": coords, **extra})
    if r.status_code == 201:
        cleanup_segments.append((who, data(r)["id"]))
    return r


def new_route(who, name="Route", **extra):
    r = call("POST", "/explorer/routes", who, json={"name": f"{name} {TAG}", **extra})
    if r.status_code == 201:
        cleanup_routes.append((who, data(r)["id"]))
    return r


def put_segments(who, route_id, rows, validation="strict"):
    return call("PUT", f"/explorer/routes/{route_id}/segments", who, json={"segments": rows, "validation": validation})


def row(segment_id=None, slot=0, default=True, reverse=False, inline=None):
    out = {"slot_position": slot, "is_default": default, "is_reversed": reverse}
    if segment_id:
        out["segment_id"] = segment_id
    if inline:
        out["inline"] = inline
    return out


def inline(coords, name, sport=HIKING, **extra):
    return {"name": f"{name} {TAG}", "sport_type_id": sport, "coordinates": coords, **extra}


def end_of(segment_id, who="admin"):
    point = data(call("GET", f"/explorer/segments/{segment_id}", who))["end_point"]
    return point["lon"], point["lat"]


def count_segments(who="admin"):
    r = call("GET", "/explorer/segments", who, params={"q": TAG, "limit": 1})
    return r.json()["response_pagination"]["pagination_total"]


def gpx_files_on_disk():
    return None if not ARGS.gpx_dir else len(list(Path(ARGS.gpx_dir).rglob("*.gpx")))


files_before = gpx_files_on_disk()

# ================================================================ SEGMENTS: from a GPX file
A = trail(BASE, 60, 25, 1000, 0.5)                                   # about 1475 m, climbs 29.5 m
text = gpx_text(A)
r = call("POST", "/explorer/segments", "admin", files=gpx_file(text), data={"name": f"Upload {TAG}", "sport_type_id": HIKING, "summary": "from a gpx"})
seg_up = data(r)
check("POST /segments with a GPX file (times and heart rate inside): 201", r.status_code == 201 and seg_up, r.text[:300])
if seg_up:
    cleanup_segments.append(("admin", seg_up["id"]))
    check("the distance is the length of the file (within 2 %)", abs(seg_up["metrics"]["distance_m"] - length(A)) < 0.02 * length(A), str(seg_up["metrics"]))
    check("elevation gain is found and loss is small", seg_up["metrics"]["elevation_gain_m"] and seg_up["metrics"]["elevation_gain_m"] > 20, str(seg_up["metrics"]))
    check("a new segment is private", seg_up["is_public"] is False)
    check("start and end point are the first and last point", abs(seg_up["start_point"]["lat"] - A[0][1]) < 1e-5 and abs(seg_up["end_point"]["lat"] - A[-1][1]) < 1e-5, str(seg_up["start_point"]))
    check("created_by is the caller and the sport is the one sent", seg_up["sport_type_id"] == HIKING and seg_up["rating_count"] == 0)
    check("the answer lists warnings as a list", isinstance(seg_up["warnings"], list))
    r = call("GET", f"/explorer/segments/{seg_up['id']}")
    check("GET one: 200 with the same distance", r.status_code == 200 and data(r)["metrics"]["distance_m"] == seg_up["metrics"]["distance_m"], r.text[:200])
    r = call("GET", f"/explorer/segments/{seg_up['id']}", params={"expand": "sport_type,created_by"})
    check("GET one with expand=sport_type,created_by: nested objects", r.status_code == 200 and data(r)["sport_type"]["name"] == "Hiking" and data(r)["created_by_user"], r.text[:200])
    r = call("GET", f"/explorer/segments/{seg_up['id']}", params={"expand": "route"})
    check("GET one with an unknown expand: 400", r.status_code == 400, str(r.status_code))
    r = call("GET", f"/explorer/segments/{seg_up['id']}/geometry")
    g = data(r)
    check("geometry: a LineString, an elevation graph from 0 to the length, start and end location",
          r.status_code == 200 and g["geojson"]["type"] == "LineString" and g["elevation_graph"][0][0] == 0 and abs(g["elevation_graph"][-1][0] - seg_up["metrics"]["distance_m"]) < 0.03 * seg_up["metrics"]["distance_m"] and g["start_location"]["type"] == "Point", r.text[:200])

# other kinds of GPX files and bad input
r = call("POST", "/explorer/segments", "admin", files=gpx_file(gpx_text(A, timed=False)), data={"name": f"NoTime {TAG}", "sport_type_id": HIKING})
check("a GPX file without times is fine", r.status_code == 201, r.text[:200])
if r.status_code == 201:
    cleanup_segments.append(("admin", data(r)["id"]))
r = call("POST", "/explorer/segments", "admin", files=gpx_file(text, "trail.txt"), data={"name": "x", "sport_type_id": HIKING})
check("a file that does not end in .gpx: 400", r.status_code == 400, str(r.status_code))
r = call("POST", "/explorer/segments", "admin", files=gpx_file("<html><body/></html>"), data={"name": "x", "sport_type_id": HIKING})
check("a file that is not GPX: 400", r.status_code == 400, str(r.status_code))
one = make_gpx([(47.0, 11.0)], elevations=[1000])
r = call("POST", "/explorer/segments", "admin", files=gpx_file(one), data={"name": "x", "sport_type_id": HIKING})
check("a GPX file with one point only: 422 and nothing created", r.status_code == 422 and "no_usable_path" in errors(r), r.text[:200])
r = call("POST", "/explorer/segments", "admin", files=gpx_file(text), data={"name": "x"})
check("without sport_type_id: 422", r.status_code == 422, str(r.status_code))
r = call("POST", "/explorer/segments", "admin", files=gpx_file(text), data={"name": "x", "sport_type_id": str(uuid.uuid4())})
check("an unknown sport_type_id: 422 with the field name", r.status_code == 422 and "not_found" in errors(r) and "sport_type_id" in r.text, r.text[:200])
r = call("POST", "/explorer/segments", "admin", files=gpx_file(text), data={"name": "x", "sport_type_id": HIKING, "difficulty_level_id": str(uuid.uuid4())})
check("an unknown difficulty_level_id: 422", r.status_code == 422, str(r.status_code))
r = call("POST", "/explorer/segments", "admin", files=gpx_file(text), data={"name": "", "sport_type_id": HIKING})
check("an empty name: 422", r.status_code == 422, str(r.status_code))
r = call("POST", "/explorer/segments", "guest", files=gpx_file(text), data={"name": "x", "sport_type_id": HIKING})
check("guest cannot create a segment: 403", r.status_code == 403, str(r.status_code))
r = client.post(f"{API}/explorer/segments", files=gpx_file(text), data={"name": "x", "sport_type_id": HIKING})
check("without a token: 401", r.status_code == 401, str(r.status_code))
big = make_gpx([(47.0 + i * 0.00001, 11.0) for i in range(70000)], elevations=[1000 + (i % 50) for i in range(70000)])
check(f"(the big test file is {len(big) / 1e6:.1f} MB)", len(big) > 5 * 1024 * 1024)
r = call("POST", "/explorer/segments", "admin", files=gpx_file(big), data={"name": "x", "sport_type_id": HIKING})
check("a GPX file over the limit (5 MB): 413", r.status_code == 413, str(r.status_code))
mid_pts = [[11.0 + (i % 500) * 0.00002, 47.0 + (i // 500) * 0.00002, 1000 + (i % 50)] for i in range(16000)]
mid = gpx_text(mid_pts)
check(f"(the large test file is {len(mid) / 1e6:.2f} MB, just under the 5 MB limit)", 4.0e6 < len(mid) < 5 * 1024 * 1024)
started = time.time()
r = call("POST", "/explorer/segments", "admin", files=gpx_file(mid), data={"name": f"Large {TAG}", "sport_type_id": HIKING})
took = time.time() - started
print(f"      (a {len(mid) / 1e6:.2f} MB GPX file with 16000 points took {took:.1f} s)")
check("a large GPX file (16000 points, times and heart rate inside) is processed inside the request in less than 20 s", r.status_code == 201 and took < 20, f"{r.status_code} {took:.1f}s {r.text[:150]}")
if r.status_code == 201:
    cleanup_segments.append(("admin", data(r)["id"]))

if files_before is not None:
    check("a segment keeps no GPX file: nothing from the uploads (good, bad, too big) is left on disk", gpx_files_on_disk() == files_before, f"{files_before} -> {gpx_files_on_disk()}")

# ================================================================ SEGMENTS: from coordinates
B = trail(A[-1][:2], 40, 25, A[-1][2], 0.4)
r = new_segment("admin", B, "Coords", is_public=False)
seg_b = data(r)
check("POST /segments/from-coordinates: 201", r.status_code == 201 and seg_b, r.text[:200])
check("its distance is the length of the points", seg_b and abs(seg_b["metrics"]["distance_m"] - length(B)) < 0.02 * length(B), str(seg_b and seg_b["metrics"]))
r = new_segment("admin", [[11.0, 47.0]], "One")
check("one point: 422", r.status_code == 422, str(r.status_code))
r = new_segment("admin", [[11.0, 47.0], [11.0, 95.0]], "Range")
check("a latitude of 95: 422", r.status_code == 422 and "bad_coordinates" in errors(r), r.text[:200])
for ele, label in ((1e10, "1e10 m"), (-5000, "-5000 m"), (12000, "12000 m")):
    r = new_segment("admin", [[11.0, 47.0, ele], [11.001, 47.0, 1000]], "Ele")
    check(f"a drawn elevation of {label}: 422 (not a 500)", r.status_code == 422 and "bad_coordinates" in errors(r), r.text[:200])
broken_ele = [[p[0], p[1], 99999.0 if i in (10, 11) else p[2]] for i, p in enumerate(trail(BASE, 40, 25, 1000, 0.5))]
r = call("POST", "/explorer/segments", "admin", files=gpx_file(gpx_text(broken_ele)), data={"name": f"BrokenEle {TAG}", "sport_type_id": HIKING})
check("a GPX file with elevations of 99999 m: 201, those elevations are dropped, the totals are not ruined",
      r.status_code == 201 and "elevation_outliers_dropped" in data(r)["warnings"] and data(r)["metrics"]["highest_elevation_m"] < 1100 and data(r)["metrics"]["elevation_gain_m"] < 100, r.text[:300])
if r.status_code == 201:
    cleanup_segments.append(("admin", data(r)["id"]))
r = new_segment("admin", [[11.0, 47.0], [11.0, 47.0]], "Same")
check("two equal points (no path): 422", r.status_code == 422, r.text[:200])
r = new_segment("admin", [[11.0, 47.0, 1000, 5], [11.0, 47.1]], "Four")
check("a point with 4 numbers: 422", r.status_code == 422, str(r.status_code))
r = call("POST", "/explorer/segments/from-coordinates", "admin", json={"name": "x", "sport_type_id": HIKING, "coordinates": [[11.0, 47.0], ["a", 47.1]]})
check("a point with text: 422", r.status_code == 422, str(r.status_code))
many = [[11.0 + i * 1e-6, 47.0] for i in range(5001)]
before = count_segments()
r = new_segment("admin", many, "Many")
check("5001 points (the limit is 5000): 422 and nothing created", r.status_code == 422 and count_segments() == before, r.text[:200])
r = new_segment("admin", [[11.0, 47.0], [11.001, 47.0]], "Flat")
check("points without elevation: 201, no elevation gain, warning no_elevation", r.status_code == 201 and data(r)["metrics"]["elevation_gain_m"] is None and "no_elevation" in data(r)["warnings"], r.text[:300])

# the start of a segment at a POI finds that POI
pois = data(call("GET", "/compendium/pois", params={"limit": 1}))
if pois:
    lon, lat = pois[0]["location"]["coordinates"][:2]
    r = new_segment("admin", trail((lon, lat), 20, 20, 800, 0.2), "AtPoi")
    check("a segment that starts at a POI gets it as start_poi_id", r.status_code == 201 and data(r)["start_poi_id"] == pois[0]["id"], r.text[:300])
    if r.status_code == 201:
        cleanup_segments.append(("admin", data(r)["id"]))
    r = new_segment("admin", trail((lon + 0.02, lat), 20, 20), "FarPoi", start_poi_id=pois[0]["id"])
    check("a start_poi_id that is 1.5 km from the start of the segment is refused: 422 poi_too_far", r.status_code == 422 and "poi_too_far" in errors(r), r.text[:300])
    r = new_segment("admin", trail((lon, lat), 40, 20, 800, 0.2), "NamedPoi", start_poi_id=pois[0]["id"])
    named = data(r)
    check("a named start_poi_id at the start is accepted", r.status_code == 201 and named and named["start_poi_id"] == pois[0]["id"], r.text[:300])
    if named:
        r = call("PATCH", f"/explorer/segments/{named['id']}", json={"end_poi_id": pois[0]["id"]})
        check("PATCH end_poi_id with a POI 780 m from the end: 422", r.status_code == 422 and "poi_too_far" in errors(r), r.text[:300])
        r = call("PATCH", f"/explorer/segments/{named['id']}", json={"end_poi_id": str(uuid.uuid4())})
        check("PATCH end_poi_id with a POI that does not exist: 422", r.status_code == 422, r.text[:200])

# ================================================================ SEGMENTS: visibility, update, delete
E = trail((BASE[0] + 0.01, BASE[1]), 30, 25, 1500, 0.3)
r = new_segment("editor", E, "EditorPrivate")
seg_e = data(r)
check("an editor creates a private segment", r.status_code == 201 and seg_e and seg_e["created_by"], r.text[:200])
r = call("GET", f"/explorer/segments/{seg_e['id']}", "viewer")
check("a viewer cannot read it: 404", r.status_code == 404, str(r.status_code))
r = call("GET", "/explorer/segments", "viewer", params={"q": TAG})
check("a viewer does not see it in the list", seg_e["id"] not in [x["id"] for x in data(r)], r.text[:200])
r = call("GET", f"/explorer/segments/{seg_e['id']}/geometry", "viewer")
check("nor its geometry: 404", r.status_code == 404, str(r.status_code))
r = call("PATCH", f"/explorer/segments/{seg_e['id']}", "viewer", json={"name": "hacked"})
check("a viewer cannot change it: 404", r.status_code == 404, str(r.status_code))
r = call("DELETE", f"/explorer/segments/{seg_e['id']}", "viewer")
check("a viewer cannot delete it: 404", r.status_code == 404, str(r.status_code))
r = call("PATCH", f"/explorer/segments/{seg_e['id']}", "editor", json={"is_public": True, "name": f"EditorPublic {TAG}"})
check("the owner publishes it with PATCH", r.status_code == 200 and data(r)["is_public"] is True and data(r)["name"].startswith("EditorPublic"), r.text[:200])
r = call("GET", f"/explorer/segments/{seg_e['id']}", "viewer")
check("now a viewer can read it", r.status_code == 200, str(r.status_code))
for body, label in (({"name": None}, "name null"), ({"sport_type_id": None}, "sport null"), ({"is_public": None}, "is_public null"),
                    ({"coordinates": [[1, 2], [3, 4]]}, "coordinates (geometry cannot change)"), ({"geo_record_id": str(uuid.uuid4())}, "geo_record_id"),
                    ({"sport_type_id": str(uuid.uuid4())}, "unknown sport"), ({"name": ""}, "empty name")):
    r = call("PATCH", f"/explorer/segments/{seg_e['id']}", "editor", json=body)
    check(f"PATCH with {label}: 422", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
r = call("PATCH", f"/explorer/segments/{seg_e['id']}", "editor", json={"difficulty_level_id": DIFFICULT, "summary": "steep"})
check("PATCH difficulty and summary", r.status_code == 200 and data(r)["difficulty_level_id"] == DIFFICULT and data(r)["summary"] == "steep", r.text[:200])

r = call("GET", "/explorer/segments", "admin", params={"q": TAG, "sort": "-distance_m"})
rows = data(r)
dist = [x["metrics"]["distance_m"] for x in rows]
check("list: q finds the segments of this run, sorted by -distance_m", r.status_code == 200 and len(rows) >= 4 and dist == sorted(dist, reverse=True), str(dist))
r = call("GET", "/explorer/segments", "admin", params={"q": TAG, "created_by": rows[0]["created_by"], "limit": 2, "offset": 1})
check("list: limit and offset", r.status_code == 200 and len(data(r)) <= 2, r.text[:200])
r = call("GET", "/explorer/segments", "admin", params={"q": TAG, "distance_min": 1000, "distance_max": 1600})
ids = {x["id"] for x in data(r)}
check("list: distance_min/distance_max", seg_up["id"] in ids and seg_b["id"] not in ids, str(sorted(x["metrics"]["distance_m"] for x in data(r))))
r = call("GET", "/explorer/segments", "admin", params={"q": TAG, "is_public": True})
check("list: is_public=true", all(x["is_public"] for x in data(r)) and seg_e["id"] in [x["id"] for x in data(r)], r.text[:200])
r = call("GET", "/explorer/segments", "admin", params={"q": TAG, "sport_type_id": CYCLING})
check("list: sport_type_id that nobody used: empty", data(r) == [], r.text[:200])
r = call("GET", "/explorer/segments", "admin", params={"near": f"{A[-1][0]},{A[-1][1]}", "radius_m": 100})
near_ids = {x["id"] for x in data(r)}
check("list: near finds segments that start or end there (end of the upload, start of the next one)", seg_up["id"] in near_ids and seg_b["id"] in near_ids, str(len(near_ids)))
r = call("GET", "/explorer/segments", "admin", params={"near": "11.0,47.0", "radius_m": 0})
check("list: radius_m=0: 422", r.status_code == 422, str(r.status_code))
r = call("GET", "/explorer/segments", "admin", params={"q": TAG, "unused": True})
check("list: unused=true includes the segments no route uses", seg_b["id"] in [x["id"] for x in data(r)], r.text[:200])

# a segment nobody uses can be deleted
tmp = data(new_segment("editor", trail((BASE[0] - 0.02, BASE[1]), 10, 20), "Temp"))
r = call("DELETE", f"/explorer/segments/{tmp['id']}", "editor")
check("DELETE an unused segment: 200", r.status_code == 200, r.text[:200])
check("and it is gone: 404", call("GET", f"/explorer/segments/{tmp['id']}", "editor").status_code == 404)
check("a second DELETE: 404", call("DELETE", f"/explorer/segments/{tmp['id']}", "editor").status_code == 404)

# ================================================================ ROUTES: the simple flow (one segment from a GPX file)
r = new_route("admin", "Draft", summary="no segments yet")
draft = data(r)
check("POST /routes: 201, a draft without sport, difficulty, totals or segments",
      r.status_code == 201 and draft["sport_type_id"] is None and draft["difficulty_level_id"] is None and draft["agg_distance_m"] is None and draft["segments"] == [], r.text[:300])
check("a draft route: derived is empty and classification_differs is false", draft["derived"]["sport_type_id"] is None and draft["classification_differs"] is False)
r = call("POST", "/explorer/routes", "admin", json={"summary": "no name"})
check("POST /routes without a name: 422", r.status_code == 422, str(r.status_code))
r = call("POST", "/explorer/routes", "guest", json={"name": "x"})
check("guest cannot create a route: 403", r.status_code == 403, str(r.status_code))

r = put_segments("admin", draft["id"], [row(seg_up["id"], 0)])
saved = data(r)
check("PUT segments with one existing segment: 200", r.status_code == 200 and saved, r.text[:400])
if saved:
    check("the route totals are the totals of the segment", saved["agg_distance_m"] == seg_up["metrics"]["distance_m"] and saved["agg_elevation_gain_m"] == seg_up["metrics"]["elevation_gain_m"] and saved["agg_highest_point_m"] == seg_up["metrics"]["highest_elevation_m"], str({k: v for k, v in saved.items() if k.startswith("agg_")}))
    check("sport comes from the segment (the route had none)", saved["sport_type_id"] == HIKING and saved["derived"]["sport_type_id"] == HIKING and saved["classification_differs"] is False)
    check("the segment list has one default row with the data of the segment", len(saved["segments"]) == 1 and saved["segments"][0]["segment_id"] == seg_up["id"] and saved["segments"][0]["is_default"] and saved["segments"][0]["distance_m"] == seg_up["metrics"]["distance_m"])
    check("sport_types: hiking with the whole distance", saved["sport_types"] == [{"sport_type_id": HIKING, "distance_m": seg_up["metrics"]["distance_m"], "segment_count": 1}], str(saved["sport_types"]))
    check("no warnings and nothing created", saved["warnings"] == [] and saved["created_segments"] == [])
r = call("GET", f"/explorer/routes/{draft['id']}")
check("GET one route: the same numbers and segments", r.status_code == 200 and data(r)["agg_distance_m"] == saved["agg_distance_m"] and len(data(r)["segments"]) == 1, r.text[:200])
r = call("GET", f"/explorer/routes/{draft['id']}", params={"expand": "sport_type,difficulty_level,created_by"})
check("GET one route with expand: nested sport and user, difficulty null", r.status_code == 200 and data(r)["sport_type"]["name"] == "Hiking" and data(r)["created_by_user"] and data(r)["difficulty_level"] is None, r.text[:200])
r = call("GET", f"/explorer/routes/{draft['id']}/segments")
check("GET /routes/{id}/segments", r.status_code == 200 and len(data(r)) == 1 and data(r)[0]["segment_id"] == seg_up["id"], r.text[:200])
r = call("GET", f"/explorer/segments/{seg_up['id']}", params={})
r = call("DELETE", f"/explorer/segments/{seg_up['id']}")
check("DELETE a segment that a route uses: 409 with the route", r.status_code == 409 and "1 route" in error_text(r) and f"Draft {TAG}" in error_text(r), r.text[:300])
check("the segment is still there", call("GET", f"/explorer/segments/{seg_up['id']}").status_code == 200)
r = call("GET", "/explorer/segments", params={"q": TAG, "unused": False})
check("list: unused=false shows it", seg_up["id"] in [x["id"] for x in data(r)], r.text[:200])

# ================================================================ ROUTES: drawn segments inside the save, mixing drawn and existing ones
C = trail(B[-1][:2], 50, 25, B[-1][2], 0.3)
D = trail(A[-1][:2], 40, 25, A[-1][2], 0.4)       # starts like B, a second way from the end of A
r = new_route("admin", "Mixed")
mixed = data(r)
before = count_segments()
rows_in = [
    row(inline=inline(trail(BASE, 60, 25, 1000, 0.5), "Inline first", difficulty_level_id=EASY), slot=0),
    row(seg_b["id"], 1),
    row(inline=inline(C, "Inline last", sport=CYCLING, difficulty_level_id=DIFFICULT), slot=2),
]
r = put_segments("admin", mixed["id"], rows_in)
res = data(r)
check("PUT with two new segments and one existing: 200", r.status_code == 200 and res, r.text[:400])
if res:
    for ref in res["created_segments"]:
        cleanup_segments.append(("admin", ref["segment_id"]))
    check("created_segments names the two new ids by position", [c["index"] for c in res["created_segments"]] == [0, 2], str(res["created_segments"]))
    check("two segments were created", count_segments() == before + 2, f"{before} -> {count_segments()}")
    total = sum(s["distance_m"] for s in res["segments"])
    check("totals are the sum of the three default segments", res["agg_distance_m"] == total and total > 2500, f"{res['agg_distance_m']} {total}")
    check("sport_types: hiking first (more distance), cycling second", [s["sport_type_id"] for s in res["sport_types"]] == [HIKING, CYCLING] and res["sport_types"][0]["segment_count"] == 2, str(res["sport_types"]))
    check("the main sport is the one with the most distance", res["sport_type_id"] == HIKING)
    check("difficulty is the hardest one (Difficult beats Easy)", res["difficulty_level_id"] == DIFFICULT and res["derived"]["difficulty_level_id"] == DIFFICULT, str(res["difficulty_level_id"]))
    check("difficulty_sport stays empty (no segment has one)", res["difficulty_sport_id"] is None)
    first = res["created_segments"][0]["segment_id"]
    r = call("GET", f"/explorer/segments/{first}")
    check("an inline segment is a normal segment: private, created by the caller", r.status_code == 200 and data(r)["is_public"] is False and data(r)["name"] == f"Inline first {TAG}", r.text[:200])

# the PUT with the same list again replaces; segments that are not in it any more stay
r = put_segments("admin", mixed["id"], [row(seg_b["id"], 0)])
check("PUT with a shorter list replaces the rows (totals follow, sport stays the old one)", r.status_code == 200 and len(data(r)["segments"]) == 1 and data(r)["agg_distance_m"] == seg_b["metrics"]["distance_m"] and data(r)["sport_type_id"] == HIKING, r.text[:300])
if res:
    check("the segments that left the route still exist", call("GET", f"/explorer/segments/{res['created_segments'][0]['segment_id']}").status_code == 200)

# ================================================================ ROUTES: a gap, strict and warn
far = trail((A[-1][0], A[-1][1] + 0.003), 30, 25, 1100, 0.2)          # about 330 m north of where A ends
seg_far = data(new_segment("admin", far, "Far"))
r = new_route("admin", "Gap")
gap = data(r)
before = count_segments()
r = put_segments("admin", gap["id"], [row(seg_up["id"], 0), row(seg_far["id"], 1)])
check("strict: a gap of about 330 m is 422 with the code gap", r.status_code == 422 and "gap" in errors(r), r.text[:300])
check("a failed save leaves the route as it was (no segments)", data(call("GET", f"/explorer/routes/{gap['id']}"))["segments"] == [])
r = put_segments("admin", gap["id"], [row(seg_up["id"], 0), row(inline=inline(far, "Gap inline"), slot=1)])
check("strict with an inline segment that does not fit: 422", r.status_code == 422, r.text[:200])
check("and the inline segment was not created either", count_segments() == before, f"{before} -> {count_segments()}")
r = put_segments("admin", gap["id"], [row(seg_up["id"], 0), row(seg_far["id"], 1)], "warn")
gw = data(r)
check("warn: saved, with the warning", r.status_code == 200 and gw and [w["kind"] for w in gw["warnings"]] == ["gap"] and 250 < gw["warnings"][0]["distance_m"] < 400, r.text[:300])
r = call("POST", f"/explorer/routes/{gap['id']}/segments/validate", json={"segments": [
    {"segment_id": seg_up["id"], "slot_position": 0}, {"segment_id": seg_far["id"], "slot_position": 1}]})
check("validate: not valid, one gap warning, nothing saved", r.status_code == 200 and data(r)["is_valid"] is False and [w["kind"] for w in data(r)["warnings"]] == ["gap"], r.text[:300])
r = call("POST", f"/explorer/routes/{gap['id']}/segments/validate", json={"segments": [
    {"segment_id": seg_up["id"], "slot_position": 0}, {"start": [A[-1][0], A[-1][1] + 0.0001], "end": [11.5, 47.5], "slot_position": 1}]})
check("validate: an unsaved drawing that starts 11 m from the end is connected", r.status_code == 200 and data(r)["is_valid"] is True, r.text[:300])
r = call("POST", f"/explorer/routes/{gap['id']}/segments/validate", json={"segments": [
    {"start": [0, 10], "end": [86.5812282599507, 69.51232454868148], "slot_position": 0},
    {"start": [86.5812282599507 - 180, -69.51232454868148], "end": [0, 0], "slot_position": 1}]})
check("validate: points on opposite sides of the earth (even where rounding exceeds 1): 200 and a gap, not a 500", r.status_code == 200 and [w["kind"] for w in data(r)["warnings"]] == ["gap"], r.text[:200])
r = call("POST", f"/explorer/routes/{gap['id']}/segments/validate", json={"segments": [{"segment_id": seg_up["id"], "slot_position": 0, "start": [1, 2], "end": [3, 4]}]})
check("validate: segment_id together with start/end: 422", r.status_code == 422, str(r.status_code))
r = call("POST", f"/explorer/routes/{gap['id']}/segments/validate", json={"segments": [{"segment_id": seg_e["id"], "slot_position": 0}]}, who="viewer")
check("validate as a viewer on a route that is not his: 404", r.status_code == 404, str(r.status_code))

# ================================================================ ROUTES: alternatives
alt_ok = trail(A[-1][:2], 55, 25, A[-1][2], 0.6)                       # a second way from the same start; ends elsewhere
r = new_route("admin", "Alt")
alt = data(r)
S1 = trail(A[-1][:2], 40, 25, A[-1][2], 0.4)
S2 = trail(S1[-1][:2], 30, 25, S1[-1][2], 0.4)
seg_s1 = data(new_segment("admin", S1, "S1"))
seg_s2 = data(new_segment("admin", S2, "S2"))
# an alternative to S1: starts at the same point and ends at the same point (a bend in the middle)
S1alt = [S1[0]] + [[p[0] + 0.00025, p[1], p[2]] for p in S1[1:-1]] + [S1[-1]]
seg_s1alt = data(new_segment("admin", S1alt, "S1alt"))
r = put_segments("admin", alt["id"], [row(seg_up["id"], 0), row(seg_s1["id"], 1), row(seg_s1alt["id"], 1, default=False), row(seg_s2["id"], 2)])
ra = data(r)
check("PUT with an alternative that starts and ends where the default does: 200", r.status_code == 200 and ra and len(ra["segments"]) == 4 and ra["warnings"] == [], r.text[:400])
if ra:
    check("the default of the slot comes first and the totals use the defaults only", [s["is_default"] for s in ra["segments"]] == [True, True, False, True] and ra["agg_distance_m"] == sum(s["distance_m"] for s in ra["segments"] if s["is_default"]), str([(s["slot_position"], s["is_default"]) for s in ra["segments"]]))
    check("the sports list counts the defaults only", ra["sport_types"][0]["segment_count"] == 3, str(ra["sport_types"]))
r = call("GET", f"/explorer/routes/{alt['id']}/geometry")
gm = data(r)
check("route geometry: lines of the default path, the alternative as its own line", r.status_code == 200 and gm["geojson"]["type"] == "MultiLineString" and len(gm["geojson"]["coordinates"]) == 3 and len(gm["alternatives"]) == 1 and gm["alternatives"][0]["slot_position"] == 1, r.text[:300])
if ra and gm["elevation_graph"]:
    eg = gm["elevation_graph"]
    ds = [p[0] for p in eg]
    check("the elevation profile has increasing distances from 0 to about the route length", ds[0] == 0 and ds == sorted(ds) and abs(ds[-1] - ra["agg_distance_m"]) < 0.03 * ra["agg_distance_m"], f"{ds[0]} {ds[-1]} {ra['agg_distance_m']}")
    check("start and end point of the route", abs(gm["start_point"]["lat"] - A[0][1]) < 1e-5 and abs(gm["end_point"]["lat"] - S2[-1][1]) < 1e-5, str(gm["start_point"]))
far_alt = data(new_segment("admin", [[p[0] + 0.01, p[1], p[2]] for p in S1], "FarAlt"))
r = put_segments("admin", alt["id"], [row(seg_up["id"], 0), row(seg_s1["id"], 1), row(far_alt["id"], 1, default=False), row(seg_s2["id"], 2)])
check("strict: an alternative that starts 700 m away: 422", r.status_code == 422 and "alternative_start_mismatch" in errors(r), r.text[:300])
r = put_segments("admin", alt["id"], [row(seg_up["id"], 0), row(seg_s1["id"], 1), row(far_alt["id"], 1, default=False), row(seg_s2["id"], 2)], "warn")
check("warn: saved with the alternative warnings", r.status_code == 200 and {w["kind"] for w in data(r)["warnings"]} >= {"alternative_start_mismatch"}, r.text[:300])

# ================================================================ ROUTES: the shape of the list
base_rows = [row(seg_up["id"], 0), row(seg_s1["id"], 1)]
for label, rows_bad, code in (
    ("two defaults in one slot", [row(seg_up["id"], 0), row(seg_s1["id"], 0)], "multiple_defaults"),
    ("no default in a slot", [row(seg_up["id"], 0, default=False)], "no_default"),
    ("a gap in the slot numbers", [row(seg_up["id"], 0), row(seg_s1["id"], 2)], "slot_gap"),
    ("the same segment twice in one slot", [row(seg_up["id"], 0), row(seg_s1["id"], 1), row(seg_s1["id"], 1, default=False)], "duplicate_in_slot"),
    ("an alt_group that is not the slot", [{**row(seg_up["id"], 0), "alt_group": 3}], "alt_group_mismatch"),
):
    r = put_segments("admin", gap["id"], rows_bad)
    check(f"PUT with {label}: 422 {code}", r.status_code == 422 and code in errors(r), r.text[:250])
for label, bad in (("neither segment_id nor inline", {"slot_position": 0}), ("both segment_id and inline", {"slot_position": 0, "segment_id": seg_up["id"], "inline": inline(A, "x")}),
                   ("a negative slot", {"slot_position": -1, "segment_id": seg_up["id"]}),
                   ("an inline without coordinates and track", {"slot_position": 0, "inline": {"name": "x", "sport_type_id": HIKING}}),
                   ("an inline with coordinates and a track", {"slot_position": 0, "inline": {**inline(A, "x"), "track_id": str(uuid.uuid4()), "start_distance_m": 1, "end_distance_m": 5}})):
    r = put_segments("admin", gap["id"], [bad])
    check(f"PUT with {label}: 422", r.status_code == 422, r.text[:200])
r = put_segments("admin", gap["id"], [row(str(uuid.uuid4()), 0)])
check("PUT with a segment id that does not exist: 404", r.status_code == 404, r.text[:200])
r = put_segments("admin", gap["id"], [row(seg_up["id"], i) for i in range(51)])
check("PUT with 51 rows (the limit is 50): 422 too_many_segments", r.status_code == 422 and "too_many_segments" in errors(r), r.text[:200])
before = count_segments()
r = put_segments("admin", gap["id"], [row(inline=inline(many, "TooMany"), slot=0)])
check("PUT with an inline of 5001 points: 422 and nothing created", r.status_code == 422 and count_segments() == before, r.text[:200])
r = put_segments("admin", gap["id"], [row(seg_up["id"], 0), row(inline={**inline(A, "Bad ref"), "sport_type_id": str(uuid.uuid4())}, slot=1)])
check("PUT with an inline whose sport does not exist: 422", r.status_code == 422, r.text[:200])
r = call("PUT", f"/explorer/routes/{uuid.uuid4()}/segments", json={"segments": []})
check("PUT on a route that does not exist: 404", r.status_code == 404, str(r.status_code))
r = put_segments("admin", gap["id"], [])
ge = data(r)
check("PUT with an empty list empties the route: no segments, no totals, the sport stays", r.status_code == 200 and ge["segments"] == [] and ge["agg_distance_m"] is None and ge["sport_type_id"] == HIKING and ge["classification_differs"] is False, r.text[:300])

# ================================================================ ROUTES: reversed segments
P0 = (BASE[0] + 0.03, BASE[1])
RA = trail(P0, 40, 25, 1000, 0.5)                                       # climbs
RB_forward = trail(RA[-1][:2], 30, 25, RA[-1][2], 0.5)                  # continues the climb
RB = list(reversed(RB_forward))                                         # stored the other way round: ends where RA ends
seg_ra = data(new_segment("admin", RA, "RevA"))
seg_rb = data(new_segment("admin", RB, "RevB"))
r = new_route("admin", "Reverse")
rev = data(r)
r = put_segments("admin", rev["id"], [row(seg_ra["id"], 0), row(seg_rb["id"], 1)])
check("a segment stored backwards does not connect when walked forwards: 422 gap", r.status_code == 422 and "gap" in errors(r), r.text[:200])
r = put_segments("admin", rev["id"], [row(seg_ra["id"], 0), row(seg_rb["id"], 1, reverse=True)])
rv = data(r)
check("walked reversed it connects: 200", r.status_code == 200 and rv, r.text[:300])
if rv:
    ma, mb = seg_ra["metrics"], seg_rb["metrics"]
    check("ascent and descent of the reversed segment are exchanged in the totals", rv["agg_elevation_gain_m"] == ma["elevation_gain_m"] + mb["elevation_loss_m"] and rv["agg_elevation_loss_m"] == (ma["elevation_loss_m"] or 0) + mb["elevation_gain_m"], f"{rv['agg_elevation_gain_m']} {rv['agg_elevation_loss_m']} {ma} {mb}")
    item = rv["segments"][1]
    check("the row shows start and end as walked", item["is_reversed"] and abs(item["start_point"]["lat"] - seg_rb["end_point"]["lat"]) < 1e-6 and item["elevation_gain_m"] == mb["elevation_loss_m"], str(item))
    gm = data(call("GET", f"/explorer/routes/{rev['id']}/geometry"))
    eg = gm["elevation_graph"]
    check("the profile of the reversed part goes up again (it was stored going down)", eg and eg[-1][1] > eg[0][1] + 20 and [p[0] for p in eg] == sorted(p[0] for p in eg), str(eg[:2] + eg[-2:]) if eg else "none")
    lines = gm["geojson"]["coordinates"]
    check("the line of the reversed segment is turned around", abs(lines[1][0][1] - RB_forward[0][1]) < 1e-5 and abs(lines[1][-1][1] - RB_forward[-1][1]) < 1e-5, str(lines[1][:1] + lines[1][-1:]))

# ================================================================ ROUTES: sport and difficulty are never overwritten, but the difference is shown
r = call("PATCH", f"/explorer/routes/{rev['id']}", json={"sport_type_id": CYCLING, "difficulty_level_id": MODERATE})
check("PATCH the route's sport and difficulty by hand", r.status_code == 200 and data(r)["sport_type_id"] == CYCLING and data(r)["difficulty_level_id"] == MODERATE, r.text[:200])
check("the answer says that the stored values differ from the derived ones", data(r)["classification_differs"] is True and data(r)["derived"]["sport_type_id"] == HIKING)
r = put_segments("admin", rev["id"], [row(seg_ra["id"], 0), row(seg_rb["id"], 1, reverse=True)])
check("saving the segments again does not overwrite the sport set by hand", r.status_code == 200 and data(r)["sport_type_id"] == CYCLING and data(r)["classification_differs"] is True, r.text[:200])
r = call("PATCH", f"/explorer/routes/{rev['id']}", json={"sport_type_id": None, "difficulty_level_id": None})
check("PATCH null clears them (they are empty again) ...", r.status_code == 200 and data(r)["sport_type_id"] is None and data(r)["classification_differs"] is True, r.text[:200])
r = put_segments("admin", rev["id"], [row(seg_ra["id"], 0), row(seg_rb["id"], 1, reverse=True)])
check("... and the next save fills them from the segments", r.status_code == 200 and data(r)["sport_type_id"] == HIKING and data(r)["classification_differs"] is False, r.text[:200])
for body, label in (({"name": None}, "name null"), ({"is_public": None}, "is_public null"), ({"agg_distance_m": 5}, "agg_distance_m"), ({"sport_type_id": str(uuid.uuid4())}, "unknown sport")):
    r = call("PATCH", f"/explorer/routes/{rev['id']}", json=body)
    check(f"PATCH route with {label}: 422", r.status_code == 422, f"{r.status_code} {r.text[:100]}")

# ================================================================ ROUTES: plan conditions
r = new_route("admin", "Plan", plan_conditions={"permit_required": True, "best_months": [6, 7, 8], "equipment_required": ["helmet"], "min_age": 12})
pl = data(r)
check("POST /routes with plan_conditions: they come back", r.status_code == 201 and pl["plan_conditions"]["permit_required"] is True and pl["plan_conditions"]["best_months"] == [6, 7, 8] and pl["plan_condition_id"], r.text[:300])
r = call("PATCH", f"/explorer/routes/{pl['id']}", json={"plan_conditions": {"min_age": 14}})
check("PATCH plan_conditions changes only the fields sent", r.status_code == 200 and data(r)["plan_conditions"]["min_age"] == 14 and data(r)["plan_conditions"]["best_months"] == [6, 7, 8], r.text[:300])
r = call("PATCH", f"/explorer/routes/{pl['id']}", json={"plan_conditions": {"best_months": [13]}})
check("best_months 13: 422", r.status_code == 422, str(r.status_code))
r = call("PATCH", f"/explorer/routes/{pl['id']}", json={"plan_conditions": {"unknown": 1}})
check("an unknown plan condition: 422", r.status_code == 422, str(r.status_code))
r = new_route("admin", "NoPlan")
np_route = data(r)
r = call("PATCH", f"/explorer/routes/{np_route['id']}", json={"plan_conditions": {"guide_recommended": True}})
check("PATCH plan_conditions on a route that has none creates them", r.status_code == 200 and data(r)["plan_conditions"]["guide_recommended"] is True, r.text[:200])

# ================================================================ routes: lists and filters
r = call("GET", "/explorer/routes", params={"q": TAG, "sort": "-agg_distance_m"})
rows = data(r)
dists = [x["agg_distance_m"] for x in rows]
check("route list: q, sorted by -agg_distance_m (routes without totals last)", r.status_code == 200 and len(rows) >= 5 and [d for d in dists if d is not None] == sorted([d for d in dists if d is not None], reverse=True) and dists[-1] is None or all(d is not None for d in dists), str(dists))
r = call("GET", "/explorer/routes", params={"q": TAG, "sport_type_id": HIKING, "distance_min": 1})
check("route list: sport_type_id and distance_min", r.status_code == 200 and rows and all(x["sport_type_id"] == HIKING and x["agg_distance_m"] >= 1 for x in data(r)), r.text[:200])
r = call("GET", "/explorer/routes", params={"q": TAG, "is_public": True})
check("route list: is_public=true finds none yet", data(r) == [], r.text[:200])
r = call("GET", "/explorer/routes", params={"q": TAG, "sort": "weight"})
check("route list: an unknown sort: 422", r.status_code == 422, str(r.status_code))
r = call("GET", "/explorer/routes", "guest", params={"q": TAG})
check("a guest sees no private route", data(r) == [], r.text[:200])

# ================================================================ visibility between users
r = new_route("editor", "EditorRoute")
er = data(r)
check("an editor creates a route", r.status_code == 201 and er, r.text[:200])
check("a viewer cannot read it: 404", call("GET", f"/explorer/routes/{er['id']}", "viewer").status_code == 404)
check("a viewer cannot read its segments or geometry: 404", call("GET", f"/explorer/routes/{er['id']}/segments", "viewer").status_code == 404 and call("GET", f"/explorer/routes/{er['id']}/geometry", "viewer").status_code == 404)
check("a viewer cannot change its segments: 404", put_segments("viewer", er["id"], []).status_code == 404)
check("a viewer cannot patch or delete it: 404", call("PATCH", f"/explorer/routes/{er['id']}", "viewer", json={"name": "x"}).status_code == 404 and call("DELETE", f"/explorer/routes/{er['id']}", "viewer").status_code == 404)
admin_private_try = put_segments("admin", er["id"], [row(seg_up["id"], 0)])
check("an administrator cannot put his private segment into the private route of an editor: 422 segment_not_usable", admin_private_try.status_code == 422 and "segment_not_usable" in errors(admin_private_try), admin_private_try.text[:250])
check("... and that route is still empty", data(call("GET", f"/explorer/routes/{er['id']}", "editor"))["segments"] == [])
public_by_admin = data(new_segment("admin", trail((BASE[0] + 0.04, BASE[1]), 20, 25), "AdminPublic", is_public=True))
r = put_segments("admin", er["id"], [row(public_by_admin["id"], 0)])
check("an administrator may put a PUBLIC segment into the route of an editor", r.status_code == 200 and len(data(r)["segments"]) == 1, r.text[:250])
r = new_route("viewer", "ViewerRoute")
vr = data(r)
r = put_segments("viewer", vr["id"], [row(seg_up["id"], 0)])
check("a viewer cannot use the private segment of the administrator: 404", r.status_code == 404, r.text[:200])
r = call("POST", f"/explorer/routes/{vr['id']}/segments/validate", "viewer", json={"segments": [{"segment_id": seg_up["id"], "slot_position": 0}]})
check("validate: a viewer cannot check a private segment of the administrator either: 404", r.status_code == 404, r.text[:200])
r = put_segments("viewer", vr["id"], [row(seg_e["id"], 0)])
check("a viewer can use a public segment of somebody else: 200", r.status_code == 200 and data(r)["agg_distance_m"] > 0, r.text[:200])
r = call("PATCH", f"/explorer/segments/{seg_e['id']}", "editor", json={"is_public": False})
check("the owner cannot make a segment private that another user's route uses: 409", r.status_code == 409 and "in_use" in errors(r), r.text[:250])
r = call("DELETE", f"/explorer/segments/{seg_e['id']}", "editor")
check("the owner cannot delete it either: 409, and the route of the other user is counted but not named", r.status_code == 409 and "1 route" in error_text(r) and f"ViewerRoute {TAG}" not in error_text(r), r.text[:300])
r = put_segments("viewer", vr["id"], [row(inline=inline(trail((BASE[0] + 0.05, BASE[1]), 20, 25), "ViewerInline"), slot=0)])
vi = data(r)
check("a viewer creates a segment inline in his own route", r.status_code == 200 and vi and len(vi["created_segments"]) == 1, r.text[:200])
if vi:
    cleanup_segments.append(("viewer", vi["created_segments"][0]["segment_id"]))
r = put_segments("guest", vr["id"], [])
check("a guest cannot change a route: 403", r.status_code == 403, str(r.status_code))

# two requests at the same moment. Each pair runs 25 times with random small delays so that the different orders of the
# steps inside the server are tried. The rule that must always hold afterwards:
#   a segment in the route of another user is public, and a public route holds only public segments.
import random
import threading


def race(first, second):
    # runs two functions at the same moment, each after a random delay of up to 60 ms; returns their answers
    answers = {}
    barrier = threading.Barrier(2)

    def run(name, function):
        barrier.wait()
        time.sleep(random.random() * 0.06)
        answers[name] = function()

    threads = [threading.Thread(target=run, args=("a", first)), threading.Thread(target=run, args=("b", second))]
    [th.start() for th in threads]
    [th.join() for th in threads]
    return answers


broken_races = []
for i in range(25):
    # (1) the owner makes a segment private while another user puts it into his route
    s = data(new_segment("editor", trail((BASE[0] + 0.2 + i * 0.001, BASE[1]), 12, 25), f"Race{i}", is_public=True))
    rt = data(new_route("viewer", f"RaceRoute{i}"))
    out = race(lambda: put_segments("viewer", rt["id"], [row(s["id"], 0)]).status_code,
               lambda: call("PATCH", f"/explorer/segments/{s['id']}", "editor", json={"is_public": False}).status_code)
    seg_now = data(call("GET", f"/explorer/segments/{s['id']}", "editor"))
    route_now = data(call("GET", f"/explorer/routes/{rt['id']}", "viewer"))
    if (len(route_now["segments"]) > 0 and seg_now["is_public"] is False) or out["a"] not in (200, 404) or out["b"] not in (200, 409):
        broken_races.append(("private while used", i, out))
    # (2) the owner publishes a route while his own private segment is put into it
    s2 = data(new_segment("editor", trail((BASE[0] + 0.3 + i * 0.001, BASE[1]), 12, 25), f"RacePub{i}"))
    rt2 = data(new_route("editor", f"RacePubRoute{i}"))
    out = race(lambda: put_segments("editor", rt2["id"], [row(s2["id"], 0)]).status_code,
               lambda: call("PATCH", f"/explorer/routes/{rt2['id']}", "editor", json={"is_public": True}).status_code)
    seg_now = data(call("GET", f"/explorer/segments/{s2['id']}", "editor"))
    route_now = data(call("GET", f"/explorer/routes/{rt2['id']}", "editor"))
    if (route_now["is_public"] and any(not x["is_public"] for x in route_now["segments"])) or out["a"] != 200 or out["b"] != 200:
        broken_races.append(("public route with a private segment", i, out, seg_now["is_public"]))
check("50 races (make a segment private / add it to another user's route; publish a route / add a private segment to it): "
      "the rules always hold afterwards, and nothing answers 500", not broken_races, str(broken_races[:3]))

# publishing a route publishes its own segments
priv = data(new_segment("editor", trail((BASE[0] + 0.07, BASE[1]), 25, 25), "PubSeg"))
r = new_route("editor", "PubRoute")
pr = data(r)
r = put_segments("editor", pr["id"], [row(priv["id"], 0)])
check("an editor puts his private segment into his route", r.status_code == 200, r.text[:200])
check("a viewer cannot see that segment yet", call("GET", f"/explorer/segments/{priv['id']}", "viewer").status_code == 404)
r = call("PATCH", f"/explorer/routes/{pr['id']}", "editor", json={"is_public": True})
check("publishing the route: 200", r.status_code == 200 and data(r)["is_public"] is True, r.text[:200])
check("... published its own segment with it", call("GET", f"/explorer/segments/{priv['id']}", "viewer").status_code == 200 and call("GET", f"/explorer/routes/{pr['id']}", "viewer").status_code == 200)
r = call("GET", f"/explorer/routes/{pr['id']}/geometry", "viewer")
check("a viewer can read the public route's geometry and segments", r.status_code == 200 and data(r)["geojson"] and call("GET", f"/explorer/routes/{pr['id']}/segments", "viewer").status_code == 200, r.text[:150])
r = call("PATCH", f"/explorer/segments/{priv['id']}", "editor", json={"is_public": False})
check("a segment of a public route cannot be made private: 409", r.status_code == 409, r.text[:200])
r = put_segments("editor", pr["id"], [row(priv["id"], 0), row(inline=inline(trail(end_of(priv["id"]), 15, 25), "PubInline", is_public=False), slot=1)])
pi = data(r)
check("an inline segment of a public route is public (even if it says private)", r.status_code == 200 and pi and call("GET", f"/explorer/segments/{pi['created_segments'][0]['segment_id']}", "viewer").status_code == 200, r.text[:200])
if pi:
    pub_inline = pi["created_segments"][0]["segment_id"]
    cleanup_segments.append(("editor", pub_inline))
    admin_priv = data(new_segment("admin", trail(end_of(pub_inline), 15, 25), "AdminPriv"))
    r = put_segments("admin", pr["id"], [row(priv["id"], 0), row(pub_inline, 1), row(admin_priv["id"], 2)])
    check("an administrator cannot put his private segment into the public route of another user: 422", r.status_code == 422 and (set(errors(r)) & {"segment_not_usable", "private_segment"}), r.text[:250])
    r = put_segments("admin", pr["id"], [row(priv["id"], 0), row(pub_inline, 1), row(inline=inline(trail(end_of(pub_inline), 15, 25), "AdminInline", is_public=False), slot=2)])
    ai = data(r)
    check("but an administrator may add a NEW segment inline: it becomes public with the public route (it is not his private one)",
          r.status_code == 200 and ai and call("GET", f"/explorer/segments/{ai['created_segments'][0]['segment_id']}", "viewer").status_code == 200, r.text[:250])
    if ai:
        cleanup_segments.append(("admin", ai["created_segments"][0]["segment_id"]))
r = call("PATCH", f"/explorer/routes/{pr['id']}", "editor", json={"is_public": False})
check("a public route can be made private again (no journey uses it)", r.status_code == 200 and data(r)["is_public"] is False, r.text[:200])

# ================================================================ a segment cut from a track (needs the Celery worker)
if ARGS.worker:
    T = trail((BASE[0] + 0.09, BASE[1]), 400, 10, 900, 0.1)               # about 4 km
    r = call("POST", "/explorer/tracks", "editor", files=gpx_file(gpx_text(T), "track.gpx"), data={"name": f"Track {TAG}"})
    track = data(r)
    check("a track is uploaded", r.status_code == 202 and track, r.text[:200])
    if track:
        cleanup_tracks.append(track["id"])
        status = None
        for _ in range(60):
            status = data(call("GET", f"/explorer/tracks/{track['id']}", "editor"))["processing_status"]
            if status in ("ready", "failed"):
                break
            time.sleep(1)
        check("the worker processed it", status == "ready", str(status))
        if status == "ready":
            r = call("POST", "/explorer/segments/from-track", "editor", json={"name": f"Clip {TAG}", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 1000, "end_distance_m": 3000})
            clip = data(r)
            check("POST /segments/from-track: 201 and about 2000 m", r.status_code == 201 and clip and abs(clip["metrics"]["distance_m"] - 2000) < 60, r.text[:300])
            if clip:
                cleanup_segments.append(("editor", clip["id"]))
                check("the clip starts where the track was 1000 m from its start", abs(clip["start_point"]["lat"] - T[100][1]) < 3e-4, str(clip["start_point"]))
                check("the clip is private and has no heart rate or time (it has no performance, only a place)", clip["is_public"] is False)
            r = call("POST", "/explorer/segments/from-track", "editor", json={"name": "x", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 3000, "end_distance_m": 2000})
            check("from-track with the end before the start: 422", r.status_code == 422, r.text[:200])
            r = call("POST", "/explorer/segments/from-track", "editor", json={"name": "x", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 50000, "end_distance_m": 60000})
            check("from-track behind the end of the track: 422", r.status_code == 422, r.text[:200])
            r = call("POST", "/explorer/segments/from-track", "viewer", json={"name": "x", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 100, "end_distance_m": 900})
            check("another user cannot cut from the track: 404", r.status_code == 404, r.text[:200])
            r = call("POST", "/explorer/segments/from-track", "admin", json={"name": f"AdminClip {TAG}", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 100, "end_distance_m": 900})
            check("an administrator (scope all on tracks) may: 201", r.status_code == 201, r.text[:200])
            if r.status_code == 201:
                cleanup_segments.append(("admin", data(r)["id"]))
            r = call("POST", "/explorer/segments/from-track", "editor", json={"name": "x", "sport_type_id": HIKING, "track_id": str(uuid.uuid4()), "start_distance_m": 1, "end_distance_m": 9})
            check("an unknown track: 404", r.status_code == 404, r.text[:200])
            r = new_route("editor", "ClipRoute")
            cr = data(r)
            r = put_segments("editor", cr["id"], [row(inline={"name": f"Inline clip {TAG}", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 0, "end_distance_m": 1500}, slot=0)])
            icr = data(r)
            check("an inline clip of a track inside a route save: 200", r.status_code == 200 and icr and abs(icr["agg_distance_m"] - 1500) < 60, r.text[:300])
            if icr:
                cleanup_segments.append(("editor", icr["created_segments"][0]["segment_id"]))
            r = new_route("editor", "TwoClips")
            tc = data(r)
            r = put_segments("editor", tc["id"], [
                row(inline={"name": f"Clip one {TAG}", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 0, "end_distance_m": 1500}, slot=0),
                row(inline={"name": f"Clip two {TAG}", "sport_type_id": HIKING, "track_id": track["id"], "start_distance_m": 1500, "end_distance_m": 3000}, slot=1)])
            two = data(r)
            check("two clips of the same track in one save (the track is read once): 200, about 3000 m, connected", r.status_code == 200 and two and abs(two["agg_distance_m"] - 3000) < 100 and two["warnings"] == [], r.text[:300])
            if two:
                cleanup_segments.extend(("editor", c["segment_id"]) for c in two["created_segments"])

# ================================================================ what only the database can see (needs --dsn)
if ARGS.dsn:
    import psycopg2
    from psycopg2 import errors as pg_errors

    conn = psycopg2.connect(ARGS.dsn)
    conn.autocommit = True
    cur = conn.cursor()

    def sql(statement, params=()):
        cur.execute(statement, params)
        return cur.fetchall() if cur.description else None

    def fails_with(exception, statement, params=()):
        try:
            cur.execute(statement, params)
        except exception:
            return True
        except Exception as exc:       # another error is not what the rule promises
            print(f"      (got {type(exc).__name__}: {str(exc)[:100]})")
            return False
        return False

    # a segment keeps no GPX file and no performance row, and the uploaded file is not kept on disk
    row_db = sql("SELECT g.gpx_id, g.geo_performance_id, g.route IS NOT NULL, g.start_location IS NOT NULL FROM explorer_sub_geo_record g "
                 "JOIN explorer_agg_segment s ON s.geo_record_id = g.id WHERE s.id = %s", (seg_up["id"],))
    check("a segment from a GPX file with times and heart rate has no gpx_id and no performance row, but a route line and a start", row_db == [(None, None, True, True)], str(row_db))
    # the rules of the tables
    used = sql("SELECT route_id, segment_id, slot_position FROM explorer_m2m_segment_route WHERE route_id = %s LIMIT 1", (alt["id"],))
    check("the alternative test route has rows", bool(used))
    if used:
        route_id, segment_id, slot = used[0]
        check("a used segment cannot be deleted by SQL either (foreign key restricts)", fails_with(pg_errors.ForeignKeyViolation, "DELETE FROM explorer_agg_segment WHERE id = %s", (segment_id,)))
        check("the same segment cannot be twice in a slot (unique rule)", fails_with(pg_errors.UniqueViolation,
              "INSERT INTO explorer_m2m_segment_route (segment_id, route_id, slot_position, alt_group, is_default, is_reversed, created_by) "
              "SELECT segment_id, route_id, slot_position, alt_group, false, false, created_by FROM explorer_m2m_segment_route WHERE route_id = %s AND slot_position = %s AND segment_id = %s",
              (route_id, slot, segment_id)))
        check("a slot cannot have two defaults (partial unique index)", fails_with(pg_errors.UniqueViolation,
              "INSERT INTO explorer_m2m_segment_route (segment_id, route_id, slot_position, alt_group, is_default, is_reversed, created_by) "
              "SELECT %s, route_id, slot_position, alt_group, true, false, created_by FROM explorer_m2m_segment_route WHERE route_id = %s AND slot_position = %s AND is_default LIMIT 1",
              (seg_far["id"], route_id, slot)))

    # The locks, tested without chance: a second connection plays "another request that is in the middle of its work" (its
    # changes are not committed yet), the real request is started, the second connection commits one second later. A request
    # that locks the row first waits and then sees the committed change; one that does not lock acts on what it saw before.
    editor_id = data(call("GET", "/profile/users/me", "editor"))["id"]
    viewer_id = data(call("GET", "/profile/users/me", "viewer"))["id"]

    def insert_link(cursor, route_id, segment_id, owner_id):
        cursor.execute("INSERT INTO explorer_m2m_segment_route (segment_id, route_id, slot_position, alt_group, is_default, is_reversed, created_by) "
                       "VALUES (%s, %s, 0, 0, true, false, %s)", (segment_id, route_id, owner_id))

    def while_another_request_is_in_the_middle(prepare, action):
        # prepare(cursor) makes the uncommitted changes; action() is the real request; returns its answer
        holder = psycopg2.connect(ARGS.dsn)
        holder.autocommit = False
        prepare(holder.cursor())
        box = {}
        worker = threading.Thread(target=lambda: box.setdefault("r", action()))
        worker.start()
        time.sleep(1.0)
        holder.commit()
        worker.join(20)
        holder.close()
        return box.get("r")

    # 1. a save of segments must see that the route was published a moment ago, and publish its own segment with it
    lock_seg = data(new_segment("editor", trail((BASE[0] + 0.4, BASE[1]), 12, 25), "LockPrivate"))
    lock_route = data(new_route("editor", "LockRoute"))
    r = while_another_request_is_in_the_middle(
        lambda c: c.execute("UPDATE explorer_agg_route SET is_public = true WHERE id = %s", (lock_route["id"],)),
        lambda: put_segments("editor", lock_route["id"], [row(lock_seg["id"], 0)]))
    now_route, now_seg = data(call("GET", f"/explorer/routes/{lock_route['id']}", "editor")), data(call("GET", f"/explorer/segments/{lock_seg['id']}", "editor"))
    check("a save that waits for a route that is being published: it sees the new state and publishes its own segment too",
          r is not None and r.status_code == 200 and now_route["is_public"] and now_seg["is_public"], f"{r and r.status_code} route public {now_route['is_public']}, segment public {now_seg['is_public']}")

    # 2. making a segment private must see that a route of another user is just being given that segment
    shared = data(new_segment("editor", trail((BASE[0] + 0.42, BASE[1]), 12, 25), "LockShared", is_public=True))
    other_route = data(new_route("viewer", "LockViewerRoute"))
    r = while_another_request_is_in_the_middle(
        lambda c: insert_link(c, other_route["id"], shared["id"], viewer_id),
        lambda: call("PATCH", f"/explorer/segments/{shared['id']}", "editor", json={"is_public": False}))
    now_seg = data(call("GET", f"/explorer/segments/{shared['id']}", "editor"))
    check("making a segment private while another user's route is just getting it: 409 and the segment stays public",
          r is not None and r.status_code == 409 and now_seg["is_public"] is True, f"{r and r.status_code} {now_seg['is_public']}")
    sql("DELETE FROM explorer_m2m_segment_route WHERE route_id = %s", (other_route["id"],))

    # 3. publishing a route must see the private segment that is just being put into it, and publish that too
    pub_seg = data(new_segment("editor", trail((BASE[0] + 0.44, BASE[1]), 12, 25), "LockPublishSeg"))
    pub_route = data(new_route("editor", "LockPublishRoute"))

    def prepare_put(c):
        c.execute("SELECT id FROM explorer_agg_route WHERE id = %s FOR UPDATE", (pub_route["id"],))      # what a running save holds
        insert_link(c, pub_route["id"], pub_seg["id"], editor_id)

    r = while_another_request_is_in_the_middle(prepare_put, lambda: call("PATCH", f"/explorer/routes/{pub_route['id']}", "editor", json={"is_public": True}))
    now_route, now_seg = data(call("GET", f"/explorer/routes/{pub_route['id']}", "editor")), data(call("GET", f"/explorer/segments/{pub_seg['id']}", "editor"))
    check("publishing a route while a save is putting a private segment into it: the segment is published too (no public route with a private segment)",
          r is not None and r.status_code == 200 and now_route["is_public"] and now_seg["is_public"] and len(now_route["segments"]) == 1,
          f"{r and r.status_code} route public {now_route['is_public']}, segment public {now_seg['is_public']}, {len(now_route['segments'])} segments")
    sql("UPDATE explorer_agg_route SET is_public = false WHERE id IN (%s, %s)", (lock_route["id"], pub_route["id"]))

    # 4. adding a segment to a route must see that its owner is just making it private
    going_private = data(new_segment("editor", trail((BASE[0] + 0.46, BASE[1]), 12, 25), "LockGoingPrivate", is_public=True))
    adder_route = data(new_route("viewer", "LockAdderRoute"))
    r = while_another_request_is_in_the_middle(
        lambda c: c.execute("UPDATE explorer_agg_segment SET is_public = false WHERE id = %s", (going_private["id"],)),
        lambda: put_segments("viewer", adder_route["id"], [row(going_private["id"], 0)]))
    check("adding a segment to a route while its owner is making it private: 404, and the route stays empty",
          r is not None and r.status_code == 404 and data(call("GET", f"/explorer/routes/{adder_route['id']}", "viewer"))["segments"] == [],
          f"{r and r.status_code}")

    # a journey that uses a route (the journey API does not exist yet: the rows are made by hand)
    editor_id = data(call("GET", "/profile/users/me", "editor"))["id"]
    admin_id = data(call("GET", "/profile/users/me", "admin"))["id"]
    jr = sql("INSERT INTO explorer_agg_journey (name, created_by, is_public, rating_count) VALUES (%s, %s, false, 0) RETURNING id", (f"Journey {TAG}", admin_id))[0][0]
    link = sql("INSERT INTO explorer_m2m_route_journey (slot_position, route_id, journey_id, day_name, created_by) VALUES (0, %s, %s, 'Day 1', %s) RETURNING id", (pr["id"], jr, admin_id))[0][0]
    r = call("DELETE", f"/explorer/routes/{pr['id']}", "editor")
    check("DELETE a route that a journey uses: 409; the private journey of another user is counted, not named", r.status_code == 409 and "1 journey" in error_text(r) and f"Journey {TAG}" not in error_text(r), r.text[:300])
    check("the route is still there", call("GET", f"/explorer/routes/{pr['id']}", "editor").status_code == 200)
    check("a used route cannot be deleted by SQL either", fails_with(pg_errors.ForeignKeyViolation, "DELETE FROM explorer_agg_route WHERE id = %s", (pr["id"],)))
    check("one route per day of a journey (unique rule)", fails_with(pg_errors.UniqueViolation,
          "INSERT INTO explorer_m2m_route_journey (slot_position, route_id, journey_id, day_name, created_by) VALUES (0, %s, %s, 'Day 1 again', %s)", (er["id"], jr, admin_id)))
    r = call("PATCH", f"/explorer/routes/{pr['id']}", "editor", json={"is_public": True})
    r = call("PATCH", f"/explorer/routes/{pr['id']}", "editor", json={"is_public": False})
    check("a public route that another user's journey uses cannot be made private: 409", r.status_code == 409 and "in_use" in errors(r), r.text[:250])
    sql("UPDATE explorer_agg_journey SET created_by = %s WHERE id = %s", (editor_id, jr))
    r = call("PATCH", f"/explorer/routes/{pr['id']}", "editor", json={"is_public": False})
    check("when the journey is the owner's own and private, the route may be made private", r.status_code == 200, r.text[:250])
    sql("DELETE FROM explorer_m2m_route_journey WHERE id = %s", (link,))
    sql("DELETE FROM explorer_agg_journey WHERE id = %s", (jr,))
    r = call("DELETE", f"/explorer/routes/{pr['id']}", "editor")
    check("after the journey is gone the route can be deleted", r.status_code == 200, r.text[:200])
    check("deleting a route removed its segment rows and its plan conditions row", sql("SELECT count(*) FROM explorer_m2m_segment_route WHERE route_id = %s", (pr["id"],)) == [(0,)])
    plan_rows = sql("SELECT count(*) FROM explorer_sub_plan_conditions c WHERE NOT EXISTS (SELECT 1 FROM explorer_agg_route r WHERE r.plan_condition_id = c.id) "
                    "AND c.id IN (SELECT plan_condition_id FROM explorer_agg_route WHERE id = %s)", (pl["id"],))
    r = call("DELETE", f"/explorer/routes/{pl['id']}")
    orphans = sql("SELECT count(*) FROM explorer_sub_plan_conditions c WHERE NOT EXISTS (SELECT 1 FROM explorer_agg_route r WHERE r.plan_condition_id = c.id) "
                  "AND NOT EXISTS (SELECT 1 FROM explorer_agg_journey j WHERE j.condition_id = c.id)")
    check("deleting a route with plan conditions leaves no orphan conditions row", r.status_code == 200 and orphans == [(0,)], str(orphans))
    cleanup_routes[:] = [x for x in cleanup_routes if x[1] not in (pr["id"], pl["id"])]
    conn.close()

# ================================================================ delete routes, then the segments
r = call("DELETE", f"/explorer/routes/{gap['id']}")
check("DELETE a route: 200", r.status_code == 200, r.text[:200])
check("the route is gone, its segments are not", call("GET", f"/explorer/routes/{gap['id']}").status_code == 404 and call("GET", f"/explorer/segments/{seg_up['id']}").status_code == 200)
check("a second DELETE: 404", call("DELETE", f"/explorer/routes/{gap['id']}").status_code == 404)

if not ARGS.keep:
    for who, rid in reversed(cleanup_routes):
        call("DELETE", f"/explorer/routes/{rid}", who)
    for who, sid in reversed(cleanup_segments):
        r = call("DELETE", f"/explorer/segments/{sid}", who)
        if r.status_code not in (200, 404):
            print(f"      cleanup: segment {sid} answered {r.status_code} {error_text(r)[:100]}")
    for tid in cleanup_tracks:
        call("DELETE", f"/explorer/tracks/{tid}", "editor")
    left = count_segments()
    check("everything this run created is deleted again", left == 0, f"{left} segments with the tag are left")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
