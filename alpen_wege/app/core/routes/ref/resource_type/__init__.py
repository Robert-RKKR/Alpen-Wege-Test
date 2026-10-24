from ._router import router
from . import upload_csv, get_many, create, get_one, update, delete

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/upload-csv, /stats) come before /{id} paths.
ENDPOINT_MODULES = (upload_csv, get_many, create, get_one, update, delete,)

__all__ = ["router"]
