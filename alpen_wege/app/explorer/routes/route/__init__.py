from ._router import router
from . import create, get_many, get_one, geometry, get_segments, validate_segments, set_segments, update, delete

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths come before /{id} paths.
ENDPOINT_MODULES = (create, get_many, get_one, geometry, get_segments, validate_segments, set_segments, update, delete,)

__all__ = ["router"]
