# Standard library
import asyncio
import inspect
import random
from types import SimpleNamespace

# Third-party
import pytest
from pydantic import BaseModel, create_model

# Local application
from app.core.utils.expand import MAX_DEPTH, MAX_LENGTH, MAX_LINKS, ExpandPlan, Link, expand_plan, links_of
from app.core.utils.responses import AppError


class D(BaseModel):
    id: int


class C(BaseModel):
    id: int
    d: D | None = Link()


class B(BaseModel):
    id: int
    c: C | None = Link()
    d2: D | None = Link()


class A(BaseModel):
    id: int
    name: str
    b: B | None = Link()
    c: C | None = Link()
    creator: D | None = Link("created_by")


# MAX_LINKS + 1 links named l0, l1, ...
Wide = create_model("Wide", id=(int, ...), **{f"l{i}": (D | None, Link()) for i in range(MAX_LINKS + 1)})


def _names(tree):
    return {name: _names(node.children) for name, node in tree.items()}


def _bad(expand, schema=A):
    with pytest.raises(AppError) as caught:
        ExpandPlan.parse(schema, expand)
    return caught.value


def test_nothing_requested_gives_an_empty_plan():
    for value in (None, "", "  ", ",", " , ,"):
        plan = ExpandPlan.parse(A, value)
        assert plan.tree == {} and plan.load_options(object) == []


def test_one_name_and_a_path_of_the_maximum_depth():
    assert _names(ExpandPlan.parse(A, "b").tree) == {"b": {}}
    assert MAX_DEPTH == 3
    assert _names(ExpandPlan.parse(A, "b.c.d").tree) == {"b": {"c": {"d": {}}}}


def test_a_path_one_level_too_deep_is_refused_before_its_names_are_read():
    error = _bad("b.c.d.x")
    assert error.status_code == 400 and "levels" in error.error_message


def test_paths_are_merged_into_one_tree():
    tree = ExpandPlan.parse(A, "b.c,b.d2,c").tree
    assert _names(tree) == {"b": {"c": {}, "d2": {}}, "c": {}}


def test_the_public_name_can_differ_from_the_field_name():
    plan = ExpandPlan.parse(A, "created_by")
    assert plan.tree["created_by"].link.attr == "creator"
    assert "created_by" in _bad("creator").error_message      # the field name is not the public name


def test_an_unknown_name_lists_the_allowed_names_of_that_level():
    message = _bad("zzz").error_message
    assert "Allowed at this level: b, c, created_by." in message
    assert "Allowed at this level: c, d2." in _bad("b.zzz").error_message


def test_plain_fields_cannot_be_expanded():
    assert _bad("id").status_code == 400 and _bad("name").status_code == 400


def test_malformed_paths_are_refused():
    for value in ("b.", ".b", "b..c", "b,,.c"):
        assert _bad(value).status_code == 400, value


def test_whitespace_and_repeated_names_count_once():
    assert _names(ExpandPlan.parse(A, " b , b.c , b ").tree) == {"b": {"c": {}}}


def test_the_limit_counts_distinct_links():
    ok = ",".join(f"l{i}" for i in range(MAX_LINKS))
    assert len(ExpandPlan.parse(Wide, ok).tree) == MAX_LINKS
    error = _bad(ok + f",l{MAX_LINKS}", Wide)
    assert error.status_code == 400 and f"maximum is {MAX_LINKS}" in error.error_message


def test_an_error_has_the_standard_shape():
    error = _bad("zzz")
    assert error.response_message == "Bad request"
    assert error.error_errors[0]["field"] == "expand" and error.error_errors[0]["code"] == "invalid_expand"


def test_a_link_must_be_typed_as_a_model():
    class Bad(BaseModel):
        x: int | None = Link()

    with pytest.raises(TypeError, match="Bad.x"):
        links_of(Bad)


def _obj():
    d = SimpleNamespace(id=1)
    c = SimpleNamespace(id=2, d=d)
    b = SimpleNamespace(id=3, c=c, d2=d)
    return SimpleNamespace(id=4, name="a", b=b, c=c, creator=d)


def test_render_without_a_request_leaves_every_link_none():
    out = ExpandPlan.parse(A, None).render(_obj())
    assert out == {"id": 4, "name": "a", "b": None, "c": None, "creator": None}


def test_render_fills_only_the_requested_links():
    out = ExpandPlan.parse(A, "b.c").render(_obj())
    assert out["b"]["c"] == {"id": 2, "d": None}      # c is filled, its own link d is not
    assert out["b"]["d2"] is None                       # loaded on the object, but not asked for
    assert out["c"] is None and out["creator"] is None


def test_render_gives_none_for_a_requested_link_that_is_empty():
    obj = _obj()
    obj.creator = None
    assert ExpandPlan.parse(A, "created_by").render(obj)["creator"] is None


def test_render_never_reads_a_link_that_was_not_requested():
    # An unloaded relationship (lazy="raise") raises when it is read.
    class Trap(SimpleNamespace):
        @property
        def b(self):
            raise RuntimeError("relationship read although it was not requested")

    obj = Trap(id=4, name="a", c=None, creator=None)
    assert ExpandPlan.parse(A, "created_by").render(obj)["b"] is None


def test_render_takes_extra_values_for_computed_fields_and_validator_keys():
    obj = SimpleNamespace(id=4, b=None, c=None, creator=None)      # no name attribute
    out = ExpandPlan.parse(A, None).render(obj, name="given", extra_key=1)
    assert out["name"] == "given" and out["extra_key"] == 1


def test_the_dependency_documents_the_allowed_names_and_checks_the_value():
    dependency = expand_plan(A)
    assert "b, c, created_by" in inspect.signature(dependency).parameters["expand"].default.description
    assert asyncio.run(dependency("b")).tree.keys() == {"b"}
    with pytest.raises(AppError):
        asyncio.run(dependency("zzz"))


def test_a_value_that_is_too_long_is_refused_and_a_long_name_is_not_repeated_in_full():
    error = _bad("b," * (MAX_LENGTH // 2 + 1))
    assert error.status_code == 400 and f"longer than {MAX_LENGTH}" in error.error_message
    assert len(_bad("x" * 500 + ".b").error_message) < 400


def test_two_links_with_the_same_public_name_are_refused():
    class Twice(BaseModel):
        x: D | None = Link("same")
        y: D | None = Link("same")

    with pytest.raises(ValueError, match="same"):
        links_of(Twice)


def test_a_link_to_a_list_of_models_is_refused_with_a_clear_message():
    class Many(BaseModel):
        items: list[D] | None = Link()

    with pytest.raises(TypeError, match="list of models"):
        links_of(Many)


def test_random_input_gives_a_plan_or_a_400_and_nothing_else():
    rng = random.Random(7)
    alphabet = "abcd.,_ -%\x00éB"
    for _ in range(500):
        value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 80)))
        try:
            ExpandPlan.parse(A, value)
        except AppError as error:
            assert error.status_code == 400, value
