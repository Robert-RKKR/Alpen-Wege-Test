# Standard library
import json

# Local application
from app.config import get_settings
from app.core.utils.api_paths import SEGMENT_UPLOAD_PATH, TRACK_UPLOAD_PATH


class UploadSizeLimitMiddleware:
    def __init__(self, app):
        self.app = app
        settings = get_settings()
        self.max_bytes = (settings.GPX_MAX_UPLOAD_MB + 1) * 1024 * 1024
        self.path = TRACK_UPLOAD_PATH
        # path -> (largest body in bytes, limit in MB for the message); a request bigger than the file limit plus 1 MB of form is refused
        self.limits = {
            TRACK_UPLOAD_PATH: (self.max_bytes, settings.GPX_MAX_UPLOAD_MB),
            SEGMENT_UPLOAD_PATH: ((settings.SEGMENT_GPX_MAX_UPLOAD_MB + 1) * 1024 * 1024, settings.SEGMENT_GPX_MAX_UPLOAD_MB),
        }

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] == "http"
            and scope["method"] == "POST"
            and scope["path"] in self.limits
        ):
            max_bytes, max_mb = self.limits[scope["path"]]
            headers = dict(scope.get("headers", []))
            cl = headers.get(b"content-length")
            if cl and cl.isdigit() and int(cl) > max_bytes:
                body = json.dumps({
                    "code": 413,
                    "status": "error",
                    "message": f"File too large (maximum {max_mb} MB).",
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
