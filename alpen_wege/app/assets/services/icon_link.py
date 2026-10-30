"""Sets icon_id on the countries and regions whose ISO code matches the key of an icon: the API version of scripts/sql/icons_link.sql.

  countries : icon.key = 'flag_' + lower(iso_code)          (flag_at)
  regions   : icon.key = 'flag_' + lower(iso_code, - as _)  (CH-ZH -> flag_ch_zh)
Only EMPTY links are filled; a link that is set is never changed. Run it again after every load of icons.
The reference tables and resource types are not here: their icon_id is required, so they always have one.
"""
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.assets.models.models_agg.icon import AssetAggIcon
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.models.models_cat.region import CompendiumCatRegion

LINKED_BY_CODE = {"country": CompendiumCatCountry, "region": CompendiumCatRegion}


def _matches(what, model):
    if what == "country":
        return AssetAggIcon.key == func.concat("flag_", func.lower(model.iso_code))
    return model.iso_code.is_not(None) & (AssetAggIcon.key == func.concat("flag_", func.lower(func.replace(model.iso_code, "-", "_"))))


async def link_icons(db: AsyncSession) -> tuple[dict[str, int], dict[str, int]]:
    # (newly linked per table, rows still without an icon per table); tables with nothing to report are left out. The caller commits.
    linked, empty = {}, {}
    for what, model in LINKED_BY_CODE.items():
        result = await db.execute(
            update(model).where(model.icon_id.is_(None), _matches(what, model)).values(icon_id=AssetAggIcon.id)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount:
            linked[what] = result.rowcount
        left = (await db.execute(select(func.count()).select_from(model).where(model.icon_id.is_(None)))).scalar_one()
        if left:
            empty[what] = left
    return linked, empty
