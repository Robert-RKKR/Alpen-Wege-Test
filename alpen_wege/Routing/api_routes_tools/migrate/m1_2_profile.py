import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mig_lib import *
R = f"{APP}/profile/routes"

# ---- auth/ folder: the four action files use the folder's shared router
write(f"{R}/auth/_router.py", "# Third-party\nfrom fastapi import APIRouter\n\nrouter = APIRouter()\n")
for stem in ("register", "login", "refresh", "logout"):
    assert_known(Mod(f"{R}/{stem}.py"), {"router"})
    s = read(f"{R}/{stem}.py")
    assert s.count("router = APIRouter()") == 1, stem
    s = s.replace("router = APIRouter()", "from ._router import router")
    write(f"{R}/auth/{stem}.py", s)
    os.remove(f"{R}/{stem}.py")
    clean(f"{R}/auth/{stem}.py")
    # `from ._router import router` must sit with the other imports: move it right after the import block
    t = read(f"{R}/auth/{stem}.py")
    t = t.replace("\nfrom ._router import router\n", "\n", 1)
    mod = Mod(f"{R}/auth/{stem}.py") if False else None
    lines = t.splitlines(keepends=True)
    # find last top-level import line
    import ast
    tree = ast.parse(t)
    last = max(n.end_lineno for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom)))
    lines.insert(last, "\nfrom ._router import router\n")
    write(f"{R}/auth/{stem}.py", tidy("".join(lines)))
INIT = ("from ._router import router\nfrom . import {mods}\n\n"
        "# Importing a module registers its endpoint on `router`. List every endpoint module here;\n"
        "# fixed paths (/upload-csv, /stats) come before /{{id}} paths.\n"
        "ENDPOINT_MODULES = ({mods},)\n\n__all__ = [\"router\"]\n")
write(f"{R}/auth/__init__.py", INIT.format(mods="register, login, refresh, logout"))

# ---- user/ folder
me = Mod(f"{R}/me.py")
assert_known(me, {"router"})
assert_known(Mod(f"{R}/admin.py"), {"router"})
write(f"{R}/user/_router.py", "# Third-party\nfrom fastapi import APIRouter\n\nrouter = APIRouter()\n")
shared_body = me.funcs["_user_to_read"].replace("def _user_to_read(", "def user_to_read(")
write(f"{R}/user/_shared.py", me.header + "\n\n\n" + shared_body + "\n")
clean(f"{R}/user/_shared.py"); write(f"{R}/user/_shared.py", tidy(read(f"{R}/user/_shared.py")))

def to_user_file(old, new, extra_imports):
    s = read(old)
    s = s.replace("router = APIRouter()\n", "")
    s = re.sub(r"\b_user_to_read\b", "user_to_read", s)
    s = s.replace("from app.profile.routes.me import user_to_read\n", "")
    return s, extra_imports

# me.py: drop the helper function, import it from _shared
s = read(f"{R}/me.py")
start = s.index("def _user_to_read(")
end = s.index('@router.get("/me"')
s = s[:start] + s[end:]
s = s.replace("router = APIRouter()\n", "")
s = re.sub(r"\b_user_to_read\b", "user_to_read", s)
s = s.replace("\n\n\n@router.get(\"/me\"", "\nfrom ._router import router\nfrom ._shared import user_to_read\n\n\n@router.get(\"/me\"", 1)
write(f"{R}/user/me.py", s); clean(f"{R}/user/me.py"); write(f"{R}/user/me.py", tidy(read(f"{R}/user/me.py")))

s = read(f"{R}/admin.py")
s = s.replace("from app.profile.routes.me import _user_to_read\n", "")
s = s.replace("router = APIRouter()\n", "\nfrom ._router import router\nfrom ._shared import user_to_read\n")
s = re.sub(r"\b_user_to_read\b", "user_to_read", s)
write(f"{R}/user/admin.py", s); clean(f"{R}/user/admin.py"); write(f"{R}/user/admin.py", tidy(read(f"{R}/user/admin.py")))
write(f"{R}/user/__init__.py", INIT.format(mods="me, admin"))
os.remove(f"{R}/me.py"); os.remove(f"{R}/admin.py")

# ---- access_policy.py -> resource_type.py + access_policy.py
ap = Mod(f"{R}/access_policy.py")
assert_known(ap, {"resource_type_router", "access_policy_router"})
rt_funcs = ["list_resource_types", "create_resource_type", "get_resource_type", "update_resource_type",
            "delete_resource_type", "upload_resource_type_csv"]
ap_funcs = ["list_access_policies", "create_access_policy", "get_access_policy", "update_access_policy",
            "delete_access_policy", "upload_access_policy_csv"]
leftover = [n for n in ap.funcs if n not in rt_funcs + ap_funcs]
assert not leftover, leftover
def build(stem, funcs, old_name, router_line):
    body = "\n\n\n".join(ap.funcs[n] for n in funcs)
    body = body.replace(f"@{old_name}.", "@router.")
    write(f"{R}/{stem}.py", ap.header + "\n\n" + router_line + "\n\n\n" + body + "\n")
    clean(f"{R}/{stem}.py"); write(f"{R}/{stem}.py", tidy(read(f"{R}/{stem}.py")))
build("resource_type", rt_funcs, "resource_type_router", 'router = APIRouter(prefix="/resource-types", tags=["Auth - Resource Types"])')
build("access_policy", ap_funcs, "access_policy_router", 'router = APIRouter(prefix="/access-policies", tags=["Auth - Access Policies"])')

write(f"{R}/__init__.py", '''from fastapi import APIRouter

from . import access_policy, resource_type
from .auth import router as auth_actions_router
from .user import router as user_router

auth_router = APIRouter(prefix="/auth", tags=["Auth"])
auth_router.include_router(auth_actions_router)
auth_router.include_router(resource_type.router)
auth_router.include_router(access_policy.router)

users_router = APIRouter(prefix="/users", tags=["Users"])
users_router.include_router(user_router)

router = APIRouter()
router.include_router(auth_router)
router.include_router(users_router)
''')

# ---- main.py: one profile router
m = read(f"{APP}/main.py")
m = m.replace("from app.profile.routes import auth_router\nfrom app.profile.routes import users_router\n", "from app.profile.routes import router as profile_router\n")
m = m.replace("    app.include_router(auth_router, prefix=api_v1_prefix)\n    app.include_router(users_router, prefix=api_v1_prefix)\n", "    app.include_router(profile_router, prefix=api_v1_prefix)\n")
write(f"{APP}/main.py", m)
