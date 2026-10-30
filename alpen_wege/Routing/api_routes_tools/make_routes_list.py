#!/usr/bin/env python3
"""Writes Routing/api_routes_list.md from a dump of the app's route table.

    cd <repo> && PYTHONPATH=. python scripts/route_map.py dump /tmp/routes.json
    python make_routes_list.py /tmp/routes.json api_routes_list.md "2026-10-30"

Access column: key.action = resource_access (scope of the role: own, public, all); a group name = require_groups;
login = any logged-in user; public = no token needed.
"""
import json
import sys
from collections import defaultdict

ORDER = ["profile", "core", "compendium", "explorer", "assets", "management", "social"]


def access(rec):
    for p in rec["permissions"]:
        q = json.loads(p)
        if q["call"].endswith("resource_access.<locals>._check"):
            return f"`{q['args']['resource_key']}.{q['args']['action']}`"
        if q["call"].endswith("require_groups.<locals>._check"):
            return "`" + "`, `".join(q["args"]["allowed_groups"]) + "`"
    return "`login`" if rec["security"] else "`public`"


def main(dump_path, out_path, date):
    d = json.load(open(dump_path, encoding="utf-8"))
    routes = d["routes"]
    ws = {k: v for k, v in routes.items() if k.startswith("WS ")}
    routes = {k: v for k, v in routes.items() if k not in ws}
    api = {k: v for k, v in routes.items() if k.split(" ", 1)[1].startswith("/api/v1/")}
    groups = defaultdict(lambda: defaultdict(list))
    other = []
    for key, rec in routes.items():
        method, path = key.split(" ", 1)
        if not path.startswith("/api/v1/"):
            other.append((method, path, access(rec), rec["summary"]))
            continue
        parts = path.split("/")
        groups[parts[3]][parts[4]].append((method, path, access(rec), rec["summary"]))
    lines = [
        f"# All API routes (current repo, {date})", "",
        "Every URL starts with the base URL of your API plus `/api/v1`. On your machine that is `http://localhost:8000/api/v1` "
        "(in Postman: `{{hostname}}:{{port}}/{{api_path}}`). This list was written from the app's own route table, so it matches the code: "
        f"{len(api)} HTTP routes under `/api/v1`, `GET /health`, and {len(ws)} WebSocket routes ({len(api) + len(other) + len(ws)} in total). "
        "Swagger is at `/docs`, ReDoc at `/redoc`, the OpenAPI file at `/openapi.json`.", "",
        "**Access** column: `login` = any logged-in user; `administrator` = administrator group only; `key.action` (for example "
        "`track.read`, `segment.create`, `icon.read`) = the access policy of your role for that resource and action (scope own, public or all); "
        "`public` = no token needed.", "",
    ]
    for app in sorted(groups, key=lambda a: ORDER.index(a) if a in ORDER else 99):
        lines += [f"## {app}", ""]
        for resource in sorted(groups[app]):
            lines += [f"### {resource}", "", "| Method | URL | Access | What |", "|---|---|---|---|"]
            for method, path, acc, summary in sorted(groups[app][resource], key=lambda r: (r[1].replace("{", "~"), r[0])):
                lines.append(f"| {method} | `{path}` | {acc} | {summary} |")
            lines.append("")
    lines += ["## Other", "", "| Method | URL | Access | What |", "|---|---|---|---|"]
    for method, path, acc, summary in sorted(other):
        lines.append(f"| {method} | `{path}` | {acc} | {summary} |")
    for key, rec in sorted(ws.items()):
        lines.append(f"| WebSocket | `{key.split(' ', 1)[1]}` | `token` | {rec['name'].replace('_', ' ')} |")
    open(out_path, "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print(f"{len(api)} routes written to {out_path}")


if __name__ == "__main__":
    main(*sys.argv[1:4])
