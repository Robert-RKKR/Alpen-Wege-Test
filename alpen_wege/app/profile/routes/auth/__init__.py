from ._router import router
from . import register, login, refresh, logout

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (register, login, refresh, logout,)

__all__ = ["router"]
