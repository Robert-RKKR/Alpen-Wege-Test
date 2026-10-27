#!/usr/bin/env python
"""Sandbox measurement for the list-filter proposal: payload size and time per limit value, and what odd values do.

    python measure_lists.py [--base http://127.0.0.1:8000/api/v1] [--n 7]
"""
import argparse
import gzip
import statistics
import time
import httpx

parser = argparse.ArgumentParser()
parser.add_argument("--base", default="http://127.0.0.1:8000/api/v1")
parser.add_argument("--n", type=int, default=7)
args = parser.parse_args()
client = httpx.Client(timeout=120)
token = client.post(f"{args.base}/profile/auth/login", json={"email": "admin@alpenwege.dev", "password": "!Password@5005"}).json()["response_data"]["access_token"]
H = {"Authorization": f"Bearer {token}", "Connection": "close"}   # a server that answers 500 closes the connection


class Reset:
    # what the caller sees when the server drops the connection (an unhandled error)
    status_code = "RESET"
    content = b""


def get(path, params=None):
    try:
        return client.get(args.base + path, headers=H, params=params)
    except httpx.TransportError:
        return Reset()


def timed(path, params):
    times, size, gz, status, total = [], 0, 0, None, None
    for _ in range(args.n):
        start = time.perf_counter()
        r = get(path, params)
        times.append((time.perf_counter() - start) * 1000)
        status = r.status_code
    if status == 200:
        size, gz = len(r.content), len(gzip.compress(r.content))
        pag = r.json().get("response_pagination") or {}
        total = f"{len(r.json()['response_data'])} of {pag.get('pagination_total')}"
    return status, size, gz, statistics.median(times), total


print("== payload and time per limit value (median of %d requests)" % args.n)
print(f"{'list':<14}{'limit':>7}{'rows':>16}{'KB':>9}{'KB gzip':>9}{'median ms':>11}")
for name, path, limits in (("pois", "/compendium/pois", (10, 50, 100, 200, 500, 1000, 5000, 20758)),
                           ("regions", "/compendium/regions", (50, 100, 500, 1000, 2000)),
                           ("compendium-types", "/core/compendium-types", (100, 1000)),
                           ("countries", "/compendium/countries", (100, 250))):
    for limit in limits:
        status, size, gz, ms, rows = timed(path, {"limit": limit})
        print(f"{name:<14}{limit:>7}{rows if rows else status:>16}{size / 1024:>9.0f}{gz / 1024:>9.0f}{ms:>11.0f}")

print("\n== deep pages of pois (limit 100)")
for offset in (0, 5000, 10000, 20000):
    status, size, gz, ms, rows = timed("/compendium/pois", {"limit": 100, "offset": offset})
    print(f"offset {offset:>6}: {rows}, {ms:.0f} ms")

print("\n== odd values: status code of each list route (a 500 is a bug, 422 is the right answer)")
routes = ("/compendium/pois", "/compendium/regions", "/compendium/countries", "/core/rarities", "/explorer/tracks",
          "/explorer/gear", "/management/event-log", "/management/jobs", "/management/my-jobs", "/profile/access-policies",
          "/profile/users/", "/core/resource-types")
cases = (("limit=-1", {"limit": -1}), ("limit=0", {"limit": 0}), ("limit=1000000", {"limit": 1000000}),
         ("limit=abc", {"limit": "abc"}), ("offset=-5", {"offset": -5}), ("offset=99999999", {"offset": 99999999}))
print(f"{'route':<26}" + "".join(f"{c[0]:>16}" for c in cases))
for route in routes:
    row = []
    for label, params in cases:
        if route == "/profile/users/" and "offset" in params:
            params = {"skip": params["offset"]}
        if route == "/management/jobs":
            params = {**params, "created_from": "2020-01-01T00:00:00", "created_to": "2031-01-01T00:00:00"}
        r = get(route, params)
        extra = ""
        if r.status_code == 200:
            pag = r.json().get("response_pagination") or {}
            extra = f"/{len(r.json()['response_data'])}r" + (f"/L{pag.get('pagination_limit')}" if pag else "")
        row.append(f"{r.status_code}{extra}")
    print(f"{route:<26}" + "".join(f"{x:>16}" for x in row))
