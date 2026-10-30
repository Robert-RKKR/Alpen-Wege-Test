from ._router import router
from . import get_many, create, upload_csv, link, get_one, file, replace_file, update, delete

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths come before /{id} paths.
ENDPOINT_MODULES = (get_many, create, upload_csv, link, get_one, file, replace_file, update, delete,)

__all__ = ["router"]
