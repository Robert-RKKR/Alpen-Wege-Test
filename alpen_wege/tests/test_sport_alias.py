# Standard library
from uuid import UUID, uuid4

# Third-party
import pytest

# Local application
from app.explorer.services.sport_inference import normalise, resolve_sport_id


@pytest.fixture
def sports():
    return {
        normalise(name): uuid4()
        for name in [
            "Hiking", "Trail Running", "Cycling", "Road Cycling",
            "Gravel Cycling", "Mountain Biking", "Ski Touring",
            "Backcountry Skiing", "Cross-Country Skiing", "Snowshoeing",
            "Via Ferrata", "Rock Climbing", "Alpine Mountaineering",
        ]
    }


def test_normalise():
    assert normalise("  Trail_Running ") == "trail running"
    assert normalise("Cross-Country Skiing") == "cross country skiing"
    assert normalise("MTB") == "mtb"


def test_exact_match(sports):
    assert resolve_sport_id("Hiking", sports) == sports["hiking"]
    assert resolve_sport_id("HIKING", sports) == sports["hiking"]
    assert resolve_sport_id("  hiking  ", sports) == sports["hiking"]


def test_alias_match(sports):
    assert resolve_sport_id("walking", sports) == sports["hiking"]
    assert resolve_sport_id("wandern", sports) == sports["hiking"]
    assert resolve_sport_id("running", sports) == sports["trail running"]
    assert resolve_sport_id("mtb", sports) == sports["mountain biking"]
    assert resolve_sport_id("klettersteig", sports) == sports["via ferrata"]
    assert resolve_sport_id("langlauf", sports) == sports["cross country skiing"]
    assert resolve_sport_id("freeride", sports) == sports["backcountry skiing"]


def test_unknown_returns_none(sports):
    assert resolve_sport_id("paragliding", sports) is None
    assert resolve_sport_id("12345", sports) is None
    assert resolve_sport_id("", sports) is None
