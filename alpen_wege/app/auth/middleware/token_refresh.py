# Standard library
from datetime import datetime, timezone

# Third-party
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Local application
from app.auth.services.jwt import blacklist_token, create_access_token
from app.config import get_settings

settings = get_settings()


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    # Middleware that transparently rotates a user's access token on every
    # successful authenticated request, issuing a fresh token and revoking the
    # old one.
    async def dispatch(self, request: Request, call_next) -> Response:
        # Handle a request and, for authenticated calls, attach a rotated
        # token.
        # Params:
        #   request: the incoming Starlette request (auth deps populate
        # request.state).
        #   call_next: callable that runs the rest of the middleware/route
        # chain.
        # Returns: the response, with an X-Access-Token header when a token was
        # rotated.
        # Run the downstream handler first so auth dependencies populate
        # request.state.
        response = await call_next(request)

        user_id = getattr(request.state, "authenticated_user_id", None)
        if user_id and response.status_code < 400:
            old_jti = request.state.old_jti
            old_exp = request.state.old_token_exp
            user_group = request.state.authenticated_user_group

            now_ts = int(datetime.now(timezone.utc).timestamp())
            remaining = old_exp - now_ts
            total_lifetime = settings.JWT_EXPIRE_MINUTES * 60

            # Only rotate when less than half the token's lifetime remains.
            if remaining < total_lifetime / 2:
                new_token = create_access_token(user_id, user_group)
                if remaining > 0:
                    await blacklist_token(old_jti, remaining)
                response.headers["X-Access-Token"] = new_token

        return response
