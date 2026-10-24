import os, sys, ast; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mig_lib import *
C = f"{APP}/compendium/routes"

# ---- P1-5 one shared apply_scope
write(f"{APP}/core/utils/scope.py", '''# Standard library
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.profile.permissions import AccessContext


def apply_scope(stmt, model, access: "AccessContext"):
    # Narrow a SELECT to the rows the caller may see:
    #   "own"    -> rows created by the caller
    #   "public" -> rows created by the caller or marked is_public
    #   "all"    -> no filter
    if access.scope == "own":
        stmt = stmt.where(model.created_by == access.user.id)
    elif access.scope == "public":
        stmt = stmt.where(
            (model.created_by == access.user.id) | (model.is_public == True)  # noqa: E712
        )
    return stmt
''')
IMPORT = "from app.core.utils.scope import apply_scope\n"
C = f"{APP}/compendium/routes"
def drop_local(path, old_name="_apply_scope", shared_form=False):
    s = read(path)
    mod = Mod(path)
    func_name = "apply_scope" if shared_form else old_name
    src = mod.funcs[func_name]
    s = s.replace(src, "")
    s = re.sub(rf"\b{old_name}\b", "apply_scope", s)
    write(path, tidy(s))
    clean(path); write(path, tidy(read(path)))
    add_import(path, IMPORT)
import ast
for f in ("country", "region", "post", "poi_region"):
    drop_local(f"{C}/{f}.py")
drop_local(f"{APP}/explorer/routes/gear.py")
# folder resources: shared copy lives in _shared.py as apply_scope (already renamed in P1-4)
for res in ("poi", "card"):
    sh = f"{C}/{res}/_shared.py"
    s = read(sh); mod = Mod(sh)
    write(sh, tidy(s.replace(mod.funcs["apply_scope"], "")))
    clean(sh); write(sh, tidy(read(sh)))
    for p in Path(f"{C}/{res}").glob("*.py"):
        t = read(p)
        if "from ._shared import" in t and "apply_scope" in t:
            m = re.search(r"from \._shared import ([^\n]+)\n", t)
            names = [n.strip() for n in m.group(1).split(",") if n.strip() != "apply_scope"]
            repl = (f"from ._shared import {', '.join(names)}\n" if names else "")
            t = t.replace(m.group(0), repl)
            write(p, t)
            add_import(p, IMPORT)
# track: signature (stmt, access) -> shared (stmt, model, access)
sh = f"{APP}/explorer/routes/track/_shared.py"
s = read(sh); mod = Mod(sh)
write(sh, tidy(s.replace(mod.funcs["apply_scope"], "")))
clean(sh); write(sh, tidy(read(sh)))
p = f"{APP}/explorer/routes/track/get_many.py"
t = read(p)
t = t.replace("from ._shared import apply_scope, ", "from ._shared import ").replace("base = apply_scope(base, access)", "base = apply_scope(base, ExplorerAggTrack, access)")
write(p, t)
add_import(p, IMPORT)
