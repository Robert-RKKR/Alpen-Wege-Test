from app.core.models.models_ref import CoreRefSportType
from app.core.schemas.ref import RefWithFactorRead, RefWithFactorUpdate, SportTypeCreate

from ._factory import build_ref_router

# Special: SportType (name required)
router = build_ref_router(
    model=CoreRefSportType, create_schema=SportTypeCreate, update_schema=RefWithFactorUpdate,
    read_schema=RefWithFactorRead, slug="sport-types",
)
