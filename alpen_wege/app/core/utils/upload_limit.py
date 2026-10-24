# Standard library
import json

# Local application
from app.config import get_settings
from app.core.utils.api_paths import TRACK_UPLOAD_PATH


class UploadSizeLimitMiddleware:
    def __init__(self, app):
        self.app = app
        settings = get_settings()
        self.max_bytes = (settings.GPX_MAX_UPLOAD_MB + 1) * 1024 * 1024
        self.path = TRACK_UPLOAD_PATH

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"] == self.path
        ):
            headers = dict(scope.get("headers", []))
            cl = headers.get(b"content-length")
            if cl and int(cl) > self.max_bytes:
                body = json.dumps({
                    "code": 413,
                    "status": "error",
                    "message": f"File too large (maximum {get_settings().GPX_MAX_UPLOAD_MB} MB).",
                    "data": None,
                }).encode()
                await send({
                    "type": "http.response.start",
                    "status": 413,
                    "headers": [
                        [b"content-type", b"application/json"],
                        [b"content-length", str(len(body)).encode()],
                    ],
                })
                await send({
                    "type": "http.response.body",
                    "body": body,
                })
                return

        await self.app(scope, receive, send)
