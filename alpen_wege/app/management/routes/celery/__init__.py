from ._router import router
from . import status, workers, tasks_registered, tasks_active, task_detail, beat

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (status, workers, tasks_registered, tasks_active, task_detail, beat,)

__all__ = ["router"]
