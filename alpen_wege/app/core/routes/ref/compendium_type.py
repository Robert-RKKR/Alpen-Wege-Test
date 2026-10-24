from app.core.models.models_ref import CoreRefCompendiumType
from app.core.schemas.ref import CompendiumTypeCreate, CompendiumTypeRead, CompendiumTypeUpdate

from ._factory import build_ref_router

# Special: CompendiumType (+ is_collectable)
router = build_ref_router(
    model=CoreRefCompendiumType, create_schema=CompendiumTypeCreate, update_schema=CompendiumTypeUpdate,
    read_schema=CompendiumTypeRead, slug="compendium-types",
)
