# Standard library
import asyncio
import importlib.util
import inspect
import re
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

# Third-party
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import asyncpg

# Local application
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

NAME = ("q", "created_by")                       # the filters of every lookup table
RANK = NAME + ("rank_min", "rank_max")           # the tables with a scale (rank) have two more
RANKED = "name created_at updated_at point_factor rank"
P1000, P100, P100_500 = (1000, None), (100, None), (100, 500)   # (default, maximum) rows of a page, as before
REFERENCE_TABLES = {                             # path -> (sort names, filters)
    "companies": ("name created_at updated_at", NAME),
    "gear-types": ("name created_at updated_at", NAME),
    "achievement-categories": ("name created_at updated_at point_factor", NAME),
    "achievement-scopes": ("name created_at updated_at point_factor", NAME),
    "achievement-types": ("name created_at updated_at point_factor", NAME),
    "difficulty-levels": (RANKED, RANK),
    "point-reasons": ("name created_at updated_at point_factor", NAME),
    "post-types": ("name created_at updated_at point_factor", NAME),
    "rarities": (RANKED, RANK),
    "region-types": ("name created_at updated_at point_factor", NAME),
    "schedule-statuses": ("name created_at updated_at point_factor", NAME),
    "snow-conditions": ("name created_at updated_at point_factor", NAME),
    "trail-conditions": ("name created_at updated_at point_factor", NAME),
    "visibilities": (RANKED, RANK),
    "waypoint-types": ("name created_at updated_at point_factor", NAME),
    "weather-conditions": ("name created_at updated_at point_factor", NAME),
    "sport-types": ("name created_at updated_at point_factor", NAME),
    "difficulty-sports": (RANKED, RANK + ("sport_type_id",)),
    "compendium-types": ("name created_at updated_at point_factor", NAME + ("is_collectable",)),
}

# Every list route (a GET that returns a page): (default, maximum) rows, default sort, sort names, filters.
# A new list route has to be added here, or it is not one of the standard lists.
LIST_ROUTES = {f"/api/v1/core/{path}": (P1000, "name", sorts.split(), filters) for path, (sorts, filters) in REFERENCE_TABLES.items()}
LIST_ROUTES.update({
    "/api/v1/core/resource-types": (P1000, "key", ["key", "created_at"], ("q",)),
    "/api/v1/compendium/pois": (P1000, "name", ["name", "altitude_m", "created_at", "updated_at"], (
        "q", "compendium_type_id", "main_region_id", "created_by", "altitude_min", "altitude_max", "created_from", "created_to",
        "bbox", "near", "radius_m")),
    "/api/v1/compendium/regions": (P1000, "name", ["name", "created_at", "updated_at"], (
        "q", "country_id", "region_type_id", "parent_id", "created_by", "bbox")),
    "/api/v1/compendium/countries": (P1000, "name", ["name", "iso_code", "created_at"], ("q", "iso_code", "created_by")),
    "/api/v1/compendium/cards": (P1000, "name", ["name", "created_at", "updated_at"], (
        "q", "rarity_id", "compendium_type_id", "poi_id", "created_by")),
    "/api/v1/compendium/posts": (P1000, "name", ["name", "created_at", "updated_at"], ("q", "post_type_id", "created_by")),
    "/api/v1/compendium/poi-regions": (P1000, "slot_position", ["slot_position", "created_at"], ("poi_id", "region_id", "created_by")),
    "/api/v1/explorer/gear": (P1000, "-created_at", ["name", "created_at", "weight_g"], (
        "q", "company_id", "gear_type_id", "created_by", "weight_min", "weight_max")),
    "/api/v1/explorer/segments": (P1000, "-created_at", ["name", "created_at", "updated_at", "distance_m", "elevation_gain_m"], (
        "q", "sport_type_id", "difficulty_level_id", "difficulty_sport_id", "created_by", "is_public", "unused", "start_poi_id",
        "end_poi_id", "distance_min", "distance_max", "elevation_gain_min", "elevation_gain_max", "near", "radius_m")),
    "/api/v1/explorer/routes": (P1000, "-created_at", ["name", "created_at", "updated_at", "agg_distance_m", "agg_elevation_gain_m", "rating_avg"], (
        "q", "sport_type_id", "difficulty_level_id", "difficulty_sport_id", "created_by", "is_public", "distance_min", "distance_max",
        "elevation_gain_min", "elevation_gain_max")),
    "/api/v1/explorer/tracks": (P100_500, "-recorded_at", ["recorded_at", "created_at", "name", "distance_m", "elevation_gain_m"], (
        "archived", "processing_status", "sport_type_id", "q", "is_public", "created_by", "difficulty_level_id",
        "difficulty_sport_id", "start_poi_id", "end_poi_id", "recorded_from", "recorded_to", "distance_min", "distance_max",
        "elevation_gain_min", "elevation_gain_max")),
    "/api/v1/management/event-log": (P100, "-changed_at", ["changed_at", "seq"], (
        "entity_type", "entity_id", "action", "changed_by", "changed_from", "changed_to")),
    "/api/v1/management/jobs": (P100_500, "-created_at", ["created_at", "finished_at", "status"], (
        "status", "kind", "user_id", "task_name", "subject_type", "subject_id", "active", "created_from", "created_to")),
    "/api/v1/management/my-jobs": (P100_500, "-created_at", ["created_at", "finished_at", "status"], (
        "status", "kind", "subject_type", "subject_id", "active", "created_from", "created_to")),
    "/api/v1/profile/access-policies": (P1000, "group", ["group", "resource_key", "action"], ("group", "resource_key", "action", "scope")),
    "/api/v1/profile/users/": (P1000, "-created_at", ["created_at", "username", "last_active_at"], (
        "q", "is_active", "user_group", "created_from", "created_to")),
})


def _route_map():
    spec = importlib.util.spec_from_file_location("route_map", ROOT / "scripts" / "route_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _get_routes() -> dict:
    # path -> (route, the dependencies in the order FastAPI resolves them) for every GET route
    found = {}
    for route, original in _route_map()._iter_routes(app.routes):
        if type(original).__name__ == "APIRoute" and "GET" in original.methods and getattr(route, "dependant", None) is not None:
            found[route.path] = (route, list(route.dependant.dependencies))
    return found


def _qualname(call) -> str:
    return getattr(call, "__qualname__", "")


def _closure(call) -> dict:
    return inspect.getclosurevars(call).nonlocals


def _own_dependencies(dependencies: list):
    page = [d for d in dependencies if "page_params" in _qualname(d.call)]
    sort = [d for d in dependencies if "sort_params" in _qualname(d.call)]
    filters = [d for d in dependencies if _qualname(d.call).split(".")[-1].endswith("Filters")]
    return page, sort, filters


def test_the_list_routes_are_exactly_the_known_ones():
    # every GET that has page_params is in LIST_ROUTES and the other way round
    paging = {path for path, (_, deps) in _get_routes().items() if _own_dependencies(deps)[0]}
    assert paging == set(LIST_ROUTES)
    assert len(LIST_ROUTES) == 35


def test_every_list_route_has_the_documented_page_sort_and_filters():
    routes = _get_routes()
    for path, (profile, default_sort, sort_names, filter_names) in LIST_ROUTES.items():
        route, dependencies = routes[path]
        page, sort, filters = _own_dependencies(dependencies)
        assert len(page) == 1 and len(sort) == 1 and len(filters) == 1, path
        assert _closure(page[0].call)["maximum"] == profile[1], path
        assert _closure(sort[0].call)["default"] == default_sort, path
        options = _closure(sort[0].call)["options"]
        assert sorted(options) == sorted(sort_names), path
        assert default_sort.lstrip("-") in options, path
        parameters = [p for p in inspect.signature(filters[0].call.__init__).parameters if p != "self"]
        assert tuple(parameters) == tuple(filter_names), path


def test_the_login_dependency_comes_before_the_paging_one():
    # a caller without a token must get 401, not the 422 of the paging dependency (a NUL character, a bad limit)
    for path in LIST_ROUTES:
        route, dependencies = _get_routes()[path]
        call = dependencies[0].call
        listing = getattr(call, "__module__", "") == "app.core.utils.listing"
        assert not listing and not _qualname(call).endswith("Filters"), f"{path}: {_qualname(call)} is resolved before the login"


def test_the_openapi_limit_and_offset_of_every_list_route():
    spec = app.openapi()
    for path, (profile, *_rest) in LIST_ROUTES.items():
        parameters = {p["name"]: p for p in spec["paths"][path]["get"]["parameters"]}
        assert parameters["limit"]["schema"]["default"] == profile[0], path
        assert parameters["limit"]["schema"]["minimum"] == 1, path
        offset = "skip" if path == "/api/v1/profile/users/" else "offset"      # the users list has always called it skip
        assert offset in parameters and ({"skip", "offset"} - {offset}).isdisjoint(parameters), path
        assert parameters[offset]["schema"]["minimum"] == 0 and parameters[offset]["schema"]["default"] == 0, path
        assert (str(profile[1]) in parameters["limit"]["description"]) == (profile[1] is not None), path
        assert "sort" in parameters and parameters["sort"]["description"], path
        assert all(parameters[name]["description"] for name in ("q",) if name in parameters), path


def test_a_list_route_does_not_use_the_old_unlimited_paging():
    # the old routes had `limit: int = 1000` in their own signature; paging now comes from page_params only
    for path in LIST_ROUTES:
        route, _deps = _get_routes()[path]
        own = {p.name for p in route.dependant.query_params}
        assert not own & {"limit", "offset", "skip"}, f"{path} declares its own paging parameter"


def test_list_route_files_use_the_helpers_and_not_their_own_paging():
    files = sorted(ROOT.glob("app/*/routes/**/get_many.py"))
    checked = 0
    for file in files:
        text = file.read_text(encoding="utf-8")
        if "ok_list(" not in text:
            continue
        checked += 1
        name = str(file.relative_to(ROOT))
        assert "page_params(" in text and "sort_params(" in text and "Depends()" in text, name
        assert not re.search(r"\blimit: int\b|\boffset: int\b|\bskip: int\b", text), name
        assert "count_stmt" not in text, name
        assert re.search(r"total=total, limit=page\.limit, offset=page\.offset", text), name
    assert checked == 35


def test_a_bad_paging_value_without_a_token_still_answers_401():
    problems = _route_map().probe_routes({f"GET {path}": {"name": _name_of(path), "security": [{}]} for path in LIST_ROUTES}, "limit=0&offset=-1")
    assert problems == []


def _name_of(path: str) -> str:
    return getattr(_get_routes()[path][0].endpoint, "__name__", "")


def test_every_list_route_with_an_access_context_narrows_by_the_scope():
    # The live check cannot see a dropped scope when the policy of the seed gives "all" to everybody, so the code is read:
    # a list that takes an AccessContext uses apply_scope (objects), apply_visibility (tracks) or the own-scope condition
    # of the lookup tables.
    checked = 0
    for file in sorted(ROOT.glob("app/*/routes/**/get_many.py")):
        text = file.read_text(encoding="utf-8")
        if "access: AccessContext" not in text:
            continue
        checked += 1
        name = str(file.relative_to(ROOT))
        assert "apply_scope(" in text or "apply_visibility(" in text or 'access.scope == "own"' in text, f"{name} ignores the scope"
        if "apply_visibility" in text:
            assert "apply_visibility(" in text and "apply_scope(" in text, f"{name}: the track list needs both"
    assert checked == 29   # 6 compendium lists, gear, segment, route, track and the 19 lookup tables


# ------------------------------------------------------------------ the default order is the old one

# path -> (column name, descending) of the order that each list had before; ties are now broken by the id
OLD_ORDER = {path: ("name", False) for path in LIST_ROUTES if path.startswith("/api/v1/core/") or path in (
    "/api/v1/compendium/pois", "/api/v1/compendium/regions", "/api/v1/compendium/countries", "/api/v1/compendium/cards",
    "/api/v1/compendium/posts")}
OLD_ORDER.update({
    "/api/v1/core/resource-types": ("key", False),
    "/api/v1/compendium/poi-regions": ("slot_position", False),
    "/api/v1/explorer/gear": ("created_at", True),
    "/api/v1/explorer/segments": ("created_at", True),
    "/api/v1/explorer/routes": ("created_at", True),
    "/api/v1/explorer/tracks": ("coalesce", True),          # coalesce(recorded_at, created_at)
    "/api/v1/management/event-log": ("changed_at", True),
    "/api/v1/management/jobs": ("created_at", True),
    "/api/v1/management/my-jobs": ("created_at", True),
    "/api/v1/profile/users/": ("created_at", True),
    "/api/v1/profile/access-policies": ("user_group", False),   # then resource key, then action
})


def _default_sort(dependency):
    # what the sort dependency gives when the caller sends no ?sort=
    return asyncio.run(dependency.call(sort=None))


def test_the_default_order_of_every_list_is_the_old_one():
    routes = _get_routes()
    assert set(OLD_ORDER) == set(LIST_ROUTES)
    for path, (name, descending) in OLD_ORDER.items():
        sort = _default_sort(_own_dependencies(routes[path][1])[1][0])
        column = getattr(sort.column, "key", None) or getattr(sort.column, "name", None)
        assert (column, sort.descending) == (name, descending), path
        assert sort.tie_breaker is not None, path
    keys = _default_sort(_own_dependencies(routes["/api/v1/profile/access-policies"][1])[1][0]).tie_breaker
    assert [getattr(c, "key", None) for c in keys] == ["key", "action", "id"]   # group, then resource key, then action


# ------------------------------------------------------------------ every filter filters the column it is named after

# the filters whose name is not the name of a column: parameter -> text that the condition must contain
EXPECT = {
    "q": "ILIKE", "bbox": "ST_Intersects(", "near": "ST_DWithin(geography(", "active": ".status IN",
    "altitude_min": ".altitude_m >= 7", "altitude_max": ".altitude_m <= 7", "weight_min": ".weight_g >= 7", "weight_max": ".weight_g <= 7",
    "distance_min": ".distance_m >= 7", "distance_max": ".distance_m <= 7",
    "rank_min": ".rank >= 7", "rank_max": ".rank <= 7",
    "elevation_gain_min": ".elevation_gain_m >= 7", "elevation_gain_max": ".elevation_gain_m <= 7",
    "created_from": ".created_at >= ", "created_to": ".created_at < ", "changed_from": ".changed_at >= ", "changed_to": ".changed_at < ",
    "recorded_from": "coalesce(explorer_agg_track.recorded_at, explorer_agg_track.created_at) >= ",
    "recorded_to": "coalesce(explorer_agg_track.recorded_at, explorer_agg_track.created_at) < ",
    "group": "profile_access_policy.user_group = ", "resource_key": "core_ref_resource_type.key = ",
    "user_group": "profile_user_credentials.user_group = ", "entity_type": "mgmt_ref_entity_type.key = ",
    "iso_code": "upper(compendium_cat_country.iso_code) = ",
    "unused": "NOT (EXISTS (SELECT",
}
# the same parameter name on a list whose column has another name (the totals of a route are called agg_...)
EXPECT_BY_PATH = {
    ("/api/v1/explorer/routes", "distance_min"): ".agg_distance_m >= 7", ("/api/v1/explorer/routes", "distance_max"): ".agg_distance_m <= 7",
    ("/api/v1/explorer/routes", "elevation_gain_min"): ".agg_elevation_gain_m >= 7",
    ("/api/v1/explorer/routes", "elevation_gain_max"): ".agg_elevation_gain_m <= 7",
}
SKIP = {"archived", "radius_m"}          # archived is applied by apply_visibility, radius_m belongs to near
# the columns that the text search q looks at; the lookup tables use the default
Q_COLUMNS = {
    "/api/v1/compendium/pois": ["name", "name_de", "name_pl"],
    "/api/v1/explorer/gear": ["name", "name_de", "name_pl", "model"],
    "/api/v1/explorer/tracks": ["name", "name_de", "name_pl", "summary"],
    "/api/v1/profile/users/": ["username", "email", "first_name", "last_name"],
    "/api/v1/core/resource-types": ["key"],
}


def _sample(name: str, annotation):
    many = "list" in str(annotation)
    if name in ("group", "user_group"):
        return "viewer"
    if name == "action":
        return "read"
    if name == "scope":
        return "own"
    if name in ("status", "processing_status"):
        return "ready" if name == "processing_status" else "queued"
    if name == "bbox":
        return "7,46,8,47"
    if name == "near":
        return "7.7,46.0"
    if name in ("entity_type", "resource_key", "kind", "task_name", "subject_type", "action", "q"):
        return "ab"
    if name == "iso_code":
        return "ch"
    if name.endswith("_from") or name.endswith("_to"):
        return datetime(2026, 10, 1)
    if name in ("is_active", "is_collectable", "active", "is_public", "unused"):
        return True
    if name.endswith("_min") or name.endswith("_max"):
        return 7
    if name.endswith("_id") or name in ("created_by", "changed_by"):
        return [UUID(int=1)] if many else UUID(int=1)
    raise AssertionError(f"no sample value for the filter {name}")


def _model_of(route):
    module = sys.modules[route.endpoint.__module__]
    return getattr(module, "M", None) or module.T          # the jobs list calls its model T


def _where(statement) -> str:
    text = str(statement.compile(dialect=asyncpg.dialect(), compile_kwargs={"literal_binds": True}))
    parts = re.split(r"\s+WHERE\s+", text, maxsplit=1)
    return " ".join(parts[1].split()) if len(parts) == 2 else ""


def _filter_class(dependencies):
    return _own_dependencies(dependencies)[2][0].call


def test_every_filter_filters_the_column_it_is_named_after():
    # With no database the live check is the only one that sees a filter that uses the wrong column; this test reads the
    # SQL: one filter at a time is set, and the WHERE clause must name the right column and carry the value.
    routes = _get_routes()
    checked = 0
    for path in LIST_ROUTES:
        filters_class = _filter_class(routes[path][1])
        model = _model_of(routes[path][0])
        parameters = [p for p in inspect.signature(filters_class.__init__).parameters.values() if p.name != "self"]
        for parameter in parameters:
            if parameter.name in SKIP:
                continue
            kwargs = {p.name: (False if p.name in ("archived", "active") else None) for p in parameters}
            value = _sample(parameter.name, parameter.annotation)
            kwargs[parameter.name] = value
            if parameter.name == "radius_m":
                continue
            filters = filters_class(**kwargs)
            two_arguments = len(inspect.signature(filters.apply).parameters) == 2
            statement = filters.apply(select(model), model) if two_arguments else filters.apply(select(model))
            where = _where(statement)
            label = f"{path} {parameter.name}"
            assert where, f"{label}: no condition"
            expected = EXPECT_BY_PATH.get((path, parameter.name)) or EXPECT.get(parameter.name)
            if expected is None:
                assert hasattr(model, parameter.name), f"{label}: not a column of {model.__name__}; add it to EXPECT"
                expected = f"{model.__tablename__}.{parameter.name} "
            assert expected in where, f"{label}: {where!r} does not contain {expected!r}"
            if parameter.name.endswith("_id") or parameter.name in ("created_by", "changed_by"):
                assert str(UUID(int=1)) in where, f"{label}: the value is not in the condition"
            checked += 1
    assert checked > 100


def test_the_text_search_looks_at_the_right_columns():
    routes = _get_routes()
    for path in LIST_ROUTES:
        filters_class = _filter_class(routes[path][1])
        names = [p.name for p in inspect.signature(filters_class.__init__).parameters.values() if p.name != "self"]
        if "q" not in names:
            continue
        model = _model_of(routes[path][0])
        kwargs = {name: (False if name in ("archived", "active") else None) for name in names}
        kwargs["q"] = "ab"
        filters = filters_class(**kwargs)
        two_arguments = len(inspect.signature(filters.apply).parameters) == 2
        where = _where(filters.apply(select(model), model) if two_arguments else filters.apply(select(model)))
        columns = Q_COLUMNS.get(path, ["name", "name_de", "name_pl"])
        assert sorted(re.findall(rf"{model.__tablename__}\.(\w+) ILIKE", where)) == sorted(columns), path


def test_the_map_filters_use_the_right_geometry_column():
    routes = _get_routes()
    for path, parameter, column in (
        ("/api/v1/compendium/pois", "bbox", "compendium_cat_poi.location"),        # the point of the POI
        ("/api/v1/compendium/pois", "near", "compendium_cat_poi.location"),
        ("/api/v1/compendium/regions", "bbox", "compendium_cat_region.bbox"),      # the area of the region, not its centre
    ):
        filters_class = _filter_class(routes[path][1])
        names = [p.name for p in inspect.signature(filters_class.__init__).parameters.values() if p.name != "self"]
        kwargs = {name: None for name in names}
        kwargs[parameter] = _sample(parameter, None)
        model = _model_of(routes[path][0])
        assert column in _where(filters_class(**kwargs).apply(select(model))), (path, parameter)


def test_every_sort_name_sorts_by_the_column_it_is_named_after():
    # sort=weight_g must not sort by something else. The exceptions are the names that are not a column name.
    different = {("/api/v1/profile/access-policies", "group"): "user_group", ("/api/v1/profile/access-policies", "resource_key"): "key",
                 ("/api/v1/explorer/tracks", "recorded_at"): "coalesce"}
    routes = _get_routes()
    checked = 0
    for path in LIST_ROUTES:
        sort_dependency = _own_dependencies(routes[path][1])[1][0]
        for name, column in _closure(sort_dependency.call)["options"].items():
            actual = getattr(column, "key", None) or getattr(column, "name", None)
            assert actual == different.get((path, name), name), f"{path}: sort={name} sorts by {actual}"
            checked += 1
    assert checked > 100
