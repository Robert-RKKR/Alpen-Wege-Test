from ._router import router
from . import me, admin

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (me, admin,)

__all__ = ["router"]
