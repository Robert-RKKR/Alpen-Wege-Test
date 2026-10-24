import os, sys; sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mig_lib import *
R = f"{APP}/core/routes"
mod = Mod(f"{R}/ref.py")
_expected = {"CoreRefCompany", "CoreRefGearType", "CoreRefAchievementCategory", "CoreRefAchievementScope",
             "CoreRefAchievementType", "CoreRefDifficultyLevel", "CoreRefPointReason", "CoreRefPostType", "CoreRefRarity",
             "CoreRefRegionType", "CoreRefScheduleStatus", "CoreRefSnowCondition", "CoreRefTrailCondition",
             "CoreRefVisibility", "CoreRefWaypointType", "CoreRefWeatherCondition", "CoreRefSportType",
             "CoreRefDifficultySport", "CoreRefCompendiumType"}
_registered = set(re.findall(r"\bCoreRef\w+", read(f"{R}/ref.py").split("def _build_ref_router", 1)[1]))
if _registered != _expected:
    raise SystemExit(f"STOP: core/routes/ref.py registers other tables than this script knows: "
                     f"{sorted(_registered ^ _expected)}")
fn = mod.funcs["_build_ref_router"].replace("def _build_ref_router(", "def build_ref_router(")
write(f"{R}/ref/_factory.py", mod.header + "\n\n\n" + fn + "\n")
clean(f"{R}/ref/_factory.py"); write(f"{R}/ref/_factory.py", tidy(read(f"{R}/ref/_factory.py")))

BASE = ("RefBaseCreate", "RefBaseUpdate", "RefBaseRead")
FACT = ("RefWithFactorCreate", "RefWithFactorUpdate", "RefWithFactorRead")
tables = [  # (file stem, model class, schemas, slug) in today's registration order
    ("company", "CoreRefCompany", BASE, "companies"),
    ("gear_type", "CoreRefGearType", BASE, "gear-types"),
    ("achievement_category", "CoreRefAchievementCategory", FACT, "achievement-categories"),
    ("achievement_scope", "CoreRefAchievementScope", FACT, "achievement-scopes"),
    ("achievement_type", "CoreRefAchievementType", FACT, "achievement-types"),
    ("difficulty_level", "CoreRefDifficultyLevel", FACT, "difficulty-levels"),
    ("point_reason", "CoreRefPointReason", FACT, "point-reasons"),
    ("post_type", "CoreRefPostType", FACT, "post-types"),
    ("rarity", "CoreRefRarity", FACT, "rarities"),
    ("region_type", "CoreRefRegionType", FACT, "region-types"),
    ("schedule_status", "CoreRefScheduleStatus", FACT, "schedule-statuses"),
    ("snow_condition", "CoreRefSnowCondition", FACT, "snow-conditions"),
    ("trail_condition", "CoreRefTrailCondition", FACT, "trail-conditions"),
    ("visibility", "CoreRefVisibility", FACT, "visibilities"),
    ("waypoint_type", "CoreRefWaypointType", FACT, "waypoint-types"),
    ("weather_condition", "CoreRefWeatherCondition", FACT, "weather-conditions"),
    ("sport_type", "CoreRefSportType", ("SportTypeCreate", "RefWithFactorUpdate", "RefWithFactorRead"), "sport-types"),
    ("difficulty_sport", "CoreRefDifficultySport", ("DifficultySportCreate", "DifficultySportUpdate", "DifficultySportRead"), "difficulty-sports"),
    ("compendium_type", "CoreRefCompendiumType", ("CompendiumTypeCreate", "CompendiumTypeUpdate", "CompendiumTypeRead"), "compendium-types"),
]
assert len(tables) == 19
SPECIAL = {"sport_type": "# Special: SportType (name required)",
           "difficulty_sport": "# Special: DifficultySport (+ sport_type_id)",
           "compendium_type": "# Special: CompendiumType (+ is_collectable)"}
for stem, model, (c, u, r), slug in tables:
    schemas = sorted({c, u, r})
    write(f"{R}/ref/{stem}.py", (
        f"from app.core.models.models_ref import {model}\n"
        f"from app.core.schemas.ref import {', '.join(schemas)}\n\n"
        f"from ._factory import build_ref_router\n\n"
        + (SPECIAL[stem] + "\n" if stem in SPECIAL else "") +
        f"router = build_ref_router(\n"
        f"    model={model}, create_schema={c}, update_schema={u},\n"
        f"    read_schema={r}, slug=\"{slug}\",\n"
        f")\n"))
init = "from fastapi import APIRouter\n\nfrom . import (\n" + "".join(f"    {t[0]},\n" for t in tables) + ")\n\nrouter = APIRouter(prefix=\"/ref\")\n"
init += "".join(f"router.include_router({t[0]}.router)\n" for t in tables)
write(f"{R}/ref/__init__.py", init)
os.remove(f"{R}/ref.py")
write(f"{R}/__init__.py", "from fastapi import APIRouter\n\nfrom .ref import router as ref_router\n\nrouter = APIRouter()\nrouter.include_router(ref_router)\n")
