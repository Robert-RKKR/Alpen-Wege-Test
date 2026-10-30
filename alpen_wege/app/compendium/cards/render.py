import base64
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

# Raise when the template or the layout changes: every stored card file becomes stale.
TEMPLATE_VERSION = 8                 # 8: one spacing system, plain icons; 7: chip icons, larger short descriptions; 6: 5-digit number, PNG flags

BLEED = 30                           # user units, 10 = 1 mm: 3 mm dark bleed
BASE = 630                           # the shorter side of every card (63 mm)
DEFAULT_RATIO = (63, 88)             # trading card; the only ratio the render job stores
STYLES = ("standard", "3d")          # one template per style: templates/{style}.svg.j2; add a name here and a file there
DEFAULT_STYLE = "standard"           # the only style the render job stores
MIN_RATIO, MAX_RATIO = 0.4, 2.5      # width / height: 2:5 (tall) to 5:2 (wide); beyond that nothing fits
LANDSCAPE_FROM = 1.3                 # from this width / height the photo sits left of the texts
NUMBER_DIGITS = 5                    # card number is printed as No 00013 (and in file names)
FLAG_PX = 320                        # side of the flag picture (shown 40 units = 4 mm wide: 1800 dpi, sharp even at 5000 px cards)
DEFAULT_DPI = 300                    # png / jpg sharpness; the only one the render job stores
MIN_DPI, MAX_DPI = 72, 2000          # png / jpg sharpness on request
MAX_PIXELS = 50_000_000              # width x height of a png / jpg: about 0.5 GB of memory while it is drawn
# One spacing system for the whole card (user units, 10 = 1 mm):
EDGE = 18                            # card edge to photo and boxes; also the gap between boxes (vertical and horizontal)
PAD = 22                             # inside every box, and the distance of texts on the photo from its edge
RADIUS = 18                          # corner radius of the photo window and of every box
CHIP_H = 74
ICON = 20                            # stat chip icon, drawn in a 24 x 24 box scaled to this
CHIP_LABEL_X = PAD + ICON + 6        # a stat chip: icon, then the label from here; the value sits on a row below
CHIP_LABEL_RIGHT = 12                # room a label keeps to the right edge of its chip
CHIP_ICON_CY = 23.3                  # y of the middle of the icon in a chip; the label is centred on it (its cap height is 0.73 em)
FONT_FAMILY = "Inter"
FOIL_FROM_RANK = 5                   # legendary and above get the holographic frame
FALLBACK_RARITY = {"name": "", "rank": 0, "color": "#95A5A6"}
BAND = "#0F141B"                     # bleed, and what the inner ring is mixed with
TEXT_DARK, TEXT_LIGHT = "#111827", "#FFFFFF"
MIN_PANEL_CONTRAST = 4.5             # WCAG AA for normal text: the veil behind texts gets stronger until this is met

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

def parse_ratio(value: str | None) -> tuple[int, int]:
    # "16:9" -> (16, 9). Whole numbers 1..100 on both sides, width / height between MIN_RATIO and MAX_RATIO.
    if not value:
        return DEFAULT_RATIO
    m = re.fullmatch(r"\s*(\d{1,3})\s*[:x]\s*(\d{1,3})\s*", value)
    if not m:
        raise ValueError("Use width:height with whole numbers, for example 63:88, 1:1 or 16:9.")
    w, h = int(m.group(1)), int(m.group(2))
    if not (1 <= w <= 100 and 1 <= h <= 100):
        raise ValueError("Both sides must be between 1 and 100.")
    if not (MIN_RATIO <= w / h <= MAX_RATIO):
        raise ValueError(f"The ratio must be between 2:5 and 5:2 (width / height {MIN_RATIO} to {MAX_RATIO}).")
    return w, h


def parse_style(value: str | None) -> str:
    # "3D" -> "3d". Only a name from STYLES is accepted, so the value never reaches the template loader as a path.
    if not value:
        return DEFAULT_STYLE
    style = value.strip().lower()
    if style not in STYLES:
        raise ValueError(f"Unknown style. Use one of: {', '.join(STYLES)}.")
    return style


def picture_px(ratio: tuple[int, int], dpi: int) -> tuple[int, int]:
    # pixels of a png / jpg: the card with its bleed (user units, 10 = 1 mm) at dpi
    w, h = card_size(ratio)
    f = dpi / 254
    return round((w + 2 * BLEED) * f), round((h + 2 * BLEED) * f)


def check_dpi(ratio: tuple[int, int], dpi: int) -> None:
    # a wide or tall card has more pixels than a 63:88 one at the same dpi: refuse what would not fit in memory
    w, h = picture_px(ratio, dpi)
    if w * h > MAX_PIXELS:
        cw, ch = card_size(ratio)
        top = int(254 * (MAX_PIXELS / ((cw + 2 * BLEED) * (ch + 2 * BLEED))) ** 0.5)
        raise ValueError(f"At {dpi} dpi this shape would be {w} x {h} pixels, more than the limit of {MAX_PIXELS:,}. "
                         f"Use up to {top} dpi for this ratio.")


def card_size(ratio: tuple[int, int]) -> tuple[int, int]:
    # the shorter side is always BASE, so text sizes stay the same on every format
    r = ratio[0] / ratio[1]
    return (BASE, round(BASE / r)) if r <= 1 else (round(BASE * r), BASE)


def _mountain(px, py, pw, ph) -> str:
    # placeholder ridge, drawn relative to the photo box
    pts = [(0.257, 0.494), (0.374, 0.643), (0.576, 0.302), (0.761, 0.600), (0.845, 0.494), (1.0, 0.664)]
    path = f"M{px} {py + ph} " + " ".join(f"L{round(px + fx * pw)} {round(py + fy * ph)}" for fx, fy in pts)
    return path + f" V{py + ph} Z"


def _description(text: str, width: float, height: float) -> tuple[int, int, list[str], int]:
    # (font size, line height, lines, y of the first baseline from the top of the box). The first baseline sits one PAD plus
    # the cap height below the top, whatever the size, so the space above the text equals the one at the left; the lines
    # have to end one PAD (minus the descender) above the bottom.
    for size in (24, 22, 21, 20, 19, 18, 17, 16):          # a short text gets the larger sizes and fills its panel better
        lh = round(size * 1.42)
        top = PAD + round(size * 0.73)
        max_lines = max(1, int((height - PAD - size * 0.25 - top) // lh) + 1)
        lines = wrap(text, size, width)
        if len(lines) <= max_lines:
            return size, lh, lines, top
    return size, lh, (_ellipsize(lines[:max_lines], size, width, False) if lines else []), top


MAX_JUSTIFY_STRETCH = 2.5            # a line whose spaces would grow more than this many times stays left-aligned


def justify(lines: list[str], size: float, width: float) -> list[list[tuple[float, str]]]:
    # Each line as (x offset, word) pairs. The spaces of every line but the last are widened so the line fills width;
    # the last line, a one-word line and a line that would need very wide gaps stay left-aligned (as in print).
    space = text_width(" ", size)
    out = []
    for i, line in enumerate(lines):
        words = line.split()
        widths = [text_width(w, size) for w in words]
        gap = space
        if i < len(lines) - 1 and len(words) > 1:
            stretched = (width - sum(widths)) / (len(words) - 1)
            if space <= stretched <= space * MAX_JUSTIFY_STRETCH:
                gap = stretched
        x, row = 0.0, []
        for w, ww in zip(words, widths):
            row.append((round(x, 2), w))
            x += ww + gap
        out.append(row)
    return out


def _layout(model: dict, ratio: tuple[int, int] = DEFAULT_RATIO) -> dict:
    W, H = card_size(ratio)
    landscape = W / H >= LANDSCAPE_FROM
    gap, edge, chip_h, footer_h = EDGE, EDGE, CHIP_H, 72

    if landscape:
        # photo on the left over the full height, chips and description on the right
        panel_w = max(420, round(W * 0.45))
        px, py, ph = edge, edge, H - 2 * edge
        pw = W - 3 * edge - panel_w
        panel_x = px + pw + edge
        stats_x, stats_w, stats_y = panel_x, panel_w, edge
        desc_x, desc_w = panel_x, panel_w
        footer_x = panel_x + PAD
    else:
        # photo on top, chips below it, description, footer
        px, py, pw = edge, edge, W - 2 * edge
        free = H - edge - gap - chip_h - gap - footer_h
        ph = round(free * 470 / 678)                       # 470 on the 63:88 card, as before
        stats_x, stats_w, stats_y = edge, pw, py + ph + gap
        desc_x, desc_w = edge, pw
        footer_x = edge + PAD
    desc_y = stats_y + chip_h + gap
    desc_h = H - footer_h - desc_y
    # footer line centred in the band between the description and the inner edge of the frame (cap height of 16 = 11.6)
    footer_y = H - round((footer_h + edge) / 2 - 5.8)

    name_size, name_lines = fit(model["name"] or "", pw - 2 * PAD, 2, [56, 50, 44, 38], bold=True)
    name_lh = round(name_size * 1.05)
    loc_y = py + ph - PAD - 6                              # the pin reaches 5 below the baseline: it ends one PAD above the photo edge
    name_y = loc_y - 30 - (len(name_lines) - 1) * name_lh
    location = " · ".join(p for p in (model.get("region"), model.get("country")) if p)
    loc_size, loc_lines = fit(location, pw - 2 * PAD - 30, 1, [20, 18, 16])

    desc_size, desc_lh, desc_lines, desc_top = _description(model.get("description") or "", desc_w - 2 * PAD, desc_h)

    rarity_label = " / ".join(x.upper() for x in (
        (model.get("rarity") or {}).get("name"), (model.get("difficulty_level") or {}).get("name")) if x)
    rarity_w = text_width(rarity_label, 16, True) + 3 * len(rarity_label)
    footer_room = (W - edge - PAD) - (footer_x + 30 + rarity_w + 24)
    footer_size, footer_lines = fit(model.get("footer") or "", max(footer_room, 1), 1, [14, 12])

    number_label = f"No {model['number']:0{NUMBER_DIGITS}d}"
    sport = model.get("difficulty_sport") or {}
    diamond = _safe_color(sport.get("color")) if sport else None
    # number pill: 18 of room on both ends; with the diamond (18 wide, its centre at 27) the number starts after it
    diamond_x = 27
    number_x = 45 if diamond else 18
    return {
        "W": W, "H": H, "bleed": BLEED, "landscape": landscape, "pad": PAD, "radius": RADIUS,
        "px": px, "py": py, "pw": pw, "ph": ph, "mountain": _mountain(px, py, pw, ph),
        "flag_x": px + pw - PAD - 22,                      # centre of the first flag badge (radius 22): its edge is one PAD in
        "name_size": name_size, "name_lines": name_lines, "name_lh": name_lh, "name_y": name_y,
        "loc_y": loc_y, "loc_size": loc_size, "location": loc_lines[0] if loc_lines else "",
        "stats": _stat_chips(model, stats_x, stats_w, stats_y), "chip_label_x": CHIP_LABEL_X, "chip_icon_y": CHIP_ICON_CY - ICON / 2,
        "desc_x": desc_x, "desc_y": desc_y, "desc_w": desc_w, "desc_h": desc_h,
        "desc_size": desc_size, "desc_lines": desc_lines, "desc_lh": desc_lh, "desc_top": desc_top,
        "desc_words": justify(desc_lines, desc_size, desc_w - 2 * PAD),
        "footer_x": footer_x, "footer_y": footer_y, "footer_right": W - edge - PAD, "footer_size": footer_size,
        "footer": (footer_lines[0] if footer_lines else "") if footer_room > 40 else "",
        "number_label": number_label, "number_x": number_x, "diamond": diamond, "diamond_x": diamond_x, "rarity_label": rarity_label,
        "pill_w": round(text_width(number_label, 20, True) + 1.5 * len(number_label) + number_x + 18),
    }


def _share_widths(chips: list[dict], free: float) -> None:
    # Split free by weight. A chip whose share is below its min_w gets exactly min_w and the others share the rest.
    # (A long label such as the German "Schwierigkeit" would otherwise not fit a narrow chip on a wide card.)
    fixed: set[int] = set()
    while True:
        rest = free - sum(chips[i]["min_w"] for i in fixed)
        total = sum(c["weight"] for i, c in enumerate(chips) if i not in fixed)
        too_narrow = [i for i, c in enumerate(chips)
                      if i not in fixed and total and rest * c["weight"] / total < c["min_w"]]
        if not too_narrow or len(fixed) + len(too_narrow) == len(chips):
            break
        fixed.update(too_narrow)
    for i, c in enumerate(chips):
        c["w"] = round(c["min_w"] if i in fixed else rest * c["weight"] / total)
    # rounding (or an impossible fit): the widest chip takes the difference so the row still ends at the right edge
    drift = round(free) - sum(c["w"] for c in chips)
    max(chips, key=lambda c: c["w"])["w"] += drift


def _stat_chips(model: dict, x0: int, width: int, y: int) -> list[dict]:
    labels = model["labels"]
    chips = []
    if model.get("type"):
        chips.append({"icon": "type", "label": labels["type"], "value": model["type"], "weight": 1.6})
    if model.get("altitude_m") is not None:
        chips.append({"icon": "altitude", "label": labels["altitude"], "weight": 1.0,
                      "value": f"{model['altitude_m']:,}".replace(",", "\u202f") + " m"})
    if model.get("difficulty_sport") and model["difficulty_sport"].get("short"):
        chips.append({"icon": "difficulty", "label": labels["difficulty"], "value": model["difficulty_sport"]["short"], "weight": 1.0})
    if not chips:
        return []
    gap = EDGE
    free = width - gap * (len(chips) - 1)
    for c in chips:
        label = c["label"].upper()
        # a chip never gets narrower than its label needs next to the icon, at the smallest label size (10)
        c["min_w"] = math.ceil(CHIP_LABEL_X + CHIP_LABEL_RIGHT + text_width(label, 10, True) + 0.12 * 10 * len(label))
    _share_widths(chips, free)
    x = x0
    for c in chips:
        c["x"], c["y"] = x, y
        c["size"], lines = fit(c["value"], c["w"] - 2 * PAD, 1, [26, 23, 20, 18], bold=True)   # one PAD on both sides
        c["value"] = lines[0] if lines else ""
        label = c["label"].upper()
        c["label_size"] = next((ls for ls in (13, 12, 11, 10)
                                if text_width(label, ls, True) + 0.12 * ls * len(label) <= c["w"] - CHIP_LABEL_X - CHIP_LABEL_RIGHT), 10)
        c["label_y"] = round(CHIP_ICON_CY + 0.365 * c["label_size"], 1)      # baseline: middle of the capitals on the icon's middle
        x += c["w"] + gap
    return chips


def _safe_color(value: str | None, default: str | None = None) -> str | None:
    # colours come from reference tables an admin edits; only a hex colour may reach an SVG attribute
    return value if value and _COLOR.fullmatch(value) else default


# ------------------------------------------------------------------ colours

def _rgb(h: str) -> list[int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    return [int(h[i:i + 2], 16) for i in (0, 2, 4)]


def _hex(c) -> str:
    return "#" + "".join(f"{max(0, min(255, round(v))):02X}" for v in c)


def mix(a: str, b: str, t: float) -> str:
    # t = 0 gives a, t = 1 gives b
    return _hex([x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b))])


def luminance(h: str) -> float:
    f = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (v / 255 for v in _rgb(h))
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(bg: str) -> str:
    # dark or white, whichever reads better on bg (WCAG contrast)
    return TEXT_DARK if contrast(bg, TEXT_DARK) >= contrast(bg, TEXT_LIGHT) else TEXT_LIGHT


def palette(color: str) -> dict:
    # Every colour of the card body from the rarity colour: a calm gradient (a little towards grey so strong colours do
    # not shout), one text colour for the whole card chosen on the harder end of the gradient, and a veil behind the
    # texts (light behind dark text, dark behind white text) made just strong enough for MIN_PANEL_CONTRAST.
    calm = mix(color, "#808080", 0.15)
    top, bottom = mix(calm, "#FFFFFF", 0.10), mix(calm, "#000000", 0.18)
    worst = min((top, bottom), key=lambda b: max(contrast(b, TEXT_DARK), contrast(b, TEXT_LIGHT)))
    text = text_on(worst)
    veil = "#FFFFFF" if text == TEXT_DARK else "#000000"
    opacity = 0.22
    while opacity < 0.6 and min(contrast(mix(b, veil, opacity), text) for b in (top, bottom)) < MIN_PANEL_CONTRAST:
        opacity += 0.04
    return {
        "body_top": top, "body_bottom": bottom, "band": BAND, "ring": mix(color, BAND, 0.5),
        "text": text, "panel": veil, "panel_op": round(opacity, 2),
    }


@lru_cache(maxsize=512)
def flag_href(iso: str) -> str | None:
    # The flag is drawn to a PNG once and embedded as a PNG data URI. An SVG inside an <image> (what this used to be) is
    # shown by browsers but dropped by many viewers and editors (Office, Illustrator, image viewers): the flag
    # circles stayed empty in a downloaded file. A PNG in an <image> works everywhere.
    if not iso.isalpha() or len(iso) != 2:
        return None
    path = FLAG_DIR / f"{iso.lower()}.svg"
    if not path.is_file():
        return None
    try:
        import cairosvg

        png = cairosvg.svg2png(bytestring=path.read_bytes(), output_width=FLAG_PX, output_height=FLAG_PX)
    except Exception:
        return None                                  # the card then prints the country code instead of the flag
    return "data:image/png;base64," + base64.b64encode(png).decode()


# ------------------------------------------------------------------ public API

def render_svg(model: dict, photo_href: str | None = None, ratio: tuple[int, int] = DEFAULT_RATIO,
               style: str = DEFAULT_STYLE) -> str:
    # model: the render model (see services.build_render_model); photo_href: a data: URI of the main photo;
    # ratio: (width, height) from parse_ratio; style: a name from STYLES (the template templates/{style}.svg.j2)
    style = parse_style(style)
    rarity = {**FALLBACK_RARITY, **(model.get("rarity") or {})}
    rarity["color"] = _safe_color(rarity.get("color"), FALLBACK_RARITY["color"])
    rarity["foil"] = (rarity.get("rank") or 0) >= FOIL_FROM_RANK
    L = _layout(model, ratio)
    return _env.get_template(f"{style}.svg.j2").render(
        font=f"{FONT_FAMILY}, 'Helvetica Neue', Arial, sans-serif",
        number_label=L["number_label"], name=model["name"] or "",
        flags=[{"iso": f["iso"], "href": flag_href(f["iso"])} for f in model.get("flags", [])][:4],
        rarity=rarity, photo_href=photo_href, L=L, P=palette(rarity["color"]),
    )


def svg_to(svg: str, fmt: str, dpi: int = DEFAULT_DPI) -> bytes:
    # dpi: sharpness of a png / jpg (pixels per inch of the printed card, bleed included); the file also records it.
    # Ignored for svg and pdf, which are vector.
    import cairosvg

    data = svg.encode()
    if fmt == "svg":
        return data
    if fmt == "pdf":
        return cairosvg.svg2pdf(bytestring=data)
    view_w = float(re.search(r'viewBox="\S+ \S+ (\S+) \S+"', svg).group(1))   # user units, 10 = 1 mm
    width_px = round(view_w / 10 / 25.4 * dpi)
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
