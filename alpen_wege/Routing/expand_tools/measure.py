#!/usr/bin/env python
"""Counts SQL statements and measures the time of a few single-object GETs (sandbox measurement for the plan).

    python measure.py PG_LOG [--n 150]     (Postgres runs with log_statement='all'; PG_LOG is its log file)
"""
import argparse
import re
import statistics
import time
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("pg_log")
parser.add_argument("--n", type=int, default=150)
parser.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
args = parser.parse_args()
client = httpx.Client(timeout=60)
token = client.post(f"{args.base}/profile/auth/login", json={"email": "admin@alpenwege.dev", "password": "!Password@5005"}).json()["response_data"]["access_token"]
H = {"Authorization": f"Bearer {token}"}

def get(path, params=None):
    r = client.get(args.base + path, headers=H, params=params)
    return r

def selects():
    text = open(args.pg_log, errors="replace").read()
    return len(re.findall(r"LOG:\s+(?:execute [^:]*|statement): *\s*SELECT", text))

poi = get("/compendium/pois", {"limit": 1}).json()["response_data"][0]
region = get("/compendium/regions", {"limit": 1}).json()["response_data"][0]
rarity = get("/core/rarities", {"limit": 1}).json()["response_data"][0]
country = get("/compendium/countries", {"limit": 1}).json()["response_data"][0]
log = get("/management/event-log", {"limit": 1}).json()["response_data"][0]

cases = [
    ("poi", f"/compendium/pois/{poi['id']}", None),
    ("poi expand=compendium_type,main_region", f"/compendium/pois/{poi['id']}", {"expand": "compendium_type,main_region"}),
    ("poi expand=created_by", f"/compendium/pois/{poi['id']}", {"expand": "created_by"}),
    ("poi expand=main_region.country,main_region.region_type,compendium_type,created_by", f"/compendium/pois/{poi['id']}",
     {"expand": "main_region.country,main_region.region_type,compendium_type,created_by"}),
    ("region", f"/compendium/regions/{region['id']}", None),
    ("region expand=country,region_type,parent", f"/compendium/regions/{region['id']}", {"expand": "country,region_type,parent"}),
    ("country", f"/compendium/countries/{country['id']}", None),
    ("rarity", f"/core/rarities/{rarity['id']}", None),
    ("rarity expand=created_by", f"/core/rarities/{rarity['id']}", {"expand": "created_by"}),
    ("event log", f"/management/event-log/{log['id']}", None),
    ("event log expand=changed_by,entity_type", f"/management/event-log/{log['id']}", {"expand": "changed_by,entity_type"}),
]
print(f"{'request':<82} {'SELECTs':>7} {'median ms':>10} {'p95 ms':>8}")
for name, path, params in cases:
    probe = get(path, params)
    if probe.status_code != 200:
        print(f"{name:<82} status {probe.status_code}"); continue
    before = selects()
    get(path, params)
    count = selects() - before
    times = []
    for _ in range(args.n):
        start = time.perf_counter()
        get(path, params)
        times.append((time.perf_counter() - start) * 1000)
    times.sort()
    print(f"{name:<82} {count:>7} {statistics.median(times):>10.1f} {times[int(len(times) * 0.95)]:>8.1f}")
