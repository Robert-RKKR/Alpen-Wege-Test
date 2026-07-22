from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth.services.jwt import blacklist_token, create_access_token


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        user_id = getattr(request.state, "authenticated_user_id", None)
        if user_id and response.status_code < 400:
            old_jti = request.state.old_jti
            old_exp = request.state.old_token_exp
            user_group = request.state.authenticated_user_group

            new_token = create_access_token(user_id, user_group)

            remaining = old_exp - int(datetime.now(timezone.utc).timestamp())
            if remaining > 0:
                await blacklist_token(old_jti, remaining)

            response.headers["X-Access-Token"] = new_token

        return response
