# Standard library
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

# Third-party
from fastapi import Query, Request
from pydantic import AfterValidator
from sqlalchemy import func, or_

# Local application
from app.core.utils.responses import AppError

# (default, maximum) rows per page, exactly as each list had them before the filters came: most lists default to 1000
# with no maximum, the event log defaults to 100, tracks and the two job lists to 100 with a maximum of 500.
PAGE_1000 = (1000, None)
PAGE_100 = (100, None)
PAGE_100_MAX_500 = (100, 500)
MAX_IDS = 50                   # values of one multi-value filter, for example compendium_type_id=a&compendium_type_id=b
MAX_RADIUS_M = 100_000         # near + radius_m
MAX_OFFSET = 1_000_000_000     # limit and offset up to here; larger values overflow the database's integer and would answer 500
NUMBER_RANGE = (-1_000_000_000, 1_000_000_000)   # the integer filters (altitude_min, weight_max, ...): within a 32-bit integer


# ------------------------------------------------------------------ errors

def invalid(field: str, code: str, message: str) -> AppError:
    # the same 422 as FastAPI's own for a wrong query parameter (field "query.limit"), so a client handles one error format
    return AppError(
        422,
        "Validation failed",
        error_message="The request contains 1 invalid field(s). Check error_errors for details.",
        error_errors=[{"field": f"query.{field}", "code": code, "message": message}],
    )


# ------------------------------------------------------------------ values the database cannot take

def reject_nul_characters(request: Request) -> None:
    # PostgreSQL cannot store a NUL character in text; a query with one would answer 500. Unknown parameters are NOT
    # refused: as before, a parameter that a list does not know is ignored.
    for name, value in request.query_params.multi_items():
        if "\x00" in name or "\x00" in value:
            raise invalid(name.replace("\x00", "")[:40], "invalid_character", "A query parameter contains a NUL character.")


# ------------------------------------------------------------------ page

@dataclass(frozen=True)
class Page:
    limit: int
    offset: int


def page_params(profile: tuple[int, int | None] = PAGE_1000, offset_alias: str | None = None):
    # Dependency factory: Depends(page_params(PAGE_100)) adds the documented limit and offset. limit below 1 or offset
    # below 0 (or above 1,000,000,000) answer 422; a list with a maximum lowers a larger limit to it (pagination_limit
    # in the answer says which limit was used), a list without one does not. offset_alias renames the offset parameter
    # (the users list has always called it skip).
    default, maximum = profile
    note = f"Default {default}" + (f", at most {maximum}; a larger value is lowered to {maximum}." if maximum else ".")

    async def _dependency(
        request: Request,
        limit: int = Query(default, ge=1, le=MAX_OFFSET, description=f"Rows per page. {note}"),
        offset: int = Query(0, ge=0, le=MAX_OFFSET, alias=offset_alias, description="Rows to skip. A value behind the last row gives an empty page."),
    ) -> Page:
        reject_nul_characters(request)
        return Page(min(limit, maximum) if maximum else limit, offset)

    return _dependency


# ------------------------------------------------------------------ sort

def _may_be_null(column) -> bool:
    # A column that is NOT NULL needs no NULLS LAST, and writing it would stop PostgreSQL from reading an index in order
    # (measured on 1,000,000 event-log rows: 0.15 ms against 92 ms for the newest 100). An expression counts as nullable.
    try:
        return bool(column.property.columns[0].nullable)   # a mapped attribute
    except AttributeError:
        return bool(getattr(column, "nullable", True))     # a table column, an expression


@dataclass(frozen=True)
class Sort:
    column: object
    descending: bool
    tie_breaker: object | tuple | None   # one column, or several for a list with a composite default order

    def apply(self, stmt):
        # NULLs last in both directions (only where the column can be NULL); the tie breaker (the id) keeps pages stable
        # when many rows share a value
        order = self.column.desc() if self.descending else self.column.asc()
        if _may_be_null(self.column):
            order = order.nulls_last()
        ties = () if self.tie_breaker is None else self.tie_breaker if isinstance(self.tie_breaker, tuple) else (self.tie_breaker,)
        return stmt.order_by(order, *ties)


def sort_params(options: dict, default: str, tie_breaker=None):
    # Dependency factory: options maps a public name to a column or expression, default is "name" or "-created_at".
    # ?sort=name sorts ascending, ?sort=-name descending; one field; a name that is not in options answers 422.
    names = ", ".join(options)

    async def _dependency(
        sort: str | None = Query(None, description=f"Sort field; a leading '-' sorts descending. One of: {names}. Default {default}."),
    ) -> Sort:
        value = sort or default
        name = value[1:] if value.startswith("-") else value
        if name not in options:
            raise invalid("sort", "invalid_sort", f"Cannot sort by '{name[:40]}'. Allowed: {names}.")
        return Sort(options[name], value.startswith("-"), tie_breaker)

    return _dependency


# ------------------------------------------------------------------ filter building blocks

def search_query(what: str):
    return Query(None, max_length=100, description=f"Text search: {what}, not case sensitive, at least 2 characters (empty: no search).")


def number_query(what: str):
    # an integer filter, limited to what a 32-bit database column can compare (a larger number would answer 500)
    return Query(None, ge=NUMBER_RANGE[0], le=NUMBER_RANGE[1], description=what)


def _moment(value: datetime | None) -> datetime | None:
    if value is not None and not 1900 <= value.year <= 2200:
        raise ValueError("The year must be between 1900 and 2200.")   # the database driver fails on the year 10000 and answers 500
    return value


def moment_query(what: str):
    # a date or time filter: `created_from: moment_query("Created at or after this date or time.") = None`. Give a time zone
    # (2026-10-01T00:00:00Z); without one the time zone of the database session applies. The validator lives in the
    # Annotated type together with the Query, because FastAPI ignores it next to a `= Query(...)` default.
    return Annotated[datetime | None, AfterValidator(_moment), Query(description=what)]


def ids_query(what: str):
    return Query(None, max_length=MAX_IDS, description=f"{what}. Repeat the parameter for several values (at most {MAX_IDS}).")


def escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def contains(text: str | None, *columns):
    # text appears in one of the columns; the characters % and _ of the text are not wildcards
    if text is None or not text.strip():
        return None   # an empty search box means no search
    text = text.strip()
    if len(text) < 2:
        raise invalid("q", "too_short", "The search text needs at least 2 characters.")
    pattern = f"%{escape_like(text)}%"
    return or_(*(column.ilike(pattern, escape="\\") for column in columns))


def one_of(column, values: list[UUID] | None):
    return column.in_(values) if values else None


def at_least(column, value):
    return column >= value if value is not None else None


def at_most(column, value):
    return column <= value if value is not None else None


def since(column, value: datetime | None):
    return column >= value if value is not None else None


def before(column, value: datetime | None):
    # exclusive, so that created_from=day1&created_to=day2 does not return the first moment of day2 twice
    return column < value if value is not None else None


def equals(column, value):
    # None and "" (a form field left empty) mean: not given. 0 and False are values.
    return column == value if value is not None and value != "" else None


def where_all(stmt, *conditions):
    for condition in conditions:
        if condition is not None:
            stmt = stmt.where(condition)
    return stmt


# ------------------------------------------------------------------ geography

_NUMBER = re.compile(r"-?\d{1,7}(\.\d{1,15})?")   # plain decimals only: no 1e9, no 1_0, no nan, no inf


def _numbers(field: str, value: str, count: int) -> list[float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != count or not all(_NUMBER.fullmatch(part) for part in parts):
        raise invalid(field, f"invalid_{field}", f"{field} needs {count} numbers separated by commas.")
    return [float(part) for part in parts]


def _check_point(field: str, lon: float, lat: float) -> None:
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise invalid(field, f"invalid_{field}", "Longitude must be between -180 and 180 and latitude between -90 and 90.")


def bbox_condition(column, value: str | None):
    # bbox=min_lon,min_lat,max_lon,max_lat (west, south, east, north); uses the GiST index of the column
    if value is None:
        return None
    west, south, east, north = _numbers("bbox", value, 4)
    _check_point("bbox", west, south)
    _check_point("bbox", east, north)
    if west >= east or south >= north:
        raise invalid("bbox", "invalid_bbox", "bbox must go from west to east and from south to north (a box over the 180th meridian: ask twice).")
    return func.ST_Intersects(column, func.ST_MakeEnvelope(west, south, east, north, 4326))


def near_condition(column, near: str | None, radius_m: int | None):
    # near=lon,lat with radius_m (default 5000, at most 100000) in metres; uses the index on (column)::geography
    if near is None:
        if radius_m is not None:
            raise invalid("radius_m", "needs_near", "radius_m can only be used together with near.")
        return None
    lon, lat = _numbers("near", near, 2)
    _check_point("near", lon, lat)
    radius = 5000 if radius_m is None else radius_m
    if not 1 <= radius <= MAX_RADIUS_M:
        raise invalid("radius_m", "invalid_radius_m", f"radius_m must be between 1 and {MAX_RADIUS_M}.")
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
    # geography(x) is the function behind x::geography, so the planner finds the index on (location)::geography; a
    # SQLAlchemy cast() to Geography writes geography(Geometry,4326) and gets a full scan (measured: 54 ms against 5 ms)
    return func.ST_DWithin(func.geography(column), func.geography(point), radius)


# ------------------------------------------------------------------ the filters shared by the reference tables

class NameFilters:
    # q and created_by: the filters of every lookup table (the 19 tables of core and the like)
    def __init__(
        self,
        q: str | None = search_query("name in English, German or Polish"),
        created_by: UUID | None = Query(None, description="Rows created by this user."),
    ):
        self.q = q
        self.created_by = created_by

    def apply(self, stmt, model):
        return where_all(stmt, contains(self.q, model.name, model.name_de, model.name_pl), equals(model.created_by, self.created_by))
