# Third-party
from fastapi import APIRouter

# Special: CompendiumType (+ is_collectable)
router = APIRouter(prefix="/compendium-types", tags=["Reference - Compendium Types"])
