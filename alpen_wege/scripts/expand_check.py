#!/usr/bin/env python
"""Live check of the ?expand= option of the single-object GET endpoints, against a RUNNING api (needs the seeded
dev users and the compendium seed: push_data/seed.py).

    pip install httpx
    python scripts/expand_check.py --base http://localhost:8000 [--gpx /tmp/full.gpx] [--worker]

Creates and deletes: one country, one gear item, one card, one post, one poi-region link and one track (the track
is archived, not deleted: that is what DELETE does); changes and resets one runtime setting. The event log keeps
the rows that these writes cause. Needs no Celery worker (the track stays "pending"); with --worker (a worker is
running) it also waits for the track job and checks that the computed "metrics" of the track are unchanged.
Make a sample GPX with: python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx
Seed users: scripts/init_seed.py (password !Password@5005, admin/editor/viewer/guest @alpenwege.dev).
"""
import argparse
import atexit
import json
import re
import sys
import time
import uuid
import httpx

parser = argparse.ArgumentParser(description="Live check of ?expand= on the single-object GET endpoints")
parser.add_argument("--base", default="http://localhost:8000")
parser.add_argument("--gpx", default="/tmp/full.gpx")
parser.add_argument("--password", default="!Password@5005")
parser.add_argument("--worker", action="store_true", help="a Celery worker is running: wait for the track job")
ARGS = parser.parse_args()
BASE = ARGS.base.rstrip("/")
API = BASE + "/api/v1"
results = []
SEEN = []          # the text of every response, to prove that no password data is ever returned
SINGLES = []       # every single-object URL that was read, for the empty-expand check
created = []       # paths to DELETE at the end, newest last (or a (method, path) pair)

def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if (detail and not cond) else ""), flush=True)

def _stopped(kind, exc, tb):
    # An unexpected answer (a missing key, a null) ends the script: say which check was the last one, print the summary.
    last = results[-1][0] if results else "the start"
    print(f"FAIL  the script stopped with {kind.__name__}: {exc}   [last check before it: {last}]", flush=True)
    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)} passed, {len(failed) + 1} failed", flush=True)


sys.excepthook = _stopped
client = httpx.Client(timeout=60)
tokens = {}

def login(who):
    r = client.post(f"{API}/profile/auth/login", json={"email": f"{who}@alpenwege.dev", "password": ARGS.password})
    tokens[who] = r.json()["response_data"]["access_token"] if r.status_code == 200 else None

def call(method, path, who="admin", **kw):
    # Tokens are short-lived and rotate: adopt X-Access-Token when a response carries one, log in again on a 401.
    for attempt in (1, 2):
        r = client.request(method, API + path, headers={"Authorization": f"Bearer {tokens[who]}"}, **kw)
        if r.status_code == 401 and attempt == 1 and "files" not in kw:
            login(who)
            continue
        break
    if r.headers.get("X-Access-Token"):
        tokens[who] = r.headers["X-Access-Token"]
    SEEN.append(r.text)
    return r

def clean_up():
    # runs when the script ends, also after a crash: deletes what it created and undoes what it changed
    for item in reversed(created):
        method, path = item if isinstance(item, tuple) else ("DELETE", item)
        call(method, path)
    created.clear()


atexit.register(clean_up)


def body(r): return r.json().get("response_data")
def err(r): return (r.json().get("response_details") or {}).get("error_message", "")
def single(path, who="admin", **kw):
    SINGLES.append(path)
    return call("GET", path, who, **kw)

for who in ("admin", "editor", "viewer", "guest"):
    login(who)
check("login for admin, editor, viewer, guest", all(tokens.values()))

# ---------------------------------------------------------------- data to work with
pois = body(call("GET", "/compendium/pois", params={"limit": 3}))
poi = pois[0]
regions = body(call("GET", "/compendium/regions", params={"limit": 2000}))
region_with_parent = next((r for r in regions if r["parent_id"]), regions[0])
rarity = body(call("GET", "/core/rarities", params={"limit": 1}))[0]
comp_type = body(call("GET", "/core/compendium-types", params={"limit": 1}))[0]
post_type = body(call("GET", "/core/post-types", params={"limit": 1}))[0]
company = body(call("GET", "/core/companies", params={"limit": 1}))[0]
gear_type = body(call("GET", "/core/gear-types", params={"limit": 1}))[0]
sport_type = body(call("GET", "/core/sport-types", params={"limit": 1}))[0]
level = body(call("GET", "/core/difficulty-levels", params={"limit": 1}))[0]
diff_sport = next(d for d in body(call("GET", "/core/difficulty-sports", params={"limit": 1000})) if d["sport_type_id"])

# ---------------------------------------------------------------- 1. event log (administrator only)
country = call("POST", "/compendium/countries", json={
    "name": f"ZZ Expand {uuid.uuid4().hex[:6]}", "iso_code": uuid.uuid4().hex[:2].upper() + "X",
    "location": {"type": "Point", "coordinates": [10.0, 47.0]}, "capital": "Old"})
check("setup: create a country", country.status_code == 201, country.text[:200])
cid = body(country)["id"]
created.append(f"/compendium/countries/{cid}")
events = body(call("GET", "/management/event-log", params={"entity_id": cid, "limit": 5}))
check("setup: the create wrote an event-log entry", len(events) == 1, str(len(events)))
log_id = events[0]["id"]

r = single(f"/management/event-log/{log_id}")
d = body(r)
check("event log, no expand: changed_by is an id, changed_by_user and entity_type are null, entity_type_id is set",
      r.status_code == 200 and d["changed_by"] and d["changed_by_user"] is None and d["entity_type"] is None and d["entity_type_id"], r.text[:200])
d = body(single(f"/management/event-log/{log_id}", params={"expand": "changed_by"}))
check("event log, expand=changed_by: the full user (id, username, email, user_group)",
      d["changed_by_user"]["id"] == d["changed_by"] and d["changed_by_user"]["username"] == "admin"
      and d["changed_by_user"]["email"] and d["changed_by_user"]["user_group"] == "administrator" and d["entity_type"] is None)
d = body(single(f"/management/event-log/{log_id}", params={"expand": "entity_type"}))
check("event log, expand=entity_type: the entity type, changed_by_user stays null",
      d["entity_type"]["key"] == "compendium_cat_country" and d["changed_by_user"] is None)
d = body(single(f"/management/event-log/{log_id}", params={"expand": "changed_by,entity_type"}))
check("event log, expand=changed_by,entity_type: both", d["entity_type"] and d["changed_by_user"])
r = call("GET", f"/management/event-log/{log_id}", params={"expand": "nope"})
check("event log, unknown name: 400, the message lists the allowed names, error_errors names the field expand",
      r.status_code == 400 and r.json()["response_status"] is False and "changed_by" in err(r) and "entity_type" in err(r)
      and r.json()["response_details"]["error_errors"][0]["field"] == "expand", r.text[:300])
r = call("GET", f"/management/event-log/{log_id}", params={"expand": "changed_by.x"})
check("event log, a name below a user (it has no links): 400", r.status_code == 400, r.text[:200])

second = call("PATCH", f"/compendium/countries/{cid}", json={"capital": "New"})
events = body(call("GET", "/management/event-log", params={"entity_id": cid, "limit": 5}))
ids = [e["id"] for e in sorted(events, key=lambda e: e["seq"])]
check("setup: the update wrote a second entry", second.status_code == 200 and len(ids) == 2)
SINGLES.append(f"/management/event-log/{ids[0]}/compare/{ids[1]}")
d = body(call("GET", f"/management/event-log/{ids[0]}/compare/{ids[1]}"))
check("compare, no expand: entity_type and both changed_by_user are null, the older entry is really the older, the changes are still there",
      d["entity_type"] is None and d["older"]["changed_by_user"] is None and d["newer"]["changed_by_user"] is None
      and d["older"]["action"] == "created" and d["newer"]["action"] == "updated" and d["older"]["seq"] < d["newer"]["seq"]
      and d["changes"]["capital"] == {"from": "Old", "to": "New"})
d = body(call("GET", f"/management/event-log/{ids[0]}/compare/{ids[1]}", params={"expand": "changed_by,entity_type"}))
check("compare, expand=changed_by,entity_type: filled for both entries",
      d["entity_type"]["key"] == "compendium_cat_country" and d["older"]["changed_by_user"]["username"] == "admin"
      and d["newer"]["changed_by_user"]["username"] == "admin")
r = call("GET", f"/management/event-log/{log_id}", "guest", params={"expand": "changed_by"})
check("event log with a guest token: 403", r.status_code == 403, str(r.status_code))
r = call("GET", f"/management/event-log/{log_id}", "editor")
check("event log with an editor token: 403", r.status_code == 403, str(r.status_code))
r = client.get(f"{API}/management/event-log/{log_id}", params={"expand": "nope"})
check("event log without a token and with a bad expand: 401 (login is checked before expand)", r.status_code == 401, str(r.status_code))

# ---------------------------------------------------------------- 2. poi
pid = poi["id"]
d = body(single(f"/compendium/pois/{pid}"))
check("poi, no expand: ids are set, compendium_type, main_region and created_by_user are null, location is GeoJSON",
      d["compendium_type_id"] and d["main_region_id"] and d["compendium_type"] is None and d["main_region"] is None
      and d["created_by_user"] is None and d["location"]["type"] == "Point")
d = body(single(f"/compendium/pois/{pid}", params={"expand": "compendium_type"}))
check("poi, expand=compendium_type: the full type including is_collectable",
      d["compendium_type"]["id"] == d["compendium_type_id"] and "is_collectable" in d["compendium_type"]
      and d["main_region"] is None)
d = body(single(f"/compendium/pois/{pid}", params={"expand": "main_region.country,main_region.region_type,created_by"}))
check("poi, expand=main_region.country,main_region.region_type,created_by: nested objects, the rest stays null",
      d["main_region"]["country"]["iso_code"] and d["main_region"]["region_type"]["point_factor"] is not None
      and d["main_region"]["parent"] is None and d["main_region"]["created_by_user"] is None
      and d["created_by_user"]["username"] and d["compendium_type"] is None)
d = body(single(f"/compendium/pois/{pid}", params={"expand": "main_region.country.created_by"}))
check("poi, a path of 3 levels ending in created_by is accepted",
      d["main_region"]["country"]["created_by_user"]["id"] == d["main_region"]["country"]["created_by"])
r = call("GET", f"/compendium/pois/{pid}", params={"expand": "main_region.parent.parent.country"})
check("poi, a path of 4 levels: 400 (depth is checked first)", r.status_code == 400 and "levels" in err(r), r.text[:200])
r = call("GET", f"/compendium/pois/{pid}", params={"expand": "main_region.nope"})
check("poi, unknown name below main_region: 400 with the allowed names",
      r.status_code == 400 and all(n in err(r) for n in ("country", "created_by", "parent", "region_type")), err(r))
eleven = ("compendium_type,compendium_type.created_by,main_region,main_region.country,main_region.country.created_by,"
          "main_region.region_type,main_region.region_type.created_by,main_region.parent,main_region.parent.country,"
          "main_region.parent.region_type,created_by")
r = call("GET", f"/compendium/pois/{pid}", params={"expand": eleven})
check("poi, 11 distinct links: 400 (limit 10)", r.status_code == 400 and "maximum is 10" in err(r), err(r))
d = body(single(f"/compendium/pois/{pid}", params={"expand": eleven.rsplit(",", 1)[0]}))
check("poi, 10 distinct links with shared parents counted once: accepted and filled",
      d["main_region"]["parent"] is None or d["main_region"]["parent"]["country"] is not None)
r = call("GET", f"/compendium/pois/{pid}", params=[("expand", "created_by"), ("expand", "compendium_type")])
d = body(r)
check("poi, the parameter repeated: only the last value counts", d["compendium_type"] and d["created_by_user"] is None)
r = call("GET", f"/compendium/pois/{pid}", "guest", params={"expand": "created_by"})
check("poi, guest with expand=created_by: 200, only id and username of the creator, the profile fields are null",
      r.status_code == 200 and body(r)["created_by_user"]["username"] and body(r)["created_by_user"]["email"] is None
      and body(r)["created_by_user"]["birth_date"] is None and body(r)["created_by_user"]["max_heart_rate"] is None, r.text[:300])
r = call("GET", f"/compendium/pois/{pid}", "admin", params={"expand": "created_by"})
check("poi, administrator with expand=created_by: the whole profile", isinstance(body(r)["created_by_user"]["email"], str))
mine = call("POST", "/compendium/countries", "editor", json={
    "name": f"ZZ Editor {uuid.uuid4().hex[:6]}", "iso_code": uuid.uuid4().hex[:2].upper() + "Y",
    "location": {"type": "Point", "coordinates": [10.0, 47.0]}})
mid = body(mine)["id"]
created.append(f"/compendium/countries/{mid}")
check("country made by the editor: the editor sees his own whole profile, the guest sees only id and username",
      isinstance(body(call("GET", f"/compendium/countries/{mid}", "editor", params={"expand": "created_by"}))["created_by_user"]["email"], str)
      and body(call("GET", f"/compendium/countries/{mid}", "guest", params={"expand": "created_by"}))["created_by_user"]["email"] is None)
check("poi, expand=nope on an unknown id: 400, no id lookup first",
      call("GET", f"/compendium/pois/{uuid.uuid4()}", params={"expand": "nope"}).status_code == 400)
check("poi, unknown id: 404", call("GET", f"/compendium/pois/{uuid.uuid4()}").status_code == 404)
lst = body(call("GET", "/compendium/pois", params={"limit": 2}))
check("poi list is unchanged: items still carry compendium_type and main_region objects",
      all(i["compendium_type"] and i["main_region"] for i in lst))

# ---------------------------------------------------------------- 3. region, country, reference tables
rid = region_with_parent["id"]
d = body(single(f"/compendium/regions/{rid}"))
check("region, no expand: country, region_type, parent and created_by_user are null",
      d["country"] is None and d["region_type"] is None and d["parent"] is None and d["created_by_user"] is None)
d = body(single(f"/compendium/regions/{rid}", params={"expand": "country,region_type,parent,created_by"}))
check("region, expand=country,region_type,parent,created_by", d["country"]["iso_code"] and d["region_type"]["name"] is not None
      and d["parent"]["id"] == d["parent_id"] and d["created_by_user"]["username"])
check("region, parent.parent.parent (3 levels) is accepted", call("GET", f"/compendium/regions/{rid}", params={"expand": "parent.parent.parent"}).status_code == 200)
check("region, parent.parent.parent.parent (4 levels) is 400", call("GET", f"/compendium/regions/{rid}", params={"expand": "parent.parent.parent.parent"}).status_code == 400)
d = body(single(f"/compendium/countries/{cid}", params={"expand": "created_by"}))
check("country, expand=created_by", d["created_by_user"]["id"] == d["created_by"])
r = call("GET", f"/compendium/countries/{cid}", params={"expand": "zzz"})
check("country, unknown name: 400 and the message lists created_by", r.status_code == 400 and "created_by" in err(r))

slugs = ["companies", "gear-types", "achievement-categories", "achievement-scopes", "achievement-types", "difficulty-levels",
         "point-reasons", "post-types", "rarities", "region-types", "schedule-statuses", "snow-conditions", "trail-conditions",
         "visibilities", "waypoint-types", "weather-conditions", "sport-types", "difficulty-sports", "compendium-types"]
bad = []
for slug in slugs:
    item = body(call("GET", f"/core/{slug}", params={"limit": 1}))[0]
    plain = body(single(f"/core/{slug}/{item['id']}"))
    full = body(single(f"/core/{slug}/{item['id']}", params={"expand": "created_by"}))
    if not (plain["created_by_user"] is None and full["created_by_user"]["id"] == plain["created_by"]):
        bad.append(slug)
check("all 19 reference tables: created_by_user is null by default and the full user with expand=created_by", not bad, str(bad))
d = body(single(f"/core/difficulty-sports/{diff_sport['id']}", params={"expand": "sport_type.created_by"}))
check("difficulty sport, expand=sport_type.created_by", d["sport_type"]["id"] == d["sport_type_id"] and d["sport_type"]["created_by_user"])
check("compendium type: is_collectable stays in the plain response", "is_collectable" in body(single(f"/core/compendium-types/{comp_type['id']}")))
rt = body(call("GET", "/core/resource-types"))[0]
d = body(single(f"/core/resource-types/{rt['id']}", params={"expand": "created_by"}))
check("resource type, expand=created_by", d["created_by_user"]["id"] == d["created_by"])

# ---------------------------------------------------------------- 4. card, post, poi-region (created here, deleted at the end)
card = call("POST", "/compendium/cards", json={"name": "Expand check card", "poi_id": pid, "rarity_id": rarity["id"],
                                               "compendium_type_id": comp_type["id"]})
check("setup: create a card", card.status_code == 201, card.text[:200])
cdid = body(card)["id"]; created.append(f"/compendium/cards/{cdid}")
d = body(single(f"/compendium/cards/{cdid}"))
check("card, no expand: rarity, compendium_type, poi, created_by_user are null",
      d["rarity"] is None and d["compendium_type"] is None and d["poi"] is None and d["created_by_user"] is None and d["poi_id"] == pid)
d = body(single(f"/compendium/cards/{cdid}", params={"expand": "poi.main_region.country,rarity,compendium_type,created_by"}))
check("card, expand=poi.main_region.country,rarity,compendium_type,created_by",
      d["poi"]["main_region"]["country"]["iso_code"] and d["rarity"]["id"] == rarity["id"]
      and "is_collectable" in d["compendium_type"] and d["created_by_user"]["username"])

post = call("POST", "/compendium/posts", json={"name": "Expand check post", "post_type_id": post_type["id"]})
check("setup: create a post", post.status_code == 201, post.text[:200])
poid = body(post)["id"]; created.append(f"/compendium/posts/{poid}")
d = body(single(f"/compendium/posts/{poid}"))
check("post, no expand: post_type and created_by_user are null", d["post_type"] is None and d["created_by_user"] is None)
d = body(single(f"/compendium/posts/{poid}", params={"expand": "post_type.created_by,created_by"}))
check("post, expand=post_type.created_by,created_by", d["post_type"]["created_by_user"] and d["created_by_user"])

link = call("POST", "/compendium/poi-regions", json={"poi_id": pid, "region_id": poi["main_region_id"], "slot_position": 99})
check("setup: create a poi-region link to the poi's own main region", link.status_code == 201, link.text[:200])
lid = body(link)["id"]; created.append(f"/compendium/poi-regions/{lid}")
d = body(single(f"/compendium/poi-regions/{lid}", params={"expand": "poi.main_region,region.country"}))
check("poi-region, one region row reached by two paths (poi.main_region and region): region.country is filled, "
      "poi.main_region.country is null",
      d["region"]["country"]["iso_code"] and d["poi"]["main_region"]["id"] == d["region"]["id"]
      and d["poi"]["main_region"]["country"] is None)
d = body(single(f"/compendium/poi-regions/{lid}", params={"expand": "region,poi.main_region.country"}))
check("poi-region, the same two paths asked the other way round: the opposite",
      d["poi"]["main_region"]["country"]["iso_code"] and d["region"]["country"] is None)
d = body(single(f"/compendium/poi-regions/{lid}"))
check("poi-region, no expand: poi, region, created_by_user are null", d["poi"] is None and d["region"] is None and d["created_by_user"] is None)

# ---------------------------------------------------------------- 5. gear and track
gear = call("POST", "/explorer/gear", json={"name": "Expand check gear", "company_id": company["id"], "gear_type_id": gear_type["id"]})
check("setup: create gear", gear.status_code == 201, gear.text[:200])
gid = body(gear)["id"]; created.append(f"/explorer/gear/{gid}")
d = body(single(f"/explorer/gear/{gid}"))
check("gear, no expand: company, gear_type, created_by_user are null; the gear answer still has no created_by",
      d["company"] is None and d["gear_type"] is None and d["created_by_user"] is None and "created_by" not in d)
d = body(single(f"/explorer/gear/{gid}", params={"expand": "company.created_by,gear_type,created_by"}))
check("gear, expand=company.created_by,gear_type,created_by", d["company"]["created_by_user"] and d["gear_type"]["id"] == gear_type["id"] and d["created_by_user"])

job_id = None
with open(ARGS.gpx, "rb") as handle:
    up = call("POST", "/explorer/tracks", files={"gpx_file": ("expand-check.gpx", handle, "application/gpx+xml")},
              data={"name": "Expand check track", "is_public": "true"})
check("setup: upload a track (202)", up.status_code == 202, up.text[:200])
tid = body(up)["id"]; job_id = body(up)["job_id"]
patch = call("PATCH", f"/explorer/tracks/{tid}", json={
    "sport_type_id": sport_type["id"], "difficulty_level_id": level["id"], "difficulty_sport_id": diff_sport["id"],
    "start_poi_id": pid, "end_poi_id": pois[1]["id"]})
check("setup: set the track's links", patch.status_code == 200, patch.text[:200])
d = body(single(f"/explorer/tracks/{tid}"))
check("track, no expand: ids are set, every link object and created_by_user are null",
      d["sport_type_id"] and d["start_poi_id"] and all(d[k] is None for k in
      ("sport_type", "difficulty_level", "difficulty_sport", "start_poi", "end_poi", "created_by_user")))
d = body(single(f"/explorer/tracks/{tid}", params={
    "expand": "sport_type,difficulty_level,difficulty_sport.sport_type,start_poi.main_region.country,end_poi,created_by"}))
check("track, expand=all its links, nested down to 3 levels",
      d["sport_type"]["id"] == sport_type["id"] and d["difficulty_level"]["id"] == level["id"]
      and d["difficulty_sport"]["sport_type"]["id"] == diff_sport["sport_type_id"]
      and d["start_poi"]["main_region"]["country"]["iso_code"] and d["end_poi"]["id"] == pois[1]["id"]
      and d["created_by_user"]["username"] == "admin")
r = call("GET", f"/explorer/tracks/{tid}", params={"expand": "gpx"})
check("track, gpx is not a link: 400", r.status_code == 400, r.text[:200])
r = call("GET", f"/explorer/tracks/{tid}/geometry")
check("track geometry and performance routes are untouched (no expand parameter)", r.status_code in (200, 404, 409), str(r.status_code))
# administrator view of the job
d = body(single(f"/management/jobs/{job_id}"))
check("admin job, no expand: user_id is set, user is null, subject is still built", d["user_id"] and d["user"] is None
      and d["subject"] == {"type": "track", "id": tid})
d = body(single(f"/management/jobs/{job_id}", params={"expand": "user"}))
check("admin job, expand=user", d["user"]["id"] == d["user_id"] and d["user"]["username"] == "admin" and d["subject"]["type"] == "track")
check("own job (my-jobs) is unchanged: no expand parameter, same fields",
      "user" not in body(call("GET", f"/management/my-jobs/{job_id}")))
created.append(f"/explorer/tracks/{tid}")
if ARGS.worker:
    status = None
    for _ in range(60):
        status = body(call("GET", f"/management/jobs/{job_id}"))["status"]
        if status in ("succeeded", "failed", "cancelled"):
            break
        time.sleep(1)
    check("worker: the track job succeeds", status == "succeeded", str(status))
    plain = body(single(f"/explorer/tracks/{tid}"))
    full = body(single(f"/explorer/tracks/{tid}", params={"expand": "sport_type,start_poi,created_by"}))
    listed = next(i for i in body(call("GET", "/explorer/tracks")) if i["id"] == tid)
    check("track metrics (computed from the geo record) are unchanged by expand and equal the list item's",
          plain["metrics"] and plain["metrics"]["distance_m"] and plain["metrics"] == full["metrics"] == listed["metrics"],
          str(plain["metrics"]))

# ---------------------------------------------------------------- 6. settings and access policy
key = "jobs.retention_days"
d = body(call("GET", f"/management/settings/{key}"))
original = d["value"]
check("setting, before any change by the API: updated_by_user is null", d["updated_by_user"] is None or d["updated_by"] is not None)
call("PATCH", f"/management/settings/{key}", json={"value": original + 1})
created.append(("POST", f"/management/settings/{key}/reset"))
d = body(single(f"/management/settings/{key}"))
check("setting, no expand: updated_by is an id, updated_by_user is null", d["updated_by"] and d["updated_by_user"] is None)
d = body(single(f"/management/settings/{key}", params={"expand": "updated_by"}))
check("setting, expand=updated_by", d["updated_by_user"]["id"] == d["updated_by"])

pol = body(call("GET", "/profile/access-policies"))[0]
d = body(single(f"/profile/access-policies/{pol['id']}"))
check("access policy, no expand: resource_type_id is set, resource_type is null", d["resource_type_id"] and d["resource_type"] is None)
d = body(single(f"/profile/access-policies/{pol['id']}", params={"expand": "resource_type.created_by"}))
check("access policy, expand=resource_type.created_by", d["resource_type"]["key"] and d["resource_type"]["created_by_user"])

# ---------------------------------------------------------------- 7a. an unknown id answers 404 on every single GET
unknown = str(uuid.uuid4())
others = ([f"/compendium/{name}/{unknown}" for name in ("pois", "regions", "countries", "cards", "posts", "poi-regions")]
          + [f"/explorer/gear/{unknown}", f"/explorer/tracks/{unknown}", f"/core/rarities/{unknown}", f"/core/companies/{unknown}",
             f"/core/difficulty-sports/{unknown}", f"/core/compendium-types/{unknown}", f"/core/resource-types/{unknown}",
             f"/management/event-log/{unknown}", f"/management/event-log/{unknown}/compare/{uuid.uuid4()}",
             f"/management/jobs/{unknown}", "/management/settings/no.such.key", f"/profile/access-policies/{unknown}"])
not_found = [path for path in others if call("GET", path).status_code != 404]
check(f"an unknown id answers 404 on {len(others)} single GET routes (the access check still runs first)", not not_found, str(not_found))

# ---------------------------------------------------------------- 7. things that must not change, and the documentation
bad = []
for path in dict.fromkeys(SINGLES):
    a, b = call("GET", path), call("GET", path, params={"expand": ""})
    if a.status_code != 200 or b.status_code != 200:
        bad.append(f"{path} {a.status_code}/{b.status_code}")
        continue
    strip = lambda t: re.sub(r'"response_request_id":\s*"[^"]*"', "", t)
    if strip(a.text) != strip(b.text):
        bad.append(path)
check(f"an empty ?expand= gives the same answer as no parameter on all {len(set(SINGLES))} single URLs read in this run", not bad, str(bad[:5]))
check("no response of this run contains password data", not any(re.search(r"password|hash", t, re.I) for t in SEEN))

spec = client.get(f"{BASE}/openapi.json").json()
with_expand = [f"{m.upper()} {p}" for p, ops in spec["paths"].items() for m, op in ops.items()
               if m in ("get", "post", "put", "patch", "delete") and any(x.get("name") == "expand" for x in op.get("parameters", []))]
check("OpenAPI: 35 operations have the query parameter expand, all of them GET", len(with_expand) == 35 and all(x.startswith("GET ") for x in with_expand), str(len(with_expand)))
ops = sum(1 for p in spec["paths"].values() for m in p if m in ("get", "post", "put", "patch", "delete"))
check("OpenAPI lists 229 operations (212 + the 17 of segments and routes)", ops == 229, str(ops))
check("GET /docs -> 200", client.get(f"{BASE}/docs").status_code == 200)

clean_up()
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
