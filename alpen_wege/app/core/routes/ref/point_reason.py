from app.core.models.models_ref import CoreRefPointReason
from app.core.schemas.ref import RefWithFactorCreate, RefWithFactorRead, RefWithFactorUpdate

from ._factory import build_ref_router

router = build_ref_router(
    model=CoreRefPointReason, create_schema=RefWithFactorCreate, update_schema=RefWithFactorUpdate,
    read_schema=RefWithFactorRead, slug="point-reasons",
)
