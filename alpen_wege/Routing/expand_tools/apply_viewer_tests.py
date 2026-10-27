#!/usr/bin/env python
"""Tests and live check for option B of decision 2 (see apply_viewer.py). Run after apply_viewer.py, same copy.

    python apply_viewer_tests.py REPO_COPY
"""
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()


def stop(message):
    raise SystemExit(f"STOP: {message}")


def sub_once(path: Path, old: str, new: str):
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        stop(f"{path.name}: expected exactly one of {old!r}, found {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8", newline="\n")


wiring = ROOT / "tests/test_expand_wiring.py"
sub_once(wiring, "from app.profile.schemas.user_read import ExpandedUser, UserRead",
         "from app.profile.schemas.user_read import ExpandedUser, UserExpandedRead, UserRead")
sub_once(wiring, "    UserRead: ProfileUsrUser,\n}", "    ExpandedUser: ProfileUsrUser,\n}")
sub_once(wiring, "    assert ExpandedUser is UserRead\n",
         "    assert ExpandedUser is UserExpandedRead and issubclass(ExpandedUser, UserRead)\n")

(ROOT / "tests/test_expand_user.py").write_text('''# Standard library
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
''', encoding="utf-8", newline="\n")

check = ROOT / "scripts/expand_check.py"
sub_once(check, '''r = call("GET", f"/compendium/pois/{pid}", "guest", params={"expand": "created_by"})
check("poi, guest with expand=created_by: 200 and the full user profile (the accepted visibility rule)",
      r.status_code == 200 and isinstance(body(r)["created_by_user"].get("email"), str), r.text[:200])
''', '''r = call("GET", f"/compendium/pois/{pid}", "guest", params={"expand": "created_by"})
check("poi, guest with expand=created_by: 200, only id and username of the creator, the profile fields are null",
      r.status_code == 200 and body(r)["created_by_user"]["username"] and body(r)["created_by_user"]["email"] is None
      and body(r)["created_by_user"]["birth_date"] is None and body(r)["created_by_user"]["max_heart_rate"] is None, r.text[:300])
r = call("GET", f"/compendium/pois/{pid}", "admin", params={"expand": "created_by"})
check("poi, administrator with expand=created_by: the whole profile", isinstance(body(r)["created_by_user"]["email"], str))
mine = call("POST", "/compendium/countries", "editor", json={
    "name": f"ZZ Editor {uuid.uuid4().hex[:6]}", "iso_code": uuid.uuid4().hex[:2].upper() + "Y",
    "location": {"type": "Point", "coordinates": [10.0, 47.0]}})
mid = body(mine)["id"]
created.append(f"/compendium/countries/{mid}")
check("country made by the editor: the editor sees his own whole profile, the guest sees only id and username",
      isinstance(body(call("GET", f"/compendium/countries/{mid}", "editor", params={"expand": "created_by"}))["created_by_user"]["email"], str)
      and body(call("GET", f"/compendium/countries/{mid}", "guest", params={"expand": "created_by"}))["created_by_user"]["email"] is None)
''')
print("done: tests and live check of option B")
