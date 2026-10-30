"""Reads an uploaded SVG file for the create and replace routes and returns the cleaned copy."""
import re

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from app.assets.services.icon_svg import CleanSvg, InvalidSvg, clean_svg, default_max_bytes
from app.config import get_settings
from app.core.utils.responses import AppError


async def read_clean_svg(file: UploadFile) -> CleanSvg:
    limit = default_max_bytes()
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise AppError(413, f"File too large (maximum {get_settings().ICON_MAX_UPLOAD_KB} KB).")
    try:
        return await run_in_threadpool(clean_svg, raw, limit)
    except InvalidSvg as exc:
        raise AppError(400, f"Not a usable SVG file: {exc}.")


def key_from_filename(filename: str | None) -> str:
    # "Flag AT.svg" -> "flag_at"; may be empty when nothing usable is left
    stem = (filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = stem[:-4] if stem.lower().endswith(".svg") else stem
    return re.sub(r"[^a-z0-9_.-]+", "_", stem.lower()).strip("_")[:100]
