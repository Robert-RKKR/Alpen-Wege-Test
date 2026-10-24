# Standard library
import re
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

# Third-party
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

# Local application
from app.core.utils.api_paths import TRACK_UPLOAD_PATH, job_url
from app.core.utils.scope import apply_scope
from app.core.utils.upload_limit import UploadSizeLimitMiddleware
from app.explorer.models.models_agg.track import ExplorerAggTrack
from app.main import app
from app.profile.dependencies.current_user import oauth2_scheme

JOB_ID = "11111111-1111-1111-1111-111111111111"
ROOT = Path(__file__).resolve().parents[1]


def test_track_upload_path_is_the_create_track_route():
    # UploadSizeLimitMiddleware matches this exact path; if the route moves, this test fails.
    assert app.url_path_for("create_track") == TRACK_UPLOAD_PATH


def test_upload_guard_is_installed_and_watches_the_create_track_route():
    assert any(m.cls is UploadSizeLimitMiddleware for m in app.user_middleware), "middleware is not registered"
    assert UploadSizeLimitMiddleware(app=None).path == app.url_path_for("create_track")


def test_job_url_is_the_owner_job_route():
    # The Location header of every 202 response must point at a real route.
    assert app.url_path_for("get_my_job", job_id=JOB_ID) == job_url(JOB_ID)


def test_token_url_is_the_login_route():
    # OpenAPI metadata only: the login route takes JSON, so Swagger's own login dialog cannot use it anyway.
    assert oauth2_scheme.model.flows.password.tokenUrl == app.url_path_for("login")


def test_route_files_never_write_an_api_url():
    # URLs come from the routers' prefixes and from core/utils/api_paths.py, never from a string in a route file.
    offenders = [
        str(path.relative_to(ROOT))
        for path in sorted((ROOT / "app").glob("*/routes/**/*.py"))
        if re.search(r"/api/v1", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"hard-coded /api/v1 in: {offenders}"


def _where_clause(scope: str) -> str:
    access = SimpleNamespace(scope=scope, user=SimpleNamespace(id=uuid4()))
    stmt = apply_scope(select(ExplorerAggTrack), ExplorerAggTrack, access)
    return str(stmt.compile(dialect=postgresql.dialect())).partition("WHERE")[2].strip()


def test_apply_scope_filters_by_scope():
    assert _where_clause("all") == ""
    own = _where_clause("own")
    assert "created_by" in own and " OR " not in own
    public = _where_clause("public")
    assert "created_by" in public and "is_public" in public and " OR " in public
