# Standard library
import ast
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
API_APPS = {"core", "compendium", "explorer", "profile", "management", "social", "assets"}
NOT_UNDER_API = {"/health"}  # the documentation URLs are not API routes
TYPE_FOLDERS = {"m2m", "ref", "sub"}  # the only folders that group resources; every other folder IS a resource
MAX_ROUTE_FILE_LINES = 300   # a single endpoint file; the standard expects far less


def _routes_dirs() -> list[Path]:
    return sorted(APP_DIR.glob("*/routes"))


def _package_dirs(routes_dir: Path) -> list[Path]:
    return sorted(p for p in routes_dir.rglob("*") if p.is_dir() and (p / "__init__.py").exists())


def _imported_from_package(init_file: Path) -> set[str]:
    # Names pulled in by `from . import a, b` and `from .a import x` inside a package __init__.
    names: set[str] = set()
    for node in ast.walk(ast.parse(init_file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module is None:
                names.update(alias.name for alias in node.names)
            else:
                names.add(node.module.split(".")[0])
    return names


def _load_route_map():
    spec = importlib.util.spec_from_file_location("route_map", ROOT / "scripts" / "route_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_url_is_api_v1_app_resource():
    # Standard U1: /api/v1/{app}/{resource}. Uses scripts/route_map.py to list the routes.
    route_map = _load_route_map()
    wrong = []
    for key in route_map.dump()["routes"]:
        path = key.split(" ", 1)[1]
        if path in NOT_UNDER_API:
            continue
        parts = path.strip("/").split("/")
        if parts[:2] != ["api", "v1"] or len(parts) < 4 or parts[2] not in API_APPS:
            wrong.append(key)
    assert not wrong, f"URLs outside /api/v1/<app>/<resource>: {wrong}"


def test_every_route_is_served_by_its_own_function():
    # Finds a route that another route hides (for example /{id} declared before /stats) and secured routes
    # that do not answer 401 without a token. Needs no database.
    route_map = _load_route_map()
    problems = route_map.probe_routes(route_map.dump()["routes"])
    assert not problems, problems


def test_no_module_reads_a_name_it_does_not_define():
    # A forgotten import or a renamed helper that is only used inside a function body would fail only when that
    # endpoint is called. This looks for such names in every module of the app. Needs no database.
    problems = _load_route_map().undefined_names()
    assert not problems, problems


def test_routes_folders_hold_only_folders():
    # Every resource is a folder. A loose .py file next to __init__.py is a resource that was not given its folder.
    loose = [str(f.relative_to(ROOT)) for d in _routes_dirs() for f in d.glob("*.py") if f.name != "__init__.py"]
    assert not loose, f"resources must be folders: {loose}"


def test_type_folders_only_for_m2m_ref_sub():
    # m2m, ref and sub group resources; they hold only resource folders. Any other folder is a resource itself:
    # it has _router.py and no sub-folder with resources.
    wrong = []
    for d in _routes_dirs():
        for folder in _package_dirs(d):
            is_type_folder = (folder / "_router.py").exists() is False
            children_dirs = [c for c in folder.iterdir() if c.is_dir() and (c / "__init__.py").exists()]
            if is_type_folder:
                if folder.name not in TYPE_FOLDERS:
                    wrong.append(f"{folder.relative_to(ROOT)}: a folder without _router.py must be one of {sorted(TYPE_FOLDERS)}")
                loose = [f.name for f in folder.glob("*.py") if f.name != "__init__.py"]
                if loose:
                    wrong.append(f"{folder.relative_to(ROOT)}: type folders hold only resource folders, found {loose}")
            elif children_dirs:
                wrong.append(f"{folder.relative_to(ROOT)}: a resource folder cannot contain folders")
    assert not wrong, wrong


def test_every_module_in_a_routes_folder_is_imported():
    # An endpoint file (or a resource folder in a type folder) that its folder's __init__.py does not import adds no
    # route, and nothing fails.
    missing = []
    for d in _routes_dirs():
        for folder in _package_dirs(d):
            wanted = {f.stem for f in folder.glob("*.py") if not f.stem.startswith("_")}
            wanted |= {c.name for c in folder.iterdir()
                       if c.is_dir() and (c / "__init__.py").exists() and not c.name.startswith("_")}
            for name in sorted(wanted - _imported_from_package(folder / "__init__.py")):
                missing.append(f"{folder.relative_to(ROOT)}/{name}")
    assert not missing, f"not imported by their __init__.py: {missing}"


def test_no_resource_is_both_a_file_and_a_folder():
    # With poi.py and poi/ side by side Python silently uses the folder.
    both = [str(f.relative_to(ROOT)) for d in _routes_dirs() for f in d.rglob("*.py") if (f.parent / f.stem).is_dir()]
    assert not both, f"file and folder with the same name: {both}"


def test_endpoint_files_stay_small():
    big = []
    for d in _routes_dirs():
        for f in d.rglob("*.py"):
            lines = len(f.read_text(encoding="utf-8").splitlines())
            if lines > MAX_ROUTE_FILE_LINES:
                big.append(f"{f.relative_to(ROOT)} ({lines} lines)")
    assert not big, f"split the file: {big}"
