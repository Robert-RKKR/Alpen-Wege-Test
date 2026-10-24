from ._router import router
from . import get_many, stats, get_one

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (get_many, stats, get_one,)

__all__ = ["router"]
