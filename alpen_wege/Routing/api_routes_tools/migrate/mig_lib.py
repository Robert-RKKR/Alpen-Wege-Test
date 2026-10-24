# Helpers for the sandbox dry run of the routes migration (not part of the plan's deliverables).
"""Helpers for the routes migration scripts (see Routing/api_routes_implementation_plan.md).

Environment:
  AW_ROOT    repo root to change (default: current directory)
  AW_PYLIB   folder that contains autoflake and pyflakes (pip install --target <folder> autoflake)
"""
import ast, os, re, shutil, subprocess, sys
from pathlib import Path

ROOT = os.path.abspath(os.environ.get("AW_ROOT", os.getcwd()))
APP = f"{ROOT}/app"
PYLIB = os.environ.get("AW_PYLIB", "/tmp/pylib")

def read(p): return Path(p).read_text(encoding="utf-8")
def write(p, s):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(s, encoding="utf-8")

class Mod:
    def __init__(self, path):
        self.path = path
        self.src = read(path)
        self.lines = self.src.splitlines(keepends=True)
        self.tree = ast.parse(self.src)
        self.funcs, self.assigns = {}, {}
        header_end = 0
        for node in self.tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                self.funcs[node.name] = "".join(self.lines[start - 1:node.end_lineno])
            elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                self.assigns[node.targets[0].id] = "".join(self.lines[node.lineno - 1:node.end_lineno])
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                header_end = node.end_lineno
        self.header = "".join(self.lines[:header_end])

def clean(path):
    # remove the imports that are no longer used in a generated file
    env = dict(os.environ, PYTHONPATH=PYLIB, PYTHONDONTWRITEBYTECODE="1")
    subprocess.run([sys.executable, "-m", "autoflake", "--in-place", "--remove-all-unused-imports", str(path)],
                   check=True, env=env)

HEADERS = {"# Standard library", "# Third-party", "# Local application"}


def drop_empty_headers(text):
    # remove import section comments that no longer have an import below them
    lines = text.splitlines(keepends=True)
    out = []
    for i, line in enumerate(lines):
        if line.strip() in HEADERS:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines) or not lines[j].lstrip().startswith(("import ", "from ")):
                continue
        out.append(line)
    return "".join(out)


def tidy(text):
    text = drop_empty_headers(text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip("\n") + "\n"


def add_import(path, line):
    """Add an import line after the last absolute import, so that relative imports (from ._router ...) stay last."""
    text = read(path)
    if line.strip() in text:
        return
    tree = ast.parse(text)
    imports = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    absolute = [n for n in imports if not (isinstance(n, ast.ImportFrom) and n.level > 0)]
    anchor = (absolute or imports)[-1]
    lines = text.splitlines(keepends=True)
    lines.insert(anchor.end_lineno, line.rstrip("\n") + "\n")
    write(path, "".join(lines))


def assert_known(mod, allowed_assigns):
    """Stop when an old module has a top-level statement that the script would silently lose."""
    for node in mod.tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if isinstance(node, ast.Expr) and isinstance(getattr(node, "value", None), ast.Constant) \
                and isinstance(node.value.value, str):
            continue   # docstring
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id in allowed_assigns:
            continue
        raise SystemExit(f"STOP: {mod.path} has a top-level statement this script does not know "
                         f"(line {node.lineno}): {ast.unparse(node)[:90]}")


def rename_shared(body, mapping):
    for old, new in mapping.items():
        body = re.sub(rf"\b{re.escape(old)}\b", new, body)
    return body

def make_folder_resource(src_file, folder, prefix_line, endpoints, shared=None, shared_rename=None, init_order=None, extra_header="", module_vars=None):
    """src_file: old module path. endpoints: {file_stem: [function names]}. shared: list of assign/function names to put in _shared.py."""
    mod = Mod(src_file)
    shared = shared or []
    shared_rename = shared_rename or {}
    assert_known(mod, {"router", "logger", "settings"} | set(shared))
    shared_src = ""
    for name in shared:
        piece = mod.assigns.get(name) or mod.funcs.get(name)
        assert piece, f"{name} not found in {src_file}"
        shared_src += piece + "\n\n"
    # _router.py
    write(f"{folder}/_router.py", "# Third-party\nfrom fastapi import APIRouter\n\n" + prefix_line.strip() + "\n")
    new_shared_names = [shared_rename.get(n, n) for n in shared]
    if shared:
        sh_body = rename_shared(shared_src, shared_rename)
        sh_vars = "".join(line + "\n" for var, line in (module_vars or {}).items() if re.search(rf"\b{re.escape(var)}\b", sh_body))
        write(f"{folder}/_shared.py", mod.header + "\n" + sh_vars + "\n\n" + sh_body)
        clean(f"{folder}/_shared.py")
        write(f"{folder}/_shared.py", tidy(read(f"{folder}/_shared.py")))
    for stem, names in endpoints.items():
        body = "\n\n\n".join(mod.funcs[n] for n in names)
        body = rename_shared(body, shared_rename)
        used = [n for n in new_shared_names if re.search(rf"\b{re.escape(n)}\b", body)]
        text = mod.header + extra_header + "\nfrom ._router import router\n"
        if used:
            text += f"from ._shared import {', '.join(used)}\n"
        text += "\n"
        for var, line in (module_vars or {}).items():
            if re.search(rf"\b{re.escape(var)}\b", body):
                text += line + "\n"
        text += "\n\n" + body + "\n"
        write(f"{folder}/{stem}.py", text)
        clean(f"{folder}/{stem}.py")
        write(f"{folder}/{stem}.py", tidy(read(f"{folder}/{stem}.py")))
    order = init_order or list(endpoints)
    init = ("from ._router import router\n"
            "from . import " + ", ".join(order) + "\n\n"
            "# Importing a module registers its endpoint on `router`. List every endpoint module here;\n"
            "# fixed paths (/upload-csv, /stats) come before /{id} paths.\n"
            "ENDPOINT_MODULES = (" + ", ".join(order) + ",)\n\n"
            "__all__ = [\"router\"]\n")
    write(f"{folder}/__init__.py", init)
    # sanity: every function placed exactly once
    placed = [n for names in endpoints.values() for n in names] + shared
    leftovers = [n for n in mod.funcs if n not in placed]
    assert not leftovers, f"functions not placed from {src_file}: {leftovers}"
    os.remove(src_file)
