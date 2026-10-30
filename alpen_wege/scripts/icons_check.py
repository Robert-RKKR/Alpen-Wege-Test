#!/usr/bin/env python
"""Live check of the icons (asset_agg_icon, /assets/icons and icon_id) against a RUNNING api with the seeded dev users.

    pip install httpx
    python scripts/icons_check.py --base http://localhost:8000 [--expect-flags 270]

Order on a fresh database: scripts/init_seed.py (users, resource type `icon`, policies), then
scripts/seed_icons.py for the flags (only needed for --expect-flags). Everything this script creates is deleted again.
Checks: permissions of the four groups, upload and cleaning of an SVG (script, handler, external link), the size limits
(413), duplicate and invalid keys, creating many icons from a CSV (dry run, update, link) and the link by key, the file route (headers, ETag and 304, PNG, by key), update and replace, the link on a
reference table, a country, a region and a resource type, a wrong icon_id (422 instead of 500) on create, update and CSV
import, the 409 of a delete while the icon is used, and that the event log does not hold the SVG text.
"""
import argparse
import io
import sys
import uuid

import httpx

parser = argparse.ArgumentParser(description="Live check of /assets/icons and icon_id")
parser.add_argument("--base", default="http://localhost:8000")
parser.add_argument("--password", default="!Password@5005")
parser.add_argument("--expect-flags", type=int, default=0, help="the flags were loaded with seed_icons.py: expect at least this many flag_ icons")
ARGS = parser.parse_args()
API = ARGS.base.rstrip("/") + "/api/v1"
results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS  " if cond else "FAIL  ") + name + (f"   [{detail}]" if (detail and not cond) else ""), flush=True)


# no connection reuse: after a server error (500) the server closes the connection, and the next request would fail with a reset
client = httpx.Client(timeout=60, limits=httpx.Limits(max_keepalive_connections=0))


def login(email):
    r = client.post(f"{API}/profile/auth/login", json={"email": email, "password": ARGS.password})
    return r.json()["response_data"]["access_token"] if r.status_code == 200 else None


def H(token):
    return {"Authorization": f"Bearer {token}"}


tokens = {u: login(f"{u}@alpenwege.dev") for u in ("admin", "editor", "viewer", "guest")}
check("login for admin, editor, viewer, guest", all(tokens.values()))
admin = H(tokens["admin"])
RUN = uuid.uuid4().hex[:8]
SVG = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M3 20 12 4l9 16z" fill="#2ecc71"/></svg>'
EVIL = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 24 24" onload="alert(1)">'
        b'<script>alert(1)</script><style>@import url(http://evil.example/x.css);</style>'
        b'<use xlink:href="http://evil.example/a.svg#x"/><circle r="5" cx="12" cy="12" onclick="steal()"/></svg>')
created = {"icons": [], "companies": [], "countries": [], "regions": [], "region_types": [], "resource_types": []}


def upload(svg, key=None, name=None, headers=None, filename="test.svg"):
    data = {k: v for k, v in (("key", key), ("name", name)) if v is not None}
    return client.post(f"{API}/assets/icons", headers=headers or admin, data=data, files={"file": (filename, svg, "image/svg+xml")})


def error_codes(r):
    try:
        return [e.get("code") for e in r.json().get("response_details", {}).get("error_errors", [])]
    except Exception:
        return []


# ---- 1. permissions
for who in ("admin", "editor", "viewer", "guest"):
    r = client.get(f"{API}/assets/icons", headers=H(tokens[who]))
    check(f"GET /assets/icons as {who} -> 200", r.status_code == 200, r.text[:150])
for who in ("editor", "viewer", "guest"):
    r = upload(SVG, key=f"x_{RUN}", headers=H(tokens[who]))
    check(f"POST /assets/icons as {who} -> 403", r.status_code == 403, f"{r.status_code} {r.text[:120]}")
check("GET /assets/icons without a token -> 401", client.get(f"{API}/assets/icons").status_code == 401)

# ---- 2. upload and cleaning
r = upload(EVIL, key=f"Evil_{RUN}", name="Evil test")
check("POST an SVG with script, handlers, style and external link -> 201", r.status_code == 201, r.text[:200])
evil = r.json().get("response_data") or {}
if evil.get("id"):
    created["icons"].append(evil["id"])
removed = r.json().get("response_details", {}).get("removed", [])
check("the answer lists what was removed (script, style, onclick, onload, href)", all(any(w in x for x in removed) for w in ("<script>", "<style>", "onclick", "onload", "href")), str(removed))
check("a key sent in upper case is stored in lower case", evil.get("key") == f"evil_{RUN}", str(evil.get("key")))
check("the JSON of an icon has no svg text", "svg" not in evil and len(evil.get("sha256", "")) == 64)
r = client.get(f"{API}/assets/icons/{evil.get('id')}/file", headers=admin)
body = r.text
check("GET file -> image/svg+xml, nothing dangerous left", r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
      and not any(w in body.lower() for w in ("script", "onclick", "onload", "evil.example", "@import")), body[:200])
check("file headers: nosniff, CSP sandbox, private cache, ETag", r.headers.get("x-content-type-options") == "nosniff"
      and "sandbox" in r.headers.get("content-security-policy", "") and "private" in r.headers.get("cache-control", "") and r.headers.get("etag"))
etag = r.headers.get("etag", "")
check("GET file with If-None-Match -> 304", client.get(f"{API}/assets/icons/{evil.get('id')}/file", headers={**admin, "If-None-Match": etag}).status_code == 304)

r = upload(SVG, key=f"evil_{RUN}")
check("POST the same key again -> 409", r.status_code == 409 and "conflict" in error_codes(r), f"{r.status_code} {r.text[:150]}")
r = upload(SVG, key="has space!")
check("POST an invalid key -> 422", r.status_code == 422 and "invalid_key" in error_codes(r), f"{r.status_code} {r.text[:150]}")
r = upload(SVG, filename=f"Flag Test {RUN}.svg")
if r.status_code == 201:
    created["icons"].append(r.json()["response_data"]["id"])
check("no key sent: the key comes from the file name (Flag Test x.svg -> flag_test_x)", r.status_code == 201 and r.json()["response_data"]["key"] == f"flag_test_{RUN}", r.text[:200])
check("POST a file that is not an SVG -> 400", upload(b"<html><body/></html>", key=f"h_{RUN}").status_code == 400)
check("POST text that is not XML -> 400", upload(b"not xml", key=f"n_{RUN}").status_code == 400)
check("POST an SVG with DOCTYPE and entities -> 400", upload(b'<!DOCTYPE s [<!ENTITY a "aaaa">]><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><text>&a;</text></svg>', key=f"d_{RUN}").status_code == 400)
check("POST an SVG without viewBox and size -> 400", upload(b'<svg xmlns="http://www.w3.org/2000/svg"><circle r="2"/></svg>', key=f"v_{RUN}").status_code == 400)
big = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><!--' + b"x" * (310 * 1024) + b"--></svg>"
check("POST 310 KB (limit 300 KB) -> 413 from the route", upload(big, key=f"b_{RUN}").status_code == 413)
huge = b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><!--' + b"x" * (400 * 1024) + b"--></svg>"
check("POST 400 KB -> 413 from the size guard", upload(huge, key=f"h2_{RUN}").status_code == 413)
r = client.post(f"{API}/assets/icons", headers=admin, data={"key": f"nf_{RUN}"})
check("POST without a file -> 422", r.status_code == 422)

# ---- 3. read: one, list, filters, file by key, PNG
icon_id = evil["id"]
r = client.get(f"{API}/assets/icons/{icon_id}", headers=admin, params={"expand": "created_by"})
check("GET one with expand=created_by -> 200 and the user", r.status_code == 200 and (r.json()["response_data"].get("created_by_user") or {}).get("email") == "admin@alpenwege.dev", r.text[:200])
check("GET one with an unknown expand -> 400", client.get(f"{API}/assets/icons/{icon_id}", headers=admin, params={"expand": "nope"}).status_code == 400)
check("GET one unknown id -> 404", client.get(f"{API}/assets/icons/{uuid.uuid4()}", headers=admin).status_code == 404)
r = client.get(f"{API}/assets/icons", headers=admin, params={"key": f"EVIL_{RUN}"})
check("list with key=EVIL_x (upper case) finds it", r.status_code == 200 and [x["key"] for x in r.json()["response_data"]] == [f"evil_{RUN}"], r.text[:200])
r = client.get(f"{API}/assets/icons", headers=admin, params={"key_prefix": "flag_test_"})
check("list with key_prefix=flag_test_ finds the file-name icon", r.status_code == 200 and any(x["key"] == f"flag_test_{RUN}" for x in r.json()["response_data"]), r.text[:200])
r = client.get(f"{API}/assets/icons", headers=admin, params={"key_prefix": "100%_"})
check("a % in key_prefix is not a wildcard", r.status_code == 200 and r.json()["response_pagination"]["pagination_total"] == 0)
check("list with sort=-created_at -> 200, sort=svg -> 422", client.get(f"{API}/assets/icons", headers=admin, params={"sort": "-created_at"}).status_code == 200
      and client.get(f"{API}/assets/icons", headers=admin, params={"sort": "svg"}).status_code == 422)
check("list with q of 1 character -> 422", client.get(f"{API}/assets/icons", headers=admin, params={"q": "a"}).status_code == 422)
r = client.get(f"{API}/assets/icons/by-key/EVIL_{RUN}/file", headers=admin)
check("GET by-key/EVIL_x/file (upper case) -> the same picture", r.status_code == 200 and r.headers.get("etag") == etag, f"{r.status_code}")
check("GET by-key of an unknown key -> 404", client.get(f"{API}/assets/icons/by-key/nope_{RUN}/file", headers=admin).status_code == 404)
r = client.get(f"{API}/assets/icons/{icon_id}/file", headers=admin, params={"format": "png", "size": 48})
check("GET file as PNG, 48 px wide", r.status_code == 200 and r.headers["content-type"] == "image/png" and r.content[:8] == b"\x89PNG\r\n\x1a\n" and int.from_bytes(r.content[16:20], "big") == 48, f"{r.status_code}")
check("PNG has its own ETag and 304", client.get(f"{API}/assets/icons/{icon_id}/file", headers={**admin, "If-None-Match": r.headers.get("etag", "")}, params={"format": "png", "size": 48}).status_code == 304 and r.headers.get("etag") != etag)
check("PNG size 15 and 1025 -> 422, format=gif -> 422", all(client.get(f"{API}/assets/icons/{icon_id}/file", headers=admin, params=p).status_code == 422
      for p in ({"format": "png", "size": 15}, {"format": "png", "size": 1025}, {"format": "gif"})))

# ---- 4. update and replace
r = client.patch(f"{API}/assets/icons/{icon_id}", headers=admin, json={"name": "Renamed", "name_de": "Umbenannt", "summary": "s", "key": f"Renamed_{RUN}"})
d = r.json().get("response_data") or {}
check("PATCH names and key (key lower-cased) -> 200", r.status_code == 200 and d.get("name") == "Renamed" and d.get("key") == f"renamed_{RUN}" and d.get("name_de") == "Umbenannt", r.text[:200])
check("PATCH name null leaves the name", client.patch(f"{API}/assets/icons/{icon_id}", headers=admin, json={"name": None}).json()["response_data"]["name"] == "Renamed")
other = created["icons"][1] if len(created["icons"]) > 1 else None
check("PATCH a key that exists -> 409", other is not None and client.patch(f"{API}/assets/icons/{other}", headers=admin, json={"key": f"renamed_{RUN}"}).status_code == 409)
check("PATCH an invalid key -> 422", client.patch(f"{API}/assets/icons/{icon_id}", headers=admin, json={"key": "bad key"}).status_code == 422)
check("PATCH as viewer -> 403", client.patch(f"{API}/assets/icons/{icon_id}", headers=H(tokens["viewer"]), json={"name": "x"}).status_code == 403)
old_sha = d.get("sha256")
r = client.put(f"{API}/assets/icons/{icon_id}/file", headers=admin, files={"file": ("n.svg", SVG, "image/svg+xml")})
check("PUT file replaces the SVG (new sha256, same id and key)", r.status_code == 200 and r.json()["response_data"]["sha256"] != old_sha and r.json()["response_data"]["id"] == icon_id
      and r.json()["response_data"]["key"] == f"renamed_{RUN}", r.text[:200])
r2 = client.get(f"{API}/assets/icons/{icon_id}/file", headers=admin)
check("the file route serves the new picture", "#2ecc71" in r2.text and r2.headers["etag"] != etag)
check("PUT file with a bad file -> 400, as viewer -> 403", client.put(f"{API}/assets/icons/{icon_id}/file", headers=admin, files={"file": ("n.svg", b"nope", "image/svg+xml")}).status_code == 400
      and client.put(f"{API}/assets/icons/{icon_id}/file", headers=H(tokens["viewer"]), files={"file": ("n.svg", SVG, "image/svg+xml")}).status_code == 403)

# ---- 5. links: reference table, resource type, country, region
def make_company(**extra):
    r = client.post(f"{API}/core/companies", headers=admin, json={"name": f"Icon Co {RUN}", "color": "#112233", "icon": "building", **extra})
    if r.status_code == 201:
        created["companies"].append(r.json()["response_data"]["id"])
    return r


r = make_company(icon_id=icon_id)
co = (r.json().get("response_data") or {})
check("POST a company with icon_id -> 201 and icon_id in the answer", r.status_code == 201 and co.get("icon_id") == icon_id and co.get("icon") == "building", r.text[:200])
r = client.get(f"{API}/core/companies/{co.get('id')}", headers=admin)
check("GET the company shows icon_id", r.status_code == 200 and r.json()["response_data"]["icon_id"] == icon_id)
r = make_company()
co2 = r.json().get("response_data") or {}
check("a company without icon_id has icon_id null (old callers keep working)", r.status_code == 201 and co2.get("icon_id") is None)
r = make_company(icon_id=str(uuid.uuid4()))
check("POST a company with an unknown icon_id -> 422 icon_not_found (not 500)", r.status_code == 422 and "icon_not_found" in error_codes(r), f"{r.status_code} {r.text[:200]}")
r = client.patch(f"{API}/core/companies/{co2.get('id')}", headers=admin, json={"icon_id": str(uuid.uuid4())})
check("PATCH a company with an unknown icon_id -> 422 icon_not_found", r.status_code == 422 and "icon_not_found" in error_codes(r), f"{r.status_code} {r.text[:200]}")
r = client.patch(f"{API}/core/companies/{co2.get('id')}", headers=admin, json={"icon_id": icon_id})
check("PATCH a company: set icon_id -> 200", r.status_code == 200 and r.json()["response_data"]["icon_id"] == icon_id)
r = client.get(f"{API}/core/companies", headers=admin, params={"q": f"Icon Co {RUN}"})
check("the company list carries icon_id", r.status_code == 200 and all("icon_id" in x for x in r.json()["response_data"]) and len(r.json()["response_data"]) >= 1)

r = client.post(f"{API}/core/resource-types", headers=admin, json={"key": f"icon_test_{RUN}", "color": "#112233", "icon": "x", "icon_id": icon_id})
if r.status_code == 201:
    created["resource_types"].append(r.json()["response_data"]["id"])
check("POST a resource type with icon_id -> 201 and icon_id in the answer", r.status_code == 201 and r.json()["response_data"]["icon_id"] == icon_id, r.text[:200])
r = client.post(f"{API}/core/resource-types", headers=admin, json={"key": f"icon_bad_{RUN}", "color": "#112233", "icon": "x", "icon_id": str(uuid.uuid4())})
check("POST a resource type with an unknown icon_id -> 422", r.status_code == 422 and "icon_not_found" in error_codes(r), f"{r.status_code} {r.text[:150]}")

iso = "".join(c for c in RUN.upper() if c.isalpha())[:2].ljust(2, "Q")
r = client.post(f"{API}/compendium/countries", headers=admin, json={"name": f"Iconland {RUN}", "iso_code": iso + RUN[:2].upper(), "location": {"type": "Point", "coordinates": [10, 47]}, "icon_id": icon_id})
country = r.json().get("response_data") or {}
if country.get("id"):
    created["countries"].append(country["id"])
check("POST a country with icon_id (its flag) -> 201", r.status_code == 201 and country.get("icon_id") == icon_id, r.text[:200])
r = client.patch(f"{API}/compendium/countries/{country.get('id')}", headers=admin, json={"icon_id": str(uuid.uuid4())})
check("PATCH a country with an unknown icon_id -> 422", r.status_code == 422 and "icon_not_found" in error_codes(r), f"{r.status_code}")
r = client.get(f"{API}/compendium/countries", headers=admin, params={"q": f"Iconland {RUN}"})
check("the country list carries icon_id", r.status_code == 200 and r.json()["response_data"] and r.json()["response_data"][0]["icon_id"] == icon_id, r.text[:200])

r = client.post(f"{API}/core/region-types", headers=admin, json={"name": f"Icon type {RUN}", "color": "#112233", "icon": "x", "point_factor": 1.0})
rt = (r.json().get("response_data") or {}).get("id")
if rt:
    created["region_types"].append(rt)
r = client.post(f"{API}/compendium/regions", headers=admin, json={"name": f"Iconregion {RUN}", "location": {"type": "Point", "coordinates": [10, 47]}, "country_id": country.get("id"), "region_type_id": rt, "icon_id": icon_id})
region = r.json().get("response_data") or {}
if region.get("id"):
    created["regions"].append(region["id"])
check("POST a region with icon_id -> 201; the nested country shows its icon_id", r.status_code == 201 and region.get("icon_id") == icon_id and (region.get("country") or {}).get("icon_id") == icon_id, r.text[:300])
r = client.patch(f"{API}/compendium/regions/{region.get('id')}", headers=admin, json={"icon_id": str(uuid.uuid4())})
check("PATCH a region with an unknown icon_id -> 422", r.status_code == 422 and "icon_not_found" in error_codes(r), f"{r.status_code}")

# ---- 6. CSV import
csv_ok = f"name,color,icon,icon_id\nCsv Co {RUN},#aabbcc,truck,{icon_id}\n".encode()
r = client.post(f"{API}/core/companies/upload-csv", headers=admin, files={"file": ("c.csv", csv_ok, "text/csv")})
check("CSV import with a good icon_id -> 1 inserted", r.status_code in (200, 201) and r.json()["response_data"]["inserted"] == 1 and not r.json()["response_data"]["errors"], r.text[:200])
bad_id = str(uuid.uuid4())
csv_bad = f"name,color,icon,icon_id\nCsv Bad {RUN},#aabbcc,truck,{bad_id}\nCsv Good2 {RUN},#aabbcc,truck,{icon_id}\n".encode()
r = client.post(f"{API}/core/companies/upload-csv", headers=admin, files={"file": ("c.csv", csv_bad, "text/csv")})
res = r.json().get("response_data") or {}
check("CSV import with an unknown icon_id: that row is refused by number, the other row is imported (no 500)",
      r.status_code in (200, 201) and res.get("inserted") == 1 and len(res.get("errors", [])) == 1 and "row 2" in res["errors"][0] and "icon" in res["errors"][0], r.text[:300])
r = client.get(f"{API}/core/companies", headers=admin, params={"q": "Csv "})
for row in r.json().get("response_data", []):
    if str(row.get("name", "")).endswith(RUN):
        created["companies"].append(row["id"])

# ---- 7. delete while used, event log, delete
r = client.delete(f"{API}/assets/icons/{icon_id}", headers=admin)
text = r.text
check("DELETE an icon that is used -> 409 listing the users", r.status_code == 409 and "company" in text and "country" in text and "region" in text and "resource type" in text, f"{r.status_code} {text[:300]}")
check("DELETE as viewer -> 403", client.delete(f"{API}/assets/icons/{icon_id}", headers=H(tokens["viewer"])).status_code == 403)
r = client.get(f"{API}/management/event-log", headers=admin, params={"entity_type": "asset_agg_icon", "entity_id": icon_id})
events = r.json().get("response_data", []) if r.status_code == 200 else []
snapshots = [e.get("snapshot") or {} for e in events]
check("event log: created, updated entries exist for the icon", {e.get("action") for e in events} >= {"created", "updated"}, str([e.get("action") for e in events]))
check("event log: no entry holds the svg text, the replaced picture shows as sha256", not any("svg" in s for s in snapshots) and any("sha256" in s for s in snapshots), str(snapshots)[:300])


def cleanup():
    for kind, path in (("regions", "compendium/regions"), ("countries", "compendium/countries"), ("companies", "core/companies"),
                       ("resource_types", "core/resource-types"), ("region_types", "core/region-types")):
        for i in created[kind]:
            client.delete(f"{API}/{path}/{i}", headers=admin)


cleanup()
r = client.delete(f"{API}/assets/icons/{icon_id}", headers=admin)
check("after the users are gone: DELETE the icon -> 200", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
check("GET the deleted icon -> 404", client.get(f"{API}/assets/icons/{icon_id}", headers=admin).status_code == 404)
r = client.get(f"{API}/management/event-log", headers=admin, params={"entity_type": "asset_agg_icon", "entity_id": icon_id, "action": "deleted"})
snaps = [e.get("snapshot") or {} for e in (r.json().get("response_data") or [])]
check("event log: the delete entry exists and has no svg text", len(snaps) == 1 and "svg" not in snaps[0] and snaps[0].get("key") == f"renamed_{RUN}", str(snaps)[:200])
for i in created["icons"][1:]:
    client.delete(f"{API}/assets/icons/{i}", headers=admin)

# ---- 8. many icons at once: POST /assets/icons/upload-csv and POST /assets/icons/link
import csv as _csv


def csv_file(rows, header=("key", "svg", "name", "name_de")):
    out = io.StringIO()
    writer = _csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def import_csv(data, params=None, headers=None, filename="icons.csv"):
    return client.post(f"{API}/assets/icons/upload-csv", headers=headers or admin, params=params, files={"file": (filename, data, "text/csv")})


def result_of(r):
    return (r.json().get("response_data") or {}) if r.status_code in (200, 201) else {}


def count_icons(prefix):
    r = client.get(f"{API}/assets/icons", headers=admin, params={"key_prefix": prefix, "limit": 1})
    return r.json()["response_pagination"]["pagination_total"]


pre = f"csvt_{RUN}_"
good, other = SVG.decode(), SVG.decode().replace("#2ecc71", "#e74c3c")
rows = [[pre + "a", good, "Csv A", "Csv A de"],
        [pre + "dirty", EVIL.decode(), "Csv dirty", ""],
        ["Bad Key!", good, "x", ""],                          # wrong key
        [pre + "a", good, "twice", ""],                       # the same key again
        [pre + "notsvg", "<html><script>1</script></html>", "x", ""]]
data = csv_file(rows)
for who in ("editor", "viewer", "guest"):
    check(f"POST upload-csv as {who} -> 403", import_csv(data, headers=H(tokens[who])).status_code == 403)
    check(f"POST icons/link as {who} -> 403", client.post(f"{API}/assets/icons/link", headers=H(tokens[who])).status_code == 403)
check("POST upload-csv without a token -> 401", client.post(f"{API}/assets/icons/upload-csv", files={"file": ("i.csv", data, "text/csv")}).status_code == 401)

before = count_icons(pre)
r = import_csv(data, {"dry_run": "true", "link": "false"})
d = result_of(r)
check("dry run: counts 2 new icons, 3 rejected rows, saves nothing", r.status_code == 200 and r.json()["response_code"] == 200 and d.get("dry_run") is True
      and (d["inserted"], d["updated"], d["unchanged"], d["rejected"]) == (2, 0, 0, 3) and count_icons(pre) == before == 0, r.text[:300])
check("the rejected rows are named by row number and reason", any(e.startswith("row 4 (bad key!)") for e in d.get("errors", [])) and any("twice" in e for e in d.get("errors", []))
      and any(e.startswith("row 6") and ("xml" in e.lower() or "svg" in e.lower()) for e in d.get("errors", [])), str(d.get("errors")))
check("the notes say what the cleaner took out of the dirty icon", any(n.startswith(f"{pre}dirty: removed") and "<script>" in n and "onclick" in n for n in d.get("notes", [])), str(d.get("notes")))
check("link=false: no linking in the answer", d.get("linked") is None and d.get("still_without_icon") is None)

r = import_csv(data, {"link": "false"})
d = result_of(r)
if d.get("inserted"):
    for k in ("a", "dirty"):
        found = client.get(f"{API}/assets/icons", headers=admin, params={"key": pre + k}).json()["response_data"]
        created["icons"] += [x["id"] for x in found]
check("import: 2 icons created, saved", r.status_code == 200 and r.json()["response_code"] == 201 and d.get("inserted") == 2 and count_icons(pre) == 2, r.text[:300])
r = client.get(f"{API}/assets/icons/by-key/{pre}dirty/file", headers=admin)
check("the dirty icon was cleaned before it was stored", r.status_code == 200 and not any(w in r.text.lower() for w in ("script", "onclick", "evil.example", "@import")))
r = client.get(f"{API}/assets/icons", headers=admin, params={"key": pre + "a"})
a_row = (r.json()["response_data"] or [{}])[0]
check("names came with the row (name, name_de); a missing name is the key", a_row.get("name") == "Csv A" and a_row.get("name_de") == "Csv A de"
      and (client.get(f"{API}/assets/icons", headers=admin, params={"key": pre + "dirty"}).json()["response_data"][0]["name"] == "Csv dirty"))
r = client.get(f"{API}/management/event-log", headers=admin, params={"entity_type": "asset_agg_icon", "entity_id": a_row.get("id")})
check("the import is in the event log, without the SVG text", r.status_code == 200 and any(e["action"] == "created" and "svg" not in (e.get("snapshot") or {}) for e in r.json()["response_data"]))

d2 = result_of(import_csv(data, {"link": "false"}))
check("the same file again: nothing new, 2 unchanged", (d2.get("inserted"), d2.get("updated"), d2.get("unchanged")) == (0, 0, 2), str(d2))
d3 = result_of(import_csv(csv_file([[pre + "a", other, "Csv A changed", ""]]), {"link": "false"}))
check("without update=true an icon that exists is left alone", (d3.get("inserted"), d3.get("updated"), d3.get("unchanged")) == (0, 0, 1), str(d3))
sha_a = a_row.get("sha256")
d4 = result_of(import_csv(csv_file([[pre + "a", other, "Csv A changed", ""]]), {"update": "true", "link": "false"}))
r = client.get(f"{API}/assets/icons", headers=admin, params={"key": pre + "a"})
now = r.json()["response_data"][0]
check("with update=true it is replaced: new picture and names", d4.get("updated") == 1 and now["sha256"] != sha_a and now["name"] == "Csv A changed" and now["name_de"] is None and now["id"] == a_row["id"], str(d4))
check("update=true dry run counts the change and saves nothing", result_of(import_csv(csv_file([[pre + "a", good, "Back", ""]]), {"update": "true", "dry_run": "true", "link": "false"})).get("updated") == 1
      and client.get(f"{API}/assets/icons", headers=admin, params={"key": pre + "a"}).json()["response_data"][0]["name"] == "Csv A changed")

# link: a company whose icon text is the key (in upper case), and one with a text that has no icon
co_k = client.post(f"{API}/core/companies", headers=admin, json={"name": f"Csv link {RUN}", "color": "#112233", "icon": (pre + "a").upper()})
co_n = client.post(f"{API}/core/companies", headers=admin, json={"name": f"Csv nolink {RUN}", "color": "#112233", "icon": f"no_such_icon_{RUN}"})
for r_ in (co_k, co_n):
    if r_.status_code == 201:
        created["companies"].append(r_.json()["response_data"]["id"])
r = client.post(f"{API}/assets/icons/link", headers=admin, params={"dry_run": "true"})
d = r.json().get("response_data") or {}
check("link dry run: counts the company, saves nothing", r.status_code == 200 and d.get("dry_run") is True and d.get("linked", {}).get("company") == 1
      and client.get(f"{API}/core/companies/{co_k.json()['response_data']['id']}", headers=admin).json()["response_data"]["icon_id"] is None, r.text[:300])
r = client.post(f"{API}/assets/icons/link", headers=admin)
d = r.json().get("response_data") or {}
check("link: the company got its icon (key compared in lower case), the other is still without", r.status_code == 200 and d.get("linked", {}).get("company") == 1
      and d.get("still_without_icon", {}).get("company", 0) >= 1 and client.get(f"{API}/core/companies/{co_k.json()['response_data']['id']}", headers=admin).json()["response_data"]["icon_id"] == a_row["id"], r.text[:300])
d = (client.post(f"{API}/assets/icons/link", headers=admin).json().get("response_data") or {})
check("link again: nothing new (a link that is set is never changed)", d.get("linked") == {}, str(d))
check("import with link=true (the default) links too", (result_of(import_csv(csv_file([[f"no_such_icon_{RUN}", good, "Now it exists", ""]]))).get("linked") or {}).get("company") == 1)
found = client.get(f"{API}/assets/icons", headers=admin, params={"key": f"no_such_icon_{RUN}"}).json()["response_data"]
created["icons"] += [x["id"] for x in found]

# a file that cannot be used
check("a CSV without the column svg -> 400 that names it", (lambda r: r.status_code == 400 and "svg" in r.text)(import_csv(csv_file([["a", "x"]], header=("key", "name")))))
check("a header without rows -> 400", import_csv(b"key,svg\n").status_code == 400)
check("a file that is not UTF-8 -> 400 that says so", (lambda r: r.status_code == 400 and "UTF-8" in r.text)(import_csv("key,svg,name\nä,x,ö\n".encode("latin-1"))))
check("an empty file -> 400", import_csv(b"").status_code == 400)
check("POST upload-csv without a file -> 422", client.post(f"{API}/assets/icons/upload-csv", headers=admin).status_code == 422)
check("a CSV of 6 MB -> 413", import_csv(b"key,svg\n" + b"a," + b"x" * (6 * 1024 * 1024) + b"\n").status_code == 413)
check("the key of an uploaded row is lower-cased (Upper_Key -> upper_key)", result_of(import_csv(csv_file([[pre.upper() + "UP", good, "", ""]]), {"link": "false"})).get("inserted") == 1
      and count_icons(pre + "up") == 1)
created["icons"] += [x["id"] for x in client.get(f"{API}/assets/icons", headers=admin, params={"key_prefix": pre}).json()["response_data"]]

# clean up what this section made (companies first: a used icon cannot be deleted)
for i in created["companies"]:
    client.delete(f"{API}/core/companies/{i}", headers=admin)
created["companies"] = []
leftover = 0
for i in set(created["icons"][1:]):
    if client.delete(f"{API}/assets/icons/{i}", headers=admin).status_code not in (200, 404):
        leftover += 1
check("the icons of the section are deleted again", leftover == 0 and count_icons(pre) == 0)

if ARGS.expect_flags:
    r = client.get(f"{API}/assets/icons", headers=admin, params={"key_prefix": "flag_", "limit": 1})
    total = r.json()["response_pagination"]["pagination_total"]
    check(f"the flags are loaded: at least {ARGS.expect_flags} icons with key flag_", total >= ARGS.expect_flags, str(total))
    r = client.get(f"{API}/assets/icons/by-key/flag_at/file", headers=admin)
    check("by-key/flag_at/file -> an SVG of 512 x 512", r.status_code == 200 and 'viewBox="0 0 512 512"' in r.text)
    r = client.get(f"{API}/assets/icons/by-key/flag_ch/file", headers=admin, params={"format": "png", "size": 64})
    check("by-key/flag_ch/file as PNG", r.status_code == 200 and r.content[:4] == b"\x89PNG")

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)} of {len(results)} checks passed" + (f"; FAILED: {failed}" if failed else ""))
sys.exit(1 if failed else 0)
