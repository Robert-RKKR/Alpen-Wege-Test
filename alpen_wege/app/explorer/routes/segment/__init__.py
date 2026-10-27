from ._router import router
from . import create_from_coordinates, create_from_track, create, get_many, get_one, geometry, update, delete

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/from-coordinates, /from-track) come before /{id} paths.
ENDPOINT_MODULES = (create_from_coordinates, create_from_track, create, get_many, get_one, geometry, update, delete,)

__all__ = ["router"]
