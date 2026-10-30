import base64
import mimetypes
import os
import tempfile
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.assets.models.models_agg.icon import AssetAggIcon
from app.assets.models.models_agg.photo import AssetAggPhoto
from app.compendium.cards import render
from app.compendium.models.models_cat.card import CompendiumCatCard
from app.compendium.models.models_cat.poi import CompendiumCatPoi
from app.compendium.models.models_cat.region import CompendiumCatRegion
from app.compendium.models.models_m2m.poi_region import CompendiumM2mPoiRegion
from app.config import get_settings

LANGS = ("en", "de", "pl")
FORMATS = {"svg": "image/svg+xml", "png": "image/png", "jpg": "image/jpeg", "pdf": "application/pdf"}
STORED_FORMATS = ("svg", "png", "jpg", "pdf")
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


def _countries(card, links) -> list:
    region = card.poi.main_region
    return [c for c in [region.country if region else None] + [link.region.country for link in links if link.region] if c is not None]


def _difficulties(card) -> list:
    return [d for d in (card.difficulty_sport, card.difficulty_level) if d is not None]


def flag_icons_query(card, links):
    # the icons the card draws: the flags of its countries and the difficulty icons; the svg column is deferred, so it is named here
    ids = {c.icon_id for c in _countries(card, links) if c.icon_id is not None}
    ids |= {d.icon_id for d in _difficulties(card) if getattr(d, "icon_id", None) is not None}
    return select(AssetAggIcon.id, AssetAggIcon.sha256, AssetAggIcon.svg).where(AssetAggIcon.id.in_(ids)) if ids else None


async def load_async(db, card_id: UUID):
    # (card, extra region links, POI photo, icons {icon_id: (sha256, svg)}) or None when the card does not exist
    card = (await db.execute(card_query(card_id))).scalar_one_or_none()
    if card is None:
        return None
    links = list((await db.execute(extra_regions_query(card.poi_id))).scalars().all())
    poi_photo = None
    if card.main_photo_id is None and card.poi.main_photo_id is not None:
        poi_photo = await db.get(AssetAggPhoto, card.poi.main_photo_id)
    query = flag_icons_query(card, links)
    icons = {i: (sha, svg) for i, sha, svg in (await db.execute(query)).all()} if query is not None else {}
    return card, links, poi_photo, icons


def load_sync(session, card_id: UUID):
    card = session.execute(card_query(card_id)).scalar_one_or_none()
    if card is None:
        return None
    links = list(session.execute(extra_regions_query(card.poi_id)).scalars().all())
    poi_photo = None
    if card.main_photo_id is None and card.poi.main_photo_id is not None:
        poi_photo = session.get(AssetAggPhoto, card.poi.main_photo_id)
    query = flag_icons_query(card, links)
    icons = {i: (sha, svg) for i, sha, svg in session.execute(query).all()} if query is not None else {}
    return card, links, poi_photo, icons


def flag_svgs(flag_icons: dict) -> dict[str, str]:
    # {sha256: svg} of the flag and difficulty icons for render_svg: the model carries only the sha256 (it is hashed and returned as JSON)
    return {sha: svg for sha, svg in flag_icons.values()}


def _col(field: str, lang: str) -> str:
    return field if lang == "en" else f"{field}_{lang}"


def _fallback_langs(lang: str) -> list[str]:
    return [lang] + [x for x in LANGS if x != lang]


def _text(lang: str, *sources: tuple) -> str | None:
    # sources: (object, field) pairs in order of preference. The requested language is tried on every source first,
    # so a German card shows the German POI name before the English card name; then the other languages, en, de, pl.
    # Whitespace-only text counts as empty.
    for code in _fallback_langs(lang):
        for obj, field in sources:
            value = getattr(obj, _col(field, code), None) if obj is not None else None
            if value and value.strip():
                return value.strip()
    return None


def _t(obj, field: str, lang: str) -> str | None:
    return _text(lang, (obj, field))


def _short_grade(name: str | None) -> str | None:
    # "SAC T3 – Demanding Mountain Hiking" -> "SAC T3"
    if not name:
        return None
    for sep in (" – ", " - ", " — "):
        if sep in name:
            return name.split(sep, 1)[0].strip()
    return name


def build_render_model(card: CompendiumCatCard, extra_links: list, lang: str, poi_photo=None, flag_icons: dict | None = None) -> dict:
    # Everything printed on the card, already translated. The same model is returned by ?format=json.
    # flag_icons: {icon_id: (sha256, svg)} from load_*; a country's flag is its icon, the bundled file only when it has none;
    # the difficulty icons (sport grade first, then the level) are drawn in the footer.
    poi = card.poi
    region = poi.main_region
    flag_icons = flag_icons or {}

    flags, seen = [], set()
    for c in _countries(card, extra_links):
        if c.iso_code and c.iso_code.upper() not in seen:
            seen.add(c.iso_code.upper())
            icon = flag_icons.get(getattr(c, "icon_id", None))
            flags.append({"iso": c.iso_code.upper(), "name": _text(lang, (c, "name_common"), (c, "name")),
                          "icon_sha256": icon[0] if icon else None})

    ctype = card.compendium_type or poi.compendium_type
    # sport grade (SAC T3): text chip, with its colour as a diamond before the card number; general level (Easy): after the rarity
    difficulty_sport = difficulty_level = None
    if card.difficulty_sport is not None:
        d = card.difficulty_sport
        difficulty_sport = {"name": _t(d, "name", lang), "short": _short_grade(d.name), "rank": d.rank, "color": d.color}
    if card.difficulty_level is not None:
        d = card.difficulty_level
        difficulty_level = {"name": _t(d, "name", lang), "rank": d.rank, "color": d.color}
    difficulty_icons = []
    for d in _difficulties(card):
        icon = flag_icons.get(getattr(d, "icon_id", None))
        if icon and icon[0] not in difficulty_icons:
            difficulty_icons.append(icon[0])

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
        "name": _text(lang, (card, "name"), (poi, "name")),
        "flags": flags,
        "country": flags[0]["name"] if flags else None,
        "region": _t(region, "name", lang),
        "type": _t(ctype, "name", lang),
        "altitude_m": poi.altitude_m,
        "rarity": rarity,
        "difficulty_sport": difficulty_sport,
        "difficulty_level": difficulty_level,
        "difficulty_icons": difficulty_icons,
        "photo": {"id": str(photo.id), "path": photo.path} if photo is not None else None,
        "description": _text(lang, (card, "description"), (card, "summary"), (poi, "description"), (poi, "summary")),
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


def render_card(model: dict, fmt: str, ratio: tuple[int, int] = render.DEFAULT_RATIO, style: str = render.DEFAULT_STYLE,
                dpi: int = render.DEFAULT_DPI, flag_svgs: dict[str, str] | None = None) -> bytes:
    svg = render.render_svg(model, photo_data_uri(model), ratio, style, flag_svgs)
    return render.svg_to(svg, fmt, dpi)


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


def models_hash(models: dict[str, dict]) -> str:
    # one hash over every language, so a change of only a German or Polish text makes the files stale too
    return render.render_hash({lang: models[lang] for lang in LANGS})


def is_fresh(card: CompendiumCatCard, models: dict[str, dict]) -> bool:
    return (
        card.render_status == "done"
        and card.render_version == render.TEMPLATE_VERSION
        and card.render_hash == models_hash(models)
    )
