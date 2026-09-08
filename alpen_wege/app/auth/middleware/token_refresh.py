# Standard library
from datetime import datetime, timezone

# Third-party
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Local application
from app.auth.services.jwt import blacklist_token, create_access_token


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

        # Only rotate when a user was authenticated and the request succeeded
        # (<400).
        user_id = getattr(request.state, "authenticated_user_id", None)
        if user_id and response.status_code < 400:
            # Pull the current token's id/expiry and the user's group from
            # request state.
            old_jti = request.state.old_jti
            old_exp = request.state.old_token_exp
            user_group = request.state.authenticated_user_group

            # Issue a replacement token for the same user.
            new_token = create_access_token(user_id, user_group)

            # Revoke the old token for whatever lifetime it had left (avoid
            # reuse).
            remaining = old_exp - int(datetime.now(timezone.utc).timestamp())
            if remaining > 0:
                await blacklist_token(old_jti, remaining)

            # Hand the new token back to the client via a response header.
            response.headers["X-Access-Token"] = new_token

        return response
