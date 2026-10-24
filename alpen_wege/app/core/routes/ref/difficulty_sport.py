from app.core.models.models_ref import CoreRefDifficultySport
from app.core.schemas.ref import DifficultySportCreate, DifficultySportRead, DifficultySportUpdate

from ._factory import build_ref_router

# Special: DifficultySport (+ sport_type_id)
router = build_ref_router(
    model=CoreRefDifficultySport, create_schema=DifficultySportCreate, update_schema=DifficultySportUpdate,
    read_schema=DifficultySportRead, slug="difficulty-sports",
)
