import base64
import mimetypes
import os
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.assets.models.models_agg.photo import AssetAggPhoto
from app.compendium.cards import render
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.config import get_settings

LANGS = ("en", "de", "pl")
FORMATS = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf"}
STORED_FORMATS = ("svg", "png", "pdf")   # jpg is made from the stored png when asked for
_MAX_PHOTO_BYTES = 15 * 1024 * 1024
_PHOTO_TYPES = {"image/jpeg", "image/png", "image/webp"}

LABELS = {
    "en": {"type": "Type", "altitude": "Altitude", "difficulty": "Difficulty"},
    "de": {"type": "Typ", "altitude": "Höhe", "difficulty": "Schwierigkeit"},
    "pl": {"type": "Typ", "altitude": "Wysokość", "difficulty": "Trudność"},
}

def _card_load():
    # built on use, not at import, so the mappers are configured only when a query runs
    poi = selectinload(CompendiumCatCard.poi)
    return (
        selectinload(CompendiumCatCard.rarity),
        selectinload(CompendiumCatCard.compendium_type),
        selectinload(CompendiumCatCard.difficulty_level),
        selectinload(CompendiumCatCard.difficulty_sport),
        selectinload(CompendiumCatCard.main_photo),
        poi.selectinload(CompendiumCatPoi.compendium_type),
        poi.selectinload(CompendiumCatPoi.main_region).selectinload(CompendiumCatRegion.country),
    )


def card_query(card_id: UUID):
    return select(CompendiumCatCard).where(CompendiumCatCard.id == card_id).options(*_card_load())


def extra_regions_query(poi_id: UUID):
    return (
        select(CompendiumM2mPoiRegion)
        .where(CompendiumM2mPoiRegion.poi_id == poi_id)
        .order_by(CompendiumM2mPoiRegion.slot_position)
        .options(selectinload(CompendiumM2mPoiRegion.region).selectinload(CompendiumCatRegion.country))
    )


async def load_async(db, card_id: UUID):
    # (card, extra region links, POI photo) or None when the card does not exist
    card = (await db.execute(card_query(card_id))).scalar_one_or_none()
    if card is None:
        return None
    links = (await db.execute(extra_regions_query(card.poi_id))).scalars().all()
    poi_photo = None
    if card.main_photo_id is None and card.poi.main_photo_id is not None:
        poi_photo = await db.get(AssetAggPhoto, card.poi.main_photo_id)
    return card, list(links), poi_photo


def load_sync(session, card_id: UUID):
    card = session.execute(card_query(card_id)).scalar_one_or_none()
    if card is None:
        return None
    links = session.execute(extra_regions_query(card.poi_id)).scalars().all()
    poi_photo = None
    if card.main_photo_id is None and card.poi.main_photo_id is not None:
        poi_photo = session.get(AssetAggPhoto, card.poi.main_photo_id)
    return card, list(links), poi_photo


def _t(obj, field: str, lang: str) -> str | None:
    # translated text with English fallback; empty strings count as missing
    if obj is None:
        return None
    value = getattr(obj, f"{field}_{lang}", None) if lang != "en" else None
    return value or getattr(obj, field, None) or None


def _first(*values):
    return next((v for v in values if v), None)


def _short_grade(name: str | None) -> str | None:
    # "SAC T3 – Demanding Mountain Hiking" -> "SAC T3"
    if not name:
        return None
    for sep in (" – ", " - ", " — "):
        if sep in name:
            return name.split(sep, 1)[0].strip()
    return name


def build_render_model(card: CompendiumCatCard, extra_links: list, lang: str, poi_photo=None) -> dict:
    # Everything printed on the card, already translated. The same model is returned by ?format=json.
    poi = card.poi
    region = poi.main_region
    country = region.country if region else None

    flags, seen = [], set()
    for c in [country] + [link.region.country for link in extra_links if link.region]:
        if c is not None and c.iso_code and c.iso_code.upper() not in seen:
            seen.add(c.iso_code.upper())
            name = _first(
                getattr(c, f"name_common_{lang}", None) if lang != "en" else None,
                getattr(c, f"name_{lang}", None) if lang != "en" else None,
                c.name_common, c.name,
            )
            flags.append({"iso": c.iso_code.upper(), "name": name})

    ctype = card.compendium_type or poi.compendium_type
    difficulty = None
    if card.difficulty_sport is not None:
        d = card.difficulty_sport
        difficulty = {"kind": "sport", "name": _t(d, "name", lang), "short": _short_grade(d.name), "rank": d.rank, "color": d.color}
    elif card.difficulty_level is not None:
        d = card.difficulty_level
        difficulty = {"kind": "level", "name": _t(d, "name", lang), "short": _t(d, "name", lang), "rank": d.rank, "color": d.color}

    rarity = None
    if card.rarity is not None:
        r = card.rarity
        rarity = {"name": _t(r, "name", lang), "rank": r.rank, "color": r.color, "point_factor": r.point_factor}

    photo = card.main_photo or poi_photo
    return {
        "template_version": render.TEMPLATE_VERSION,
        "lang": lang,
        "card_id": str(card.id),
        "number": card.card_number,
        "name": _first(_t(card, "name", lang), _t(poi, "name", lang)),
        "flags": flags,
        "country": flags[0]["name"] if flags else None,
        "region": _t(region, "name", lang),
        "type": _t(ctype, "name", lang),
        "altitude_m": poi.altitude_m,
        "rarity": rarity,
        "difficulty": difficulty,
        "photo": {"id": str(photo.id), "path": photo.path} if photo is not None else None,
        "description": _first(_t(card, "description", lang), _t(card, "summary", lang),
                              _t(poi, "description", lang), _t(poi, "summary", lang)),
        "labels": LABELS[lang],
        "footer": get_settings().CARD_FOOTER,
    }


def photo_data_uri(model: dict) -> str | None:
    # The photo is embedded so the SVG is self-contained; a missing or odd file renders the placeholder.
    if not model.get("photo"):
        return None
    root = Path(get_settings().PHOTO_STORAGE_DIR).resolve()
    path = (root / model["photo"]["path"].lstrip("/")).resolve()
    if root not in path.parents or not path.is_file() or path.stat().st_size > _MAX_PHOTO_BYTES:
        return None
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in _PHOTO_TYPES:
        return None
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode()


def render_card(model: dict, fmt: str) -> bytes:
    svg = render.render_svg(model, photo_data_uri(model))
    return render.svg_to(svg, fmt)


# ------------------------------------------------------------------ stored files

def card_dir(card_id: UUID | str) -> Path:
    return Path(get_settings().CARD_STORAGE_DIR) / str(card_id)


def stored_file(card_id: UUID | str, lang: str, fmt: str) -> Path:
    return card_dir(card_id) / f"{lang}.{fmt}"


def write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def remove_files(card_id: UUID | str) -> None:
    d = card_dir(card_id)
    if d.is_dir():
        for f in d.iterdir():
            f.unlink(missing_ok=True)
        d.rmdir()


def is_fresh(card: CompendiumCatCard, model_en: dict) -> bool:
    return (
        card.render_status == "done"
        and card.render_version == render.TEMPLATE_VERSION
        and card.render_hash == render.render_hash(model_en)
    )
