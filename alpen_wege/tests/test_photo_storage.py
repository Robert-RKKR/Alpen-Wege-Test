from io import BytesIO
from types import SimpleNamespace as NS

import pytest

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

from app.assets.services import photo_storage  # noqa: E402


@pytest.fixture
def root(tmp_path, monkeypatch):
    monkeypatch.setattr(photo_storage, "get_settings", lambda: NS(PHOTO_STORAGE_DIR=str(tmp_path)))
    return tmp_path


def jpeg(size=(400, 300), exif=None):
    out = BytesIO()
    Image.new("RGB", size, (90, 140, 200)).save(out, "JPEG", exif=exif or Image.Exif())
    out.seek(0)
    return out


def test_saves_a_jpeg_under_year_month(root):
    stored = photo_storage.process_and_save(jpeg(), max_bytes=10_000_000)
    assert stored.relative_path.endswith(".jpg") and stored.relative_path.count("/") == 2
    assert (root / stored.relative_path).is_file()
    assert (stored.width, stored.height) == (400, 300)
    assert len(stored.sha256) == 64


def test_large_image_is_shrunk(root):
    stored = photo_storage.process_and_save(jpeg((5000, 2500)), max_bytes=50_000_000)
    assert max(stored.width, stored.height) == photo_storage.MAX_SIDE_PX


def test_reads_gps_and_time_and_drops_metadata(root):
    exif = Image.Exif()
    exif[0x0132] = "2025:07:14 10:30:00"
    exif[0x8825] = {1: "N", 2: (46.0, 59.0, 24.0), 3: "E", 4: (8.0, 49.0, 12.0), 5: 0, 6: 2572.0}
    stored = photo_storage.process_and_save(jpeg(exif=exif), max_bytes=10_000_000)
    assert stored.lat == pytest.approx(46.99, abs=0.01)
    assert stored.lon == pytest.approx(8.82, abs=0.01)
    assert stored.altitude_m == 2572
    assert stored.taken_at.year == 2025
    saved = Image.open(root / stored.relative_path)
    assert not saved.getexif()


def test_rejects_non_images_and_other_formats(root):
    with pytest.raises(photo_storage.NotAnImage):
        photo_storage.process_and_save(BytesIO(b"<svg xmlns='http://www.w3.org/2000/svg'/>"), max_bytes=1000)
    gif = BytesIO()
    Image.new("RGB", (10, 10)).save(gif, "GIF")
    gif.seek(0)
    with pytest.raises(photo_storage.NotAnImage):
        photo_storage.process_and_save(gif, max_bytes=100_000)
    assert not any(root.rglob("*.*"))


def test_too_large_upload(root):
    with pytest.raises(OverflowError):
        photo_storage.process_and_save(jpeg(), max_bytes=100)


def test_paths_cannot_leave_the_storage_dir(root):
    with pytest.raises(ValueError):
        photo_storage.resolve_path("../../etc/passwd")
