from sqlalchemy.orm import selectinload

from app.compendium.models.models_cat.poi import CompendiumCatPoi


EAGER = [
    selectinload(CompendiumCatPoi.compendium_type),
    selectinload(CompendiumCatPoi.main_region),
]
