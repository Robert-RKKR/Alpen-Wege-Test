import base64
import hashlib
import json
import re
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

# Raise when the template or the layout changes: every stored card file becomes stale.
TEMPLATE_VERSION = 1

W, H, BLEED = 630, 880, 30           # user units, 10 = 1 mm (63 x 88 mm card + 3 mm bleed)
FONT_FAMILY = "Inter"
FOIL_FROM_RANK = 5                   # legendary and above get the holographic frame
FALLBACK_RARITY = {"name": "", "rank": 0, "color": "#95A5A6"}

_HERE = Path(__file__).parent
FONT_DIR = _HERE / "fonts"
FLAG_DIR = _HERE / "flags"
_FONT_FILES = {False: FONT_DIR / "Inter-Regular.ttf", True: FONT_DIR / "Inter-Bold.ttf"}
_COLOR = re.compile(r"#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?")

_env = Environment(
    loader=FileSystemLoader(_HERE / "templates"),
    autoescape=select_autoescape(["j2", "svg"], default_for_string=True, default=True),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


# ------------------------------------------------------------------ text measuring

class _Metrics:
    # advance widths from the font file cairo draws with, so wrapped lines never overflow their box
    def __init__(self, path: Path):
        from fontTools.ttLib import TTFont

        font = TTFont(path, lazy=True)
        self.cmap = font.getBestCmap()
        self.hmtx = font["hmtx"]
        self.upm = font["head"].unitsPerEm

    def width(self, text: str, size: float) -> float:
        return sum(self.hmtx[self.cmap.get(ord(ch), ".notdef")][0] for ch in text) * size / self.upm


@lru_cache(maxsize=2)
def _metrics(bold: bool) -> _Metrics:
    return _Metrics(_FONT_FILES[bold])


def text_width(text: str, size: float, bold: bool = False) -> float:
    return _metrics(bold).width(text, size)


def wrap(text: str, size: float, max_w: float, bold: bool = False) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        candidate = f"{line} {word}".strip()
        if line and text_width(candidate, size, bold) > max_w:
            lines.append(line)
            line = word
        else:
            line = candidate
    return lines + [line] if line else lines


def _ellipsize(lines: list[str], size: float, max_w: float, bold: bool) -> list[str]:
    last = lines[-1]
    while last and text_width(last + "…", size, bold) > max_w:
        last = last.rsplit(" ", 1)[0] if " " in last else last[:-1]
    return lines[:-1] + [last.rstrip(",.;: ") + "…"]


def fit(text: str, max_w: float, max_lines: int, sizes: list[int], bold: bool = False) -> tuple[int, list[str]]:
    # largest size at which the text fits; at the smallest size the overflow is cut with an ellipsis
    for size in sizes:
        lines = wrap(text, size, max_w, bold)
        if len(lines) <= max_lines:
            return size, lines
    size = sizes[-1]
    return size, _ellipsize(wrap(text, size, max_w, bold)[:max_lines], size, max_w, bold)


# ------------------------------------------------------------------ layout

def _layout(model: dict) -> dict:
    photo_h = 470
    name_size, name_lines = fit(model["name"] or "", W - 88, 2, [56, 50, 44, 38], bold=True)
    name_lh = round(name_size * 1.05)
    loc_y = 18 + photo_h - 34
    name_y = loc_y - 30 - (len(name_lines) - 1) * name_lh
    location = " · ".join(p for p in (model.get("region"), model.get("country")) if p)
    loc_size, loc_lines = fit(location, W - 110, 1, [20, 18, 16])

    stats_y = 18 + photo_h + 16
    desc_y = stats_y + 74 + 16
    desc_h = H - 78 - desc_y
    text = model.get("description") or ""
    for desc_size in (21, 20, 19, 18, 17, 16):
        desc_lh = round(desc_size * 1.42)
        max_lines = int((desc_h - 36 - desc_size * 0.3) // desc_lh) + 1
        desc_lines = wrap(text, desc_size, W - 80)
        if len(desc_lines) <= max_lines:
            break
    else:
        desc_lines = _ellipsize(desc_lines[:max_lines], desc_size, W - 80, False)

    number_label = f"No {model['number']:03d}"
    return {
        "photo_h": photo_h, "name_size": name_size, "name_lines": name_lines, "name_lh": name_lh, "name_y": name_y,
        "loc_y": loc_y, "loc_size": loc_size, "location": loc_lines[0] if loc_lines else "",
        "stats_y": stats_y, "desc_y": desc_y, "desc_h": desc_h,
        "desc_size": desc_size, "desc_lines": desc_lines, "desc_lh": desc_lh,
        "number_label": number_label, "pill_w": round(text_width(number_label, 20, True) + 1.5 * len(number_label) + 36),
    }


def _stat_chips(model: dict) -> list[dict]:
    labels = model["labels"]
    chips = []
    if model.get("type"):
        chips.append({"label": labels["type"], "value": model["type"], "weight": 1.6})
    if model.get("altitude_m") is not None:
        chips.append({"label": labels["altitude"], "value": f"{model['altitude_m']:,}".replace(",", " ") + " m", "weight": 1.0})
    if model.get("difficulty"):
        d = model["difficulty"]
        chips.append({"label": labels["difficulty"], "value": d["short"], "color": _safe_color(d.get("color")), "weight": 1.0})
    if not chips:
        return []
    gap, x0 = 12, 18
    total = sum(c["weight"] for c in chips)
    free = W - 2 * x0 - gap * (len(chips) - 1)
    x = x0
    for c in chips:
        c["w"] = round(free * c["weight"] / total)
        c["x"] = x
        c["size"], lines = fit(c["value"], c["w"] - 30, 1, [26, 23, 20, 18], bold=True)
        c["value"] = lines[0] if lines else ""
        c.setdefault("color", None)
        x += c["w"] + gap
    return chips


def _safe_color(value: str | None, default: str | None = None) -> str | None:
    # colours come from reference tables an admin edits; only a hex colour may reach an SVG attribute
    return value if value and _COLOR.fullmatch(value) else default


@lru_cache(maxsize=512)
def flag_href(iso: str) -> str | None:
    if not iso.isalpha() or len(iso) != 2:
        return None
    path = FLAG_DIR / f"{iso.lower()}.svg"
    if not path.is_file():
        return None
    return "data:image/svg+xml;base64," + base64.b64encode(path.read_bytes()).decode()


# ------------------------------------------------------------------ public API

def render_svg(model: dict, photo_href: str | None = None) -> str:
    # model: the render model (see services.build_render_model); photo_href: a data: URI of the main photo
    rarity = {**FALLBACK_RARITY, **(model.get("rarity") or {})}
    rarity["color"] = _safe_color(rarity.get("color"), FALLBACK_RARITY["color"])
    rarity["foil"] = (rarity.get("rank") or 0) >= FOIL_FROM_RANK
    L = _layout(model)
    return _env.get_template("card.svg.j2").render(
        font=f"{FONT_FAMILY}, 'Helvetica Neue', Arial, sans-serif",
        number_label=L["number_label"], name=model["name"] or "",
        flags=[{"iso": f["iso"], "href": flag_href(f["iso"])} for f in model.get("flags", [])][:4],
        rarity=rarity, photo_href=photo_href,
        stats=_stat_chips(model), L=L, footer=model.get("footer") or "",
    )


def svg_to(svg: str, fmt: str, dpi: int = 300) -> bytes:
    import cairosvg

    data = svg.encode()
    if fmt == "svg":
        return data
    if fmt == "pdf":
        return cairosvg.svg2pdf(bytestring=data)
    width_px = round((W + 2 * BLEED) / 10 / 25.4 * dpi)
    png = cairosvg.svg2png(bytestring=data, output_width=width_px)
    if fmt == "png":
        return png
    if fmt == "jpg":
        from io import BytesIO

        from PIL import Image

        out = BytesIO()
        Image.open(BytesIO(png)).convert("RGB").save(out, "JPEG", quality=92, dpi=(dpi, dpi))
        return out.getvalue()
    raise ValueError(f"unknown format {fmt}")


def render_hash(model: dict) -> str:
    payload = json.dumps({"template_version": TEMPLATE_VERSION, **model}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
