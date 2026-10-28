import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from app.config import get_settings

MAX_SIDE_PX = 2560
JPEG_QUALITY = 88
_FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}
MEDIA_TYPES = {ext: mime for ext, mime in _FORMATS.values()}


class NotAnImage(Exception):
    pass


@dataclass
class StoredPhoto:
    relative_path: str
    sha256: str
    size_bytes: int
    width: int
    height: int
    taken_at: datetime | None
    lon: float | None
    lat: float | None
    altitude_m: int | None


def storage_root() -> Path:
    return Path(get_settings().PHOTO_STORAGE_DIR)


def resolve_path(relative: str) -> Path:
    root = storage_root().resolve()
    full = (root / relative).resolve()
    if root not in full.parents:
        raise ValueError("Path escapes storage root")
    return full


def _rational(v) -> float:
    return float(v[0]) / float(v[1]) if isinstance(v, tuple) else float(v)


def _gps(exif) -> tuple[float | None, float | None, int | None]:
    gps = exif.get_ifd(0x8825) if exif else {}
    try:
        def deg(values, ref):
            d, m, s = (_rational(x) for x in values)
            value = d + m / 60 + s / 3600
            return -value if ref in ("S", "W") else value

        lat = deg(gps[2], gps.get(1, "N")) if 2 in gps else None
        lon = deg(gps[4], gps.get(3, "E")) if 4 in gps else None
        if lat is not None and not (-90 <= lat <= 90) or lon is not None and not (-180 <= lon <= 180):
            lat = lon = None
        alt = round(_rational(gps[6]) * (-1 if gps.get(5) in (1, b"\x01") else 1)) if 6 in gps else None
        if alt is not None and not (-500 <= alt <= 9000):
            alt = None
        return lon, lat, alt
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return None, None, None


def _taken_at(exif) -> datetime | None:
    raw = (exif.get_ifd(0x8769).get(0x9003) if exif else None) or (exif.get(0x0132) if exif else None)
    try:
        return datetime.strptime(str(raw).strip("\x00 "), "%Y:%m:%d %H:%M:%S").replace(tzinfo=timezone.utc) if raw else None
    except ValueError:
        return None


def process_and_save(fileobj, *, max_bytes: int) -> StoredPhoto:
    # Decodes the upload (so only real JPEG/PNG/WebP is kept), applies the EXIF rotation, shrinks it to MAX_SIDE_PX and
    # writes it again without metadata. GPS position, altitude and capture time are read from EXIF before it is dropped.
    from PIL import Image, ImageOps, UnidentifiedImageError

    raw = fileobj.read(max_bytes + 1)
    if len(raw) > max_bytes:
        raise OverflowError
    Image.MAX_IMAGE_PIXELS = 60_000_000
    try:
        img = Image.open(BytesIO(raw))
        fmt = img.format
        if fmt not in _FORMATS:
            raise NotAnImage
        exif = img.getexif()
        img = ImageOps.exif_transpose(img)
        img.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError):
        raise NotAnImage
    lon, lat, alt = _gps(exif)
    taken_at = _taken_at(exif)

    img.thumbnail((MAX_SIDE_PX, MAX_SIDE_PX))
    ext, _ = _FORMATS[fmt]
    out = BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    elif fmt == "PNG":
        img.save(out, "PNG", optimize=True)
    else:
        img.save(out, "WEBP", quality=JPEG_QUALITY)
    data = out.getvalue()

    now = datetime.now(timezone.utc)
    relative = f"{now.year}/{now.month:02d}/{uuid.uuid4()}.{ext}"
    target = resolve_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    try:
        part.write_bytes(data)
        os.replace(part, target)
    except BaseException:
        part.unlink(missing_ok=True)
        raise
    return StoredPhoto(relative, hashlib.sha256(data).hexdigest(), len(data), img.width, img.height, taken_at, lon, lat, alt)


def delete_quietly(relative: str) -> None:
    try:
        resolve_path(relative).unlink(missing_ok=True)
    except Exception:
        pass
