from sqlalchemy.orm import selectinload

from app.compendium.models.models_cat.region import CompendiumCatRegion


EAGER = [
    selectinload(CompendiumCatRegion.country),
    selectinload(CompendiumCatRegion.region_type),
    selectinload(CompendiumCatRegion.parent),
]
