from app.core.models.models_ref import CoreRefCompany
from app.core.schemas.ref import RefBaseCreate, RefBaseRead, RefBaseUpdate

from ._factory import build_ref_router

router = build_ref_router(
    model=CoreRefCompany, create_schema=RefBaseCreate, update_schema=RefBaseUpdate,
    read_schema=RefBaseRead, slug="companies",
)
