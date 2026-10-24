from ._router import router
from . import get_many, get_one, update, reset

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (get_many, get_one, update, reset,)

__all__ = ["router"]
