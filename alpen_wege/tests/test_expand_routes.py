# Standard library
import importlib.util
import re
from pathlib import Path
from typing import get_args

# Local application
from app.main import app

ROOT = Path(__file__).resolve().parents[1]

# Every single-object GET that takes ?expand=. A new GET-by-id route has to be added here (and get a Detail schema)
# or to EXEMPT, so no route is left out by accident.
EXPAND_ROUTES = {
    "GET /api/v1/assets/gpx/{gpx_id}",
    "GET /api/v1/assets/icons/{icon_id}",
    "GET /api/v1/assets/photos/{photo_id}",
    "GET /api/v1/compendium/cards/{card_id}",
    "GET /api/v1/compendium/countries/{country_id}",
    "GET /api/v1/compendium/poi-regions/{poi_region_id}",
    "GET /api/v1/compendium/pois/{poi_id}",
    "GET /api/v1/compendium/posts/{post_id}",
    "GET /api/v1/compendium/regions/{region_id}",
    "GET /api/v1/core/achievement-categories/{item_id}",
    "GET /api/v1/core/achievement-scopes/{item_id}",
    "GET /api/v1/core/achievement-types/{item_id}",
    "GET /api/v1/core/companies/{item_id}",
    "GET /api/v1/core/compendium-types/{item_id}",
    "GET /api/v1/core/difficulty-levels/{item_id}",
    "GET /api/v1/core/difficulty-sports/{item_id}",
    "GET /api/v1/core/gear-types/{item_id}",
    "GET /api/v1/core/point-reasons/{item_id}",
    "GET /api/v1/core/post-types/{item_id}",
    "GET /api/v1/core/rarities/{item_id}",
    "GET /api/v1/core/region-types/{item_id}",
    "GET /api/v1/core/resource-types/{item_id}",
    "GET /api/v1/core/schedule-statuses/{item_id}",
    "GET /api/v1/core/snow-conditions/{item_id}",
    "GET /api/v1/core/sport-types/{item_id}",
    "GET /api/v1/core/trail-conditions/{item_id}",
    "GET /api/v1/core/visibilities/{item_id}",
    "GET /api/v1/core/waypoint-types/{item_id}",
    "GET /api/v1/core/weather-conditions/{item_id}",
    "GET /api/v1/explorer/gear/{gear_id}",
    "GET /api/v1/explorer/routes/{route_id}",
    "GET /api/v1/explorer/segments/{segment_id}",
    "GET /api/v1/explorer/tracks/{track_id}",
    "GET /api/v1/management/event-log/{id_1}/compare/{id_2}",
    "GET /api/v1/management/event-log/{log_id}",
    "GET /api/v1/management/jobs/{job_id}",
    "GET /api/v1/management/settings/{key}",
    "GET /api/v1/profile/access-policies/{item_id}",
}
# GET-by-id routes without links to other objects: nothing to expand
EXEMPT = {
    "GET /api/v1/profile/users/{user_id}",          # a user has no link to another object
    "GET /api/v1/management/my-jobs/{job_id}",      # the owner's job: no user, the subject is a (type, id) pair
    "GET /api/v1/management/celery/tasks/{task_id}",  # a Celery task, not a database object
}
# This route takes the names of EventLogDetail but answers with the compare schema
COMPARE = "GET /api/v1/management/event-log/{id_1}/compare/{id_2}"


def _load_route_map():
    spec = importlib.util.spec_from_file_location("route_map", ROOT / "scripts" / "route_map.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _routes() -> dict:
    return _load_route_map().dump()["routes"]


def _name(call) -> str:
    return getattr(call, "__qualname__", "")


def _expand_dependants() -> dict:
    # route key -> (route, its dependencies in the order FastAPI resolves them) for every route that has an expand_plan
    found = {}
    for route, original in _load_route_map()._iter_routes(app.routes):
        if type(original).__name__ != "APIRoute" or getattr(route, "dependant", None) is None:
            continue
        dependencies = list(route.dependant.dependencies)
        if any("expand_plan" in _name(d.call) for d in dependencies):
            found[f"GET {route.path}"] = (original, dependencies)
    return found


def test_the_routes_with_the_expand_parameter_are_exactly_the_listed_ones():
    with_expand = {key for key, record in _routes().items()
                   if any(str(p).startswith("query:expand:") for p in record.get("parameters", []))}
    assert with_expand == EXPAND_ROUTES, (sorted(with_expand ^ EXPAND_ROUTES))


def test_every_get_by_id_route_is_either_expandable_or_exempt():
    # A route that answers one object by its id: GET ... /{something} (or .../{a}/compare/{b})
    by_id = {key for key in _routes()
             if key.startswith("GET ") and re.search(r"/\{[a-z_0-9]+\}$", key)}
    assert not (by_id - EXPAND_ROUTES - EXEMPT), sorted(by_id - EXPAND_ROUTES - EXEMPT)


def test_only_get_routes_take_the_expand_parameter():
    others = [key for key, record in _routes().items()
              if not key.startswith("GET ") and any(str(p).startswith("query:expand:") for p in record.get("parameters", []))]
    assert not others, others


def test_the_login_check_comes_before_expand_in_every_route():
    # FastAPI resolves the parameters in the order they are written. With expand first, an unauthenticated caller
    # would be told the allowed names (400) instead of getting 401.
    found = _expand_dependants()
    assert set(found) == EXPAND_ROUTES
    wrong = []
    for key, (_route, dependencies) in found.items():
        names = [_name(d.call) for d in dependencies]
        plan_at = next(i for i, n in enumerate(names) if "expand_plan" in n)
        auth_at = next((i for i, n in enumerate(names) if "resource_access" in n or "require_groups" in n), None)
        if auth_at is None or auth_at > plan_at:
            wrong.append(key)
    assert not wrong, wrong


def test_a_missing_token_answers_401_even_with_a_bad_expand():
    module = _load_route_map()
    routes = {key: record for key, record in module.dump()["routes"].items() if key in EXPAND_ROUTES}
    assert len(routes) == len(EXPAND_ROUTES)
    assert module.probe_routes(routes, query="expand=zzz") == []


def test_the_answer_schema_of_every_expand_route_is_the_schema_of_its_expand_plan():
    wrong = []
    for key, (route, dependencies) in _expand_dependants().items():
        dependency = next(d for d in dependencies if "expand_plan" in _name(d.call))
        cells = dict(zip(dependency.call.__code__.co_freevars, (c.cell_contents for c in dependency.call.__closure__)))
        answer = route.response_model.model_fields["response_data"].annotation      # for example PoiDetail | None
        if key != COMPARE and cells["schema"] not in get_args(answer):
            wrong.append(f"{key}: answers {answer}, expand_plan({cells['schema'].__name__})")
    assert not wrong, wrong
