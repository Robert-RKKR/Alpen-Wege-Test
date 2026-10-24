"""Route map tool: dump every route of the app and compare two dumps.

Run from the repo root (inside the api container: `docker exec -w /app -e PYTHONPATH=/app alpen-api ...`).

    python scripts/route_map.py dump  OUT.json
    python scripts/route_map.py compare BEFORE.json AFTER.json [--rules RULES.json [--step N]]
    python scripts/route_map.py probe DUMP.json
    python scripts/route_map.py names

`dump` imports `app.main` (no database or Redis connection is opened) and writes, for every HTTP
operation: function name, tags, status code, summary, parameters, request body, responses, security
and the permission dependencies (resource_access key and action, require_groups groups). WebSocket
routes are listed with their name and path.

`compare` without --rules requires the two dumps to be identical (structure-only changes).
With --rules every old path must reappear under the new path given by the longest matching
prefix rule, with identical records, and no other route may exist. Each rule has a "step"
number; with --step N only rules with step <= N are applied and the others keep the old path,
so a migration done in steps can be checked after every step (step 0 rules always apply).

`probe` sends every HTTP route of the app (from DUMP.json, made by `dump` on the same code) one
request without a token, straight into the ASGI app (no database, no Redis, no network). It
checks that each URL is served by the function the dump names (finds routes shadowed by another
route) and that every secured route answers 401.

`names` imports every module of the app and reports names that a function reads from the module's globals
but the module does not define (a forgotten import or a renamed helper that is only used inside a function
body). Nothing else in the toolset sees this kind of mistake; it needs no database.

`dump` also records, per route, what the function captured from the factory that built it (the 19 reference
tables share function names, the permission key and the schemas: only the captured model and slug tell them
apart), and the middleware list and exception handlers of the app.
"""
# Standard library
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

HTTP_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PRIMITIVE = (str, int, float, bool, type(None))
COMPARED_FIELDS = (
    "name", "tags", "status", "summary", "description", "deprecated",
    "parameters", "request_body", "responses", "security", "permissions", "endpoint_closure",
)


# ------------------------------------------------------------------ dump

def _closure_values(call) -> dict:
    # Values captured by a dependency factory, e.g. resource_access("poi", "read").
    names = getattr(getattr(call, "__code__", None), "co_freevars", ())
    cells = getattr(call, "__closure__", None) or ()
    out = {}
    for name, cell in zip(names, cells):
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, PRIMITIVE):
            out[name] = value
        elif isinstance(value, (tuple, list)) and all(isinstance(v, PRIMITIVE) for v in value):
            out[name] = list(value)
    return out


def _endpoint_closure(fn) -> dict:
    # What a route function captured from the factory that built it (model class, schemas, slug): 19 reference tables
    # share the same function names, so only this tells them apart.
    out = {}
    names = getattr(getattr(fn, "__code__", None), "co_freevars", ())
    for name, cell in zip(names, getattr(fn, "__closure__", None) or ()):
        try:
            value = cell.cell_contents
        except ValueError:
            continue
        if isinstance(value, PRIMITIVE):
            out[name] = value
        elif isinstance(value, type):
            out[name] = f"{value.__module__}.{value.__qualname__}"
    return out


def _call_name(call) -> str:
    # Functions have __qualname__; callable objects (OAuth2PasswordBearer) only their class has one.
    qualname = getattr(call, "__qualname__", None) or type(call).__qualname__
    module = getattr(call, "__module__", None) or type(call).__module__
    return f"{module}.{qualname}"


def _permissions(dependant) -> list:
    found: list[str] = []

    def walk(dep):
        for sub in dep.dependencies:
            if sub.call is not None:
                found.append(json.dumps(
                    {"call": _call_name(sub.call), "args": _closure_values(sub.call)},
                    sort_keys=True,
                ))
            walk(sub)

    if dependant is not None:
        walk(dependant)
    return sorted(set(found))


def _iter_routes(routes):
    # Newer FastAPI keeps included routers nested (lazy); older versions flatten them.
    for route in routes:
        if hasattr(route, "effective_candidates"):
            yield from _iter_routes(route.effective_candidates())
        else:
            yield route, getattr(route, "original_route", route)


_COMPONENTS: dict = {}


def _resolve_bodies(node):
    # FastAPI names form-upload schemas after the operation id, which contains the URL path
    # ("Body_create_track_api_v1_tracks_post"). Compare their content, not their generated name.
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/Body_"):
            body = dict(_COMPONENTS.get(ref.rsplit("/", 1)[1], {}))
            body.pop("title", None)
            return {"form_body": _resolve_bodies(body)}
        return {k: _resolve_bodies(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_resolve_bodies(v) for v in node]
    return node


def _schema_json(node) -> str:
    return json.dumps(_resolve_bodies(node), sort_keys=True)


def _operation_record(op: dict) -> dict:
    params = sorted(
        f"{p['in']}:{p['name']}:{'req' if p.get('required') else 'opt'}:{_schema_json(p.get('schema'))}"
        for p in op.get("parameters", [])
    )
    body = op.get("requestBody")
    request_body = None
    if body:
        request_body = {ct: _schema_json(v.get("schema")) for ct, v in sorted(body.get("content", {}).items())}
        request_body["required"] = bool(body.get("required"))
    responses = {
        code: {ct: _schema_json(v.get("schema")) for ct, v in sorted(resp.get("content", {}).items())}
        for code, resp in sorted(op.get("responses", {}).items())
    }
    return {
        "tags": list(op.get("tags", [])),
        "summary": op.get("summary"),
        "description": (op.get("description") or "").strip(),
        "deprecated": bool(op.get("deprecated")),
        "parameters": params,
        "request_body": request_body,
        "responses": responses,
        "security": op.get("security"),
    }


def dump() -> dict:
    import fastapi

    from app.main import app

    spec = app.openapi()
    _COMPONENTS.clear()
    _COMPONENTS.update(spec.get("components", {}).get("schemas", {}))
    routes: dict[str, dict] = {}
    duplicates: list[str] = []
    ws_count = 0
    for route, original in _iter_routes(app.routes):
        kind = type(original).__name__
        if kind == "APIWebSocketRoute":
            ws_count += 1
            params = {p: "{" + p + "}" for p in getattr(original, "param_convertors", {})}
            path = app.url_path_for(original.name, **params)
            routes[f"WS {path}"] = {"name": original.name}
            continue
        if kind != "APIRoute":
            continue
        for method in sorted(m for m in (original.methods or ()) if m in HTTP_METHODS):
            path = route.path
            record = {
                "name": original.name,
                "status": original.status_code,
                "permissions": _permissions(getattr(route, "dependant", None)),
                "endpoint_closure": _endpoint_closure(original.endpoint),
            }
            op = spec.get("paths", {}).get(path, {}).get(method.lower())
            if op is not None:
                record.update(_operation_record(op))
            else:
                record["hidden_from_openapi"] = True
            if f"{method} {path}" in routes:
                duplicates.append(f"{method} {path}")
            routes[f"{method} {path}"] = record
    if duplicates:
        raise SystemExit("Two routes share the same method and path (the first one hides the other): "
                         + ", ".join(sorted(set(duplicates))))
    return {"fastapi_version": fastapi.__version__, "websocket_routes": ws_count, "routes": routes,
            "middleware": [f"{m.cls.__module__}.{m.cls.__qualname__}" for m in app.user_middleware],
            "exception_handlers": sorted(f"{getattr(k, '__name__', k)}={v.__module__}.{v.__qualname__}" for k, v in app.exception_handlers.items())}


# ------------------------------------------------------------------ compare

def _map_path(path: str, rules: list[dict] | None, step: int | None):
    # Returns (new_path, rule). Without rules every path maps to itself.
    if rules is None:
        return path, None
    best = None
    for rule in rules:
        old = rule["old"]
        if path == old or path.startswith(old + "/"):
            if best is None or len(old) > len(best["old"]):
                best = rule
    if best is None:
        if path.startswith("/api/v1"):
            return None, None
        return path, None  # /health and other non-API paths are not part of the rules
    if step is not None and best.get("step", 0) > step:
        return path, None  # this rule belongs to a later step: the path must still be the old one
    return best["new"] + path[len(best["old"]):], best


def compare(before: dict, after: dict, rules: list[dict] | None, step: int | None = None) -> list[str]:
    errors: list[str] = []
    if before.get("fastapi_version") != after.get("fastapi_version"):
        errors.append(
            f"NOTE fastapi version differs: {before.get('fastapi_version')} vs {after.get('fastapi_version')}"
        )
    expected: dict[str, tuple[str, dict, dict | None]] = {}
    for key, record in before["routes"].items():
        method, path = key.split(" ", 1)
        new_path, rule = _map_path(path, rules, step)
        if new_path is None:
            errors.append(f"UNMAPPED  {key}: no rule covers this path")
            continue
        new_key = f"{method} {new_path}"
        if new_key in expected:
            errors.append(f"COLLISION {key} and {expected[new_key][0]} both map to {new_key}")
        expected[new_key] = (key, record, rule)

    for new_key, (old_key, record, rule) in expected.items():
        got = after["routes"].get(new_key)
        if got is None:
            errors.append(f"MISSING   {old_key}  ->  expected {new_key}")
            continue
        for field in COMPARED_FIELDS:
            want = record.get(field)
            if field == "tags" and rule and "tags" in rule:
                want = rule["tags"]
            if want != got.get(field):
                errors.append(f"DIFF      {new_key}: {field}\n            before: {want}\n            after:  {got.get(field)}")

    for new_key in after["routes"]:
        if new_key not in expected:
            errors.append(f"UNEXPECTED {new_key}")
    for field in ("middleware", "exception_handlers"):
        if field in before and before[field] != after.get(field):
            errors.append(f"DIFF      app.{field}\n            before: {before[field]}\n            after:  {after.get(field)}")
    return errors


# ------------------------------------------------------------------ probe

def probe_routes(routes: dict) -> list[str]:
    # Sends every HTTP route one request without a token; returns the problems found.
    import asyncio
    import re

    from app.main import app

    sample = "11111111-1111-1111-1111-111111111111"

    async def call(method: str, path: str):
        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
            "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
            "headers": [(b"host", b"probe")], "server": ("probe", 80), "client": ("probe", 1), "root_path": "",
        }
        sent: list[dict] = []
        delivered = False

        async def receive():
            # an empty request body first, then "client gone" (older Starlette middleware needs this)
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": b"", "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            sent.append(message)

        await app(scope, receive, send)
        status = next((m["status"] for m in sent if m["type"] == "http.response.start"), None)
        return status, getattr(scope.get("endpoint"), "__name__", None)

    problems: list[str] = []
    for key, record in routes.items():
        if key.startswith("WS ") or key.endswith(" /health"):
            continue  # /health opens a database connection
        method, path = key.split(" ", 1)
        status, endpoint = asyncio.run(call(method, re.sub(r"\{[^}]+\}", sample, path)))
        wrong_function = endpoint != record["name"]
        not_protected = bool(record.get("security")) and status != 401
        if wrong_function or not_protected:
            problems.append(
                f"PROBE     {key}: answered {status} by {endpoint!r}, expected function {record['name']!r}"
                + (" and 401" if record.get("security") else "")
            )
    return problems


def probe(dump_file: str) -> int:
    routes = json.loads(Path(dump_file).read_text(encoding="utf-8"))["routes"]
    problems = probe_routes(routes)
    probed = sum(1 for k in routes if not k.startswith("WS ") and not k.endswith(" /health"))
    for line in problems:
        print(line)
    print(f"{'FAILED' if problems else 'OK'}: probed {probed} routes, {len(problems)} problem(s)")
    return 1 if problems else 0


# ------------------------------------------------------------------ names

def undefined_names() -> list[str]:
    # Names a function reads from module globals that the module does not define.
    import builtins
    import dis
    import importlib
    import pkgutil
    import types

    import app as app_package

    problems: set[str] = set()
    for info in pkgutil.walk_packages(app_package.__path__, prefix="app."):
        if info.name.endswith(".__main__"):
            continue
        try:
            module = importlib.import_module(info.name)
        except Exception as exc:
            problems.add(f"IMPORT FAILED {info.name}: {type(exc).__name__}: {exc}")
            continue
        source_file = getattr(module, "__file__", None)
        if not source_file or not source_file.endswith(".py"):
            continue
        defined = vars(module)

        def walk(code, where):
            for instruction in dis.get_instructions(code):
                if (instruction.opname == "LOAD_GLOBAL" and instruction.argval not in defined
                        and not hasattr(builtins, instruction.argval)):
                    problems.add(f"UNDEFINED {info.name}: {instruction.argval!r} (in {where})")
            for const in code.co_consts:
                if isinstance(const, types.CodeType):
                    walk(const, const.co_name)

        walk(compile(Path(source_file).read_text(encoding="utf-8"), source_file, "exec"), "<module>")
    return sorted(problems)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_dump = sub.add_parser("dump")
    p_dump.add_argument("out")
    sub.add_parser("names")
    p_probe = sub.add_parser("probe")
    p_probe.add_argument("dump")
    p_cmp = sub.add_parser("compare")
    p_cmp.add_argument("before")
    p_cmp.add_argument("after")
    p_cmp.add_argument("--rules")
    p_cmp.add_argument("--step", type=int, default=None)
    args = parser.parse_args()

    if args.command == "dump":
        data = dump()
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
        print(f"{len(data['routes'])} routes ({data['websocket_routes']} WebSocket) written to {args.out}")
        return 0

    if args.command == "probe":
        return probe(args.dump)

    if args.command == "names":
        problems = undefined_names()
        for line in problems:
            print(line)
        print(f"{'FAILED' if problems else 'OK'}: {len(problems)} undefined name(s)")
        return 1 if problems else 0

    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))["rules"] if args.rules else None
    errors = compare(before, after, rules, args.step)
    hard = [e for e in errors if not e.startswith("NOTE")]
    for e in errors:
        print(e)
    if hard:
        print(f"\nFAILED: {len(hard)} problem(s) ({len(before['routes'])} routes before, {len(after['routes'])} after)")
        return 1
    print(f"OK: {len(before['routes'])} routes before, {len(after['routes'])} after, "
          f"{('mapped by rules' + (f' up to step {args.step}' if args.step is not None else '')) if rules else 'identical'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
