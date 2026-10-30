"""Icons (asset_agg_icon): the table, the 22 links, the schemas, the SQL scripts, the guards. No database needed."""
# Standard library
import asyncio
import importlib.util
import json
import re
import uuid
from pathlib import Path
from types import SimpleNamespace

# Third-party
import pytest
from pydantic import BaseModel
from sqlalchemy import Text, event, inspect as sa_inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from starlette.requests import Request

# Local application
import app.assets.models  # noqa: F401  every model must be registered before the metadata is read
import app.compendium.models  # noqa: F401
import app.core.models  # noqa: F401
import app.explorer.models  # noqa: F401
import app.management.models  # noqa: F401
import app.profile.models  # noqa: F401
import app.social.models  # noqa: F401
from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.schemas.asset import IconUpdate
from app.assets.services import icon_files
from app.assets.services.icon_usage import ICON_USERS
from app.core.base import Base
from app.core.utils import csv_import
from app.core.utils.api_paths import ICON_CSV_UPLOAD_PATH, ICON_UPLOAD_PATH
from app.core.utils.integrity import is_missing_icon
from app.core.utils.responses import AppError
from app.core.utils.upload_limit import UploadSizeLimitMiddleware
from app.main import app
from app.management.utils import event_logger
from app.management.utils.seed_entity_types import IGNORE_FIELDS_MAP

ROOT = Path(__file__).resolve().parents[1]
SQL = ROOT / "scripts" / "sql"


def _tables_with_icon_id():
    return {t.name: t for t in Base.metadata.tables.values() if "icon_id" in t.c}


# ---------------------------------------------------------------- the 22 links
def test_22_tables_have_the_link_restrict_and_indexed():
    tables = _tables_with_icon_id()
    assert len(tables) == 22, sorted(tables)
    for name, t in tables.items():
        column = t.c.icon_id
        fks = list(column.foreign_keys)
        assert len(fks) == 1 and fks[0].column.table.name == "asset_agg_icon" and fks[0].column.name == "id", name
        assert fks[0].ondelete == "RESTRICT", f"{name}: a used icon must not be deletable"
        optional = name in ("compendium_cat_country", "compendium_cat_region")
        assert column.nullable == optional, f"{name}: icon_id is required on the reference tables, optional on countries and regions"
        assert any([c.name for c in ix.columns] == ["icon_id"] for ix in t.indexes), f"{name}: no index on icon_id"


def test_every_table_with_the_link_is_in_the_usage_list():
    # a reference table added later must not forget the delete check of the icon route
    with_link = set(_tables_with_icon_id())
    assert {m.__tablename__ for m in ICON_USERS.values()} == with_link, "icon_usage.ICON_USERS differs from the tables that have icon_id"
    assert len(ICON_USERS) == len({m for m in ICON_USERS.values()}) == 22


def test_the_old_icon_text_is_gone():
    assert [t.name for t in Base.metadata.tables.values() if "icon" in t.c] == []


def test_icon_model_rules():
    t = AssetAggIcon.__table__
    assert not t.c.svg.nullable and not t.c.key.nullable and not t.c.sha256.nullable and not t.c.name.nullable
    assert AssetAggIcon.__mapper__.column_attrs["svg"].deferred, "a list must not read the SVG text of every row"
    assert {c.name for c in t.constraints if c.name} >= {"uq_asset_agg_icon_key", "ck_asset_agg_icon_key", "ck_asset_agg_icon_svg", "ck_asset_agg_icon_sha256"}
    assert "is_public" not in t.c and "path" not in t.c, "decision D1: icons are read by everybody, there is no file"
    assert list(t.dispatch.after_create), "the updated_at trigger is created together with the table"


# ---------------------------------------------------------------- schemas
def _schema_classes():
    modules = ("app.core.schemas.ref", "app.profile.schemas.access_policy", "app.compendium.schemas.country", "app.compendium.schemas.region")
    for name in modules:
        module = importlib.import_module(name)
        for cls in vars(module).values():
            if isinstance(cls, type) and issubclass(cls, BaseModel) and cls.__module__ == name:
                yield cls


def test_no_schema_has_the_icon_text_and_every_ref_country_and_region_schema_has_icon_id():
    classes = list(_schema_classes())
    assert [c.__name__ for c in classes if "icon" in c.model_fields] == []
    for c in classes:
        if re.search(r"(Create|Update|Read|SlimRead|Detail)$", c.__name__) and not c.__name__.startswith("AccessPolicy"):
            assert "icon_id" in c.model_fields, c.__name__


def test_create_update_read_types_of_icon_id():
    from app.core.schemas.ref import RefBaseCreate, RefBaseRead, RefBaseUpdate
    from app.profile.schemas.access_policy import ResourceTypeCreate, ResourceTypeUpdate

    for create in (RefBaseCreate, ResourceTypeCreate):
        extra = {"key": "k"} if create is ResourceTypeCreate else {}
        with pytest.raises(Exception):
            create(color="#000000", **extra)                                                 # the icon is required
        with pytest.raises(Exception):
            create(color="#000000", icon_id=None, **extra)
        with pytest.raises(Exception):
            create(color="#000000", icon_id="not-a-uuid", **extra)
        assert create(color="#000000", icon_id=str(uuid.uuid4()), **extra).icon_id is not None
    for update in (RefBaseUpdate, ResourceTypeUpdate):
        with pytest.raises(Exception):
            update(icon_id=None)                                                             # it cannot be removed
        assert update().model_dump(exclude_unset=True) == {}                                 # not sent: unchanged
    assert RefBaseRead.model_fields["icon_id"].is_required()


def test_icon_update_lowercases_the_key_and_checks_its_shape():
    assert IconUpdate(key="  Flag_AT ").key == "flag_at"
    for bad in ("bad key", "", "x" * 101, "ümlaut"):
        with pytest.raises(Exception):
            IconUpdate(key=bad)
    assert IconUpdate().key is None and "svg" not in IconUpdate.model_fields


# ---------------------------------------------------------------- an unknown icon_id is a 422, not a 500
def _integrity(message: str) -> IntegrityError:
    return IntegrityError("INSERT ...", {}, Exception(message))


def test_is_missing_icon_matches_only_a_write_with_an_unknown_icon():
    assert is_missing_icon(_integrity('insert or update on table "core_ref_company" violates foreign key constraint "core_ref_company_icon_id_fkey"'))
    assert is_missing_icon(_integrity('insert or update on table "compendium_cat_region" violates foreign key constraint "compendium_cat_region_icon_id_fkey"'))
    # the delete side belongs to DELETE /assets/icons/{id} (409)
    assert not is_missing_icon(_integrity('update or delete on table "asset_agg_icon" violates foreign key constraint "core_ref_company_icon_id_fkey" on table "core_ref_company"'))
    # other links and other errors stay what they were
    assert not is_missing_icon(_integrity('insert or update on table "compendium_cat_poi" violates foreign key constraint "compendium_cat_poi_main_photo_id_fkey"'))
    assert not is_missing_icon(_integrity('duplicate key value violates unique constraint "core_ref_company_name_key"'))


def test_the_app_answers_an_unknown_icon_with_422_and_leaves_other_integrity_errors_alone():
    handler = app.exception_handlers[IntegrityError]
    response = asyncio.run(handler(None, _integrity('insert or update on table "core_ref_rarity" violates foreign key constraint "core_ref_rarity_icon_id_fkey"')))
    body = json.loads(response.body)
    assert response.status_code == 422 and body["response_code"] == 422
    assert body["response_details"]["error_errors"] == [{"field": "icon_id", "code": "icon_not_found", "message": "The icon does not exist."}]
    other = _integrity('duplicate key value violates unique constraint "core_ref_rarity_name_key"')
    with pytest.raises(IntegrityError) as raised:
        asyncio.run(handler(None, other))
    assert raised.value is other           # raised again: the generic 500 handler answers exactly as before


# ---------------------------------------------------------------- CSV import checks icon_id once per icon
class _Base2(DeclarativeBase):
    pass


class WithIcon(_Base2):
    __tablename__ = "with_icon"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    created_by: Mapped[uuid.UUID] = mapped_column(nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    icon_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)


class _File:
    def __init__(self, text):
        self._b = text.encode()

    async def read(self):
        return self._b


class _Db:
    def __init__(self, known):
        self.known, self.asked, self.added, self.commits = set(known), [], [], 0

    async def get(self, model, key, options=None):
        assert model is AssetAggIcon and options, "the SVG text must not be read for an existence check"
        self.asked.append(key)
        return object() if key in self.known else None

    def add_all(self, objects):
        self.added.extend(objects)

    async def commit(self):
        self.commits += 1


def _import(text, known):
    db = _Db(known)
    return asyncio.run(csv_import.import_csv(_File(text), WithIcon, uuid.uuid4(), db)), db


def test_csv_row_with_unknown_icon_is_refused_by_number_and_the_others_are_imported():
    good, bad = uuid.uuid4(), uuid.uuid4()
    result, db = _import(f"name,icon_id\nA,{good}\nB,{bad}\nC,\nD,{good}\n", {good})
    assert result["inserted"] == 3 and [o.name for o in db.added] == ["A", "C", "D"]
    assert result["errors"] == ["row 3: icon_id: the icon does not exist"]
    assert sorted(map(str, db.asked)) == sorted(map(str, [good, bad])) and db.commits == 1      # one query per distinct icon


def test_csv_without_the_icon_column_makes_no_icon_query():
    result, db = _import("name\nA\nB\n", set())
    assert result["inserted"] == 2 and db.asked == []


# ---------------------------------------------------------------- the event log does not copy the SVG
def _icon(**kw):
    return AssetAggIcon(id=uuid.uuid4(), key="flag_at", name="Flag AT", svg="<svg>" + "x" * 1000 + "</svg>", sha256="a" * 64, **kw)


def test_snapshot_skips_ignored_fields_and_the_icon_entity_ignores_svg():
    assert IGNORE_FIELDS_MAP["asset_agg_icon"] == ["svg"]
    icon = _icon()
    assert "svg" in event_logger._snapshot_fields(icon)                                        # unchanged behaviour without the setting
    snap = event_logger._snapshot_fields(icon, frozenset({"svg"}))
    assert "svg" not in snap and snap["key"] == "flag_at" and snap["sha256"] == "a" * 64


def test_created_and_deleted_entries_of_an_icon_hold_no_svg_text(monkeypatch):
    meta = event_logger._EntityMeta(entity_type_id=uuid.uuid4(), tracking_mode="all", ignore_fields=frozenset(IGNORE_FIELDS_MAP["asset_agg_icon"]))
    monkeypatch.setitem(event_logger._entity_cache, "asset_agg_icon", meta)
    added = []
    db = SimpleNamespace(add=added.append)
    icon = _icon()
    event_logger.log_created(db, icon, uuid.uuid4())
    event_logger.log_deleted(db, icon, uuid.uuid4())
    assert [e.action for e in added] == ["created", "deleted"]
    assert all("svg" not in e.snapshot and e.snapshot["key"] == "flag_at" for e in added)


# ---------------------------------------------------------------- permissions: everybody reads, only the administrator writes
def _init_seed():
    spec = importlib.util.spec_from_file_location("init_seed_for_test", ROOT / "scripts" / "init_seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_policy_matrix_for_the_icon_resource():
    seed = _init_seed()
    assert "icon" in [k for k, *_ in seed.RESOURCE_TYPES] and "icon" in seed.REF_KEYS and "icon" in seed.ALL_KEYS
    rules = {(g, a): s for g, key, a, s in seed.build_policies() if key == "icon"}
    assert {a for g, a in rules if g == "administrator"} == {"create", "read", "update", "delete"}
    assert all(s == "all" for (g, a), s in rules.items() if g == "administrator")
    for group in ("editor", "viewer", "guest"):
        assert {a: s for (g, a), s in rules.items() if g == group} == {"read": "all"}, group      # no write, and no owner/public scope
    assert {(g, a): s for g, key, a, s in seed.build_policies() if key == "ref"} == {k: v for k, v in rules.items()}   # same as the reference tables


def test_icons_policy_sql_gives_the_same_rules_as_init_seed():
    # scripts/sql/icons_policy.sql is for a database that has policies (init_seed.py would rebuild them all from scratch)
    seed = _init_seed()
    wanted = {(g, a, s) for g, key, a, s in seed.build_policies() if key == "icon"}
    sql = (SQL / "icons_policy.sql").read_text()
    pairs = re.findall(r"\('(administrator|editor|viewer|guest)', '(create|read|update|delete)'\)", sql)
    assert len(pairs) == len(set(pairs)) == 7 and {(g, a, "all") for g, a in pairs} == wanted
    assert "'icon', 'Icon', '#607D8B', 'image'" in sql and ("icon", "Icon", "#607D8B", "image") in seed.RESOURCE_TYPES   # the same resource type row


# ---------------------------------------------------------------- the routes and the upload guard
def test_the_icon_routes_exist_with_their_names():
    paths = {name: app.url_path_for(name, **kw) for name, kw in {
        "list_icons": {}, "create_icon": {}, "get_icon": {"icon_id": "1"}, "update_icon": {"icon_id": "1"},
        "delete_icon": {"icon_id": "1"}, "get_icon_file": {"icon_id": "1"}, "replace_icon_file": {"icon_id": "1"},
        "get_icon_file_by_key": {"key": "k"},
    }.items()}
    assert paths["list_icons"] == paths["create_icon"] == "/api/v1/assets/icons" == ICON_UPLOAD_PATH
    assert paths["get_icon_file_by_key"] == "/api/v1/assets/icons/by-key/k/file"


def _guard_answer(content_length):
    sent, called = [], []

    async def inner(scope, receive, send):
        called.append(True)

    async def send(message):
        sent.append(message)

    guard = UploadSizeLimitMiddleware(inner)
    asyncio.run(guard({"type": "http", "method": "POST", "path": ICON_UPLOAD_PATH, "headers": [(b"content-length", str(content_length).encode())]}, None, send))
    return guard, sent, bool(called)


def test_upload_guard_watches_icons_with_a_limit_in_kb_and_the_other_messages_are_unchanged():
    guard, _, _ = _guard_answer(1)
    max_bytes, number, unit = guard.limits[ICON_UPLOAD_PATH]
    assert (number, unit) == (300, "KB") and max_bytes == (300 + 64) * 1024
    assert [guard.limits[p][2] for p in guard.limits if p not in (ICON_UPLOAD_PATH, ICON_CSV_UPLOAD_PATH)] == ["MB", "MB", "MB"]
    assert all(isinstance(v[1], int) for v in guard.limits.values())
    assert guard.limits[ICON_CSV_UPLOAD_PATH][1:] == (5, "MB") and guard.limits[ICON_CSV_UPLOAD_PATH][0] == 6 * 1024 * 1024    # the CSV of many icons: 5 MB
    _, sent, called = _guard_answer(max_bytes + 1)
    assert sent[0]["status"] == 413 and not called and json.loads(sent[1]["body"])["message"] == "File too large (maximum 300 KB)."
    assert _guard_answer(max_bytes)[2] is True


# ---------------------------------------------------------------- serving a picture
def _request(if_none_match: str | None = None) -> Request:
    headers = [] if if_none_match is None else [(b"if-none-match", if_none_match.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 5"><rect width="10" height="5" fill="#f00"/></svg>'


def _serve(request, fmt="svg", size=64, sha="abc"):
    return asyncio.run(icon_files.icon_response(request, key="flag_at", svg=SVG, sha256=sha, fmt=fmt, size=size))


def test_the_picture_is_served_with_safe_headers_and_an_etag():
    r = _serve(_request())
    assert r.status_code == 200 and r.media_type == "image/svg+xml" and r.body.decode() == SVG
    assert r.headers["etag"] == '"abc"' and r.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in r.headers["content-security-policy"] and "default-src 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "private, max-age=3600" and r.headers["content-disposition"] == 'inline; filename="flag_at.svg"'


def test_if_none_match_gives_304_also_for_a_weak_tag_or_a_list_and_a_new_hash_gives_200():
    assert _serve(_request('"abc"')).status_code == 304
    assert _serve(_request('W/"abc"')).status_code == 304
    assert _serve(_request('"zzz", "abc"')).status_code == 304
    assert _serve(_request('"other"')).status_code == 200
    assert _serve(_request('"abc"'), sha="def").status_code == 200       # the picture changed
    assert _serve(_request('"abc"')).body == b""


def test_png_is_drawn_from_the_svg_with_its_own_etag():
    r = _serve(_request(), fmt="png", size=40)
    assert r.status_code == 200 and r.media_type == "image/png" and r.body[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(r.body[16:20], "big") == 40 and int.from_bytes(r.body[20:24], "big") == 20     # width 40, the 2:1 shape is kept
    assert r.headers["etag"] == '"abc-40"' and _serve(_request('"abc"'), fmt="png", size=40).status_code == 200
    assert _serve(_request('"abc-40"'), fmt="png", size=40).status_code == 304


def test_a_picture_that_cannot_be_drawn_answers_422_not_500():
    with pytest.raises(AppError) as raised:
        asyncio.run(icon_files.icon_response(_request(), key="k", svg="<svg", sha256="x", fmt="png", size=64))
    assert raised.value.status_code == 422


# ---------------------------------------------------------------- the SQL scripts agree with the models
def _quoted_tables(text: str) -> set[str]:
    return set(re.findall(r"'((?:core_ref|compendium_cat)_[a-z_]+)'", text))


def test_the_sql_scripts_name_the_same_22_tables_as_the_models():
    models = {m.__tablename__ for m in ICON_USERS.values()}

    def loop_tables(name):    # the tables the script loops over: the ARRAY[...] (a table can also be named in a comment text)
        return _quoted_tables(re.search(r"ARRAY\[(.*?)\]", (SQL / name).read_text(), flags=re.S).group(1))

    assert loop_tables("icons_ddl.sql") == models and loop_tables("icons_rollback.sql") == models
    assert _quoted_tables((SQL / "icons_ddl.sql").read_text()) == models
    assert _quoted_tables((SQL / "icons_rollback.sql").read_text()) == models
    link_sql = (SQL / "icons_link.sql").read_text()
    assert set(re.findall(r"UPDATE ([a-z_]+)", link_sql)) == {"compendium_cat_country", "compendium_cat_region"}
    refs = {t for t in models if t.startswith("core_ref_")}
    assert len(refs) == 20
    for name in ("icons_drop_text.sql", "icons_rollback_text.sql"):
        text = (SQL / name).read_text()
        arrays = [_quoted_tables(a) for a in re.findall(r"ARRAY\[(.*?)\]", text, flags=re.S)]
        assert arrays and all(a == refs for a in arrays), name                            # never countries or regions
    preflight = (SQL / "icons_preflight.sql").read_text()
    assert _quoted_tables(preflight) == models
    assert set(re.findall(r"SELECT icon FROM ((?:core_ref)_[a-z_]+)", preflight)) == {t for t in models if t.startswith("core_ref_")}


def test_the_ddl_creates_the_table_the_model_describes():
    ddl = (SQL / "icons_ddl.sql").read_text()
    body = ddl[ddl.index("CREATE TABLE IF NOT EXISTS asset_agg_icon"):ddl.index(");", ddl.index("CREATE TABLE IF NOT EXISTS asset_agg_icon"))]
    columns = re.findall(r"^\s{4}([a-z0-9_]+)\s+[a-z]", body, flags=re.M)
    assert set(columns) == {c.name for c in AssetAggIcon.__table__.c}, columns
    for c in AssetAggIcon.__table__.constraints:
        if c.name and c.name.startswith("ck_"):
            expression = re.sub(r"\s+", " ", str(c.sqltext))
            assert re.search(rf"CONSTRAINT {c.name} CHECK \({re.escape(expression)}\)", re.sub(r"\s+", " ", body)), c.name
    assert "uq_asset_agg_icon_key UNIQUE (key)" in body
    assert "trg_set_updated_at BEFORE UPDATE ON asset_agg_icon" in ddl and "ON DELETE RESTRICT" in ddl
    for comment in ("created_by", "name", "svg", "sha256"):                           # the comments of a migrated and of a fresh database are the same
        assert AssetAggIcon.__table__.c[comment].comment in ddl, comment
    drop = (SQL / "icons_drop_text.sql").read_text()
    assert AssetAggIcon.__table__.c.key.comment.replace("'", "''") in drop, "step 2 sets the comment of key"


def test_step_2_gives_a_migrated_reference_table_the_same_icon_id_as_a_fresh_one():
    drop = (SQL / "icons_drop_text.sql").read_text()
    column = Base.metadata.tables["core_ref_sport_type"].c.icon_id
    assert column.comment in drop and "SET NOT NULL" in drop and "DROP COLUMN IF EXISTS icon" in drop
    assert drop.index("RAISE EXCEPTION") < drop.index("SET NOT NULL"), "the check for empty links comes before any change"
