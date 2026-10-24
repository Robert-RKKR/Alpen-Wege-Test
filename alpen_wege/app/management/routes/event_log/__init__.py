from ._router import router
from . import get_many, entity_types, get_one, compare

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (get_many, entity_types, get_one, compare,)

__all__ = ["router"]
