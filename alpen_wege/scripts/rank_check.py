#!/usr/bin/env python
"""Live check of the rank column (difficulty levels, difficulty sports, rarities, visibilities), against a RUNNING api
(needs the seeded dev users and the push_data seed).

    pip install httpx
    python scripts/rank_check.py --base http://localhost:8000

Creates and deletes a few rows in the rarities table (and changes nothing else). The event log keeps the rows that
these writes cause. Seed users: scripts/init_seed.py (password !Password@5005).
"""
import argparse
import io
import sys
import uuid

import httpx

parser = argparse.ArgumentParser(description="Live check of the rank column of the four scale tables")
parser.add_argument("--base", default="http://localhost:8000")
parser.add_argument("--password", default="!Password@5005")
ARGS = parser.parse_args()
API = ARGS.base.rstrip("/") + "/api/v1"
results = []
created = []
client = httpx.Client(timeout=30)


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if (detail and not cond) else ""), flush=True)


def login(who):
    r = client.post(f"{API}/profile/auth/login", json={"email": f"{who}@alpenwege.dev", "password": ARGS.password})
    return r.json()["response_data"]["access_token"]


TOKEN = {who: login(who) for who in ("admin", "viewer")}


def call(method, path, who="admin", **kw):
    return client.request(method, API + path, headers={"Authorization": f"Bearer {TOKEN[who]}"}, **kw)


def data(r):
    return r.json().get("response_data")


def cleanup():
    for path in created:
        call("DELETE", path)


# ---------------------------------------------------------------- lists: rank is in the answer, sort and filter work
for path, expected_max in (("difficulty-levels", 7), ("rarities", 6), ("visibilities", 8)):
    r = call("GET", f"/core/{path}", params={"sort": "rank"})
    rows = data(r)
    ranks = [x.get("rank") for x in rows]
    check(f"GET /core/{path}?sort=rank: 200, every row has an integer rank", r.status_code == 200 and rows and all(isinstance(x, int) for x in ranks), r.text[:200])
    check(f"GET /core/{path}?sort=rank: ascending, 1 to {expected_max}", ranks == sorted(ranks) and ranks[0] == 1 and ranks[-1] == expected_max, str(ranks))
    r = call("GET", f"/core/{path}", params={"sort": "-rank"})
    ranks = [x["rank"] for x in data(r)]
    check(f"GET /core/{path}?sort=-rank: descending", ranks == sorted(ranks, reverse=True) and ranks[0] == expected_max, str(ranks))
    r = call("GET", f"/core/{path}", params={"rank_min": 2, "rank_max": 3})
    ranks = sorted(x["rank"] for x in data(r))
    check(f"GET /core/{path}?rank_min=2&rank_max=3: only ranks 2 and 3", r.status_code == 200 and ranks == [2, 3], str(ranks))
    r = call("GET", f"/core/{path}", params={"rank_min": 5000})
    check(f"GET /core/{path}?rank_min=5000: empty list", r.status_code == 200 and data(r) == [] and r.json()["response_pagination"]["pagination_total"] == 0, r.text[:200])
    for bad in ("abc", "99999999999", "1.5"):
        r = call("GET", f"/core/{path}", params={"rank_min": bad})
        check(f"GET /core/{path}?rank_min={bad}: 422", r.status_code == 422, str(r.status_code))
    r = call("GET", f"/core/{path}", params={"rank_min": 4, "rank_max": 2})
    check(f"GET /core/{path}?rank_min=4&rank_max=2: empty, not an error", r.status_code == 200 and data(r) == [], str(r.status_code))

r = call("GET", "/core/difficulty-sports", params={"limit": 1000})
rows = data(r)
check("GET /core/difficulty-sports: 67 rows, all with a rank", r.status_code == 200 and len(rows) == 67 and all(isinstance(x.get("rank"), int) for x in rows), r.text[:200])
by_sport = {}
for x in rows:
    by_sport.setdefault(x["sport_type_id"], []).append(x)
check("difficulty-sports: inside a sport type the rank follows point_factor",
      all((a["point_factor"] <= b["point_factor"]) == (a["rank"] <= b["rank"])
          for items in by_sport.values() for a in items for b in items), "")
sport = next(s for s, items in by_sport.items() if len(items) == 17)           # climbing: UIAA and French in one scale
r = call("GET", "/core/difficulty-sports", params={"sport_type_id": sport, "sort": "-rank", "rank_min": 14})
names = [x["name"] for x in data(r)]
check("difficulty-sports: sport_type_id with rank_min and sort=-rank", r.status_code == 200 and len(names) == 2 and names[0].startswith("French 8a+"), str(names))

# ---------------------------------------------------------------- a table without a scale has no rank
r = call("GET", "/core/snow-conditions", params={"limit": 3})
check("snow-conditions rows have no rank", r.status_code == 200 and all("rank" not in x for x in data(r)), r.text[:200])
r = call("GET", "/core/snow-conditions", params={"sort": "rank"})
check("snow-conditions?sort=rank: 422", r.status_code == 422, str(r.status_code))
r = call("GET", "/core/snow-conditions", params={"rank_min": 1})
check("snow-conditions?rank_min=1: the unknown parameter is ignored, 200", r.status_code == 200, str(r.status_code))

# ---------------------------------------------------------------- create, update, delete
unique = uuid.uuid4().hex[:8]
new = {"name": f"RankCheck {unique}", "color": "#112233", "icon": f"rank_check_{unique}", "point_factor": 1.0}
r = call("POST", "/core/rarities", json=new)
check("POST /core/rarities without rank: 422", r.status_code == 422, r.text[:200])
for bad in (-1, 1001, 70000, "x", 2.5, None):
    r = call("POST", "/core/rarities", json={**new, "rank": bad})
    check(f"POST /core/rarities with rank {bad!r}: 422", r.status_code == 422, str(r.status_code))
r = call("POST", "/core/rarities", json={**new, "rank": 3})
row = data(r)
check("POST /core/rarities with rank 3: 201 and the rank is in the answer", r.status_code == 201 and row and row["rank"] == 3, r.text[:200])
if row:
    created.append(f"/core/rarities/{row['id']}")
    rid = row["id"]
    r = call("GET", f"/core/rarities/{rid}")
    check("GET one rarity: rank 3", r.status_code == 200 and data(r)["rank"] == 3, r.text[:200])
    r = call("GET", f"/core/rarities/{rid}", params={"expand": "created_by"})
    check("GET one rarity with expand=created_by: rank and user", r.status_code == 200 and data(r)["rank"] == 3 and data(r)["created_by_user"], r.text[:200])
    r = call("PATCH", f"/core/rarities/{rid}", json={"rank": 5})
    check("PATCH rank 5: 200", r.status_code == 200 and data(r)["rank"] == 5, r.text[:200])
    r = call("PATCH", f"/core/rarities/{rid}", json={"name": f"RankCheck {unique} b"})
    check("PATCH only the name: rank stays 5", r.status_code == 200 and data(r)["rank"] == 5, r.text[:200])
    for bad in (-1, 1001):
        r = call("PATCH", f"/core/rarities/{rid}", json={"rank": bad})
        check(f"PATCH rank {bad}: 422", r.status_code == 422, str(r.status_code))
    for field in ("rank", "point_factor", "color", "icon"):
        r = call("PATCH", f"/core/rarities/{rid}", json={field: None})
        check(f"PATCH {field} null: 422 (a required column, not a database error)", r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    r = call("GET", f"/core/rarities/{rid}")
    check("after the bad PATCH calls the rank is still 5", data(r)["rank"] == 5, r.text[:200])
    r = call("POST", "/core/rarities", json={**new, "rank": 3}, who="viewer")
    check("viewer cannot create a rarity: 403", r.status_code == 403, str(r.status_code))

# ---------------------------------------------------------------- CSV import carries the rank
csv_body = f"name,color,icon,point_factor,rank\nCsv A {unique},#000000,csv_a_{unique},1,2\nCsv B {unique},#000000,csv_b_{unique},1,4\n"
r = call("POST", "/core/rarities/upload-csv", files={"file": ("r.csv", io.BytesIO(csv_body.encode()), "text/csv")})
check("POST /core/rarities/upload-csv with a rank column: 201, 2 inserted", r.status_code in (200, 201) and data(r)["inserted"] == 2 and not data(r)["errors"], r.text[:200])
r = call("GET", "/core/rarities", params={"q": unique, "sort": "rank"})
rows = [x for x in data(r) if x["name"].startswith("Csv ")]
check("the imported rows have ranks 2 and 4", [x["rank"] for x in rows] == [2, 4], r.text[:200])
for x in rows:
    created.append(f"/core/rarities/{x['id']}")
bad_csv = f"name,color,icon,point_factor\nCsv C {unique},#000000,csv_c_{unique},1\n"
r = call("POST", "/core/rarities/upload-csv", files={"file": ("r.csv", io.BytesIO(bad_csv.encode()), "text/csv")})
r2 = call("GET", "/core/rarities", params={"q": f"Csv C {unique}"})
check("CSV without the rank column: nothing inserted, one clear error naming rank (no 500)",
      r.status_code in (200, 201) and data(r)["inserted"] == 0 and len(data(r)["errors"]) == 1 and "rank" in data(r)["errors"][0] and data(r2) == [], r.text[:200])
bad_csv = f"name,color,icon,point_factor,rank\nCsv D {unique},#000000,csv_d_{unique},1,\nCsv E {unique},#000000,csv_e_{unique},1,6\n"
r = call("POST", "/core/rarities/upload-csv", files={"file": ("r.csv", io.BytesIO(bad_csv.encode()), "text/csv")})
rows = data(call("GET", "/core/rarities", params={"q": f"Csv E {unique}"}))
check("CSV with an empty rank in one row: that row is reported, the other row is imported",
      r.status_code in (200, 201) and data(r)["inserted"] == 1 and data(r)["errors"] == ["row 2: missing value for rank"] and len(rows) == 1, r.text[:200])
for x in rows:
    created.append(f"/core/rarities/{x['id']}")

# ---------------------------------------------------------------- nested objects carry the rank
spec = call("GET", "/../openapi.json").json() if False else client.get(ARGS.base.rstrip("/") + "/openapi.json").json()
schemas = spec["components"]["schemas"]
card = next((v for k, v in schemas.items() if k.startswith("CardRead")), None)
ref = (card or {}).get("properties", {}).get("rarity", {})
text = str(ref)
check("openapi: CardRead.rarity uses the ranked schema", "RefRankedRead" in text, text[:200])
detail = next((v for k, v in schemas.items() if k.startswith("TrackDetail")), None)
text = str((detail or {}).get("properties", {}).get("difficulty_level", {}))
check("openapi: TrackDetail.difficulty_level uses the ranked schema", "RefRankedDetail" in text, text[:200])

cleanup()
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
