"""Serving an icon: the SVG text as it is stored, or a PNG rendered from it."""
from functools import lru_cache

from fastapi import Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from app.core.utils.responses import AppError

PNG_MIN, PNG_MAX = 16, 1024     # width of a PNG in pixels (the height follows the shape of the icon)

# The SVG is served as a picture only. These headers keep a script in a file (there should be none: the text is cleaned
# when it is stored) from running when somebody opens the URL directly.
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
    "Cache-Control": "private, max-age=3600",
}


@lru_cache(maxsize=512)
def _png(svg: str, size: int) -> bytes:
    import cairosvg

    return cairosvg.svg2png(bytestring=svg.encode("utf-8"), output_width=size)


async def icon_response(request: Request, *, key: str, svg: str, sha256: str, fmt: str, size: int) -> Response:
    # 304 when the browser already has this version (ETag = the SHA-256 of the text, plus the size for a PNG)
    etag = f'"{sha256}"' if fmt == "svg" else f'"{sha256}-{size}"'
    headers = {**SECURITY_HEADERS, "ETag": etag}
    sent = request.headers.get("if-none-match", "")
    if etag in [part.strip().removeprefix("W/") for part in sent.split(",")]:
        return Response(status_code=304, headers=headers)
    if fmt == "png":
        try:
            body = await run_in_threadpool(_png, svg, size)
        except Exception:
            raise AppError(422, "This icon cannot be drawn as a PNG.")
        return Response(body, media_type="image/png", headers={**headers, "Content-Disposition": f'inline; filename="{key}.png"'})
    return Response(svg, media_type="image/svg+xml", headers={**headers, "Content-Disposition": f'inline; filename="{key}.svg"'})
