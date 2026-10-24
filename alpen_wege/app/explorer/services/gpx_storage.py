# Standard library
import hashlib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Local application
from app.config import get_settings


class UploadTooLarge(Exception):
    pass


@dataclass(frozen=True)
class StoredFile:
    relative_path: str
    sha256: str
    size_bytes: int


def storage_root() -> Path:
    return Path(get_settings().GPX_STORAGE_DIR)


def new_relative_path(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year}/{now.month:02d}/{uuid.uuid4()}.gpx"


def resolve_path(relative: str) -> Path:
    root = storage_root().resolve()
    full = (root / relative).resolve()
    if not str(full).startswith(str(root)):
        raise ValueError("Path escapes storage root")
    return full


def save_upload(fileobj, *, max_bytes: int) -> StoredFile:
    relative = new_relative_path()
    target = resolve_path(relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".gpx.part")

    h = hashlib.sha256()
    size = 0
    chunk_size = 1024 * 1024

    try:
        with open(part, "wb") as f:
            while True:
                chunk = fileobj.read(chunk_size)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise UploadTooLarge(
                        f"File exceeds {max_bytes // (1024 * 1024)} MB limit"
                    )
                h.update(chunk)
                f.write(chunk)
        os.rename(part, target)
    except Exception:
        if part.exists():
            part.unlink(missing_ok=True)
        raise

    return StoredFile(
        relative_path=relative,
        sha256=h.hexdigest(),
        size_bytes=size,
    )


def delete_quietly(relative: str) -> None:
    try:
        path = resolve_path(relative)
        path.unlink(missing_ok=True)
    except Exception:
        pass
