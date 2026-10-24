#!/usr/bin/env python
"""Live check of the new URL scheme against a RUNNING api (needs the seeded dev users).

    pip install httpx            # websockets is already there (uvicorn[standard])
    python scripts/e2e_check.py --base http://localhost:8000 [--gpx /tmp/full.gpx] [--worker]

Makes four logins, reads every list URL, checks that the old URLs are gone, permissions, a create/update/delete
and a CSV import on /core/companies, a 23 MB upload (must be refused with 413), a real GPX upload (202, Location
header, job URL), both WebSockets and the Swagger token URL. With --worker it also waits for the track job.
Leaves behind: one archived test track ("E2E track"). The test company is deleted again.
Make a sample GPX with: python scripts/make_sample_gpx.py --variant full --out /tmp/full.gpx
Seed users: scripts/init_seed.py (password !Password@5005, admin/editor/viewer/guest @alpenwege.dev).
"""
import argparse
import asyncio, json, os, re, sys, time, uuid
import httpx, websockets

parser = argparse.ArgumentParser(description="Live check of the /api/v1/{app}/{resource} URL scheme")
parser.add_argument("--base", default="http://localhost:8000")
parser.add_argument("--gpx", default="/tmp/full.gpx")
parser.add_argument("--password", default="!Password@5005")
parser.add_argument("--worker", action="store_true", help="a Celery worker is running: wait for the track job")
ARGS = parser.parse_args()
BASE = ARGS.base.rstrip("/")
API = BASE + "/api/v1"
WS_BASE = BASE.replace("https://", "wss://").replace("http://", "ws://")
PASSWORD = ARGS.password
GPX = ARGS.gpx
results = []

def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if (detail and not cond) else ""), flush=True)

client = httpx.Client(timeout=60)

def login(email):
    r = client.post(f"{API}/profile/auth/login", json={"email": email, "password": PASSWORD})
    return r.json()["response_data"]["access_token"] if r.status_code == 200 else None

def H(token): return {"Authorization": f"Bearer {token}"}

tokens = {u: login(f"{u}@alpenwege.dev") for u in ("admin", "editor", "viewer", "guest")}
check("login at /profile/auth/login for admin, editor, viewer, guest", all(tokens.values()))
admin, viewer = tokens["admin"], tokens["viewer"]

# ---- 1. every list URL answers 200 for the administrator
slugs = ["companies", "gear-types", "achievement-categories", "achievement-scopes", "achievement-types", "difficulty-levels",
         "point-reasons", "post-types", "rarities", "region-types", "schedule-statuses", "snow-conditions", "trail-conditions",
         "visibilities", "waypoint-types", "weather-conditions", "sport-types", "difficulty-sports", "compendium-types"]
paths = (["/profile/users/me", "/profile/users/", "/profile/access-policies", "/core/resource-types"]
         + [f"/core/{s}" for s in slugs]
         + [f"/compendium/{p}" for p in ("countries", "regions", "pois", "cards", "posts", "poi-regions")]
         + ["/explorer/gear", "/explorer/tracks", "/management/settings", "/management/event-log",
            "/management/jobs/stats", "/management/my-jobs", "/management/celery/status"])
JOBS_WITH_DATES = {"created_from": "2020-01-01T00:00:00", "created_to": "2031-01-01T00:00:00"}  # without both dates the list returns 500: bug already in the original code
def status_of(p):
    try:
        return client.get(API + p, headers=H(admin)).status_code
    except httpx.HTTPError as exc:
        return type(exc).__name__
bad = [(p, status_of(p)) for p in paths]
bad = [(p, s) for p, s in bad if s != 200]
check(f"GET {len(paths)} list/read URLs under the new scheme answer 200 (admin)", not bad, str(bad))

check("GET /management/jobs (with both dates) -> 200", client.get(f"{API}/management/jobs", headers=H(admin), params=JOBS_WITH_DATES).status_code == 200)

# ---- 2. old URLs are gone
old = ["/pois", "/cards", "/countries", "/regions", "/posts", "/poi-regions", "/gear", "/tracks", "/ref/companies", "/ref/sport-types",
       "/auth/access-policies", "/auth/resource-types", "/users/me", "/users/", "/jobs"]
still = [(p, s) for p in old if (s := client.get(API + p, headers=H(admin)).status_code) != 404]
still += [(p, s) for p in ("/auth/login", "/auth/register", "/ws/ticket") if (s := client.post(API + p, json={}).status_code) != 404]
check(f"{len(old) + 3} old URLs answer 404", not still, str(still))

# ---- 3. permissions still hold at the new URLs
check("no token: GET /compendium/pois -> 401", client.get(f"{API}/compendium/pois").status_code == 401)
check("no token: GET /management/settings -> 401", client.get(f"{API}/management/settings").status_code == 401)
for p in ("/management/settings", "/core/resource-types", "/profile/access-policies", "/profile/users/", "/management/jobs/stats"):
    check(f"viewer: GET {p} -> 403", client.get(API + p, headers=H(viewer)).status_code == 403)
check("viewer: POST /core/companies -> 403", client.post(f"{API}/core/companies", headers=H(viewer), json={"name": "x", "color": "#1", "icon": "i"}).status_code == 403)

# ---- 4. create, read, update, delete through the factory-built ref router
r = client.post(f"{API}/core/companies", headers=H(admin), json={"name": "E2E Co", "color": "#112233", "icon": "building"})
cid = r.json().get("response_data", {}).get("id") if r.status_code == 201 else None
check("POST /core/companies -> 201", r.status_code == 201, r.text[:200])
if cid:
    check("GET /core/companies/{id} -> 200", client.get(f"{API}/core/companies/{cid}", headers=H(admin)).status_code == 200)
    check("PATCH /core/companies/{id} -> 200", client.patch(f"{API}/core/companies/{cid}", headers=H(admin), json={"name": "E2E Co 2"}).status_code == 200)
    log = client.get(f"{API}/management/event-log", headers=H(admin), params={"entity_type": "core_ref_company", "limit": 10}).json()
    actions = {e.get("action") for e in log.get("response_data", [])}
    check("event log recorded the create and the update of the company", {"create", "update"} <= actions or {"created", "updated"} <= actions, str(actions))
    check("DELETE /core/companies/{id} -> 200", client.delete(f"{API}/core/companies/{cid}", headers=H(admin)).status_code == 200)
    check("GET deleted company -> 404", client.get(f"{API}/core/companies/{cid}", headers=H(admin)).status_code == 404)
csv_body = b"name,color,icon\nCsv Co,#aabbcc,truck\n"
r = client.post(f"{API}/core/companies/upload-csv", headers=H(admin), files={"file": ("c.csv", csv_body, "text/csv")})
check("POST /core/companies/upload-csv imports (envelope code 201)", r.status_code in (200, 201) and r.json().get("response_code") == 201, r.text[:200])
for company in client.get(f"{API}/core/companies", headers=H(admin), params={"limit": 1000}).json()["response_data"]:
    if company["name"] == "Csv Co":
        client.delete(f"{API}/core/companies/{company['id']}", headers=H(admin))

# ---- 5. track upload: size guard, Location header, job URL
big = b"x" * 23_000_000   # the guard allows (GPX_MAX_UPLOAD_MB + 1) MiB = 22,020,096 bytes
r = client.post(f"{API}/explorer/tracks", headers=H(admin), data={"name": "big"}, files={"gpx_file": ("big.gpx", big, "application/gpx+xml")})
check("23 MB upload to /explorer/tracks is stopped by the size guard (413)", r.status_code == 413, f"{r.status_code} {r.text[:120]}")
r = client.post(f"{API}/tracks", headers=H(admin), data={"name": "big"}, files={"gpx_file": ("big.gpx", big, "application/gpx+xml")})
check("23 MB upload to the OLD /tracks -> 404", r.status_code == 404, str(r.status_code))
job_id = None
with open(GPX, "rb") as f:
    r = client.post(f"{API}/explorer/tracks", headers=H(admin), data={"name": "E2E track"}, files={"gpx_file": ("full.gpx", f, "application/gpx+xml")})
check("POST /explorer/tracks with a GPX file -> 202", r.status_code == 202, f"{r.status_code} {r.text[:200]}")
if r.status_code == 202:
    job_id = r.json()["response_data"]["job_id"]
    loc = r.headers.get("location", "")
    check("Location header is /api/v1/management/my-jobs/<job_id>", loc == f"/api/v1/management/my-jobs/{job_id}", loc)
    g = client.get(BASE + loc, headers=H(admin))
    check("GET Location -> 200 and is that job", g.status_code == 200 and g.json()["response_data"]["id"] == job_id, g.text[:160])
    check("job is in GET /management/my-jobs", any(j["id"] == job_id for j in client.get(f"{API}/management/my-jobs", headers=H(admin)).json()["response_data"]))
    check("admin sees it in GET /management/jobs/{id}", client.get(f"{API}/management/jobs/{job_id}", headers=H(admin)).status_code == 200)

# ---- 6. WebSocket
async def ws_checks():
    t = client.post(f"{API}/management/ws/ticket", headers=H(admin))
    check("POST /management/ws/ticket -> 200", t.status_code == 200, t.text[:100])
    ticket = t.json()["response_data"]["ticket"]
    async with websockets.connect(f"{WS_BASE}/api/v1/management/ws?ticket={ticket}") as ws:
        first = json.loads(await asyncio.wait_for(ws.recv(), 10))
        check("WS /management/ws: first message is 'sync'", first.get("type") == "sync", str(first)[:120])
    if job_id:
        t2 = client.post(f"{API}/management/ws/ticket", headers=H(admin)).json()["response_data"]["ticket"]
        async with websockets.connect(f"{WS_BASE}/api/v1/management/ws/jobs/{job_id}?ticket={t2}") as ws:
            first = json.loads(await asyncio.wait_for(ws.recv(), 10))
            check("WS /management/ws/jobs/{id}: first message is 'sync'", first.get("type") == "sync", str(first)[:120])
    t3 = client.post(f"{API}/management/ws/ticket", headers=H(admin)).json()["response_data"]["ticket"]
    try:
        async with websockets.connect(f"{WS_BASE}/api/v1/ws?ticket={t3}") as ws:
            check("WS on the OLD path /api/v1/ws is refused", False, "connected")
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        check("WS on the OLD path /api/v1/ws is refused (handshake rejected 403/404)", status in (403, 404), f"{type(exc).__name__} {status}")
asyncio.run(ws_checks())

# ---- 7. Swagger
spec = client.get(f"{BASE}/openapi.json").json()
token_url = spec["components"]["securitySchemes"]["OAuth2PasswordBearer"]["flows"]["password"]["tokenUrl"]
check("Swagger tokenUrl is /api/v1/profile/auth/login", token_url == "/api/v1/profile/auth/login", token_url)
check("GET /docs -> 200", client.get(f"{BASE}/docs").status_code == 200)
ops = sum(1 for p in spec["paths"].values() for m in p if m in ("get", "post", "put", "patch", "delete"))
check("OpenAPI lists 212 operations (as before)", ops == 212, str(ops))

# ---- 8. job finishes when a worker runs
if ARGS.worker and job_id:
    status = None
    for _ in range(60):
        status = client.get(f"{API}/management/my-jobs/{job_id}", headers=H(admin)).json()["response_data"]["status"]
        if status in ("succeeded", "failed", "cancelled"): break
        time.sleep(1)
    check("track job reaches 'succeeded' through the worker", status == "succeeded", str(status))
    tr = client.get(f"{API}/explorer/tracks", headers=H(admin)).json()["response_data"]
    check("track appears in GET /explorer/tracks with status ready", any(t["processing_status"] == "ready" for t in tr), str([t["processing_status"] for t in tr]))

if job_id:
    for t in client.get(f"{API}/explorer/tracks", headers=H(admin)).json()["response_data"]:
        if t["name"] == "E2E track":
            client.delete(f"{API}/explorer/tracks/{t['id']}", headers=H(admin))   # archives it

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
