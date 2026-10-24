"""Behaviour check for the routes migration: compare the CODE of every route function before and after.

    python scripts/ast_compare.py OLD_REPO_ROOT NEW_REPO_ROOT [--phase 1|2]

`route_map.py` checks what the routes declare (URLs, permissions, shapes). This script checks what the
functions DO: it parses every function in the route files (and in upload_limit.py and current_user.py),
applies the rewrites that the migration plan allows (renamed helpers; to the OLD code only: the `Location`
helper, the shared `apply_scope`, the new URL constants) and requires the NEW code to be identical. Comments and formatting are
ignored. A dropped call, a typo in a path inside a body, a swapped argument, a changed decorator option all
show up as "only in old" / "only in new".

--phase 1 (default 2) only allows the rewrites of the structure phase; use it at the end of phase 1, when the
Location helper and the URL constants are not in place yet.

It does not run anything and imports nothing from the app, so it also works on a plain checkout.
"""
import ast
import re
import sys
from collections import Counter
from pathlib import Path

ROUTE_FILES = "app/**/routes/**/*.py"
EXTRA_FILES = ["app/core/utils/upload_limit.py", "app/profile/dependencies/current_user.py",
               "app/management/jobs/kinds.py"]   # JOB_STATUSES moves here in step 1.3
NEW_ONLY_FILES = ["app/core/utils/scope.py"]  # the shared apply_scope lives here after step 1.5
# helpers that were copied into several files and are shared after the migration: compare as a set
# (a module-level logger is created once per file; apply_scope is the shared helper of step 1.5)
DEDUPE = {"apply_scope", "logger"}
# top-level assignments are compared too (constants, eager-load lists, aliases), except routers (their prefix
# and tags are checked by route_map.py) and the lists the new folders add
SKIP_ASSIGNS = {"ENDPOINT_MODULES", "__all__"}

# Rewrites that the plan allows.
# CHANGES are applied to the OLD code only: they turn the old text into the text the plan wants in the new tree,
# so a forgotten change (for example an old Location literal still in the new tree) is reported.
CHANGES_PHASE1 = [
    (r"\b_apply_scope\(base, access\)", "apply_scope(base, ExplorerAggTrack, access)"),
    (r"def _apply_scope\(stmt, model, access: AccessContext\)", 'def apply_scope(stmt, model, access: "AccessContext")'),
    (r"@resource_type_router\.", "@router."),
    (r"@access_policy_router\.", "@router."),
]
CHANGES_PHASE2 = [
    (r"""response\.headers\["Location"\] = f"/api/v1/jobs/\{job\['id'\]\}\"""", 'response.headers["Location"] = job_url(job["id"])'),
    (r'self\.path = "/api/v1/tracks"', "self.path = TRACK_UPLOAD_PATH"),
    (r'tokenUrl="/api/v1/auth/login"', 'tokenUrl=f"{API_V1}/profile/auth/login"'),
]
CHANGES = list(CHANGES_PHASE1)  # set in main() from --phase
# RENAMES are pure name changes, applied to both sides (some files keep the old name, others get the new one).
RENAMES = [
    (r"\b_EAGER\b", "EAGER"),
    (r"\b_apply_scope\b", "apply_scope"),
    (r"\b_apply_visibility\b", "apply_visibility"),
    (r"\b_ensure_visible\b", "ensure_visible"),
    (r"\b_build_metrics\b", "build_metrics"),
    (r"\b_user_to_read\b", "user_to_read"),
    (r"\b_build_ref_router\b", "build_ref_router"),
]
# Definitions that exist only in the old tree on purpose (fingerprint = name + argument names)
ALLOWED_ONLY_OLD = {
    ("apply_scope", ("stmt", "access")),   # track's own copy, replaced by the shared one
    ("_BASE_TABLES", ()), ("_FACTOR_TABLES", ()), ("routers", ()),   # core/routes/ref.py: one file per table now
}


def _normalise(source: str, old_side: bool) -> str:
    if old_side:
        for pattern, replacement in CHANGES:
            source = re.sub(pattern, replacement, source)
    for pattern, replacement in RENAMES:
        source = re.sub(pattern, replacement, source)
    return source


def _assign_name(node):
    target = node.targets[0] if isinstance(node, ast.Assign) and len(node.targets) == 1 else getattr(node, "target", None)
    return target.id if isinstance(target, ast.Name) else None


def _collect(root: Path, old_side: bool) -> dict[str, tuple[str, str, tuple]]:
    files = sorted(root.glob(ROUTE_FILES)) + [root / f for f in EXTRA_FILES]
    if not old_side:
        files += [root / f for f in NEW_ONLY_FILES]
    found: list[tuple[str, str, str, tuple]] = []
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        lines = text.splitlines(keepends=True)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start = min([node.lineno] + [d.lineno for d in node.decorator_list])
                segment = "".join(lines[start - 1:node.end_lineno])
                args = tuple(a.arg for a in node.args.args) if not isinstance(node, ast.ClassDef) else ()
                name = node.name
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and _assign_name(node) is not None \
                    and not _assign_name(node).endswith("router") and _assign_name(node) not in SKIP_ASSIGNS:
                segment = "".join(lines[node.lineno - 1:node.end_lineno])
                args = ()
                name = _assign_name(node)
            else:
                continue
            segment = _normalise(segment, old_side)
            try:
                dumped = ast.dump(ast.parse(segment.strip("\n")), include_attributes=False)
            except SyntaxError:
                dumped = "SYNTAX ERROR: " + segment
            name = _normalise(name, old_side)
            found.append((name, str(path.relative_to(root)), dumped, args))
    return found


def compare(old_root: Path, new_root: Path) -> list[str]:
    old = _collect(old_root, True)
    new = _collect(new_root, False)
    problems: list[str] = []

    def fingerprint_counter(items):
        c: Counter = Counter()
        for name, _file, dumped, _args in items:
            c[(name, dumped)] += 1
        return c

    old_c, new_c = fingerprint_counter(old), fingerprint_counter(new)
    where_old = {(n, d): f for n, f, d, _ in old}
    where_new = {(n, d): f for n, f, d, _ in new}
    args_of = {(n, d): a for n, _f, d, a in old}

    for key in sorted(set(old_c) | set(new_c)):
        name = key[0]
        o, n = old_c.get(key, 0), new_c.get(key, 0)
        if name in DEDUPE:
            o, n = min(o, 1), min(n, 1)
        if o == n:
            continue
        if o > n:
            if (name, args_of.get(key, ())) in ALLOWED_ONLY_OLD:
                continue
            problems.append(f"ONLY IN OLD  {name}  ({where_old.get(key)}): not found unchanged in the new tree")
        else:
            problems.append(f"ONLY IN NEW  {name}  ({where_new.get(key)}): differs from every old definition")
    total = len(old)
    print(f"compared {total} definitions of the old tree with {len(new)} of the new tree")
    return problems


def main() -> int:
    args = sys.argv[1:]
    phase = 2
    if "--phase" in args:
        i = args.index("--phase")
        phase = int(args[i + 1])
        del args[i:i + 2]
    if len(args) != 2 or phase not in (1, 2):
        print(__doc__)
        return 2
    CHANGES[:] = CHANGES_PHASE1 + (CHANGES_PHASE2 if phase == 2 else [])
    problems = compare(Path(args[0]), Path(args[1]))
    for p in problems:
        print(p)
    print(f"{'FAILED' if problems else 'OK'}: {len(problems)} unexpected difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
