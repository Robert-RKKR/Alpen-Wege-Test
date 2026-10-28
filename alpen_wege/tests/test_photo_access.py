import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest

from app.assets.services import photo_access
from app.core.utils.responses import AppError

ROOT = Path(__file__).resolve().parents[1]
ME, OTHER = uuid4(), uuid4()


class FakeDb:
    def __init__(self, photo):
        self.photo = photo

    async def get(self, model, pk):
        return self.photo if self.photo is not None and self.photo.id == pk else None


@pytest.fixture(autouse=True)
def _restore_scope_of(monkeypatch):
    monkeypatch.setattr(photo_access, "scope_of", photo_access.scope_of)


def run(scope, photo, photo_id=None):
    async def scope_of(db, user, key, action):
        assert (key, action) == ("photo", "read")
        return scope
    photo_access.scope_of = scope_of
    db = FakeDb(photo)
    return asyncio.run(photo_access.check_photo_link(db, NS(id=ME), photo_id if photo_id is not None else photo.id))


def photo(owner, public):
    return NS(id=uuid4(), created_by=owner, is_public=public)


@pytest.mark.parametrize("scope,owner,public,allowed", [
    ("all", OTHER, False, True),
    ("public", OTHER, True, True),
    ("public", OTHER, False, False),     # somebody else's private photo
    ("own", ME, False, True),
    ("own", OTHER, True, False),
    (None, ME, True, False),             # no read permission on photos at all
])
def test_link_only_to_a_photo_the_user_may_read(scope, owner, public, allowed):
    p = photo(owner, public)
    if allowed:
        run(scope, p)
    else:
        with pytest.raises(AppError) as e:
            run(scope, p)
        assert e.value.status_code == 422
        assert e.value.error_errors[0]["field"] == "main_photo_id"


def test_unknown_photo_is_rejected_like_a_private_one():
    with pytest.raises(AppError) as e:
        run("all", photo(ME, True), photo_id=uuid4())
    assert e.value.status_code == 422


def test_no_photo_is_always_fine():
    asyncio.run(photo_access.check_photo_link(FakeDb(None), NS(id=ME), None))


def test_csv_check_turns_the_error_into_a_row_error(monkeypatch):
    async def scope_of(db, user, key, action):
        return "own"
    monkeypatch.setattr(photo_access, "scope_of", scope_of)
    p = photo(OTHER, True)
    check = photo_access.csv_photo_check(FakeDb(p), NS(id=ME))
    with pytest.raises(ValueError):
        asyncio.run(check({"main_photo_id": p.id}))
    asyncio.run(check({"name": "no photo"}))


@pytest.mark.parametrize("entity", ["card", "poi", "post"])
def test_every_write_path_of_a_model_with_a_photo_checks_it(entity):
    folder = ROOT / "app" / "compendium" / "routes" / entity
    assert "check_photo_link(db, access.user, body.main_photo_id)" in (folder / "create.py").read_text()
    assert "check_photo_link(db, access.user," in (folder / "update.py").read_text()
    assert "row_check=csv_photo_check(db, access.user)" in (folder / "upload_csv.py").read_text()
