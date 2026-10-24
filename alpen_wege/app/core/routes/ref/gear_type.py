from app.core.models.models_ref import CoreRefGearType
from app.core.schemas.ref import RefBaseCreate, RefBaseRead, RefBaseUpdate

from ._factory import build_ref_router

router = build_ref_router(
    model=CoreRefGearType, create_schema=RefBaseCreate, update_schema=RefBaseUpdate,
    read_schema=RefBaseRead, slug="gear-types",
)
