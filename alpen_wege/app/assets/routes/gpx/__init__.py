from ._router import router
from . import get_many, get_one, file, update, delete

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths come before /{id} paths. A GPX file is created by POST /explorer/tracks, not here.
ENDPOINT_MODULES = (get_many, get_one, file, update, delete,)

__all__ = ["router"]
