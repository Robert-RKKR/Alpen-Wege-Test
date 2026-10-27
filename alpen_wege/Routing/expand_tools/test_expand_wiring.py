# Standard library
import importlib
from pathlib import Path
from types import SimpleNamespace

# Third-party
from pydantic import BaseModel
from sqlalchemy import inspect as sa_inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import configure_mappers

# Local application
import app.worker.model_registry  # noqa: F401  (imports every model package, like the API and the worker do)
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.models.models_cat.country import CompendiumCatCountry
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.models.models_cat.post import CompendiumCatPost
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.compendium.schemas.card import CardDetail
from app.compendium.schemas.country import CountryDetail
from app.compendium.schemas.poi import PoiDetail
from app.compendium.schemas.poi_region import PoiRegionDetail
from app.compendium.schemas.post import PostDetail
from app.compendium.schemas.region import RegionDetail
from app.core.base import Base, CreatorMixin, ReferenceBaseMixin
from app.core.models.models_ref import CoreRefCompany, CoreRefCompendiumType, CoreRefDifficultySport, CoreRefRarity
from app.core.models.resource_type import CoreRefResourceType
from app.core.schemas.ref import CompendiumTypeDetail, DifficultySportDetail, RefBaseDetail, RefWithFactorDetail
from app.core.utils.expand import ExpandPlan, links_of
from app.explorer.models.models_agg.gear import ExplorerAggGear
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.explorer.schemas.gear import GearDetail
from app.explorer.schemas.track import TrackDetail
from app.main import app
from app.management.models.entity_type import MgmtRefEntityType
from app.management.models.event_log import MgmtLogEvent
from app.management.models.job import MgmtLogJob
from app.management.models.settings import MgmtSettings
from app.management.schemas.event_log import EntityTypeRead, EventLogDetail
from app.management.schemas.job import JobAdminDetail
from app.management.schemas.settings import SettingDetail
from app.profile.models import ProfileUsrUser
from app.profile.models.access_policy import ProfileAccessPolicy
from app.profile.schemas.access_policy import AccessPolicyDetail, ResourceTypeDetail
from app.profile.schemas.user_read import ExpandedUser, UserRead

ROOT = Path(__file__).resolve().parents[1]

# Detail schema -> the model its objects come from. A new schema with Link() fields must be added here (test_every_schema_with_links_is_listed).
PAIRS = {
    EventLogDetail: MgmtLogEvent,
    EntityTypeRead: MgmtRefEntityType,
    PoiDetail: CompendiumCatPoi,
    CardDetail: CompendiumCatCard,
    RegionDetail: CompendiumCatRegion,
    CountryDetail: CompendiumCatCountry,
    PostDetail: CompendiumCatPost,
    PoiRegionDetail: CompendiumM2mPoiRegion,
    GearDetail: ExplorerAggGear,
    TrackDetail: ExplorerAggTrack,
    RefBaseDetail: CoreRefCompany,                 # one of the tables that use it
    RefWithFactorDetail: CoreRefRarity,            # one of the tables that use it
    DifficultySportDetail: CoreRefDifficultySport,
    CompendiumTypeDetail: CoreRefCompendiumType,
    ResourceTypeDetail: CoreRefResourceType,
    AccessPolicyDetail: ProfileAccessPolicy,
    SettingDetail: MgmtSettings,
    JobAdminDetail: MgmtLogJob,
    UserRead: ProfileUsrUser,
}
# Fields a route computes and passes to plan.render(...); the model has no such attribute
COMPUTED = {TrackDetail: {"metrics"}, JobAdminDetail: {"subject"}}
SECRET_WORDS = ("password", "hash", "credential", "token")


def test_all_mappers_configure():
    # The new read-only relationships (45 classes get created_by_user) must not break SQLAlchemy's setup.
    configure_mappers()


def test_every_plain_field_of_a_detail_schema_exists_on_its_model():
    # plan.render reads these with getattr; a typo or a renamed column would be a 500 on that route only.
    missing = []
    for schema, model in PAIRS.items():
        link_attrs = {info.attr for info in links_of(schema).values()}
        for name in schema.model_fields:
            if name in link_attrs or name in COMPUTED.get(schema, set()):
                continue
            if not hasattr(model, name):
                missing.append(f"{schema.__name__}.{name} (not on {model.__name__})")
    assert not missing, missing


def test_every_link_is_a_relationship_to_the_model_of_its_target_schema():
    problems = []
    for schema, model in PAIRS.items():
        relationships = sa_inspect(model).relationships
        for public, info in links_of(schema).items():
            if info.attr not in relationships:
                problems.append(f"{schema.__name__}.{info.attr}: {model.__name__} has no such relationship")
                continue
            if info.target not in PAIRS:
                problems.append(f"{schema.__name__}.{info.attr}: target schema {info.target.__name__} is not in PAIRS")
                continue
            target_model = relationships[info.attr].mapper.class_
            expected = PAIRS[info.target]
            shared_ref_schema = issubclass(target_model, ReferenceBaseMixin) and issubclass(expected, ReferenceBaseMixin)
            if target_model is not expected and not shared_ref_schema:
                problems.append(f"{schema.__name__}.{info.attr}: relationship goes to {target_model.__name__}, "
                                f"the schema expects {expected.__name__}")
    assert not problems, problems


def test_a_link_to_a_user_is_asked_for_without_the_suffix():
    # created_by_user is asked for as created_by, changed_by_user as changed_by, updated_by_user as updated_by
    wrong = []
    for schema in PAIRS:
        for public, info in links_of(schema).items():
            if info.attr.endswith("_user") and public != info.attr[: -len("_user")]:
                wrong.append(f"{schema.__name__}.{info.attr} is asked for as {public!r}")
    assert not wrong, wrong


def test_every_schema_with_links_is_listed():
    found = set()
    for path in sorted((ROOT / "app").glob("*/schemas/*.py")):
        module = importlib.import_module(f"app.{path.parent.parent.name}.schemas.{path.stem}")
        for name, value in vars(module).items():
            if isinstance(value, type) and issubclass(value, BaseModel) and value.__module__ == module.__name__ \
                    and links_of(value):
                found.add(value)
    assert not (found - set(PAIRS)), f"add to PAIRS: {sorted(c.__name__ for c in found - set(PAIRS))}"


def test_no_secret_field_is_reachable_through_links():
    seen, stack, bad = set(), list(PAIRS), []
    while stack:
        schema = stack.pop()
        if schema in seen:
            continue
        seen.add(schema)
        bad += [f"{schema.__name__}.{name}" for name in schema.model_fields if any(w in name.lower() for w in SECRET_WORDS)]
        stack += [info.target for info in links_of(schema).values()]
    assert not bad, bad


def test_every_model_with_a_creator_has_a_read_only_created_by_user():
    wrong = []
    for mapper in Base.registry.mappers:
        if issubclass(mapper.class_, CreatorMixin):
            rel = mapper.relationships.get("created_by_user")
            if rel is None or rel.lazy != "raise" or not rel.viewonly or rel.mapper.class_ is not ProfileUsrUser:
                wrong.append(mapper.class_.__name__)
    assert not wrong, wrong
    assert sum(1 for m in Base.registry.mappers if issubclass(m.class_, CreatorMixin)) >= 40


def test_expanded_user_shows_the_group_and_nothing_secret():
    assert ExpandedUser is UserRead
    getter = ProfileUsrUser.user_group.fget
    assert getter(SimpleNamespace(credentials=SimpleNamespace(user_group="editor"))) == "editor"
    assert getter(SimpleNamespace(credentials=None)) is None


def test_the_openapi_document_builds_with_the_recursive_region_schema():
    spec = app.openapi()
    assert "RegionDetail" in spec["components"]["schemas"]


def _paths(schema, depth=3, prefix=""):
    # every path that ?expand= accepts for the schema, up to the maximum depth
    for public, info in links_of(schema).items():
        yield prefix + public
        if depth > 1:
            yield from _paths(info.target, depth - 1, prefix + public + ".")


def test_every_path_up_to_three_levels_builds_its_loader_options():
    # SQLAlchemy checks the option chains when the statement is compiled: a link that does not lead where the schema
    # says fails here, with no database.
    dialect = postgresql.dialect()
    count = 0
    for schema, model in PAIRS.items():
        for path in _paths(schema):
            plan = ExpandPlan.parse(schema, path)
            str(select(model).options(*plan.load_options(model)).compile(dialect=dialect))
            count += 1
    assert count > 80
