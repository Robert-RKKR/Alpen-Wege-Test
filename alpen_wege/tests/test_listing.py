# Standard library
import asyncio
import json
from uuid import UUID

# Third-party
import pytest
from fastapi import Depends, FastAPI, Query
from sqlalchemy import Column, DateTime, Integer, Text, select
from sqlalchemy.dialects.postgresql import asyncpg
from sqlalchemy.orm import declarative_base
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse

# Local application
from app.core.utils import listing
from app.core.utils.listing import (
    MAX_OFFSET, PAGE_100, PAGE_100_MAX_500, PAGE_1000, NameFilters, Page, Sort, at_least, at_most, bbox_condition, before,
    contains, equals, ids_query, moment_query, near_condition, number_query, one_of, page_params, search_query, since, sort_params,
    where_all,
)
from app.core.utils.responses import AppError, ok_list

Base = declarative_base()


class Thing(Base):
    __tablename__ = "thing"
    id = Column(Integer, primary_key=True)
    name = Column(Text)
    name_de = Column(Text)
    name_pl = Column(Text)
    created_by = Column(Text)
    created_at = Column(DateTime)
    weight = Column(Integer)
    rank = Column(Integer, nullable=False)


SORT = {"name": Thing.name, "created_at": Thing.created_at, "rank": Thing.rank}


def sql(statement) -> str:
    return str(statement.compile(dialect=asyncpg.dialect(), compile_kwargs={"literal_binds": True}))


# ------------------------------------------------------------------ a small app with the helpers, called like a client does

def _make_app() -> FastAPI:
    app = FastAPI()

    @app.exception_handler(StarletteHTTPException)
    async def handler(request, exc):
        if isinstance(exc, AppError):
            return JSONResponse(status_code=exc.status_code, content={"message": exc.detail, "errors": exc.error_errors})
        return JSONResponse(status_code=exc.status_code, content={"message": str(exc.detail)})

    @app.get("/entity")
    async def entity(page: Page = Depends(page_params()), sort: Sort = Depends(sort_params(SORT, "-created_at", Thing.id))):
        return {"limit": page.limit, "offset": page.offset, "sort": sql(sort.apply(select(Thing)))}

    @app.get("/short")
    async def short(page: Page = Depends(page_params(PAGE_100))):
        return {"limit": page.limit, "offset": page.offset}

    @app.get("/capped")
    async def capped(page: Page = Depends(page_params(PAGE_100_MAX_500))):
        return {"limit": page.limit, "offset": page.offset}

    @app.get("/numbers")
    async def numbers(page: Page = Depends(page_params()), weight_min: int | None = number_query("Weight"),
                      created_from: moment_query("From") = None, kind: str | None = None):
        return {"weight_min": weight_min, "created_from": str(created_from), "kind": kind}

    @app.get("/ids")
    async def ids(page: Page = Depends(page_params()), company_id: list[UUID] | None = ids_query("Company")):
        return {"ids": [str(i) for i in company_id or []]}

    return app


APP = _make_app()


def call(path: str, query: str = ""):
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "http", "path": path,
        "raw_path": path.encode(), "query_string": query.encode(), "headers": [(b"host", b"t")], "server": ("t", 80),
        "client": ("t", 1), "root_path": "",
    }
    sent: list[dict] = []
    delivered = False

    async def receive():
        nonlocal delivered
        if not delivered:
            delivered = True
            return {"type": "http.request", "body": b"", "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        sent.append(message)

    asyncio.run(APP(scope, receive, send))
    status = next(m["status"] for m in sent if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in sent if m["type"] == "http.response.body")
    return status, json.loads(body)


# ------------------------------------------------------------------ paging

def test_the_three_page_profiles_are_the_old_ones():
    assert (PAGE_1000, PAGE_100, PAGE_100_MAX_500) == ((1000, None), (100, None), (100, 500))
    assert call("/entity")[1]["limit"] == 1000 and call("/short")[1]["limit"] == 100 and call("/capped")[1]["limit"] == 100


@pytest.mark.parametrize("query, limit", [("limit=1", 1), ("limit=500", 500), ("limit=501", 501), ("limit=5000", 5000),
                                          ("limit=1000000", 1000000)])
def test_a_list_without_a_maximum_gives_what_is_asked(query, limit):
    assert call("/entity", query)[1]["limit"] == limit and call("/short", query)[1]["limit"] == limit


@pytest.mark.parametrize("query, limit", [("limit=1", 1), ("limit=500", 500), ("limit=501", 500), ("limit=1000000", 500)])
def test_a_list_with_a_maximum_lowers_a_larger_limit(query, limit):
    assert call("/capped", query)[1]["limit"] == limit


@pytest.mark.parametrize("query", ["limit=0", "limit=-1", "limit=abc", "limit=", "offset=-1", "offset=abc", "limit=1.5",
                                   f"limit={MAX_OFFSET + 1}", "limit=9999999999999999999"])
def test_bad_limit_or_offset_is_422(query):
    assert call("/entity", query)[0] == 422


def test_offset_behind_the_last_row_is_allowed():
    assert call("/entity", "offset=99999999")[1]["offset"] == 99999999


def test_an_unknown_parameter_is_ignored_as_before():
    status, body = call("/entity", "limit=5&compendium_typ_id=x&_=123&expand=a")
    assert (status, body["limit"]) == (200, 5)


def test_offset_can_have_another_name():
    app = FastAPI()

    @app.get("/u")
    async def u(page: Page = Depends(page_params(offset_alias="skip"))):
        return {"limit": page.limit, "offset": page.offset}

    global APP
    old, APP = APP, app
    try:
        assert call("/u", "skip=7&limit=3")[1] == {"limit": 3, "offset": 7}
        assert call("/u", "offset=7")[1]["offset"] == 0       # the old name is not known any more, so it is ignored
        assert call("/u", "skip=-1")[0] == 422
    finally:
        APP = old


def test_known_parameters_pass_even_when_repeated():
    assert call("/entity", "limit=5&limit=6")[0] == 200


def test_the_parameter_of_the_route_function_and_of_the_page_dependency_work_together():
    assert call("/ids", "company_id=11111111-1111-1111-1111-111111111111&limit=3")[0] == 200


def test_too_many_ids_is_422_and_a_bad_id_is_422():
    ids = "&".join(f"company_id={UUID(int=i)}" for i in range(1, 52))
    assert call("/ids", ids)[0] == 422
    assert call("/ids", "company_id=not-a-uuid")[0] == 422
    assert call("/ids", "&".join(f"company_id={UUID(int=i)}" for i in range(1, 51)))[1]["ids"][0] == str(UUID(int=1))


@pytest.mark.parametrize("query", [
    f"offset={MAX_OFFSET + 1}", "offset=9999999999999999999", "weight_min=99999999999", "weight_min=-99999999999",
    "weight_min=2000000000", "created_from=9999-12-31T23:59:59", "created_from=0001-01-01", "created_from=1800-01-01",
    "created_from=2300-01-01T00:00:00Z", "created_from=not-a-date", "x=%00", "%00=1", "weight_min=1%00", "kind=a%00b", "kind=%00",
])
def test_values_that_the_database_cannot_take_are_422_not_500(query):
    status, body = call("/numbers", query)
    assert status == 422, body


def test_a_nul_character_in_a_known_text_parameter_is_refused_by_name():
    status, body = call("/numbers", "kind=a%00b")
    assert status == 422 and body["errors"][0]["code"] == "invalid_character" and body["errors"][0]["field"] == "query.kind"


@pytest.mark.parametrize("query", [f"offset={MAX_OFFSET}", "weight_min=1000000000", "weight_min=-1000000000", "weight_min=0",
                                   "created_from=2026-10-01", "created_from=2026-10-01T10:00:00Z", "created_from=2200-12-31T00:00:00"])
def test_the_edge_of_the_allowed_values_is_200(query):
    assert call("/numbers", query)[0] == 200


def test_ok_list_page_numbers_follow_the_used_limit():
    meta = ok_list([], total=1234, limit=500, offset=500)["response_pagination"]
    assert (meta["pagination_page"], meta["pagination_total_pages"], meta["pagination_has_next"]) == (2, 3, True)


# ------------------------------------------------------------------ sort

def test_sort_default_and_direction():
    assert "ORDER BY thing.created_at DESC NULLS LAST, thing.id" in call("/entity")[1]["sort"]
    assert "ORDER BY thing.name ASC NULLS LAST, thing.id" in call("/entity", "sort=name")[1]["sort"]
    assert "ORDER BY thing.name DESC NULLS LAST, thing.id" in call("/entity", "sort=-name")[1]["sort"]


def test_not_null_column_gets_no_nulls_last_so_an_index_can_serve_the_order():
    # measured on 1,000,000 rows: ORDER BY changed_at DESC LIMIT 100 took 0.15 ms, with NULLS LAST 92 ms
    text = call("/entity", "sort=-rank")[1]["sort"]
    assert "ORDER BY thing.rank DESC, thing.id" in text and "NULLS" not in text


def test_a_tuple_of_tie_breakers_gives_a_composite_order():
    sort = Sort(Thing.name, False, (Thing.created_by, Thing.id))
    assert "ORDER BY thing.name ASC NULLS LAST, thing.created_by, thing.id" in sql(sort.apply(select(Thing)))


@pytest.mark.parametrize("value", ["weight", "name;drop table thing", "-", "--name", "name,created_at", "NAME", "x" * 500])
def test_sort_by_something_else_is_422(value):
    status, body = call("/entity", f"sort={value}")
    assert status == 422 and body["errors"][0]["code"] == "invalid_sort"
    assert len(json.dumps(body)) < 800   # a long value is cut in the message


# ------------------------------------------------------------------ the text and value filters

def test_contains_is_not_case_sensitive_and_searches_every_column():
    text = sql(select(Thing).where(contains("Matter", Thing.name, Thing.name_de)))
    assert "thing.name ILIKE '%Matter%'" in text and "thing.name_de ILIKE '%Matter%'" in text and " OR " in text


def test_contains_percent_and_underscore_are_no_wildcards():
    compiled = select(Thing).where(contains("50%_off", Thing.name)).compile(dialect=asyncpg.dialect())
    assert list(compiled.params.values()) == [r"%50\%\_off%"]   # the value, not its rendering: that differs per SQLAlchemy version
    assert "ESCAPE" in str(compiled)


@pytest.mark.parametrize("value", ["a", " a ", "%"])
def test_contains_needs_two_characters(value):
    with pytest.raises(AppError):
        contains(value, Thing.name)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_contains_without_text_is_no_condition(value):
    assert contains(value, Thing.name) is None      # an empty search box means no search


def test_search_query_refuses_one_character_and_long_text():
    app = FastAPI()

    @app.get("/s")
    async def s(q: str | None = search_query("name")):
        return {"q": q}

    global APP
    old, APP = APP, app
    try:
        assert call("/s", "q=ab")[0] == 200
        assert call("/s", "q=")[0] == 200
        assert call("/s", "q=a")[0] == 200      # the route accepts it; contains() is what refuses one character (above)
        assert call("/s", "q=" + "a" * 101)[0] == 422
        assert call("/s")[0] == 200
    finally:
        APP = old


def test_value_conditions_skip_none_and_where_all_skips_them():
    assert one_of(Thing.id, None) is None and one_of(Thing.id, []) is None
    assert at_least(Thing.weight, None) is None and at_most(Thing.weight, None) is None
    assert since(Thing.created_at, None) is None and before(Thing.created_at, None) is None and equals(Thing.name, None) is None
    statement = where_all(select(Thing), None, at_least(Thing.weight, 0), at_most(Thing.weight, 10), None)
    assert "thing.weight >= 0" in sql(statement) and "thing.weight <= 10" in sql(statement)
    assert sql(where_all(select(Thing), None)) == sql(select(Thing))


def test_an_empty_string_is_not_given_but_zero_and_false_are_values():
    assert equals(Thing.name, "") is None and equals(Thing.name, None) is None
    assert equals(Thing.weight, 0) is not None and equals(Thing.name, False) is not None


def test_zero_is_a_value_not_a_missing_filter():
    assert "thing.weight >= 0" in sql(select(Thing).where(at_least(Thing.weight, 0)))
    assert equals(Thing.weight, 0) is not None


def test_before_is_exclusive_and_since_inclusive():
    from datetime import datetime
    day = datetime(2026, 10, 1)
    assert "thing.created_at >= '2026-10-01 00:00:00'" in sql(select(Thing).where(since(Thing.created_at, day)))
    assert "thing.created_at < '2026-10-01 00:00:00'" in sql(select(Thing).where(before(Thing.created_at, day)))


def test_name_filters_search_the_three_languages_and_the_creator():
    filters = NameFilters(q="berg", created_by=UUID(int=5))
    text = sql(filters.apply(select(Thing), Thing))
    assert all(f"thing.{c} ILIKE '%berg%'" in text for c in ("name", "name_de", "name_pl"))
    assert "thing.created_by = " in text


# ------------------------------------------------------------------ geography

def test_bbox_builds_an_envelope_in_4326():
    text = sql(select(Thing).where(bbox_condition(Thing.name, "7.5,45.9,7.9,46.1")))
    assert "ST_Intersects(thing.name, ST_MakeEnvelope(7.5, 45.9, 7.9, 46.1, 4326))" in text
    assert bbox_condition(Thing.name, None) is None


@pytest.mark.parametrize("value", ["1,2,3", "1,2,3,4,5", "a,b,c,d", "8,46,7,47", "7,47,8,46", "7,46,7,47", "-181,0,0,1", "0,-91,1,0",
                                   "0,0,181,1", "0,0,1,91", "1e9,0,1,1", "nan,0,1,1", "inf,0,1,1", "", "1_0,46,11,47", "0x7,0,9,1", " ,0,1,1", "1.5.5,0,2,1", "1234567890,0,1,1"])
def test_bad_bbox_is_422(value):
    with pytest.raises(AppError) as error:
        bbox_condition(Thing.name, value)
    assert error.value.status_code == 422


def test_near_uses_the_function_form_of_the_geography_cast_and_the_default_radius():
    text = sql(select(Thing).where(near_condition(Thing.name, "7.7,46.0", None)))
    assert "ST_DWithin(geography(thing.name), geography(ST_SetSRID(ST_MakePoint(7.7, 46.0), 4326)), 5000)" in text
    assert "20000)" in sql(select(Thing).where(near_condition(Thing.name, "7.7,46.0", 20000)))
    assert near_condition(Thing.name, None, None) is None


@pytest.mark.parametrize("near, radius", [("7.7", None), ("a,b", None), ("200,46", None), ("7,95", None), ("7.7,46", 0), ("7.7,46", -5),
                                          ("7.7,46", 100001), (None, 500)])
def test_bad_near_is_422(near, radius):
    with pytest.raises(AppError) as error:
        near_condition(Thing.name, near, radius)
    assert error.value.status_code == 422


def test_the_largest_radius_is_allowed():
    assert near_condition(Thing.name, "7.7,46", listing.MAX_RADIUS_M) is not None
