from ._router import router
from . import create, get_many, get_one, geometry, performance, update, archive, restore, reprocess

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (create, get_many, get_one, geometry, performance, update, archive, restore, reprocess,)

__all__ = ["router"]
