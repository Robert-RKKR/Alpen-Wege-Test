# Standard library
import logging
import re
from uuid import UUID

# Third-party
from sqlalchemy import select
from sqlalchemy.orm import Session

# Local application
from app.core.models.models_ref.core_ref_sport_type import CoreRefSportType

logger = logging.getLogger(__name__)

_ALIAS_MAP: dict[str, str] = {
    "hiking": "Hiking",
    "hike": "Hiking",
    "walking": "Hiking",
    "walk": "Hiking",
    "trekking": "Hiking",
    "wandern": "Hiking",
    "trail running": "Trail Running",
    "trailrunning": "Trail Running",
    "running": "Trail Running",
    "run": "Trail Running",
    "jogging": "Trail Running",
    "cycling": "Cycling",
    "biking": "Cycling",
    "bike": "Cycling",
    "ride": "Cycling",
    "cycle": "Cycling",
    "road biking": "Road Cycling",
    "road cycling": "Road Cycling",
    "road bike": "Road Cycling",
    "gravel": "Gravel Cycling",
    "gravel biking": "Gravel Cycling",
    "gravel cycling": "Gravel Cycling",
    "mountain biking": "Mountain Biking",
    "mountainbiking": "Mountain Biking",
    "mountain bike": "Mountain Biking",
    "mtb": "Mountain Biking",
    "ski touring": "Ski Touring",
    "skitouring": "Ski Touring",
    "skinning": "Ski Touring",
    "backcountry skiing": "Backcountry Skiing",
    "freeride": "Backcountry Skiing",
    "cross country skiing": "Cross-Country Skiing",
    "nordic skiing": "Cross-Country Skiing",
    "xc skiing": "Cross-Country Skiing",
    "langlauf": "Cross-Country Skiing",
    "snowshoeing": "Snowshoeing",
    "snowshoe": "Snowshoeing",
    "via ferrata": "Via Ferrata",
    "klettersteig": "Via Ferrata",
    "rock climbing": "Rock Climbing",
    "climbing": "Rock Climbing",
    "mountaineering": "Alpine Mountaineering",
    "alpine mountaineering": "Alpine Mountaineering",
    "alpinism": "Alpine Mountaineering",
}


def normalise(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[_\-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text


def resolve_sport_id(hint: str, sports: dict[str, UUID]) -> UUID | None:
    norm = normalise(hint)
    if norm in sports:
        return sports[norm]
    canonical = _ALIAS_MAP.get(norm)
    if canonical and normalise(canonical) in sports:
        return sports[normalise(canonical)]
    return None


def infer_sport_type_id(session: Session, gpx_type: str | None) -> UUID | None:
    if not gpx_type:
        return None

    rows = session.execute(
        select(CoreRefSportType.id, CoreRefSportType.name)
    ).all()

    sports: dict[str, UUID] = {}
    for row in rows:
        sports[normalise(row.name)] = row.id

    result = resolve_sport_id(gpx_type, sports)
    if result is None:
        logger.info("Unmatched GPX sport type: %r", gpx_type)
    return result
