# Standard library
import ast
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

# Local application
from app.profile.schemas.user_read import UserExpandedRead

ROOT = Path(__file__).resolve().parents[1]


def _data(user_id):
    return {"id": user_id, "username": "u", "email": "u@example.com", "first_name": "A", "last_name": "B",
            "middle_name": None, "gender": "male", "birth_date": date(1990, 1, 1), "height_cm": 180,
            "max_heart_rate": 190, "resting_heart_rate": 50, "is_active": True,
            "created_at": datetime(2026, 1, 1), "last_active_at": None, "user_group": "viewer"}


def test_an_administrator_sees_the_whole_profile():
    data = _data(uuid4())
    assert UserExpandedRead.redact(dict(data), SimpleNamespace(id=uuid4(), user_group="administrator")) == data


def test_the_user_himself_sees_the_whole_profile():
    data = _data(uuid4())
    assert UserExpandedRead.redact(dict(data), SimpleNamespace(id=data["id"], user_group="guest")) == data


def test_everybody_else_sees_only_id_and_username():
    data = _data(uuid4())
    out = UserExpandedRead.redact(dict(data), SimpleNamespace(id=uuid4(), user_group="editor"))
    assert out["id"] == data["id"] and out["username"] == "u"
    assert all(value is None for key, value in out.items() if key not in ("id", "username"))
    UserExpandedRead(**out)    # the reduced answer still validates against the response schema


def test_no_viewer_means_the_reduced_answer():
    data = _data(uuid4())
    assert UserExpandedRead.redact(dict(data), None)["email"] is None


def test_every_route_passes_the_caller_to_render():
    # plan.render(..., viewer=...) decides which user fields an expanded user shows. A forgotten viewer only hides
    # fields, but it is a mistake all the same.
    missing = []
    for path in sorted((ROOT / "app").glob("*/routes/**/*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "render"
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "plan"
                    and not any(keyword.arg == "viewer" for keyword in node.keywords)):
                missing.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not missing, missing
