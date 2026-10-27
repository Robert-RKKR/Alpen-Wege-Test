# Standard library
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, get_args, get_origin

# Third-party
from fastapi import Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import selectinload

# Local application
from app.core.utils.responses import AppError

MAX_DEPTH = 3      # longest dotted path, for example poi.main_region.country
MAX_LINKS = 10     # distinct links in one request; a parent shared by several paths counts once
MAX_LENGTH = 1000  # longest ?expand= value (10 links of 3 levels with long names need about 700 characters)


def Link(expand_name: str | None = None) -> Any:
    # Marks a field of a *Detail schema as an expandable link. The field is typed "<DetailSchema> | None" and stays
    # None unless the caller asks for it with ?expand=<name>. expand_name is the public name when it differs from
    # the field name (created_by_user is asked for as "created_by").
    extra: dict[str, Any] = {"x-expand": True}
    if expand_name:
        extra["x-expand-name"] = expand_name
    return Field(default=None, json_schema_extra=extra)


@dataclass(frozen=True)
class _LinkInfo:
    attr: str                 # field name in the schema == attribute name on the ORM object
    public: str               # name accepted in ?expand=
    target: type[BaseModel]   # schema of the linked object


def _target_schema(schema, name, annotation) -> type[BaseModel]:
    for arg in get_args(annotation) or (annotation,):
        if isinstance(arg, type) and get_origin(arg) is None and issubclass(arg, BaseModel):   # list[X] is not a model
            return arg
    raise TypeError(
        f"{schema.__name__}.{name} is marked Link() but its type {annotation!r} is not a single pydantic model "
        f"(a list of models is not supported; an unresolved forward reference? call {schema.__name__}.model_rebuild())."
    )


@lru_cache(maxsize=None)
def links_of(schema: type[BaseModel]) -> dict[str, _LinkInfo]:
    # public name -> link, for every Link() field of the schema
    found: dict[str, _LinkInfo] = {}
    for name, info in schema.model_fields.items():
        extra = info.json_schema_extra
        if not isinstance(extra, dict) or not extra.get("x-expand"):
            continue
        public = extra.get("x-expand-name") or name
        if public in found:
            raise ValueError(f"{schema.__name__}: two links are asked for as {public!r}")
        found[public] = _LinkInfo(name, public, _target_schema(schema, name, info.annotation))
    return found


@dataclass
class _Node:
    link: _LinkInfo
    children: dict[str, "_Node"] = field(default_factory=dict)


def _bad(message: str) -> AppError:
    return AppError(
        400,
        "Bad request",
        error_message=message,
        error_errors=[{"field": "expand", "code": "invalid_expand", "message": message}],
    )


def _short(text: str) -> str:
    # an error message never repeats a long input
    return text if len(text) <= 60 else text[:57] + "..."


def _count(tree: dict[str, _Node]) -> int:
    return sum(1 + _count(node.children) for node in tree.values())


def _option(model: type, node: _Node):
    # selectinload for one link; its sub-links become nested options
    option = selectinload(getattr(model, node.link.attr))
    if node.children:
        child_model = sa_inspect(model).relationships[node.link.attr].mapper.class_
        option = option.options(*[_option(child_model, child) for child in node.children.values()])
    return option


def _render(schema: type[BaseModel], obj: Any, tree: dict[str, _Node], extra: dict[str, Any]) -> dict[str, Any]:
    # A plain dict of the schema's fields. Only requested links are read from the object, so a relationship that
    # was not loaded (lazy="raise") is never touched, and a row that two paths share cannot leak into the wrong one.
    by_attr = {info.attr: info for info in links_of(schema).values()}
    out: dict[str, Any] = {}
    for name in schema.model_fields:
        if name in extra:
            out[name] = extra[name]
            continue
        info = by_attr.get(name)
        if info is None:
            out[name] = getattr(obj, name)
            continue
        node = tree.get(info.public)
        child = getattr(obj, name) if node is not None else None
        out[name] = None if child is None else _render(info.target, child, node.children, {})
    for name, value in extra.items():
        out.setdefault(name, value)
    return out


@dataclass
class ExpandPlan:
    schema: type[BaseModel]
    tree: dict[str, _Node]

    @classmethod
    def parse(cls, schema: type[BaseModel], expand: str | None) -> "ExpandPlan":
        # Checks ?expand= against the schema and builds the tree of links. Raises AppError 400 for an unknown name,
        # a path deeper than MAX_DEPTH and more than MAX_LINKS distinct links.
        if expand is not None and len(expand) > MAX_LENGTH:
            raise _bad(f"The expand value is longer than {MAX_LENGTH} characters.")
        tree: dict[str, _Node] = {}
        for raw in (expand or "").split(","):
            path = raw.strip()
            if not path:
                continue
            parts = [part.strip() for part in path.split(".")]
            if len(parts) > MAX_DEPTH:
                raise _bad(f"'{_short(path)}' is {len(parts)} levels deep; the maximum is {MAX_DEPTH}.")
            level, current = tree, schema
            for part in parts:
                links = links_of(current)
                link = links.get(part)
                if link is None:
                    allowed = ", ".join(sorted(links)) or "(nothing)"
                    raise _bad(f"Cannot expand '{_short(part)}' in '{_short(path)}'. Allowed at this level: {allowed}.")
                node = level.setdefault(part, _Node(link))
                level, current = node.children, link.target
        total = _count(tree)
        if total > MAX_LINKS:
            raise _bad(f"{total} links requested; the maximum is {MAX_LINKS}.")
        return cls(schema, tree)

    def load_options(self, model: type) -> list:
        # Options for select(model).options(*...): one extra SELECT per requested link.
        return [_option(model, node) for node in self.tree.values()]

    def render(self, obj: Any, **extra: Any) -> dict[str, Any]:
        # Object -> dict for the response model; links that were not requested are None. extra gives values for
        # fields the object does not have (computed fields) and keys that a schema validator reads.
        return _render(self.schema, obj, self.tree, extra)


def expand_plan(schema: type[BaseModel]):
    # Dependency factory: Depends(expand_plan(PoiDetail)) adds the documented ?expand= query parameter and gives the
    # route the checked ExpandPlan.
    names = ", ".join(sorted(links_of(schema))) or "none"
    description = (
        "Comma-separated links to return as full objects instead of only their IDs. "
        f"Allowed: {names}. Nest with dots, up to {MAX_DEPTH} levels (for example a.b.c). "
        f"At most {MAX_LINKS} links per request."
    )

    async def _dependency(expand: str | None = Query(None, description=description)) -> ExpandPlan:
        return ExpandPlan.parse(schema, expand)

    return _dependency
