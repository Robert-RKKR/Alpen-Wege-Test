from sqlalchemy.orm import selectinload

from app.compendium.models.models_cat.card import CompendiumCatCard


EAGER = [
    selectinload(CompendiumCatCard.rarity),
    selectinload(CompendiumCatCard.compendium_type),
    selectinload(CompendiumCatCard.poi),
]
