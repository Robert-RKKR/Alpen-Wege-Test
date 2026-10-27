# Standard library
from types import SimpleNamespace
from uuid import UUID

# Third-party
import pytest

# Local application
from app.explorer.services.visibility import in_use_error, must_stay_public, not_private_error, visible

ME, OTHER, THIRD = UUID(int=1), UUID(int=2), UUID(int=3)


def user(name, created_by, is_public=False):
    return SimpleNamespace(name=name, created_by=created_by, is_public=is_public)


@pytest.mark.parametrize("scope,created_by,is_public,expected", [
    ("all", OTHER, False, True),          # an administrator sees everything
    ("all", ME, False, True),
    ("own", ME, False, True),             # own: only what he made
    ("own", OTHER, True, False),
    ("own", OTHER, False, False),
    ("public", ME, False, True),          # public: his own and what is public
    ("public", OTHER, True, True),
    ("public", OTHER, False, False),
    (None, ME, True, False),              # no permission at all: nothing
    (None, OTHER, True, False),
])
def test_who_sees_what(scope, created_by, is_public, expected):
    assert visible(scope, ME, created_by, is_public) is expected


def test_the_conflict_names_only_what_the_caller_may_see():
    users = [user("My route", ME), user("Public route", OTHER, True), user("Secret route", OTHER)]
    error = in_use_error("segment", "route", users, "public", ME)
    text = error.error_message
    assert error.status_code == 409 and "used by 3 route(s)" in text
    assert "My route" in text and "Public route" in text and "Secret route" not in text and "1 more" in text
    assert error.error_errors[0]["code"] == "in_use"


def test_the_conflict_counts_but_names_nothing_when_nothing_is_visible():
    users = [user("Secret A", OTHER), user("Secret B", THIRD)]
    error = in_use_error("segment", "route", users, "own", ME)
    assert "used by 2 route(s)" in error.error_message and "Secret" not in error.error_message and "cannot see" in error.error_message


def test_an_administrator_sees_every_name():
    users = [user("Secret A", OTHER), user("Secret B", THIRD)]
    assert "Secret A, Secret B" in in_use_error("route", "journey", users, "all", ME).error_message


def test_a_caller_without_read_permission_sees_no_names():
    assert "Secret" not in in_use_error("segment", "route", [user("Secret", ME)], None, ME).error_message


def test_the_list_of_names_is_cut_at_twenty():
    users = [user(f"R{i:02d}", ME) for i in range(30)]
    text = in_use_error("segment", "route", users, "all", ME).error_message
    assert "R19" in text and "R20" not in text and "used by 30" in text


def test_what_forces_a_segment_to_stay_public():
    # another user's route, or any public route, keeps the segment public; the owner's own private routes do not
    assert must_stay_public([], ME) == 0
    assert must_stay_public([user("a", ME)], ME) == 0
    assert must_stay_public([user("a", ME), user("b", ME)], ME) == 0
    assert must_stay_public([user("a", OTHER)], ME) == 1
    assert must_stay_public([user("a", ME, True)], ME) == 1
    assert must_stay_public([user("a", ME), user("b", OTHER), user("c", ME, True)], ME) == 2


def test_the_not_private_conflict():
    error = not_private_error("segment", "route", 2)
    assert error.status_code == 409 and error.error_errors[0]["field"] == "is_public" and "2 route(s)" in error.error_message
