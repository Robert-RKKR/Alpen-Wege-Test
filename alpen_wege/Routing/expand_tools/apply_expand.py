#!/usr/bin/env python
"""Applies the ?expand= change (plan get_expand_implementation_plan_v2.md) to a COPY of the repo.

    python apply_expand.py REPO_COPY

Stops with "STOP: ..." (and changes nothing more) when a file is not what the plan expects, for example
because someone edited it. Run it on a scratch copy and deliver with deliver.py; never on the real repo.
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
HERE = Path(__file__).resolve().parent


def stop(message: str):
    raise SystemExit(f"STOP: {message}")


def read(rel: str) -> str:
    path = ROOT / rel
    if not path.exists():
        stop(f"{rel} does not exist")
    return path.read_text(encoding="utf-8")


def write(rel: str, text: str):
    with open(ROOT / rel, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def sub_once(rel: str, old: str, new: str):
    text = read(rel)
    found = text.count(old)
    if found != 1:
        stop(f"{rel}: expected exactly one of\n{old!r}\nfound {found}")
    write(rel, text.replace(old, new))


def append(rel: str, block: str):
    text = read(rel)
    write(rel, text.rstrip("\n") + "\n" + block)


EXPAND_IMPORT = "from app.core.utils.expand import ExpandPlan, expand_plan\n"
LINK_IMPORT = "from app.core.utils.expand import Link\n"
USER_IMPORT = "from app.profile.schemas.user_read import ExpandedUser\n"


# --------------------------------------------------------------------------- helper and alias

def step_helper():
    target = ROOT / "app/core/utils/expand.py"
    if target.exists():
        stop("app/core/utils/expand.py already exists")
    write("app/core/utils/expand.py", (HERE / "expand.py").read_text(encoding="utf-8"))
    append("app/profile/schemas/user_read.py", '''

# The user object that expanded responses return for created_by, changed_by, updated_by and user. One alias, so the
# rule "who sees which user fields" can be changed in one place.
ExpandedUser = UserRead
''')


# --------------------------------------------------------------------------- models (read-only links)

def step_models():
    sub_once("app/core/base.py",
             "    declared_attr,\n    mapped_column,\n)\n",
             "    declared_attr,\n    mapped_column,\n    relationship,\n)\n")
    sub_once("app/core/base.py",
             '''                "References profile_usr_user.id and is required (NOT NULL)."
            ),
        )
''',
             '''                "References profile_usr_user.id and is required (NOT NULL)."
            ),
        )

    @declared_attr
    def created_by_user(cls):
        # Read-only link to the creating user, loaded only when a GET asks for ?expand=created_by.
        # lazy="raise" blocks accidental loads; viewonly keeps it out of every save.
        return relationship(
            "ProfileUsrUser",
            foreign_keys=f"{cls.__name__}.created_by",
            lazy="raise",
            viewonly=True,
        )
''')

    sub_once("app/profile/models/user.py",
             '''    credentials = relationship(
        "ProfileUserCredentials",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )
''',
             '''    credentials = relationship(
        "ProfileUserCredentials",
        back_populates="user",
        uselist=False,
        lazy="selectin",
    )

    @property
    def user_group(self) -> str | None:
        # Lets an expanded user show its group like GET /profile/users/me does. The group is stored on the
        # credentials row, which is loaded together with the user (lazy="selectin").
        return self.credentials.user_group if self.credentials else None
''')

    sub_once("app/management/models/event_log.py",
             '    entity_type = relationship("MgmtRefEntityType", lazy="joined")\n',
             '    entity_type = relationship("MgmtRefEntityType", lazy="joined")\n'
             '    changed_by_user = relationship("ProfileUsrUser", foreign_keys=[changed_by], lazy="raise", viewonly=True)\n')

    sub_once("app/management/models/job.py",
             "from sqlalchemy.orm import Mapped, mapped_column\n",
             "from sqlalchemy.orm import Mapped, mapped_column, relationship\n")
    sub_once("app/management/models/job.py",
             '''        comment="When the job reached a terminal state.",
    )
''',
             '''        comment="When the job reached a terminal state.",
    )

    user = relationship("ProfileUsrUser", foreign_keys=[user_id], lazy="raise", viewonly=True)
''')

    sub_once("app/management/models/settings.py",
             "from sqlalchemy.orm import Mapped, mapped_column\n",
             "from sqlalchemy.orm import Mapped, mapped_column, relationship\n")
    sub_once("app/management/models/settings.py",
             '''        comment="User who last changed the value through the API, NULL if never changed.",
    )
''',
             '''        comment="User who last changed the value through the API, NULL if never changed.",
    )

    updated_by_user = relationship("ProfileUsrUser", foreign_keys=[updated_by], lazy="raise", viewonly=True)
''')

    sub_once("app/explorer/models/models_agg/gear.py",
             "from sqlalchemy.orm import Mapped, mapped_column\n",
             "from sqlalchemy.orm import Mapped, mapped_column, relationship\n")
    sub_once("app/explorer/models/models_agg/gear.py",
             '''            "FK to asset_agg_photo. Primary photo of this gear item shown in "
            "listings and detail views."
        ),
    )
''',
             '''            "FK to asset_agg_photo. Primary photo of this gear item shown in "
            "listings and detail views."
        ),
    )

    company = relationship("CoreRefCompany", foreign_keys=[company_id], lazy="raise", viewonly=True)
    gear_type = relationship("CoreRefGearType", foreign_keys=[gear_type_id], lazy="raise", viewonly=True)
''')

    sub_once("app/explorer/models/models_agg/track.py",
             "from sqlalchemy.orm import Mapped, mapped_column\n",
             "from sqlalchemy.orm import Mapped, mapped_column, relationship\n")
    sub_once("app/explorer/models/models_agg/track.py",
             '''        comment="FK to asset_agg_gpx. The uploaded GPX file for this track.",
    )
''',
             '''        comment="FK to asset_agg_gpx. The uploaded GPX file for this track.",
    )

    sport_type = relationship("CoreRefSportType", foreign_keys=[sport_type_id], lazy="raise", viewonly=True)
    difficulty_level = relationship("CoreRefDifficultyLevel", foreign_keys=[difficulty_level_id], lazy="raise", viewonly=True)
    difficulty_sport = relationship("CoreRefDifficultySport", foreign_keys=[difficulty_sport_id], lazy="raise", viewonly=True)
    start_poi = relationship("CompendiumCatPoi", foreign_keys=[start_poi_id], lazy="raise", viewonly=True)
    end_poi = relationship("CompendiumCatPoi", foreign_keys=[end_poi_id], lazy="raise", viewonly=True)
''')

    sub_once("app/core/models/models_ref/core_ref_difficulty_sport.py",
             "from sqlalchemy.orm import Mapped, mapped_column\n",
             "from sqlalchemy.orm import Mapped, mapped_column, relationship\n")
    sub_once("app/core/models/models_ref/core_ref_difficulty_sport.py",
             '''            "when the grade applies across multiple sports."
        ),
    )
''',
             '''            "when the grade applies across multiple sports."
        ),
    )

    sport_type = relationship("CoreRefSportType", foreign_keys=[sport_type_id], lazy="raise", viewonly=True)
''')


# --------------------------------------------------------------------------- schemas (*Detail)

def step_schemas():
    # core/schemas/ref.py
    sub_once("app/core/schemas/ref.py",
             "from pydantic import BaseModel, ConfigDict\n",
             "from pydantic import BaseModel, ConfigDict\n\n" + LINK_IMPORT + USER_IMPORT)
    append("app/core/schemas/ref.py", '''

# --- Detail schemas: single GET with ?expand= (a link is only an ID unless the caller asks for it) ---

class RefBaseDetail(RefBaseRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class RefWithFactorDetail(RefWithFactorRead):
    created_by_user: ExpandedUser | None = Link("created_by")


class DifficultySportDetail(DifficultySportRead):
    sport_type: RefWithFactorDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")


class CompendiumTypeDetail(CompendiumTypeRead):
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    # compendium
    sub_once("app/compendium/schemas/country.py",
             "from app.core.schemas.geo import GeoPoint, GeoPointField\n",
             "from app.core.schemas.geo import GeoPoint, GeoPointField\n" + LINK_IMPORT + USER_IMPORT)
    append("app/compendium/schemas/country.py", '''

class CountryDetail(CountryRead):
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    sub_once("app/compendium/schemas/region.py",
             "from app.core.schemas.ref import RefWithFactorRead\n"
             "from app.compendium.schemas.country import CountrySlimRead\n",
             "from app.core.schemas.ref import RefWithFactorDetail, RefWithFactorRead\n"
             + LINK_IMPORT + USER_IMPORT +
             "from app.compendium.schemas.country import CountryDetail, CountrySlimRead\n")
    append("app/compendium/schemas/region.py", '''

class RegionDetail(RegionRead):
    country: CountryDetail | None = Link()
    region_type: RefWithFactorDetail | None = Link()
    parent: "RegionDetail | None" = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    sub_once("app/compendium/schemas/poi.py",
             "from app.core.schemas.ref import RefWithFactorRead\n"
             "from app.compendium.schemas.region import RegionSlimRead\n",
             "from app.core.schemas.ref import CompendiumTypeDetail, RefWithFactorRead\n"
             + LINK_IMPORT + USER_IMPORT +
             "from app.compendium.schemas.region import RegionDetail, RegionSlimRead\n")
    append("app/compendium/schemas/poi.py", '''

class PoiDetail(PoiRead):
    compendium_type: CompendiumTypeDetail | None = Link()
    main_region: RegionDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    sub_once("app/compendium/schemas/card.py",
             "from app.core.schemas.ref import RefWithFactorRead\n"
             "from app.compendium.schemas.poi import PoiSlimRead\n",
             "from app.core.schemas.ref import CompendiumTypeDetail, RefWithFactorDetail, RefWithFactorRead\n"
             + LINK_IMPORT + USER_IMPORT +
             "from app.compendium.schemas.poi import PoiDetail, PoiSlimRead\n")
    append("app/compendium/schemas/card.py", '''

class CardDetail(CardRead):
    rarity: RefWithFactorDetail | None = Link()
    compendium_type: CompendiumTypeDetail | None = Link()
    poi: PoiDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    sub_once("app/compendium/schemas/post.py",
             "from app.core.schemas.ref import RefWithFactorRead\n",
             "from app.core.schemas.ref import RefWithFactorDetail, RefWithFactorRead\n" + LINK_IMPORT + USER_IMPORT)
    append("app/compendium/schemas/post.py", '''

class PostDetail(PostRead):
    post_type: RefWithFactorDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    sub_once("app/compendium/schemas/poi_region.py",
             "from app.compendium.schemas.poi import PoiSlimRead\n"
             "from app.compendium.schemas.region import RegionSlimRead\n",
             LINK_IMPORT + USER_IMPORT +
             "from app.compendium.schemas.poi import PoiDetail, PoiSlimRead\n"
             "from app.compendium.schemas.region import RegionDetail, RegionSlimRead\n")
    append("app/compendium/schemas/poi_region.py", '''

class PoiRegionDetail(PoiRegionRead):
    poi: PoiDetail | None = Link()
    region: RegionDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    # explorer
    sub_once("app/explorer/schemas/gear.py",
             "from pydantic import BaseModel\n",
             "from pydantic import BaseModel\n\n" + LINK_IMPORT + USER_IMPORT +
             "from app.core.schemas.ref import RefBaseDetail\n")
    append("app/explorer/schemas/gear.py", '''

class GearDetail(GearRead):
    company: RefBaseDetail | None = Link()
    gear_type: RefBaseDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")
''')

    sub_once("app/explorer/schemas/track.py",
             "from pydantic import BaseModel, ConfigDict, field_validator\n",
             "from pydantic import BaseModel, ConfigDict, field_validator\n\n"
             "from app.core.schemas.ref import DifficultySportDetail, RefWithFactorDetail\n"
             + LINK_IMPORT + USER_IMPORT +
             "from app.compendium.schemas.poi import PoiDetail\n")
    sub_once("app/explorer/schemas/track.py",
             "class TrackUpdate(BaseModel):\n",
             '''class TrackDetail(TrackRead):
    sport_type: RefWithFactorDetail | None = Link()
    difficulty_level: RefWithFactorDetail | None = Link()
    difficulty_sport: DifficultySportDetail | None = Link()
    start_poi: PoiDetail | None = Link()
    end_poi: PoiDetail | None = Link()
    created_by_user: ExpandedUser | None = Link("created_by")


class TrackUpdate(BaseModel):
''')

    # management
    sub_once("app/management/schemas/event_log.py",
             "from pydantic import BaseModel, Field\n",
             "from pydantic import BaseModel, Field\n\n" + LINK_IMPORT + USER_IMPORT)
    sub_once("app/management/schemas/event_log.py",
             '''class CompareEntryRef(BaseModel):
    id: UUID
    seq: int
    action: str
    changed_by: UUID
    changed_at: datetime
    request_id: str | None
''',
             '''class EventLogDetail(EventLogRead):
    entity_type: EntityTypeRead | None = Link()
    changed_by_user: ExpandedUser | None = Link("changed_by")


class CompareEntryRef(BaseModel):
    id: UUID
    seq: int
    action: str
    changed_by: UUID
    changed_at: datetime
    request_id: str | None
    changed_by_user: ExpandedUser | None = None
''')
    sub_once("app/management/schemas/event_log.py",
             "class EventLogCompare(BaseModel):\n    entity_type: EntityTypeRead\n",
             "class EventLogCompare(BaseModel):\n    entity_type: EntityTypeRead | None = None\n")

    sub_once("app/management/schemas/job.py",
             "from pydantic import BaseModel, ConfigDict, model_validator\n",
             "from pydantic import BaseModel, ConfigDict, model_validator\n\n" + LINK_IMPORT + USER_IMPORT)
    sub_once("app/management/schemas/job.py",
             "class JobAccepted(BaseModel):\n",
             '''class JobAdminDetail(JobAdminRead):
    user: ExpandedUser | None = Link()


class JobAccepted(BaseModel):
''')

    sub_once("app/management/schemas/settings.py",
             "from pydantic import BaseModel, ConfigDict\n",
             "from pydantic import BaseModel, ConfigDict\n\n" + LINK_IMPORT + USER_IMPORT)
    sub_once("app/management/schemas/settings.py",
             "class SettingUpdate(BaseModel):\n",
             '''class SettingDetail(SettingRead):
    updated_by_user: ExpandedUser | None = Link("updated_by")


class SettingUpdate(BaseModel):
''')

    # profile
    sub_once("app/profile/schemas/access_policy.py",
             "from pydantic import BaseModel, ConfigDict\n",
             "from pydantic import BaseModel, ConfigDict\n\n" + LINK_IMPORT + USER_IMPORT)
    sub_once("app/profile/schemas/access_policy.py",
             "\n\n# --- Access Policy ---\n",
             '''

class ResourceTypeDetail(ResourceTypeRead):
    created_by_user: ExpandedUser | None = Link("created_by")


# --- Access Policy ---
''')
    sub_once("app/profile/schemas/access_policy.py",
             "class AccessPolicyReadWithKey(AccessPolicyRead):\n",
             '''class AccessPolicyDetail(AccessPolicyRead):
    resource_type: ResourceTypeDetail | None = Link()


class AccessPolicyReadWithKey(AccessPolicyRead):
''')


# --------------------------------------------------------------------------- routes (single GET only)

def _insert_plan(rel: str, detail: str, after_line: str):
    # puts "plan: ExpandPlan = Depends(expand_plan(<detail>))," directly after the auth parameter line
    sub_once(rel, after_line, after_line + f"    plan: ExpandPlan = Depends(expand_plan({detail})),\n")


def _schema_import(rel: str, read_name: str, detail: str):
    text = read(rel)
    pattern = re.compile(rf"^(from app\.\S+ import .*\b){read_name}(\b.*)$", re.M)
    matches = pattern.findall(text)
    if len(matches) != 1:
        stop(f"{rel}: schema import of {read_name} not found exactly once")
    write(rel, pattern.sub(rf"\g<1>{detail}\g<2>", text))


def patch_eager_route(rel: str, model: str, read: str, detail: str, auth_line: str):
    # routes whose single GET already selects with EAGER: poi, card, region, post, poi_region
    sub_once(rel, "from app.core.utils.responses import ApiResponse, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, ok\n")
    _schema_import(rel, read, detail)
    sub_once(rel, "from ._shared import EAGER\n", "")
    sub_once(rel, f"response_model=ApiResponse[{read}])", f"response_model=ApiResponse[{detail}])")
    _insert_plan(rel, detail, auth_line)
    sub_once(rel, "        .options(*EAGER)\n", f"        .options(*plan.load_options({model}))\n")
    sub_once(rel, "    return ok(obj)\n", "    return ok(plan.render(obj))\n")


def patch_get_route(rel: str, model: str, read: str, detail: str, auth_line: str, id_name: str,
                    var: str = "obj"):
    # routes that read with db.get(...): country, gear, the reference tables
    sub_once(rel, "from fastapi import Depends\nfrom sqlalchemy.ext.asyncio import AsyncSession\n",
             "from fastapi import Depends\nfrom sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, ok\n")
    _schema_import(rel, read, detail)
    sub_once(rel, f"response_model=ApiResponse[{read}])", f"response_model=ApiResponse[{detail}])")
    _insert_plan(rel, detail, auth_line)
    sub_once(rel, f"    {var} = await db.get({model}, {id_name})\n",
             f"    stmt = (\n        select({model})\n        .where({model}.id == {id_name})\n"
             f"        .options(*plan.load_options({model}))\n    )\n"
             f"    {var} = (await db.execute(stmt)).scalar_one_or_none()\n")
    sub_once(rel, f"    return ok({var})\n", f"    return ok(plan.render({var}))\n")


REF_TABLES = {
    # folder: (model, slug as used in the not-found text) ; the schema is read from the file
    "company": "CoreRefCompany", "gear_type": "CoreRefGearType",
    "achievement_category": "CoreRefAchievementCategory", "achievement_scope": "CoreRefAchievementScope",
    "achievement_type": "CoreRefAchievementType", "difficulty_level": "CoreRefDifficultyLevel",
    "point_reason": "CoreRefPointReason", "post_type": "CoreRefPostType", "rarity": "CoreRefRarity",
    "region_type": "CoreRefRegionType", "schedule_status": "CoreRefScheduleStatus",
    "snow_condition": "CoreRefSnowCondition", "sport_type": "CoreRefSportType",
    "trail_condition": "CoreRefTrailCondition", "visibility": "CoreRefVisibility",
    "waypoint_type": "CoreRefWaypointType", "weather_condition": "CoreRefWeatherCondition",
    "compendium_type": "CoreRefCompendiumType", "difficulty_sport": "CoreRefDifficultySport",
}
REF_DETAIL = {"RefBaseRead": "RefBaseDetail", "RefWithFactorRead": "RefWithFactorDetail",
              "DifficultySportRead": "DifficultySportDetail", "CompendiumTypeRead": "CompendiumTypeDetail"}


def step_routes():
    auth = lambda key, action="read": f'    access: AccessContext = Depends(resource_access("{key}", "{action}")),\n'

    patch_eager_route("app/compendium/routes/poi/get_one.py", "CompendiumCatPoi", "PoiRead", "PoiDetail", auth("poi"))
    patch_eager_route("app/compendium/routes/card/get_one.py", "CompendiumCatCard", "CardRead", "CardDetail", auth("card"))
    patch_eager_route("app/compendium/routes/region/get_one.py", "CompendiumCatRegion", "RegionRead", "RegionDetail", auth("region"))
    patch_eager_route("app/compendium/routes/post/get_one.py", "CompendiumCatPost", "PostRead", "PostDetail", auth("post"))
    patch_eager_route("app/compendium/routes/m2m/poi_region/get_one.py", "CompendiumM2mPoiRegion", "PoiRegionRead",
                      "PoiRegionDetail", auth("poi_region"))
    patch_get_route("app/compendium/routes/country/get_one.py", "CompendiumCatCountry", "CountryRead", "CountryDetail",
                    auth("country"), "country_id")
    patch_get_route("app/explorer/routes/gear/get_one.py", "ExplorerAggGear", "GearRead", "GearDetail",
                    auth("gear"), "gear_id", var="gear")

    for folder, model in REF_TABLES.items():
        rel = f"app/core/routes/ref/{folder}/get_one.py"
        text = read(rel)
        found = [name for name in REF_DETAIL if f"ApiResponse[{name}]" in text]
        if len(found) != 1:
            stop(f"{rel}: could not tell the schema ({found})")
        patch_get_route(rel, model, found[0], REF_DETAIL[found[0]], auth("ref"), "item_id")

    # resource type (administrator only, own schema file)
    rel = "app/core/routes/ref/resource_type/get_one.py"
    sub_once(rel, "from fastapi import Depends, status\nfrom sqlalchemy.ext.asyncio import AsyncSession\n",
             "from fastapi import Depends, status\nfrom sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, AppError, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, AppError, ok\n")
    sub_once(rel, "    ResourceTypeRead,\n", "    ResourceTypeDetail,\n")
    sub_once(rel, "ApiResponse[ResourceTypeRead]", "ApiResponse[ResourceTypeDetail]")
    _insert_plan(rel, "ResourceTypeDetail", '    _admin: ProfileUsrUser = Depends(require_groups("administrator")),\n')
    sub_once(rel, "    obj = await db.get(CoreRefResourceType, item_id)\n",
             "    stmt = (\n        select(CoreRefResourceType)\n        .where(CoreRefResourceType.id == item_id)\n"
             "        .options(*plan.load_options(CoreRefResourceType))\n    )\n"
             "    obj = (await db.execute(stmt)).scalar_one_or_none()\n")
    sub_once(rel, "    return ok(obj)\n", "    return ok(plan.render(obj))\n")

    # access policy
    rel = "app/profile/routes/access_policy/get_one.py"
    sub_once(rel, "from fastapi import Depends, status\nfrom sqlalchemy.ext.asyncio import AsyncSession\n",
             "from fastapi import Depends, status\nfrom sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, AppError, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, AppError, ok\n")
    sub_once(rel, "    AccessPolicyRead,\n", "    AccessPolicyDetail,\n")
    sub_once(rel, "ApiResponse[AccessPolicyRead]", "ApiResponse[AccessPolicyDetail]")
    _insert_plan(rel, "AccessPolicyDetail", '    _admin: ProfileUsrUser = Depends(require_groups("administrator")),\n')
    sub_once(rel, "    obj = await db.get(ProfileAccessPolicy, item_id)\n",
             "    stmt = (\n        select(ProfileAccessPolicy)\n        .where(ProfileAccessPolicy.id == item_id)\n"
             "        .options(*plan.load_options(ProfileAccessPolicy))\n    )\n"
             "    obj = (await db.execute(stmt)).scalar_one_or_none()\n")
    sub_once(rel, "    return ok(obj)\n", "    return ok(plan.render(obj))\n")

    # track
    rel = "app/explorer/routes/track/get_one.py"
    sub_once(rel, "from fastapi import Depends\nfrom sqlalchemy.ext.asyncio import AsyncSession\n",
             "from fastapi import Depends\nfrom sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, ok\n")
    sub_once(rel, "from app.explorer.schemas.track import (\n    TrackRead,\n)\n",
             "from app.explorer.schemas.track import (\n    TrackDetail,\n)\n")
    sub_once(rel, "ApiResponse[TrackRead]", "ApiResponse[TrackDetail]")
    _insert_plan(rel, "TrackDetail", auth("track"))
    sub_once(rel, "    track = await db.get(ExplorerAggTrack, track_id)\n",
             "    stmt = (\n        select(ExplorerAggTrack)\n        .where(ExplorerAggTrack.id == track_id)\n"
             "        .options(*plan.load_options(ExplorerAggTrack))\n    )\n"
             "    track = (await db.execute(stmt)).scalar_one_or_none()\n")
    text = read(rel)
    block = re.compile(r"    result = TrackRead\(\n.*?\n    \)\n    return ok\(result\)\n", re.S)
    if len(block.findall(text)) != 1:
        stop(f"{rel}: the hand-built TrackRead block was not found exactly once")
    write(rel, block.sub("    return ok(plan.render(track, metrics=build_metrics(geo_rec, geo_perf)))\n", text))

    # event log
    rel = "app/management/routes/event_log/get_one.py"
    sub_once(rel, "from sqlalchemy.orm import joinedload\n", "")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, AppError, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, AppError, ok\n")
    sub_once(rel, "    EventLogRead,\n", "    EventLogDetail,\n")
    sub_once(rel, "ApiResponse[EventLogRead]", "ApiResponse[EventLogDetail]")
    _insert_plan(rel, "EventLogDetail", '    _user: ProfileUsrUser = Depends(require_groups("administrator")),\n')
    sub_once(rel, "        .options(joinedload(MgmtLogEvent.entity_type))\n",
             "        .options(*plan.load_options(MgmtLogEvent))\n")
    sub_once(rel, "    return ok(entry)\n", "    return ok(plan.render(entry))\n")

    rel = "app/management/routes/event_log/compare.py"
    sub_once(rel, "from sqlalchemy.orm import joinedload\n", "")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, AppError, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, AppError, ok\n")
    sub_once(rel, "    EventLogCompare,\n)\n", "    EventLogCompare,\n    EventLogDetail,\n)\n")
    _insert_plan(rel, "EventLogDetail", '    _user: ProfileUsrUser = Depends(require_groups("administrator")),\n')
    sub_once(rel, "        .options(joinedload(MgmtLogEvent.entity_type))\n",
             "        .options(*plan.load_options(MgmtLogEvent))\n")
    sub_once(rel, '''    def ref(e):
        return {
            "id": e.id, "seq": e.seq, "action": e.action,
            "changed_by": e.changed_by, "changed_at": e.changed_at,
            "request_id": e.request_id,
        }

    et = older.entity_type
    return ok({
        "entity_type": {
            "id": et.id, "key": et.key, "display_name": et.display_name,
            "module": et.module, "tracking_mode": et.tracking_mode,
            "ignore_fields": et.ignore_fields,
        },
        "entity_id": older.entity_id,
        "older": ref(older),
        "newer": ref(newer),
''', '''    older_d, newer_d = plan.render(older), plan.render(newer)

    def ref(d):
        return {
            "id": d["id"], "seq": d["seq"], "action": d["action"],
            "changed_by": d["changed_by"], "changed_at": d["changed_at"],
            "request_id": d["request_id"], "changed_by_user": d["changed_by_user"],
        }

    return ok({
        "entity_type": older_d["entity_type"],
        "entity_id": older.entity_id,
        "older": ref(older_d),
        "newer": ref(newer_d),
''')

    # jobs (administrator view)
    rel = "app/management/routes/jobs/get_one.py"
    sub_once(rel, "from fastapi import Depends\nfrom sqlalchemy.ext.asyncio import AsyncSession\n",
             "from fastapi import Depends\nfrom sqlalchemy import select\nfrom sqlalchemy.ext.asyncio import AsyncSession\n")
    sub_once(rel, "from app.core.utils.responses import ApiResponse, AppError, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, AppError, ok\n")
    sub_once(rel, "from app.management.schemas.job import JobAdminRead\n", "from app.management.schemas.job import JobAdminDetail\n")
    sub_once(rel, "ApiResponse[JobAdminRead]", "ApiResponse[JobAdminDetail]")
    _insert_plan(rel, "JobAdminDetail", "    _admin: ProfileUsrUser = Depends(admin_only),\n")
    sub_once(rel, "    job = await db.get(T, job_id)\n",
             "    stmt = select(T).where(T.id == job_id).options(*plan.load_options(T))\n"
             "    job = (await db.execute(stmt)).scalar_one_or_none()\n")
    sub_once(rel, "    return ok(job)\n",
             "    # JobRead builds \"subject\" from subject_type and subject_id\n"
             "    return ok(plan.render(job, subject=None, subject_type=job.subject_type, subject_id=job.subject_id))\n")

    # settings
    rel = "app/management/routes/settings/_shared.py"
    sub_once(rel, "async def get_row(db: AsyncSession, key: str) -> MgmtSettings:\n",
             "async def get_row(db: AsyncSession, key: str, options=()) -> MgmtSettings:\n")
    sub_once(rel, "    row = (await db.execute(select(MgmtSettings).where(MgmtSettings.key == key))).scalar_one_or_none()\n",
             "    stmt = select(MgmtSettings).where(MgmtSettings.key == key).options(*options)\n"
             "    row = (await db.execute(stmt)).scalar_one_or_none()\n")
    rel = "app/management/routes/settings/get_one.py"
    sub_once(rel, "from app.core.utils.responses import ApiResponse, ok\n",
             EXPAND_IMPORT + "from app.core.utils.responses import ApiResponse, ok\n"
             "from app.management.models.settings import MgmtSettings\n")
    sub_once(rel, "from app.management.schemas.settings import SettingRead\n", "from app.management.schemas.settings import SettingDetail\n")
    sub_once(rel, "ApiResponse[SettingRead]", "ApiResponse[SettingDetail]")
    _insert_plan(rel, "SettingDetail", "    _user: ProfileUsrUser = Depends(admin_only),\n")
    sub_once(rel, "    return ok(await get_row(db, key))\n",
             "    row = await get_row(db, key, plan.load_options(MgmtSettings))\n    return ok(plan.render(row))\n")


# --------------------------------------------------------------------------- tools and tests

def step_tools():
    rel = "scripts/route_map.py"
    sub_once(rel, "    python scripts/route_map.py compare BEFORE.json AFTER.json [--rules RULES.json [--step N]]\n",
             "    python scripts/route_map.py compare BEFORE.json AFTER.json [--rules RULES.json [--step N]] [--expand]\n")
    sub_once(rel, "`probe` sends every HTTP route of the app",
             "With --expand a GET route that gained exactly one new query parameter `expand` may differ in four ways, and only\n"
             "these: the parameter list (the new parameter), the permissions (the expand_plan dependency is ignored; the login and\n"
             "permission dependencies must be the same), the 200 response (`...Read_` becomes `...Detail_`) and the classes the\n"
             "function uses (a `...Read` schema may disappear). Every other route must still be identical; the number of routes\n"
             "that gained the parameter is printed. Use it after the ?expand= change (get_expand_implementation_plan_v2.md).\n\n"
             "`probe` sends every HTTP route of the app")
    sub_once(rel, '''    "parameters", "request_body", "responses", "security", "permissions", "uses",
)
''', '''    "parameters", "request_body", "responses", "security", "permissions", "uses",
)
# compare --expand: a GET route that gained the query parameter ?expand= may differ in these fields
EXPAND_FIELDS = ("parameters", "responses", "permissions", "uses")
''')
    sub_once(rel, '''def compare(before: dict, after: dict, rules: list[dict] | None, step: int | None = None) -> list[str]:
    errors: list[str] = []
''', '''def _gained_expand(old_params: list, new_params: list) -> bool:
    # the new parameter list is the old one plus exactly one query parameter named expand
    extra = [p for p in new_params if p not in old_params]
    return len(extra) == 1 and str(extra[0]).startswith("query:expand:") and [p for p in new_params if p in old_params] == old_params


def _read_to_detail(responses: dict) -> dict:
    # the 200 answer of a route that gained ?expand= names the ...Detail schema instead of the ...Read schema
    return {code: ({ct: text.replace('Read_"}', 'Detail_"}') for ct, text in content.items()} if code == "200" else content)
            for code, content in responses.items()}


def _expand_change_ok(field: str, want, have) -> bool:
    # what a route that gained ?expand= may change, field by field
    if field == "parameters":
        return True   # _gained_expand already checked it
    if field == "permissions":
        return [p for p in have if "expand_plan" not in p] == want
    if field == "responses":
        return have == want or have == _read_to_detail(want)
    if field == "uses":
        return all(name.endswith("Read") for name in set(want) - set(have))   # classes may be added, a ...Read schema may go
    return False


def compare(before: dict, after: dict, rules: list[dict] | None, step: int | None = None, expand: bool = False) -> list[str]:
    errors: list[str] = []
    gained_expand = 0
''')
    sub_once(rel, '''        for field in COMPARED_FIELDS:
            want = record.get(field)
''', '''        gained = expand and new_key.startswith("GET ") and _gained_expand(record.get("parameters", []), got.get("parameters", []))
        gained_expand += 1 if gained else 0
        for field in COMPARED_FIELDS:
            want = record.get(field)
            if gained and field in EXPAND_FIELDS and _expand_change_ok(field, want, got.get(field)):
                continue
''')
    sub_once(rel, "def probe_routes(routes: dict) -> list[str]:\n",
             "def probe_routes(routes: dict, query: str = \"\") -> list[str]:\n")
    sub_once(rel, '"query_string": b"",', '"query_string": query.encode(),')
    sub_once(rel, '''            errors.append(f"DIFF      app.{field}\\n            before: {before[field]}\\n            after:  {after.get(field)}")
    return errors
''', '''            errors.append(f"DIFF      app.{field}\\n            before: {before[field]}\\n            after:  {after.get(field)}")
    if expand:
        errors.append(f"NOTE      {gained_expand} route(s) gained the query parameter expand")
    return errors
''')
    sub_once(rel, '    p_cmp.add_argument("--step", type=int, default=None)\n',
             '    p_cmp.add_argument("--step", type=int, default=None)\n'
             '    p_cmp.add_argument("--expand", action="store_true", help="allow the changes of the ?expand= option (see the module doc)")\n')
    sub_once(rel, "    errors = compare(before, after, rules, args.step)\n",
             "    errors = compare(before, after, rules, args.step, args.expand)\n")
    sub_once(rel, "if rules else 'identical'}\")",
             "if rules else 'identical' + (' except the routes that gained ?expand=' if args.expand else '')}\")")


def step_tests():
    for name in ("test_expand.py", "test_expand_wiring.py", "test_expand_routes.py"):
        if (ROOT / "tests" / name).exists():
            stop(f"tests/{name} already exists")
        write(f"tests/{name}", (HERE / name).read_text(encoding="utf-8"))
    if (ROOT / "scripts/expand_check.py").exists():
        stop("scripts/expand_check.py already exists")
    write("scripts/expand_check.py", (HERE / "expand_check.py").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- README

README_WHO_SEES_A = (
    "| Who sees what | Whoever may read an object may see what is expanded inside it, including the whole profile "
    "(email, birth date, heart rates) of the user behind `created_by`, `changed_by`, `updated_by` or `user` |\n"
)


def step_readme():
    rel = "README.md"
    sub_once(rel, "Shared geographic / editorial catalog. GET endpoints return nested objects one level deep "
                  "(FK IDs are accepted on create/update; full sub-objects come back on read).\n",
             "Shared geographic / editorial catalog. List endpoints return their nested objects one level deep. "
             "A single-object GET returns linked objects as IDs only; ask for the full objects with `?expand=` "
             "(see \"Expanding linked objects\" below). FK IDs are accepted on create/update.\n")
    sub_once(rel, "The GET response returns the full nested objects:\n",
             "`GET /api/v1/compendium/regions/{id}?expand=country,region_type` returns the nested objects:\n")
    sub_once(rel, '''  "parent_id": null,
  "parent": null,
  "..."
}
```

---
''', '''  "parent_id": null,
  "parent": null,
  "..."
}
```

### Expanding linked objects (`?expand=`)

A single-object GET (for example `/compendium/pois/{id}`, `/explorer/tracks/{id}`, `/core/rarities/{id}`,
`/management/event-log/{id}`) returns every linked object as its ID only. Add `expand` with a comma-separated list of
links to get the full object instead. The allowed names are in the description of the `expand` parameter of each
endpoint in Swagger.

```bash
curl "http://localhost:8000/api/v1/compendium/pois/<id>?expand=main_region.country,compendium_type" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/explorer/tracks/<id>?expand=sport_type,start_poi,created_by" -H "Authorization: Bearer $TOKEN"
curl "http://localhost:8000/api/v1/management/event-log/<id>?expand=changed_by,entity_type" -H "Authorization: Bearer $TOKEN"
```

| Rule | Detail |
|------|--------|
| Names | A link is asked for by name (`main_region`, `poi`, ...). `created_by`, `changed_by` and `updated_by` fill `created_by_user`, `changed_by_user` and `updated_by_user`; every other name fills the field of the same name |
| Depth | Dotted paths go at most 3 levels deep (`main_region.country.created_by`); the parents of a path are included. One request may ask for at most 10 links in total |
| Not asked | A link that is not asked for stays `null` next to its ID (`"main_region_id": "...", "main_region": null`); `null` also appears when the ID itself is empty |
| Errors | An unknown name, a path deeper than 3 levels or more than 10 links answers `400`; `response_details.error_message` names the allowed links |
| Who sees what | Whoever may read an object may see what is expanded inside it, including the whole profile (email, birth date, heart rates) of the user behind `created_by`, `changed_by`, `updated_by` or `user` |
| Lists | List endpoints do not take `expand` and keep returning their nested objects |
| Repeating | Write `?expand=a,b`; if the parameter is repeated only the last value counts |

---
''')
    sub_once(rel, "- Helpers used by several resources live in `app/core/utils/` (`scope.py`, `api_paths.py`);",
             "- **Single-object GETs take `?expand=`.** Their `get_one.py` uses a `*Detail` schema (next to the `*Read` schema, "
             "with `Link()` fields) and `plan: ExpandPlan = Depends(expand_plan(XDetail))` from `app/core/utils/expand.py`; "
             "`select(...).options(*plan.load_options(Model))` loads the asked links and `ok(plan.render(obj))` builds the "
             "answer. A new GET-by-id route must be added to `tests/test_expand_routes.py` (and its schema to "
             "`tests/test_expand_wiring.py`).\n"
             "- Helpers used by several resources live in `app/core/utils/` (`scope.py`, `api_paths.py`, `expand.py`);")
    sub_once(rel, "`tests/test_routes_standard.py` and `tests/test_api_paths.py` enforce the rules above.",
             "`tests/test_routes_standard.py` and `tests/test_api_paths.py` enforce the rules above; "
             "`python scripts/route_map.py compare BEFORE AFTER --expand` accepts exactly the changes of the expand option; "
             "`scripts/expand_check.py` is the live check of `?expand=` (needs the seeded users and compendium data).")


def main():
    if ROOT is None or not (ROOT / "app").is_dir():
        stop("usage: apply_expand.py REPO_COPY (a folder that contains app/)")
    for step in (step_helper, step_models, step_schemas, step_routes, step_tools, step_tests, step_readme):
        step()
        print(f"done: {step.__name__}")


if __name__ == "__main__":
    main()
