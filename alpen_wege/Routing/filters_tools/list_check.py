#!/usr/bin/env python
"""Live check of paging, sorting and filters of every list GET endpoint, against a RUNNING api (needs the seeded dev
users and the compendium seed: push_data/seed.py).

    pip install httpx
    python scripts/list_check.py --base http://localhost:8000 [--gpx /tmp/full.gpx]

Part 1 goes through every list route that the OpenAPI document shows (limit, offset, sort, every filter once, the
errors). Part 2 compares the filters of the POI and region lists with a full export of the same data computed in
Python. Part 3b temporarily sets the viewer's read scope of POIs, regions and lookup tables to "own" and puts it back
(skip it with --skip-policy-step; if the script is killed, the line "RESTORE" printed before each change says how to undo
it). Part 3 creates a few rows (gear, a card, a post, a poi-region link and, with --gpx, a track), checks the
filters on them and deletes them again (a track is archived, not deleted: that is what DELETE does). The event log
keeps the rows that these writes cause. Needs no Celery worker (the track stays "pending").
Make a sample GPX with: python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx
Seed users: scripts/init_seed.py (password !Password@5005, admin/editor/viewer/guest @alpenwege.dev).
"""
import argparse
import atexit
import math
import os
import sys
import uuid
from datetime import datetime

import httpx

parser = argparse.ArgumentParser(description="Live check of paging, sorting and filters of the list endpoints")
parser.add_argument("--base", default="http://localhost:8000")
parser.add_argument("--gpx", default="/tmp/full.gpx")
parser.add_argument("--password", default="!Password@5005")
parser.add_argument("--gzip", action="store_true", help="also check compression (the application was started with GZipMiddleware: apply_filters.py --gzip)")
parser.add_argument("--skip-policy-step", action="store_true", help="do not change access policies (part 3b); use it on a database that other people are using")
ARGS = parser.parse_args()
BASE = ARGS.base.rstrip("/")
API = BASE + "/api/v1"
results = []
created = []

SAMPLE = uuid.UUID(int=1).hex
SAMPLE = str(uuid.UUID(int=1))
BY_NAME = {                       # a valid value for the filters that only accept some values or a format
    "group": "viewer", "user_group": "viewer", "action": "read", "scope": "all", "processing_status": "ready",
    "status": "queued", "iso_code": "CH", "bbox": "7,46,8,47", "near": "7.7,46.0", "radius_m": "1000", "q": "ab",
}


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if (detail and not cond) else ""), flush=True)


def _stopped(kind, exc, tb):
    last = results[-1][0] if results else "the start"
    print(f"FAIL  the script stopped with {kind.__name__}: {exc}   [last check before it: {last}]", flush=True)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed) + 1} failed", flush=True)


sys.excepthook = _stopped
client = httpx.Client(timeout=120)
tokens = {}


def login(who):
    r = client.post(f"{API}/profile/auth/login", json={"email": f"{who}@alpenwege.dev", "password": ARGS.password})
    tokens[who] = r.json()["response_data"]["access_token"] if r.status_code == 200 else None


def call(method, path, who="admin", **kw):
    # Tokens are short-lived and rotate: adopt X-Access-Token when a response carries one, log in again on a 401.
    headers = kw.pop("headers", {})
    for attempt in (1, 2):
        r = client.request(method, API + path, headers={"Authorization": f"Bearer {tokens[who]}", **headers}, **kw)
        if r.status_code == 401 and attempt == 1 and "files" not in kw:
            login(who)
            continue
        break
    if r.headers.get("X-Access-Token"):
        tokens[who] = r.headers["X-Access-Token"]
    return r


restore = []       # (path, json) of policy changes to undo


def clean_up():
    for path, payload in reversed(restore):
        call("PATCH", path, json=payload)
    restore.clear()
    for path in reversed(created):
        call("DELETE", path)
    created.clear()


atexit.register(clean_up)


def body(r):
    return r.json().get("response_data")


def meta(r):
    return r.json().get("response_pagination") or {}


def errors(r):
    return (r.json().get("response_details") or {}).get("error_errors") or []


def get(path, who="admin", **params):
    return call("GET", path, who, params={k: v for k, v in params.items() if v is not None})


def ids(r):
    return [row["id"] for row in body(r)]


def offset_name(path):
    return "skip" if path.startswith("/profile/users") else "offset"      # the users list has always called it skip


def export(path, **params):
    # every row of a list, 500 at a time, in the default order
    rows, offset = [], 0
    while True:
        r = get(path, limit=500, **{offset_name(path): offset}, **params)
        assert r.status_code == 200, (path, r.status_code, r.text[:200])
        rows += body(r)
        if not meta(r)["pagination_has_next"]:
            return rows, meta(r)["pagination_total"]
        offset += 500


def when(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


for who in ("admin", "editor", "viewer", "guest"):
    login(who)
check("login for admin, editor, viewer, guest", all(tokens.values()))

# ================================================================ 1. every list route
spec = client.get(f"{BASE}/openapi.json").json()
LISTS = {}
for path, item in spec["paths"].items():
    operation = item.get("get")
    if not operation:
        continue
    parameters = {p["name"]: p for p in operation.get("parameters", []) if p["in"] == "query"}
    if "limit" in parameters:
        LISTS[path.removeprefix("/api/v1")] = parameters
check("the OpenAPI document shows 33 list routes", len(LISTS) == 33, str(len(LISTS)))
check("every list route has limit, an offset (skip on the users list) and sort", all({"limit", offset_name(path), "sort"} <= set(p) for path, p in LISTS.items()))


def sort_names(parameters):
    text = parameters["sort"]["description"]
    return [n.strip() for n in text.split("One of:")[1].split(". Default")[0].split(",")]


def sample(parameter):
    name, schema = parameter["name"], parameter["schema"]
    if name in BY_NAME:
        return BY_NAME[name]
    kinds = [s for s in schema.get("anyOf", [schema]) if s.get("type") != "null"]
    kind = kinds[0]
    if kind.get("type") == "array":
        kind = kind["items"]
    if kind.get("format") == "uuid":
        return SAMPLE
    if kind.get("format") == "date-time":
        return "2026-01-01T00:00:00Z"
    return {"boolean": "true", "integer": "1"}.get(kind.get("type"), "x")


for path, parameters in sorted(LISTS.items()):
    maximum = int(parameters["limit"]["description"].split("at most ")[1].split(";")[0]) if "at most" in parameters["limit"]["description"] else None
    off = offset_name(path)
    default = parameters["limit"]["schema"]["default"]
    label = path
    r = get(path)
    check(f"{label}: default call is 200 and uses limit {default}", r.status_code == 200 and meta(r)["pagination_limit"] == default, r.text[:150])
    total = meta(r)["pagination_total"]
    r = get(path, limit=1)
    check(f"{label}: limit=1 gives at most one row", r.status_code == 200 and len(body(r)) <= 1 and meta(r)["pagination_limit"] == 1)
    r = get(path, limit=(maximum or 1000) + 4000)
    if maximum:
        check(f"{label}: a limit above the maximum is lowered to {maximum}", r.status_code == 200 and meta(r)["pagination_limit"] == maximum and len(body(r)) <= maximum)
    else:
        check(f"{label}: there is no maximum, the limit asked for is used", r.status_code == 200 and meta(r)["pagination_limit"] == 5000 and meta(r)["pagination_total"] == total)
    for query in ({"limit": 0}, {"limit": -1}, {"limit": "abc"}, {off: -1}, {off: "abc"}, {off: 9999999999999999999}, {off: 1000000001}, {"limit": 1000000001}, {"limit": 9999999999999999999}):
        r = get(path, **query)
        check(f"{label}: {query} is 422", r.status_code == 422, str(r.status_code))
    r = get(path, **{off: 99999999})
    check(f"{label}: an offset behind the last row is an empty page", r.status_code == 200 and body(r) == [] and meta(r)["pagination_total"] == total)
    r = get(path, bogus_filter=1, _="123", expand="a")
    check(f"{label}: an unknown parameter is ignored, as before", r.status_code == 200 and meta(r)["pagination_total"] == total, r.text[:200])
    r = get(path, sort="nonsense")
    check(f"{label}: an unknown sort is 422 invalid_sort", r.status_code == 422 and errors(r) and errors(r)[0]["code"] == "invalid_sort", r.text[:200])
    r = get(path, sort="name;drop table x")
    check(f"{label}: a sort with SQL text is 422", r.status_code == 422)
    names = sort_names(parameters)
    bad = []
    for name in names:
        for sort in (name, "-" + name):
            r = get(path, sort=sort, limit=5)
            if r.status_code != 200:
                bad.append((sort, r.status_code))
    check(f"{label}: every sort name works in both directions ({len(names)})", not bad, str(bad))
    filters = [p for name, p in parameters.items() if name not in ("limit", "offset", "skip", "sort")]
    bad = []
    for parameter in filters:
        query = {parameter["name"]: sample(parameter)}
        if parameter["name"] == "radius_m":
            query["near"] = BY_NAME["near"]
        r = get(path, limit=5, **query)
        if r.status_code != 200:
            bad.append((query, r.status_code, r.text[:120]))
    check(f"{label}: every filter accepts a value and the query runs ({len(filters)})", not bad, str(bad[:2]))
    if "q" in parameters:
        check(f"{label}: q with one character is 422", get(path, q="a").status_code == 422)
        check(f"{label}: q with 101 characters is 422", get(path, q="a" * 101).status_code == 422)
    r = client.get(API + path, params={"bogus_filter": 1})
    check(f"{label}: no token and an unknown parameter is still 401", r.status_code == 401, str(r.status_code))
    # every filter at once is no problem for the database (the AND of conditions that cannot all be true is an empty page)
    query = {p["name"]: sample(p) for p in filters}
    r = get(path, limit=5, **query)
    check(f"{label}: all filters together run", r.status_code == 200, r.text[:200])

# the administrator-only lists
for path in ("/profile/users/", "/profile/access-policies", "/core/resource-types", "/management/event-log", "/management/jobs"):
    codes = {who: get(path, who).status_code for who in ("editor", "viewer", "guest")}
    check(f"{path}: not for editor, viewer, guest (403)", set(codes.values()) == {403}, str(codes))
    r = get(path, who="viewer", bogus_filter=1)
    check(f"{path}: a viewer with an unknown parameter gets 403", r.status_code == 403, str(r.status_code))
check("the users list still takes skip", ids(get("/profile/users/", skip=1, limit=2)) == ids(get("/profile/users/", limit=3))[1:3])

# ================================================================ 2. the data of the seed against a full export
pois, poi_total = export("/compendium/pois")
check("POI export: every page is stable (no row twice, none missing)", len({p["id"] for p in pois}) == len(pois) == poi_total, f"{len(pois)} {poi_total}")
check("a page of 100 and 500 are the same rows as the start of the export",
      ids(get("/compendium/pois", limit=100)) == [p["id"] for p in pois[:100]] and ids(get("/compendium/pois", limit=100, offset=100)) == [p["id"] for p in pois[100:200]])


def same(path, expected, label, **params):
    got, total = export(path, **params)
    want = {row["id"] for row in expected}
    check(f"{label}: {len(want)} rows", {r["id"] for r in got} == want and total == len(want), f"got {total}, expected {len(want)}")
    return got


def haversine(lon1, lat1, lon2, lat2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(a))


by_type = {}
for p in pois:
    by_type.setdefault(p["compendium_type_id"], []).append(p)
type_ids = sorted(by_type, key=lambda t: -len(by_type[t]))
big, second = type_ids[0], type_ids[1]
same("/compendium/pois", by_type[big], "poi compendium_type_id", compendium_type_id=big)
same("/compendium/pois", by_type[big] + by_type[second], "poi compendium_type_id twice (OR)", compendium_type_id=[big, second])
region = max({p["main_region_id"] for p in pois if p["main_region_id"]}, key=lambda x: sum(1 for p in pois if p["main_region_id"] == x))
same("/compendium/pois", [p for p in pois if p["main_region_id"] == region], "poi main_region_id", main_region_id=region)
same("/compendium/pois", [p for p in pois if p["altitude_m"] is not None and 1000 <= p["altitude_m"] <= 1500], "poi altitude 1000..1500", altitude_min=1000, altitude_max=1500)
same("/compendium/pois", [p for p in pois if p["altitude_m"] == 0], "poi altitude 0 is a value (min 0 and max 0)", altitude_min=0, altitude_max=0)
dates = sorted({p["created_at"] for p in pois})
pivot = dates[len(dates) // 2]
same("/compendium/pois", [p for p in pois if when(p["created_at"]) >= when(pivot)], "poi created_from (inclusive)", created_from=pivot)
same("/compendium/pois", [p for p in pois if when(p["created_at"]) < when(pivot)], "poi created_to (exclusive)", created_to=pivot)
for term in ("bahnhof", "Aadorf", "SBB"):
    same("/compendium/pois", [p for p in pois if any(term.lower() in (p[f] or "").lower() for f in ("name", "name_de", "name_pl"))], f"poi q={term}", q=term)
check("poi q with percent signs is a literal search, not a wildcard", get("/compendium/pois", q="%%").status_code == 200 and meta(get("/compendium/pois", q="%%"))["pagination_total"] == sum(1 for p in pois if "%%" in (p["name"] or "")))
check("poi q with an underscore is a literal search", meta(get("/compendium/pois", q="_a"))["pagination_total"] == sum(1 for p in pois if any("_a" in (p[f] or "").lower() for f in ("name", "name_de", "name_pl"))))
box = (7.0, 46.0, 8.0, 47.0)
same("/compendium/pois", [p for p in pois if box[0] <= p["location"]["coordinates"][0] <= box[2] and box[1] <= p["location"]["coordinates"][1] <= box[3]], "poi bbox", bbox="7,46,8,47")
same("/compendium/pois", pois, "poi bbox of the world", bbox="-180,-90,180,90")
lon0, lat0 = 8.54, 47.37
for radius in (500, 5000, 30000):
    got, total = export("/compendium/pois", near=f"{lon0},{lat0}", radius_m=radius)
    must = {p["id"] for p in pois if haversine(lon0, lat0, *p["location"]["coordinates"]) <= radius * 0.99}
    may = {p["id"] for p in pois if haversine(lon0, lat0, *p["location"]["coordinates"]) <= radius * 1.01}
    found = {r["id"] for r in got}
    check(f"poi near Zurich within {radius} m: {len(found)} rows (the spheroid differs from the sphere by up to 1%)", must <= found <= may and total == len(found), f"{len(must)} {len(found)} {len(may)}")
got, total = export("/compendium/pois", near=f"{lon0},{lat0}")
check("poi near without radius_m uses 5000 m", {r["id"] for r in got} == {r["id"] for r in export("/compendium/pois", near=f"{lon0},{lat0}", radius_m=5000)[0]})
check("poi bbox and near together are an AND", meta(get("/compendium/pois", bbox="8,47,9,48", near="8.54,47.37", radius_m=3000))["pagination_total"] <= meta(get("/compendium/pois", near="8.54,47.37", radius_m=3000))["pagination_total"])
check("poi radius_m without near is 422", get("/compendium/pois", radius_m=100).status_code == 422)
for query in ({"bbox": "1,2,3"}, {"bbox": "8,47,7,46"}, {"bbox": "a,b,c,d"}, {"bbox": "0,0,181,10"}, {"near": "200,10"}, {"near": "8,47", "radius_m": 0}, {"near": "8,47", "radius_m": 100001}):
    check(f"poi {query} is 422", get("/compendium/pois", **query).status_code == 422)
too_many = [str(uuid.UUID(int=i)) for i in range(1, 52)]
check("poi 51 compendium_type_id values is 422", get("/compendium/pois", compendium_type_id=too_many).status_code == 422)
check("poi 50 compendium_type_id values is fine", get("/compendium/pois", compendium_type_id=too_many[:50]).status_code == 200)

# the sort order: numbers and dates in order, rows without a value at the end, ties by id so the pages do not shuffle
r = get("/compendium/pois", sort="altitude_m", limit=500)
values = [p["altitude_m"] for p in body(r)]
filled = [v for v in values if v is not None]
check("poi sort=altitude_m: ascending, empty values last", filled == sorted(filled) and values[len(filled):] == [None] * (len(values) - len(filled)))
r = get("/compendium/pois", sort="-altitude_m", limit=500)
values = [p["altitude_m"] for p in body(r)]
filled = [v for v in values if v is not None]
check("poi sort=-altitude_m: descending, empty values last", filled == sorted(filled, reverse=True) and values[len(filled):] == [None] * (len(values) - len(filled)))
r = get("/compendium/pois", sort="-created_at", limit=500)
stamps = [when(p["created_at"]) for p in body(r)]
check("poi sort=-created_at: newest first", stamps == sorted(stamps, reverse=True))
walked = []
for offset in range(0, 1500, 100):
    walked += ids(get("/compendium/pois", sort="altitude_m", limit=100, offset=offset))
check("poi sort=altitude_m with many equal values: 15 pages of 100 have no row twice", len(set(walked)) == len(walked) == 1500)
check("the named sort and the default are the same for sort=name", ids(get("/compendium/pois", sort="name", limit=50)) == ids(get("/compendium/pois", limit=50)))

regions, region_total = export("/compendium/regions")
check("region export: every page is stable", len({r["id"] for r in regions}) == len(regions) == region_total)
country = max({r["country_id"] for r in regions if r["country_id"]}, key=lambda c: sum(1 for r in regions if r["country_id"] == c))
same("/compendium/regions", [r for r in regions if r["country_id"] == country], "region country_id", country_id=country)
types = {r["region_type_id"] for r in regions if r["region_type_id"]}
check("region region_type_id: the types add up to the whole list", sum(meta(get("/compendium/regions", region_type_id=t, limit=1))["pagination_total"] for t in types) + sum(1 for r in regions if not r["region_type_id"]) == region_total)
parent = next((r["parent_id"] for r in regions if r["parent_id"]), None)
if parent:
    same("/compendium/regions", [r for r in regions if r["parent_id"] == parent], "region parent_id", parent_id=parent)
same("/compendium/regions", regions, "region bbox of the world", bbox="-180,-90,180,90")
check("region bbox of a small box is a subset", meta(get("/compendium/regions", bbox="8,47,8.1,47.1"))["pagination_total"] < region_total)
countries, country_total = export("/compendium/countries")
iso = countries[0]["iso_code"]
same("/compendium/countries", [c for c in countries if c["iso_code"] == iso], f"country iso_code={iso}", iso_code=iso)
r = get("/compendium/countries", sort="-iso_code", limit=250)
codes = [c["iso_code"] for c in body(r)]
check("country sort=-iso_code", codes == sorted(codes, reverse=True) or len(set(codes)) == len(codes))

# lookup tables
kinds, kind_total = export("/core/compendium-types")
yes, no = meta(get("/core/compendium-types", is_collectable="true", limit=1))["pagination_total"], meta(get("/core/compendium-types", is_collectable="false", limit=1))["pagination_total"]
check("compendium types: collectable and not collectable add up to the whole list", yes + no == kind_total and yes == sum(1 for k in kinds if k["is_collectable"]), f"{yes} {no} {kind_total}")
check("compendium types q finds by German name", all("bahn" in ((k["name"] or "") + (k["name_de"] or "") + (k["name_pl"] or "")).lower() for k in body(get("/core/compendium-types", q="bahn"))) and meta(get("/core/compendium-types", q="bahn"))["pagination_total"] >= 1)
sports, _ = export("/core/difficulty-sports")
sport = next(s["sport_type_id"] for s in sports if s["sport_type_id"])
same("/core/difficulty-sports", [s for s in sports if s["sport_type_id"] == sport], "difficulty sports sport_type_id", sport_type_id=sport)
r = get("/core/rarities", sort="-point_factor")
factors = [x["point_factor"] for x in body(r)]
check("rarities sort=-point_factor", factors == sorted(factors, reverse=True))
r = get("/core/rarities", sort="name")
check("rarities default order is the name order", ids(get("/core/rarities")) == ids(r))
for path in ("/core/sport-types", "/core/companies", "/core/gear-types"):
    rows, total = export(path)
    check(f"{path}: the whole table fits one page of 500 (default)", meta(get(path))["pagination_has_next"] is False and len(rows) == total)

# event log
log, log_total = export("/management/event-log")
check("event log: every page is stable and newest first", len({e["id"] for e in log}) == len(log) == log_total and [when(e["changed_at"]) for e in log] == sorted((when(e["changed_at"]) for e in log), reverse=True))
kind = log[0]["entity_type"]["key"] if isinstance(log[0].get("entity_type"), dict) else None
if kind:
    same("/management/event-log", [e for e in log if e["entity_type"]["key"] == kind], f"event log entity_type={kind}", entity_type=kind)
check("event log entity_type that does not exist: an empty page, not an error", meta(get("/management/event-log", entity_type="no_such_table"))["pagination_total"] == 0)
action = log[0]["action"]
same("/management/event-log", [e for e in log if e["action"] == action], f"event log action={action}", action=action)
middle = log[len(log) // 2]["changed_at"]
same("/management/event-log", [e for e in log if when(e["changed_at"]) >= when(middle)], "event log changed_from", changed_from=middle)
same("/management/event-log", [e for e in log if when(e["changed_at"]) < when(middle)], "event log changed_to", changed_to=middle)
r = get("/management/event-log", sort="seq", limit=500)
seqs = [e["seq"] for e in body(r)]
check("event log sort=seq is ascending", seqs == sorted(seqs))

# users and access policies
users, user_total = export("/profile/users/")
check("users: newest first, every page stable", len({u["id"] for u in users}) == user_total and [when(u["created_at"]) for u in users] == sorted((when(u["created_at"]) for u in users), reverse=True))
for group in ("administrator", "viewer"):
    same("/profile/users/", [u for u in users if u["user_group"] == group], f"users user_group={group}", user_group=group)
check("users user_group=nonsense is 422", get("/profile/users/", user_group="nonsense").status_code == 422)
same("/profile/users/", [u for u in users if u["is_active"]], "users is_active=true", is_active="true")
same("/profile/users/", [u for u in users if "admin" in (u["username"] + u["email"] + (u["first_name"] or "") + (u["last_name"] or "")).lower()], "users q=admin", q="admin")
names = [u["username"] for u in body(get("/profile/users/", sort="username"))]
check("users sort=username has the same names as the unsorted list", sorted(names) == sorted(u["username"] for u in users) and len(names) == user_total)
check("users: no maximum on the limit", meta(get("/profile/users/", limit=5000))["pagination_limit"] == 5000)
check("tracks, jobs and my jobs still have a maximum of 500, the event log has none", all(meta(get(p, limit=5000))["pagination_limit"] == m for p, m in (("/explorer/tracks", 500), ("/management/jobs", 500), ("/management/my-jobs", 500), ("/management/event-log", 5000))))
check("the defaults are the old ones: 1000 on most lists, 100 on tracks, event log, jobs, my jobs", all(meta(get(p, limit=None))["pagination_limit"] == d for p, d in (("/compendium/pois", 1000), ("/core/companies", 1000), ("/profile/users/", 1000), ("/profile/access-policies", 1000), ("/explorer/gear", 1000), ("/explorer/tracks", 100), ("/management/event-log", 100), ("/management/jobs", 100), ("/management/my-jobs", 100))))
policies, policy_total = export("/profile/access-policies")
same("/profile/access-policies", [p for p in policies if p["user_group"] == "viewer"], "access policies group=viewer", group="viewer")
same("/profile/access-policies", [p for p in policies if p["action"] == "read"], "access policies action=read", action="read")
same("/profile/access-policies", [p for p in policies if p["scope"] == "own"], "access policies scope=own", scope="own")
key = policies[0]["resource_key"]
same("/profile/access-policies", [p for p in policies if p["resource_key"] == key], f"access policies resource_key={key}", resource_key=key)
groups_in_order = [p["user_group"] for p in policies]
check("access policies default order: by group (the database orders the resource keys by its own collation, as before)", groups_in_order == sorted(groups_in_order))
check("access policies sort=-action and sort=resource_key run", all(get("/profile/access-policies", sort=s, limit=5).status_code == 200 for s in ("-action", "resource_key", "-group")))
resource_types, _ = export("/core/resource-types")
check("resource types q=track finds the track key", any(r["key"] == "track" for r in body(get("/core/resource-types", q="track"))))

# jobs
jobs, job_total = export("/management/jobs")
if jobs:
    status = jobs[0]["status"]
    same("/management/jobs", [j for j in jobs if j["status"] == status], f"jobs status={status}", status=status)
    check("jobs status=nonsense is 422", get("/management/jobs", status="nonsense").status_code == 422)
    check("jobs active=true: only queued and running", all(j["status"] in ("queued", "running") for j in body(get("/management/jobs", active="true"))))
check("jobs: newest first", [when(j["created_at"]) for j in jobs] == sorted((when(j["created_at"]) for j in jobs), reverse=True))
check("my jobs: status=nonsense is 422", get("/management/my-jobs", status="nonsense").status_code == 422)

# values that the database cannot take must be 422, never 500; empty text parameters (a form field left empty) mean "not given"
for path, query in (
    ("/compendium/pois", {"altitude_min": 99999999999}), ("/compendium/pois", {"altitude_max": -99999999999}),
    ("/compendium/pois", {"created_to": "9999-12-31T23:59:59"}), ("/compendium/pois", {"created_from": "0001-01-01"}),
    ("/compendium/pois", {"q": "\x00ab"}), ("/compendium/pois", {"q": "ab\x00"}),
    ("/explorer/gear", {"weight_min": 99999999999}), ("/explorer/tracks", {"distance_min": 99999999999}),
    ("/explorer/tracks", {"recorded_to": "9999-12-31"}), ("/management/event-log", {"changed_to": "9999-12-31"}),
    ("/management/event-log", {"action": "a\x00b"}), ("/management/jobs", {"kind": "\x00"}),
    ("/management/jobs", {"created_from": "9999-12-31T23:59:59"}), ("/profile/users/", {"created_to": "9999-12-31"}),
    ("/compendium/pois", {"bbox": "1_0,46,11,47"}), ("/compendium/pois", {"bbox": "1e9,0,1,1"}),
):
    r = get(path, **query)
    check(f"{path} {query} is 422 and not 500", r.status_code == 422 and r.json().get("response_status") is False, f"{r.status_code} {r.text[:120]}")
check("the server still answers after those requests", get("/compendium/pois", limit=1).status_code == 200)
for path, empty in (("/management/my-jobs", "kind"), ("/management/jobs", "kind"), ("/profile/access-policies", "resource_key"),
                    ("/profile/access-policies", "group"), ("/explorer/tracks", "processing_status"), ("/compendium/pois", "q"),
                    ("/management/jobs", "status"), ("/management/event-log", "entity_type"), ("/profile/users/", "q"), ("/compendium/countries", "q")):
    plain, empty_param = get(path, limit=1), get(path, limit=1, **{empty: ""})
    check(f"{path} {empty}= (empty) is the same as not given", empty_param.status_code == 200 and meta(empty_param)["pagination_total"] == meta(plain)["pagination_total"], f"{empty_param.status_code} {meta(empty_param)}")
check("an empty id filter is still 422 (an id must be an id or be left out)", get("/compendium/pois", compendium_type_id="").status_code == 422)
box = (8.4, 47.2, 8.41, 47.21)
area = body(get("/compendium/regions", bbox=f"{box[0]},{box[1]},{box[2]},{box[3]}", limit=500))
check("region bbox finds the regions whose area touches the box (also when their centre is outside it)", len(area) >= 1 and any(not (box[0] <= r["location"]["coordinates"][0] <= box[2] and box[1] <= r["location"]["coordinates"][1] <= box[3]) for r in area), str(len(area)))
check("region bbox over the ocean finds none", meta(get("/compendium/regions", bbox="-40,-40,-39,-39"))["pagination_total"] == 0)

# ================================================================ 3. rows that this script creates
company = body(get("/core/companies", limit=2))
company_a, company_b = company[0], company[1]
gear_types = body(get("/core/gear-types", limit=2))
tag = uuid.uuid4().hex[:6]


def make(path, who="admin", **payload):
    r = call("POST", path, who, json=payload)
    check(f"setup: POST {path} as {who}", r.status_code == 201, r.text[:200])
    created.append(f"{path}/{body(r)['id']}")
    return body(r)


g1 = make("/explorer/gear", name=f"ZZ list {tag} light", model="Alpha", company_id=company_a["id"], gear_type_id=gear_types[0]["id"], weight_g=300)
g2 = make("/explorer/gear", name=f"ZZ list {tag} heavy", model="Beta", company_id=company_b["id"], gear_type_id=gear_types[0]["id"], weight_g=1200)
g3 = make("/explorer/gear", "editor", name=f"ZZ list {tag} editor", model="Gamma", company_id=company_a["id"], gear_type_id=gear_types[1]["id"], weight_g=0)
mine = f"ZZ list {tag}"
admin_user_id = next(u for u in users if u["username"] == "admin")["id"]
check("gear q finds the three rows", sorted(ids(get("/explorer/gear", q=mine))) == sorted([g1["id"], g2["id"], g3["id"]]))
check("gear q also searches the model", ids(get("/explorer/gear", q="Alpha")) and g1["id"] in ids(get("/explorer/gear", q="Alpha")))
check("gear weight_min=1000", ids(get("/explorer/gear", q=mine, weight_min=1000)) == [g2["id"]])
check("gear weight_max=300 includes 300 and 0", sorted(ids(get("/explorer/gear", q=mine, weight_max=300))) == sorted([g1["id"], g3["id"]]))
check("gear weight_max=0 is a value: only the 0 g gear", ids(get("/explorer/gear", q=mine, weight_max=0)) == [g3["id"]])
check("gear company_id twice is an OR", sorted(ids(get("/explorer/gear", q=mine, company_id=[company_a["id"], company_b["id"]]))) == sorted([g1["id"], g2["id"], g3["id"]]))
check("gear company_id once", sorted(ids(get("/explorer/gear", q=mine, company_id=company_a["id"]))) == sorted([g1["id"], g3["id"]]))
check("gear gear_type_id", ids(get("/explorer/gear", q=mine, gear_type_id=gear_types[1]["id"])) == [g3["id"]])
check("gear sort=-weight_g", ids(get("/explorer/gear", q=mine, sort="-weight_g")) == [g2["id"], g1["id"], g3["id"]])
check("gear sort=weight_g", ids(get("/explorer/gear", q=mine, sort="weight_g")) == [g3["id"], g1["id"], g2["id"]])
scope = {who: body(get("/profile/access-policies", group=who, resource_key="gear", action="read"))[0]["scope"] for who in ("editor", "viewer")}
check("setup: editor and viewer read gear with the scope public (own and public rows)", set(scope.values()) == {"public"}, str(scope))
check("gear scope: the editor sees his own gear and not the administrator's private gear", ids(get("/explorer/gear", "editor", q=mine)) == [g3["id"]])
check("gear scope: the viewer sees none of them", ids(get("/explorer/gear", "viewer", q=mine)) == [])
check("gear scope: no filter widens it (created_by, company_id, weight_min as the editor, q as the viewer)",
      ids(get("/explorer/gear", "editor", q=mine, created_by=admin_user_id)) == [] and ids(get("/explorer/gear", "editor", q=mine, company_id=company_b["id"])) == []
      and ids(get("/explorer/gear", "editor", q=mine, weight_min=1000)) == [] and ids(get("/explorer/gear", "viewer", q="ZZ list")) == [])
check("gear scope: the total of the editor's list counts only what he may see", meta(get("/explorer/gear", "editor", q=mine))["pagination_total"] == 1)
admin_user = next(u for u in users if u["username"] == "admin")
editor_user = next(u for u in users if u["username"] == "editor")
check("gear created_by: the editor's gear, and the admin's two", ids(get("/explorer/gear", q=mine, created_by=editor_user["id"])) == [g3["id"]] and sorted(ids(get("/explorer/gear", q=mine, created_by=admin_user["id"]))) == sorted([g1["id"], g2["id"]]))
check("gear pages of 2 walk the three rows without a repeat", len(set(ids(get("/explorer/gear", q=mine, limit=2)) + ids(get("/explorer/gear", q=mine, limit=2, offset=2)))) == 3)

poi = pois[0]
card = make("/compendium/cards", name=f"ZZ card {tag}", poi_id=poi["id"], rarity_id=body(get("/core/rarities", limit=1))[0]["id"], compendium_type_id=poi["compendium_type_id"])
check("card poi_id", ids(get("/compendium/cards", poi_id=poi["id"])) == [card["id"]])
check("card compendium_type_id", card["id"] in ids(get("/compendium/cards", compendium_type_id=poi["compendium_type_id"])))
check("card rarity_id", card["id"] in ids(get("/compendium/cards", rarity_id=card["rarity_id"])))
check("card q", ids(get("/compendium/cards", q=f"card {tag}")) == [card["id"]])
check("card poi_id of another poi: empty", ids(get("/compendium/cards", poi_id=pois[1]["id"])) == [])
post_type = body(get("/core/post-types", limit=1))[0]
post = make("/compendium/posts", name=f"ZZ post {tag}", post_type_id=post_type["id"])
check("post post_type_id and q", post["id"] in ids(get("/compendium/posts", post_type_id=post_type["id"])) and ids(get("/compendium/posts", q=f"post {tag}")) == [post["id"]])
link = make("/compendium/poi-regions", poi_id=poi["id"], region_id=poi["main_region_id"], slot_position=98)
check("poi-region poi_id", ids(get("/compendium/poi-regions", poi_id=poi["id"])) == [link["id"]])
check("poi-region region_id", link["id"] in ids(get("/compendium/poi-regions", region_id=poi["main_region_id"])))
check("poi-region default sort is slot_position", [x["slot_position"] for x in body(get("/compendium/poi-regions"))] == sorted(x["slot_position"] for x in body(get("/compendium/poi-regions"))))

if os.path.exists(ARGS.gpx):
    sport = body(get("/core/sport-types", limit=1))[0]
    with open(ARGS.gpx, "rb") as handle:
        up = call("POST", "/explorer/tracks", files={"gpx_file": ("list-check.gpx", handle, "application/gpx+xml")}, data={"name": f"ZZ track {tag}", "is_public": "true"})
    check("setup: upload a track (202)", up.status_code == 202, up.text[:200])
    tid = body(up)["id"]
    call("PATCH", f"/explorer/tracks/{tid}", json={"sport_type_id": sport["id"], "start_poi_id": poi["id"]})
    created.append(f"/explorer/tracks/{tid}")
    with open(ARGS.gpx, "rb") as handle:
        up = call("POST", "/explorer/tracks", files={"gpx_file": ("list-check-private.gpx", handle, "application/gpx+xml")}, data={"name": f"ZZ private {tag}", "is_public": "false"})
    check("setup: upload a private track (202)", up.status_code == 202, up.text[:200])
    pid_private = body(up)["id"]
    created.append(f"/explorer/tracks/{pid_private}")
    check("track scope: the viewer and the editor see neither track (others only see tracks that are ready; these wait for a worker)",
          all(not {tid, pid_private} & set(ids(get("/explorer/tracks", who, q="ZZ", limit=500))) for who in ("viewer", "editor")))
    check("track scope: no filter shows the private track to the viewer (is_public=false, created_by=admin, processing_status, q)",
          all(pid_private not in ids(get("/explorer/tracks", "viewer", limit=500, **query)) for query in (
              {"is_public": "false"}, {"created_by": admin_user["id"]}, {"processing_status": "pending"}, {"q": f"private {tag}"})))
    check("track scope: the administrator sees both", {tid, pid_private} <= set(ids(get("/explorer/tracks", q="ZZ", limit=500))))
    check("track q finds it", ids(get("/explorer/tracks", q=f"track {tag}")) == [tid])
    check("track processing_status=pending", tid in ids(get("/explorer/tracks", processing_status="pending", limit=500)))
    check("track processing_status=failed does not", tid not in ids(get("/explorer/tracks", processing_status="failed", limit=500)))
    check("track sport_type_id (once and twice)", tid in ids(get("/explorer/tracks", sport_type_id=sport["id"])) and tid in ids(get("/explorer/tracks", sport_type_id=[sport["id"], SAMPLE])))
    check("track start_poi_id", ids(get("/explorer/tracks", start_poi_id=poi["id"])) == [tid] or tid in ids(get("/explorer/tracks", start_poi_id=poi["id"])))
    check("track is_public=true finds it, false does not", tid in ids(get("/explorer/tracks", is_public="true")) and tid not in ids(get("/explorer/tracks", is_public="false")))
    check("track created_by the admin", tid in ids(get("/explorer/tracks", created_by=admin_user["id"])) and tid not in ids(get("/explorer/tracks", created_by=editor_user["id"])))
    check("track recorded_from in the future: not found; in the past: found",
          tid not in ids(get("/explorer/tracks", recorded_from="2100-01-01T00:00:00Z")) and tid in ids(get("/explorer/tracks", recorded_from="2000-01-01T00:00:00Z")))
    check("track recorded_to in the past: not found", tid not in ids(get("/explorer/tracks", recorded_to="2000-01-01T00:00:00Z")))
    check("track distance_min=1: the unprocessed track has no distance yet, so it is left out", tid not in ids(get("/explorer/tracks", distance_min=1)))
    check("track without a metric filter keeps the unprocessed track (outer join)", tid in ids(get("/explorer/tracks")))
    check("track sort=distance_m and elevation_gain_m run and keep the unprocessed track last", all(
        tid in ids(get("/explorer/tracks", sort=s, limit=500)) for s in ("distance_m", "-distance_m", "elevation_gain_m", "-elevation_gain_m")))
    check("track archived=false does not show an archived one: default list has it", tid in ids(get("/explorer/tracks")))
    r = call("DELETE", f"/explorer/tracks/{tid}")
    check("track delete archives it", r.status_code in (200, 204), str(r.status_code))
    check("track archived=true finds it and the default list no longer does", tid in ids(get("/explorer/tracks", archived="true")) and tid not in ids(get("/explorer/tracks")))
    check("track processing_status=nonsense is 422", get("/explorer/tracks", processing_status="nonsense").status_code == 422)
else:
    print("SKIP  the track checks: no GPX file at", ARGS.gpx)

# ================================================================ 3b. the scope of the caller narrows every list (a policy is changed and put back)
def set_scope(group, resource_key, scope):
    policy = body(get("/profile/access-policies", group=group, resource_key=resource_key, action="read"))[0]
    if policy["scope"] != scope:
        print(f"RESTORE  PATCH /api/v1/profile/access-policies/{policy['id']}  {{\"scope\": \"{policy['scope']}\"}}   ({group}, {resource_key}, read)", flush=True)
        restore.append((f"/profile/access-policies/{policy['id']}", {"scope": policy["scope"]}))
        r = call("PATCH", f"/profile/access-policies/{policy['id']}", json={"scope": scope})
        check(f"setup: {group} reads {resource_key} with the scope {scope}", r.status_code == 200, r.text[:200])


if ARGS.skip_policy_step:
    print("SKIP  part 3b: the policy step was switched off")
else:
    set_scope("viewer", "poi", "own")
    check("poi scope own: the viewer sees no POI of others, total 0", meta(get("/compendium/pois", "viewer"))["pagination_total"] == 0 and body(get("/compendium/pois", "viewer")) == [])
    check("poi scope own: no filter brings them back (q, bbox of the world, near, compendium_type_id, sort)",
          all(meta(get("/compendium/pois", "viewer", **query))["pagination_total"] == 0 for query in (
              {"q": "bahnhof"}, {"bbox": "-180,-90,180,90"}, {"near": "8.54,47.37", "radius_m": 30000}, {"compendium_type_id": big}, {"sort": "-altitude_m"}, {"created_by": admin_user["id"]})))
    check("poi scope own: the administrator still sees all", meta(get("/compendium/pois", "admin", limit=1))["pagination_total"] == poi_total)
    set_scope("viewer", "ref", "own")
    check("lookup tables scope own: the viewer sees only rows he created (none), total 0", meta(get("/core/companies", "viewer"))["pagination_total"] == 0 and meta(get("/core/compendium-types", "viewer", q="bahn"))["pagination_total"] == 0)
    set_scope("viewer", "region", "own")
    check("region scope own: total 0 for the viewer, also with bbox", meta(get("/compendium/regions", "viewer"))["pagination_total"] == 0 and meta(get("/compendium/regions", "viewer", bbox="-180,-90,180,90"))["pagination_total"] == 0)
    for policy in list(restore):
        call("PATCH", policy[0], json=policy[1])
    restore.clear()
    check("the scopes are put back: the viewer sees the POIs again", meta(get("/compendium/pois", "viewer", limit=1))["pagination_total"] == poi_total)


if ARGS.gzip:
    # ================================================================ 4. compression
    r = client.get(API + "/compendium/pois", params={"limit": 100}, headers={"Authorization": f"Bearer {tokens['admin']}", "Accept-Encoding": "gzip"})
    check("a page of 100 POIs is compressed when the client accepts gzip", r.headers.get("content-encoding") == "gzip" and len(body(r)) == 100, r.headers.get("content-encoding", ""))
    raw = client.get(API + "/compendium/pois", params={"limit": 100}, headers={"Authorization": f"Bearer {tokens['admin']}", "Accept-Encoding": "identity"})
    check("the compressed and the plain answer carry the same rows", [p["id"] for p in body(r)] == [p["id"] for p in body(raw)] and raw.headers.get("content-encoding") is None)
    r = client.get(f"{BASE}/health", headers={"Accept-Encoding": "gzip"})
    check("a small answer (health) still decodes (Starlette compresses answers that are streamed by a middleware whatever their size)", r.status_code == 200 and r.json()["response_status"] is True)
    r = client.get(API + "/core/rarities", params={"limit": 3}, headers={"Authorization": f"Bearer {tokens['admin']}", "Accept-Encoding": "gzip"})
    check("a gzip answer keeps its pagination and rotating-token headers readable", r.status_code == 200 and meta(r)["pagination_limit"] == 3)

else:
    print("SKIP  part 4: compression is off (start the application with GZipMiddleware and use --gzip to check it)")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
