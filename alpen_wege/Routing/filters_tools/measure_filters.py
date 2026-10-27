import statistics, time, httpx
c = httpx.Client(timeout=120); API = "http://localhost:8000/api/v1"
t = c.post(API + "/profile/auth/login", json={"email": "admin@alpenwege.dev", "password": "!Password@5005"}).json()["response_data"]["access_token"]
H = {"Authorization": "Bearer " + t}
def run(path, **params):
    times = []
    for _ in range(9):
        s = time.perf_counter(); r = c.get(API + path, params=params, headers={**H, "Connection": "close"}); times.append((time.perf_counter() - s) * 1000)
    m = r.json().get("response_pagination") or {}
    return r.status_code, statistics.median(times), len(r.content) / 1024, m.get("pagination_total")
rows = [
 ("pois default (100)", "/compendium/pois", {}),
 ("pois limit=500", "/compendium/pois", {"limit": 500}),
 ("pois q=bahnhof", "/compendium/pois", {"q": "bahnhof"}),
 ("pois q=ba (2 letters, many hits)", "/compendium/pois", {"q": "ba"}),
 ("pois q=zzzz (no hit, full scan)", "/compendium/pois", {"q": "zzzz"}),
 ("pois compendium_type_id (big type)", "/compendium/pois", {"compendium_type_id": "8cccb61d-8718-4b22-b1fa-6f98b8eda4af"}),
 ("pois bbox 7,46,8,47", "/compendium/pois", {"bbox": "7,46,8,47"}),
 ("pois near Zurich 5 km", "/compendium/pois", {"near": "8.54,47.37", "radius_m": 5000}),
 ("pois near Zurich 100 km", "/compendium/pois", {"near": "8.54,47.37", "radius_m": 100000}),
 ("pois altitude 1000..1500", "/compendium/pois", {"altitude_min": 1000, "altitude_max": 1500}),
 ("pois sort=altitude_m", "/compendium/pois", {"sort": "altitude_m"}),
 ("pois sort=-created_at", "/compendium/pois", {"sort": "-created_at"}),
 ("pois sort=altitude_m offset=20000", "/compendium/pois", {"sort": "altitude_m", "offset": 20000}),
 ("pois offset=20000 default sort", "/compendium/pois", {"offset": 20000}),
 ("regions default (100)", "/compendium/regions", {}),
 ("regions bbox 7,46,8,47", "/compendium/regions", {"bbox": "7,46,8,47"}),
 ("regions q=bern", "/compendium/regions", {"q": "bern"}),
 ("event-log default (100)", "/management/event-log", {}),
 ("users default", "/profile/users/", {}),
 ("compendium-types default (500)", "/core/compendium-types", {}),
]
print(f"{'call':42} {'status':>6} {'median ms':>10} {'KB':>8} {'total':>7}")
for label, path, params in rows:
    s, ms, kb, total = run(path, **params)
    print(f"{label:42} {s:>6} {ms:>10.0f} {kb:>8.0f} {total!s:>7}")
