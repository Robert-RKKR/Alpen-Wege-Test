from ._router import router
from . import get_me, update_me, get_many, get_one, activate, deactivate, change_group

# Importing a module registers its endpoint on `router`. List every endpoint module here;
# fixed paths (/me) come before /{user_id} paths.
ENDPOINT_MODULES = (get_me, update_me, get_many, get_one, activate, deactivate, change_group,)

__all__ = ["router"]
