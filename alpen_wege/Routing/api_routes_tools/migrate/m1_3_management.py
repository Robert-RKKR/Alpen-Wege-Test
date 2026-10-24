import os, sys, ast; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mig_lib import *
M = f"{APP}/management/routes"
# ---- P1-3 management: file renames + JOB_STATUSES out of a route file
k = read(f"{APP}/management/jobs/kinds.py")
k += '\n\n# Life cycle states of a job (the `status` column of mgmt_log_job)\nJOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")\n'
write(f"{APP}/management/jobs/kinds.py", k)

mine = read(f"{M}/jobs.py")
assert 'JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")\n' in mine
mine = mine.replace('JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")\n\n', "")
mine = mine.replace("from app.management.models.job import MgmtLogJob\n", "from app.management.jobs.kinds import JOB_STATUSES\nfrom app.management.models.job import MgmtLogJob\n")
adm = read(f"{M}/admin_jobs.py")
adm = adm.replace("from app.management.routes.jobs import JOB_STATUSES\n", "")
adm = adm.replace("from app.management.models.job import MgmtLogJob\n", "from app.management.jobs.kinds import JOB_STATUSES\nfrom app.management.models.job import MgmtLogJob\n")
write(f"{M}/my_jobs.py", mine)
write(f"{M}/jobs.py", adm)
os.remove(f"{M}/admin_jobs.py")
init = read(f"{M}/__init__.py")
init = init.replace("from .admin_jobs import router as admin_jobs_router\n", "")
init = init.replace("from .jobs import router as jobs_router\n", "from .jobs import router as jobs_router\nfrom .my_jobs import router as my_jobs_router\n")
init = init.replace("admin_router.include_router(admin_jobs_router)", "admin_router.include_router(jobs_router)")
init = init.replace("router.include_router(jobs_router)\nrouter.include_router(ws_router)", "router.include_router(my_jobs_router)\nrouter.include_router(ws_router)")
write(f"{M}/__init__.py", init)

