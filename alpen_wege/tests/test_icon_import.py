"""Creating many icons through the API: the CSV import and the link by key (app/assets/services/icon_csv.py, icon_link.py, the two routes)."""
# Standard library
import asyncio
import csv
import io
import uuid
from types import SimpleNamespace

# Third-party
import pytest
from sqlalchemy.dialects import postgresql

# Local application
from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.services import icon_csv, icon_link
from app.main import app
from app.management.utils import event_logger

SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24z"/></svg>'
OTHER = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/></svg>'
USER = uuid.uuid4()


def csv_text(rows, header=("key", "svg", "name")):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(header)
    writer.writerows(rows)
    return out.getvalue()


# ---------------------------------------------------------------- parsing the file
def test_parse_reads_rows_with_or_without_the_excel_bom_and_keeps_the_svg_whole():
    for bom in ("", "﻿"):
        rows = icon_csv.parse_csv_text(bom + csv_text([["a", SVG, "A"], ["b", OTHER, ""]]))
        assert [r["key"] for r in rows] == ["a", "b"] and rows[0]["svg"] == SVG and rows[1]["name"] == ""


def test_parse_names_a_missing_column_an_empty_file_a_header_only_file_and_too_many_rows():
    with pytest.raises(ValueError, match="needs the column.*svg.*found: key, name"):
        icon_csv.parse_csv_text("key,name\na,A\n")
    with pytest.raises(ValueError, match="needs the column.*key.*svg"):
        icon_csv.parse_csv_text("")
    with pytest.raises(ValueError, match="no rows"):
        icon_csv.parse_csv_text("key,svg\n")
    with pytest.raises(ValueError, match="more than 3 rows"):
        icon_csv.parse_csv_text(csv_text([[f"k{i}", SVG, ""] for i in range(4)]), max_rows=3)
    assert len(icon_csv.parse_csv_text(csv_text([[f"k{i}", SVG, ""] for i in range(3)]), max_rows=3)) == 3


def test_parse_accepts_a_long_svg_and_columns_with_spaces_in_the_header():
    long_svg = SVG.replace("<path", "<!--" + "x" * 200_000 + "--><path")
    rows = icon_csv.parse_csv_text(" key , svg \n" + csv_text([["a", long_svg, ""]], header=("key", "svg", "name")).split("\n", 1)[1].replace(",,", ","))
    assert len(rows[0]["svg"]) > 200_000


# ---------------------------------------------------------------- the ids
def test_the_id_of_a_new_icon_depends_only_on_its_key():
    assert icon_csv.icon_id("flag_at") == icon_csv.icon_id("flag_at") != icon_csv.icon_id("flag_ch")
    assert icon_csv.icon_id("x") == uuid.uuid5(icon_csv.ICON_NAMESPACE, "x")


# ---------------------------------------------------------------- saving, without a database
class _Result:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return iter(self._items)


class _Db:
    # answers the two reads of save_icons: first the icons that exist, then the ids that are taken
    def __init__(self, existing=(), taken=()):
        self.answers = [list(existing), list(taken)]
        self.added = []

    async def execute(self, statement):
        return _Result(self.answers.pop(0))

    def add(self, obj):
        self.added.append(obj)


def _existing(key, svg=SVG, sha="a" * 64, **texts):
    return AssetAggIcon(id=uuid.uuid4(), key=key, svg=svg, sha256=sha, name=texts.pop("name", key), created_by=USER, **texts)


def _prepared(rows):
    prepared, rejected, _ = icon_csv.prepare_rows(rows)
    assert not rejected
    return prepared


@pytest.fixture
def log(monkeypatch):
    meta = event_logger._EntityMeta(entity_type_id=uuid.uuid4(), tracking_mode="all", ignore_fields=frozenset({"svg"}))
    monkeypatch.setitem(event_logger._entity_cache, "asset_agg_icon", meta)
    events = []
    return events


def _run(db, prepared, update, log):
    db.add = lambda obj: (db.added.append(obj), log.append(obj) if hasattr(obj, "action") else None)
    return asyncio.run(icon_csv.save_icons(db, prepared, USER, update=update))


def test_new_keys_are_inserted_with_their_own_id_and_logged_without_the_svg(log):
    db = _Db()
    prepared = _prepared([{"key": "a", "svg": SVG, "name": "A", "name_de": "Ah"}, {"key": "b", "svg": OTHER}])
    result = _run(db, prepared, False, log)
    assert (result.inserted, result.updated, result.unchanged) == (2, 0, 0) and result.keys == {"a": "inserted", "b": "inserted"}
    icons = [o for o in db.added if isinstance(o, AssetAggIcon)]
    assert [i.id for i in icons] == [icon_csv.icon_id("a"), icon_csv.icon_id("b")]
    assert icons[0].name == "A" and icons[0].name_de == "Ah" and icons[1].name == "b" and icons[0].created_by == USER
    events = [o for o in db.added if not isinstance(o, AssetAggIcon)]
    assert [e.action for e in events] == ["created", "created"] and all("svg" not in e.snapshot for e in events)


def test_an_id_that_belongs_to_another_key_is_not_reused(log):
    db = _Db(taken=[icon_csv.icon_id("a")])             # an icon was renamed: its id is the id of the old key "a"
    _run(db, _prepared([{"key": "a", "svg": SVG}]), False, log)
    new = [o for o in db.added if isinstance(o, AssetAggIcon)][0]
    assert new.id != icon_csv.icon_id("a")


def test_existing_keys_are_left_alone_without_update_and_replaced_with_update(log):
    prepared = _prepared([{"key": "a", "svg": OTHER, "name": "New name"}, {"key": "same", "svg": SVG, "name": "same"}])
    sha_same = prepared[1]["sha"]
    old_a, old_same = _existing("a", name="Old name"), _existing("same", sha=sha_same)
    r1 = _run(_Db([old_a, old_same]), prepared, False, log)
    assert (r1.inserted, r1.updated, r1.unchanged) == (0, 0, 2) and old_a.name == "Old name"
    db = _Db([old_a, old_same])
    r2 = _run(db, prepared, True, log)
    assert (r2.inserted, r2.updated, r2.unchanged) == (0, 1, 1) and r2.keys == {"a": "updated", "same": "unchanged"}
    assert old_a.name == "New name" and old_a.svg == prepared[0]["svg"] and old_a.sha256 == prepared[0]["sha"]
    events = [o for o in db.added if not isinstance(o, AssetAggIcon)]
    assert [e.action for e in events] == ["updated"] and "svg" not in events[0].snapshot and events[0].snapshot["name"]["new"] == "New name"


def test_the_old_svg_text_is_never_read_when_an_icon_is_replaced(log, monkeypatch):
    # on a real session the svg column is deferred: reading it would load 300 KB per icon (and fail in async code)
    real_getattr = __import__("builtins").getattr

    def guard(obj, name, *default):
        assert name != "svg" or not isinstance(obj, AssetAggIcon), "the service read icon.svg"
        return real_getattr(obj, name, *default)

    monkeypatch.setattr(icon_csv, "getattr", guard, raising=False)
    prepared = _prepared([{"key": "a", "svg": OTHER, "name": "New"}])
    icon = _existing("a", name="Old")
    r = _run(_Db([icon]), prepared, True, log)
    assert r.updated == 1 and icon.name == "New" and icon.svg == prepared[0]["svg"]


def test_an_update_that_changes_nothing_is_counted_unchanged(log):
    prepared = _prepared([{"key": "a", "svg": SVG, "name": "A", "summary": "s"}])
    same = _existing("a", sha=prepared[0]["sha"], name="A", summary="s")
    r = _run(_Db([same]), prepared, True, log)
    assert (r.updated, r.unchanged) == (0, 1)


def test_only_a_text_change_is_an_update_too(log):
    prepared = _prepared([{"key": "a", "svg": SVG, "name": "Changed"}])
    icon = _existing("a", sha=prepared[0]["sha"], name="A")
    r = _run(_Db([icon]), prepared, True, log)
    assert r.updated == 1 and icon.name == "Changed"


# ---------------------------------------------------------------- the link by key
def _sql(what):
    model = icon_link.LINKED_BY_CODE[what]
    statement = icon_link.update(model).where(model.icon_id.is_(None), icon_link._matches(what, model)).values(icon_id=AssetAggIcon.id)
    return " ".join(str(statement.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True})).split())


def test_the_link_matches_countries_and_regions_by_their_code_and_nothing_else():
    assert set(icon_link.LINKED_BY_CODE) == {"country", "region"}          # the reference tables always have an icon
    assert "asset_agg_icon.key = concat('flag_', lower(compendium_cat_country.iso_code))" in _sql("country")
    region = _sql("region")
    assert "compendium_cat_region.iso_code IS NOT NULL" in region and "concat('flag_', lower(replace(compendium_cat_region.iso_code, '-', '_')))" in region
    for what in icon_link.LINKED_BY_CODE:
        sql = _sql(what)
        assert "icon_id IS NULL" in sql and "SET icon_id=asset_agg_icon.id" in sql and "FROM asset_agg_icon" in sql, what     # only empty links are filled


def test_link_icons_visits_countries_and_regions_and_reports_only_what_changed():
    calls = []

    class Db:
        async def execute(self, statement):
            calls.append(statement)
            if len(calls) % 2 == 1:                                   # the UPDATE of a table
                return SimpleNamespace(rowcount=3 if len(calls) == 1 else 0)
            return SimpleNamespace(scalar_one=lambda: 2 if len(calls) == 4 else 0)     # the count of rows without icon

    linked, empty = asyncio.run(icon_link.link_icons(Db()))
    assert len(calls) == 4
    assert linked == {"country": 3} and empty == {"region": 2}


# ---------------------------------------------------------------- the routes
def test_the_two_routes_exist_under_the_icons_path():
    assert app.url_path_for("upload_icons_csv") == "/api/v1/assets/icons/upload-csv"
    assert app.url_path_for("link_icons_by_key") == "/api/v1/assets/icons/link"


def test_the_import_route_documents_its_options_and_the_answer():
    spec = app.openapi()
    post = spec["paths"]["/api/v1/assets/icons/upload-csv"]["post"]
    params = {p["name"]: p for p in post["parameters"]}
    assert set(params) == {"dry_run", "update", "link"} and params["link"]["schema"]["default"] is True and params["dry_run"]["schema"]["default"] is False
    assert all(params[n].get("description") for n in params) and "dry_run=true" in post["description"]
    schema = spec["components"]["schemas"]["IconImportResult"]["properties"]
    assert set(schema) == {"dry_run", "inserted", "updated", "unchanged", "rejected", "errors", "notes", "linked", "still_without_icon"}
    assert all(p.get("description") for p in schema.values())
    link = spec["paths"]["/api/v1/assets/icons/link"]["post"]
    assert [p["name"] for p in link["parameters"]] == ["dry_run"] and "icons_link.sql" in link["description"]


# ---------------------------------------------------------------- the second permission of the options
def test_require_policy_refuses_a_role_that_lacks_the_permission_and_names_it(monkeypatch):
    from app.assets.routes.icon import _shared
    from app.core.utils.responses import AppError

    asked = []

    async def scope(group, key, action, db):
        asked.append((group, key, action))
        return None if (key, action) == ("ref", "update") else "all"

    monkeypatch.setattr(_shared, "get_policy_scope", scope)
    user = SimpleNamespace(credentials=SimpleNamespace(user_group="editor"))
    asyncio.run(_shared.require_policy(None, user, "icon", "update"))                    # allowed: nothing happens
    with pytest.raises(AppError) as raised:
        asyncio.run(_shared.require_policy(None, user, "ref", "update"))
    assert raised.value.status_code == 403 and "update permission on ref" in raised.value.error_message
    assert asked == [("editor", "icon", "update"), ("editor", "ref", "update")]


def test_the_import_route_asks_for_the_extra_permissions_before_it_changes_anything():
    # The live check cannot see this with the default policies (only the administrator has icon.create), so the code is read:
    # update=true needs icon.update, link=true needs ref.update, both are checked before the first row is saved.
    from pathlib import Path

    text = (Path(__file__).resolve().parents[1] / "app/assets/routes/icon/upload_csv.py").read_text(encoding="utf-8")
    assert 'resource_access("icon", "create")' in text
    update_check = text.index('require_policy(db, access.user, "icon", "update")')
    link_check = text.index('require_policy(db, access.user, "ref", "update")')
    assert text.index("if update:") < update_check < text.index("if link:") < link_check < text.index("save_icons(")
    link_route = (Path(__file__).resolve().parents[1] / "app/assets/routes/icon/link.py").read_text(encoding="utf-8")
    assert 'resource_access("ref", "update")' in link_route
