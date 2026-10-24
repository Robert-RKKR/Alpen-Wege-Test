"""Phase 3, uniform layout: every resource, in every app, becomes a folder with one file per action.

    python m3_uniform.py <step>        (AW_ROOT = repo root, see mig_lib.py)

3.1  compendium, explorer, profile: country, region, post, gear, access_policy become folders;
     poi_region moves to compendium/routes/m2m/poi_region/
3.2  management: event_log, settings, my_jobs, jobs, broadcast, celery, ws become folders
3.3  profile/user: me.py and admin.py are split into one file per endpoint
3.4  core: the 19 reference tables stop being generated (own folder, real code in every file) and resource_type
     joins them in core/routes/ref/
3.5  tests/test_routes_standard.py of the uniform layout

Function names, paths, permissions and response models do not change. The scripts stop with STOP: ... when an old
file has a statement they do not know.
"""
import os, sys, re, ast, shutil, textwrap
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mig_lib import *

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STEP = sys.argv[1]
C = f"{APP}/compendium/routes"
E = f"{APP}/explorer/routes"
P = f"{APP}/profile/routes"
M = f"{APP}/management/routes"
K = f"{APP}/core/routes"


def guard_renames(src, rename):
    text = read(src)
    for old, new in rename.items():
        if re.search(rf"\b{re.escape(new)}\b", text):
            raise SystemExit(f"STOP: renaming {old} to {new} in {src} would collide with an existing name {new}")


def crud(src, folder, fn, shared=None, rename=None, module_vars=None):
    mod = Mod(src)
    endpoints = {
        "upload_csv": [fn["csv"]], "get_many": [fn["list"]], "create": [fn["create"]],
        "get_one": [fn["get"]], "update": [fn["update"]], "delete": [fn["delete"]],
    }
    guard_renames(src, rename or {})
    make_folder_resource(src, folder, mod.assigns["router"], endpoints, shared=shared, shared_rename=rename,
                         module_vars=module_vars)


def sub(path, old, new):
    s = read(path)
    assert old in s, (path, old)
    write(path, s.replace(old, new, 1))


if STEP == "1":
    std = lambda one, many, csv="upload_csv": dict(list=f"list_{many}", create=f"create_{one}", get=f"get_{one}",
                                                    update=f"update_{one}", delete=f"delete_{one}", csv=csv)
    crud(f"{C}/country.py", f"{C}/country", std("country", "countries"))
    crud(f"{C}/region.py", f"{C}/region", std("region", "regions"), shared=["_EAGER"], rename={"_EAGER": "EAGER"})
    crud(f"{C}/post.py", f"{C}/post", std("post", "posts"), shared=["_EAGER"], rename={"_EAGER": "EAGER"})
    crud(f"{C}/poi_region.py", f"{C}/m2m/poi_region", std("poi_region", "poi_regions"),
         shared=["_EAGER"], rename={"_EAGER": "EAGER"})
    write(f"{C}/m2m/__init__.py", "from fastapi import APIRouter\n\nfrom . import poi_region\n\n"
          "router = APIRouter()\nrouter.include_router(poi_region.router)\n")
    sub(f"{C}/__init__.py", "from .poi_region import router as poi_region_router\n", "from .m2m import router as m2m_router\n")
    sub(f"{C}/__init__.py", "router.include_router(poi_region_router)\n", "router.include_router(m2m_router)\n")
    crud(f"{E}/gear.py", f"{E}/gear", std("gear", "gear"))
    crud(f"{P}/access_policy.py", f"{P}/access_policy",
         dict(list="list_access_policies", create="create_access_policy", get="get_access_policy",
              update="update_access_policy", delete="delete_access_policy", csv="upload_access_policy_csv"))


if STEP == "2":
    LOGGER = {"logger": "logger = logging.getLogger(__name__)"}

    def custom(name, endpoints, shared=None, rename=None, order=None, module_vars=None):
        src = f"{M}/{name}.py"
        mod = Mod(src)
        guard_renames(src, rename or {})
        make_folder_resource(src, f"{M}/{name}", mod.assigns["router"], endpoints, shared=shared, shared_rename=rename,
                             init_order=order, module_vars=module_vars)

    custom("event_log", {"get_many": ["list_event_logs"], "entity_types": ["list_entity_types"],
                         "get_one": ["get_event_log"], "compare": ["compare_event_logs"]})
    custom("settings", {"get_many": ["list_settings"], "get_one": ["get_setting_route"], "update": ["update_setting"],
                        "reset": ["reset_setting"]},
           shared=["admin_only", "_get_row", "_apply"], rename={"_get_row": "get_row", "_apply": "apply"})
    custom("my_jobs", {"get_many": ["list_my_jobs"], "get_one": ["get_my_job"]})
    custom("jobs", {"get_many": ["list_all_jobs"], "stats": ["job_stats"], "get_one": ["get_any_job"]},
           shared=["admin_only", "T"])
    custom("broadcast", {"send": ["send_broadcast"]}, shared=["admin_only"], module_vars=LOGGER)
    custom("celery", {"status": ["celery_status"], "workers": ["celery_workers"], "tasks_registered": ["celery_registered"],
                      "tasks_active": ["celery_live_tasks"], "task_detail": ["celery_task_detail"], "beat": ["celery_beat"]},
           shared=["admin_only", "_cached", "_uuid_or_none", "_jobs_by_task_id"],
           rename={"_cached": "cached", "_uuid_or_none": "uuid_or_none", "_jobs_by_task_id": "jobs_by_task_id"})
    custom("ws", {"ticket": ["create_ws_ticket"], "general": ["ws_general"], "job": ["ws_job"]},
           shared=["CLOSE_UNAUTHORIZED", "CLOSE_FORBIDDEN", "CLOSE_NOT_FOUND", "CLOSE_RECONNECT", "CLOSE_TOO_MANY",
                   "MAX_CLIENT_MESSAGE_CHARS", "TERMINAL", "_consume_ticket", "_register_connection", "_dump",
                   "_general_snapshot", "_job_snapshot", "_close_code_for", "_parse", "_serve"],
           rename={"_consume_ticket": "consume_ticket", "_register_connection": "register_connection", "_dump": "dump",
                   "_general_snapshot": "general_snapshot", "_job_snapshot": "job_snapshot",
                   "_close_code_for": "close_code_for", "_parse": "parse", "_serve": "serve"},
           module_vars=LOGGER)

    # consecutive constants (CLOSE_UNAUTHORIZED = ...) belong together
    shared_ws = f"{M}/ws/_shared.py"
    write(shared_ws, re.sub(r"(?m)^([A-Z][A-Z0-9_]* = [^\n]*\n)\n\n(?=[A-Z][A-Z0-9_]* = )", r"\1", read(shared_ws)))


if STEP == "3":
    folder = f"{P}/user"
    sources = {s: Mod(f"{folder}/{s}") for s in ("me.py", "admin.py")}
    for m in sources.values():
        assert_known(m, set())
    endpoints = {  # stem: (source file, function)
        "get_me": ("me.py", "get_me"), "update_me": ("me.py", "update_me"),
        "get_many": ("admin.py", "list_users"), "get_one": ("admin.py", "get_user"),
        "activate": ("admin.py", "activate_user"), "deactivate": ("admin.py", "deactivate_user"),
        "change_group": ("admin.py", "change_group"),
    }
    for stem, (src, fn_name) in endpoints.items():
        m = sources[src]
        header = "".join(l for l in m.header.splitlines(keepends=True)
                         if not l.startswith("from ._router import") and not l.startswith("from ._shared import"))
        body = m.funcs[fn_name]
        text = header + "\nfrom ._router import router\n"
        if re.search(r"\buser_to_read\b", body):
            text += "from ._shared import user_to_read\n"
        text += "\n\n" + body + "\n"
        write(f"{folder}/{stem}.py", text)
        clean(f"{folder}/{stem}.py")
        write(f"{folder}/{stem}.py", tidy(read(f"{folder}/{stem}.py")))
    placed = {fn for _, fn in endpoints.values()}
    for m in sources.values():
        left = set(m.funcs) - placed
        assert not left, f"functions not placed: {left}"
    for s in sources:
        os.remove(f"{folder}/{s}")
    order = list(endpoints)   # /me before /{user_id}
    write(f"{folder}/__init__.py",
          "from ._router import router\nfrom . import " + ", ".join(order) + "\n\n"
          "# Importing a module registers its endpoint on `router`. List every endpoint module here;\n"
          "# fixed paths (/me) come before /{user_id} paths.\n"
          "ENDPOINT_MODULES = (" + ", ".join(order) + ",)\n\n__all__ = [\"router\"]\n")


if STEP == "4":
    fac = Mod(f"{K}/ref/_factory.py")
    fac_node = next(n for n in ast.parse(fac.src).body if isinstance(n, ast.FunctionDef) and n.name == "build_ref_router")
    nested = {}
    for n in ast.walk(fac_node):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n is not fac_node:
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            nested[n.name] = textwrap.dedent("".join(fac.lines[start - 1:n.end_lineno]))
    expected = {"list_items", "create_item", "get_item", "update_item", "delete_item", "upload_csv"}
    if set(nested) != expected:
        raise SystemExit(f"STOP: the factory has other endpoints than this script knows: {sorted(set(nested) ^ expected)}")
    stems = re.findall(r"^\s+(\w+),\n", read(f"{K}/ref/__init__.py").split("from . import (", 1)[1].split(")", 1)[0], re.M)
    assert len(stems) == 19, stems
    mapping = {"upload_csv": "upload_csv", "get_many": "list_items", "create": "create_item",
               "get_one": "get_item", "update": "update_item", "delete": "delete_item"}
    for stem in stems:
        small = read(f"{K}/ref/{stem}.py")
        m = re.search(r'model=(\w+), create_schema=(\w+), update_schema=(\w+),\s*read_schema=(\w+), slug="([^"]+)"', small)
        assert m, f"cannot read the table file {stem}.py"
        model, create_s, update_s, read_s, slug = m.groups()
        imports = "".join(l for l in small.splitlines(keepends=True) if l.startswith(("from app.core.models", "from app.core.schemas")))
        special = next((l for l in small.splitlines() if l.startswith("# Special:")), None)
        folder = f"{K}/ref/{stem}"
        tag = "Reference - " + slug.replace("-", " ").title()
        write(f"{folder}/_router.py", "# Third-party\nfrom fastapi import APIRouter\n\n" + (special + "\n" if special else "")
              + f'router = APIRouter(prefix="/{slug}", tags=["{tag}"])\n')
        for file_stem, fn_name in mapping.items():
            body = nested[fn_name]
            body = re.sub(r"\bcreate_schema\b", create_s, body)
            body = re.sub(r"\bupdate_schema\b", update_s, body)
            body = re.sub(r"\bread_schema\b", read_s, body)
            body = re.sub(r"\bresource_key\b", '"ref"', body)
            body = body.replace('f"{slug} not found"', f'"{slug} not found"').replace('f"Import {slug} from CSV"', f'"Import {slug} from CSV"')
            body = re.sub(r"\b_desc\b", f"csv_upload_description({model})", body)
            body = re.sub(r"\bmodel\b", model, body)
            assert "slug" not in body, f"slug left in {stem}/{file_stem}"
            text = fac.header + imports + "\nfrom ._router import router\n\n\n" + body + "\n"
            write(f"{folder}/{file_stem}.py", text)
            clean(f"{folder}/{file_stem}.py")
            write(f"{folder}/{file_stem}.py", tidy(read(f"{folder}/{file_stem}.py")))
        order = list(mapping)
        write(f"{folder}/__init__.py", "from ._router import router\nfrom . import " + ", ".join(order) + "\n\n"
              "# Importing a module registers its endpoint on `router`. List every endpoint module here;\n"
              "# fixed paths (/upload-csv) come before /{id} paths.\n"
              "ENDPOINT_MODULES = (" + ", ".join(order) + ",)\n\n__all__ = [\"router\"]\n")
        os.remove(f"{K}/ref/{stem}.py")
    os.remove(f"{K}/ref/_factory.py")
    # resource_type joins the reference tables
    src = f"{K}/resource_type.py"
    mod = Mod(src)
    make_folder_resource(src, f"{K}/ref/resource_type", mod.assigns["router"],
                         {"upload_csv": ["upload_resource_type_csv"], "get_many": ["list_resource_types"],
                          "create": ["create_resource_type"], "get_one": ["get_resource_type"],
                          "update": ["update_resource_type"], "delete": ["delete_resource_type"]})
    all_stems = stems + ["resource_type"]
    write(f"{K}/ref/__init__.py", "from fastapi import APIRouter\n\nfrom . import (\n" + "".join(f"    {s},\n" for s in all_stems)
          + ")\n\nrouter = APIRouter()\n" + "".join(f"router.include_router({s}.router)\n" for s in all_stems))
    write(f"{K}/__init__.py", 'from fastapi import APIRouter\n\nfrom .ref import router as ref_router\n\n'
          'router = APIRouter(prefix="/core")\nrouter.include_router(ref_router)\n')


if STEP == "5":
    shutil.copy(f"{TOOLS}/test_routes_standard.py", f"{ROOT}/tests/test_routes_standard.py")

print("step", STEP, "applied")
