import os, sys, ast; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # api_routes_tools/
from mig_lib import *
import subprocess
STEP = sys.argv[1]

def sub(path, old, new, count=1):
    s = read(path); assert old in s, f"{old!r} not in {path}"
    write(path, s.replace(old, new, count))

if STEP == "0":   # constants with the OLD values: no behaviour change
    write(f"{APP}/core/utils/api_paths.py", '''# Public URL helpers. The API lives under /api/v1 (see Routing/api_routes_structure_proposal.md).
API_V1 = "/api/v1"


def job_url(job_id) -> str:
    # Where the owner reads one of their jobs (Location header of the 202 responses).
    return f"{API_V1}/jobs/{job_id}"


# POST to this path uploads a GPX file; UploadSizeLimitMiddleware matches this exact path.
TRACK_UPLOAD_PATH = f"{API_V1}/tracks"
''')
    for f in ("compendium/routes/poi/rescan.py", "compendium/routes/card/rescan.py", "explorer/routes/track/create.py", "explorer/routes/track/reprocess.py"):
        p = f"{APP}/{f}"
        sub(p, 'response.headers["Location"] = f"/api/v1/jobs/{job[\'id\']}"', 'response.headers["Location"] = job_url(job["id"])')
        add_import(p, "from app.core.utils.api_paths import job_url")
    sub(f"{APP}/core/utils/upload_limit.py", 'self.path = "/api/v1/tracks"', "self.path = TRACK_UPLOAD_PATH")
    sub(f"{APP}/core/utils/upload_limit.py", "from app.config import get_settings\n", "from app.config import get_settings\nfrom app.core.utils.api_paths import TRACK_UPLOAD_PATH\n")
    sub(f"{APP}/main.py", '    api_v1_prefix = "/api/v1"\n', "    api_v1_prefix = API_V1\n")
    sub(f"{APP}/main.py", "from app.core.utils.responses import AppError, fail, request_id_ctx\n", "from app.core.utils.api_paths import API_V1\nfrom app.core.utils.responses import AppError, fail, request_id_ctx\n")
    shutil.copy(f"{TOOLS}/test_api_paths.py", f"{ROOT}/tests/test_api_paths.py")

if STEP == "1":   # compendium + explorer
    sub(f"{APP}/compendium/routes/__init__.py", "router = APIRouter()", 'router = APIRouter(prefix="/compendium")')
    sub(f"{APP}/explorer/routes/__init__.py", "router = APIRouter()", 'router = APIRouter(prefix="/explorer")')
    sub(f"{APP}/core/utils/api_paths.py", 'TRACK_UPLOAD_PATH = f"{API_V1}/tracks"', 'TRACK_UPLOAD_PATH = f"{API_V1}/explorer/tracks"')

if STEP == "2":   # core: /ref -> /core, resource types move to core
    sub(f"{APP}/core/routes/__init__.py", "router = APIRouter()\nrouter.include_router(ref_router)\n",
        "router = APIRouter(prefix=\"/core\")\nrouter.include_router(ref_router)\nrouter.include_router(resource_type.router)\n")
    sub(f"{APP}/core/routes/__init__.py", "from .ref import router as ref_router\n", "from . import resource_type\nfrom .ref import router as ref_router\n")
    sub(f"{APP}/core/routes/ref/__init__.py", 'router = APIRouter(prefix="/ref")', "router = APIRouter()")
    s = read(f"{APP}/profile/routes/resource_type.py")
    s = s.replace('router = APIRouter(prefix="/resource-types", tags=["Auth - Resource Types"])', 'router = APIRouter(prefix="/resource-types", tags=["Auth", "Auth - Resource Types"])')
    write(f"{APP}/core/routes/resource_type.py", s)
    os.remove(f"{APP}/profile/routes/resource_type.py")
    p = f"{APP}/profile/routes/__init__.py"
    sub(p, "from . import access_policy, resource_type\n", "from . import access_policy\n")
    sub(p, "auth_router.include_router(resource_type.router)\n", "")

if STEP == "3":   # profile: /profile prefix; folders own their prefix and tags; access policies out of /auth
    write(f"{APP}/profile/routes/auth/_router.py", "# Third-party\nfrom fastapi import APIRouter\n\nrouter = APIRouter(prefix=\"/auth\", tags=[\"Auth\"])\n")
    write(f"{APP}/profile/routes/user/_router.py", "# Third-party\nfrom fastapi import APIRouter\n\nrouter = APIRouter(prefix=\"/users\", tags=[\"Users\"])\n")
    write(f"{APP}/profile/routes/__init__.py", '''from fastapi import APIRouter

from . import access_policy
from .auth import router as auth_router
from .user import router as user_router

router = APIRouter(prefix="/profile")
router.include_router(auth_router)
router.include_router(user_router)
router.include_router(access_policy.router)
''')
    sub(f"{APP}/profile/routes/access_policy.py", 'tags=["Auth - Access Policies"]', 'tags=["Auth", "Auth - Access Policies"]')
    sub(f"{APP}/profile/dependencies/current_user.py", 'oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")', 'oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_V1}/profile/auth/login")')
    add_import(f"{APP}/profile/dependencies/current_user.py", "from app.core.utils.api_paths import API_V1")

if STEP == "4":   # management: one prefix, my-jobs, ws
    p = f"{APP}/management/routes/__init__.py"
    write(p, '''# Third-party
from fastapi import APIRouter

# Local application
from .broadcast import router as broadcast_router
from .celery import router as celery_router
from .event_log import router as event_log_router
from .jobs import router as jobs_router
from .my_jobs import router as my_jobs_router
from .settings import router as settings_router
from .ws import router as ws_router

# User routes (my-jobs, WebSocket) and administrator routes share the /management prefix.
router = APIRouter(prefix="/management")
router.include_router(my_jobs_router)
router.include_router(ws_router)
router.include_router(event_log_router)
router.include_router(settings_router)
router.include_router(jobs_router)
router.include_router(broadcast_router)
router.include_router(celery_router)
''')
    sub(f"{APP}/management/routes/my_jobs.py", 'router = APIRouter(prefix="/jobs", tags=["Management - Jobs"])', 'router = APIRouter(prefix="/my-jobs", tags=["Management - Jobs"])')
    sub(f"{APP}/core/utils/api_paths.py", 'return f"{API_V1}/jobs/{job_id}"', 'return f"{API_V1}/management/my-jobs/{job_id}"')
    sub(f"{APP}/explorer/routes/track/reprocess.py", "# GET /jobs/{id} is owner-only:", "# GET /management/my-jobs/{id} is owner-only:")
if STEP == "5":   # the project's own scripts use the new URLs
    p = f"{ROOT}/scripts/ws_check.py"
    t = read(p)
    assert t.count("{host}/api/v1/ws/ticket") == 1 and t.count('f"/api/v1/ws/jobs/{args.job}" if args.job else "/api/v1/ws"') == 1
    t = t.replace("{host}/api/v1/ws/ticket", "{host}/api/v1/management/ws/ticket")
    t = t.replace('f"/api/v1/ws/jobs/{args.job}" if args.job else "/api/v1/ws"', 'f"/api/v1/management/ws/jobs/{args.job}" if args.job else "/api/v1/management/ws"')
    write(p, t)
    p = f"{ROOT}/scripts/smoke_tracks.sh"
    t = read(p)
    assert t.count("$API/auth/login") == 1 and t.count("$API/tracks") == 9 and t.count("$API/jobs/") == 2
    t = t.replace("$API/auth/login", "$API/profile/auth/login").replace("$API/tracks", "$API/explorer/tracks").replace("$API/jobs/", "$API/management/my-jobs/")
    write(p, t)
    shutil.copy(f"{TOOLS}/e2e_check.py", f"{ROOT}/scripts/e2e_check.py")

if STEP == "6":   # the standard enforces itself
    shutil.copy(f"{TOOLS}/test_routes_standard.py", f"{ROOT}/tests/test_routes_standard.py")

print("step", STEP, "applied")
