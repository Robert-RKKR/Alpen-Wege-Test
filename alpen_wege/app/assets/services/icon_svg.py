"""Checks and cleans an uploaded SVG (flag or icon) before it is stored in asset_agg_icon.svg.

clean_svg(raw) returns a cleaned copy that is safe to serve and to embed:
  * the XML is parsed with defusedxml (no DOCTYPE, no entities, no external DTD)
  * only allow-listed elements and attributes survive (no script, style, foreignObject, animation, metadata)
  * every link must point inside the file ("#id"); the only exception is a data: PNG/JPEG/WebP on <image>
  * every url(...) in an attribute or style must be url(#id)
  * limits: file size (ICON_MAX_UPLOAD_KB), element count, nesting depth, number of <use>
Whatever is not allowed is removed, not repaired, and listed in CleanSvg.removed so the caller can tell the user. A
file that is not an SVG at all is rejected with InvalidSvg.
"""
# Standard library
import hashlib
import re
from collections import Counter
from dataclasses import dataclass
from xml.etree import ElementTree as ET

# Third-party
from defusedxml import ElementTree as DET
from defusedxml.common import DefusedXmlException

# Local application
from app.config import get_settings

SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
XML_NS = "http://www.w3.org/XML/1998/namespace"

MAX_ELEMENTS = 20000
MAX_DEPTH = 32
MAX_USE = 1000

ELEMENTS = {
    "svg", "g", "defs", "symbol", "use", "title", "desc",
    "path", "rect", "circle", "ellipse", "line", "polyline", "polygon",
    "text", "tspan", "clipPath", "mask", "marker", "pattern",
    "linearGradient", "radialGradient", "stop", "image",
}
ATTRIBUTES = {
    # structure
    "id", "class", "version", "viewBox", "width", "height", "x", "y", "preserveAspectRatio", "overflow",
    "role", "aria-label", "aria-hidden", "focusable",
    # geometry
    "d", "cx", "cy", "r", "rx", "ry", "x1", "y1", "x2", "y2", "points", "pathLength", "transform",
    # painting
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap", "stroke-linejoin",
    "stroke-miterlimit", "stroke-dasharray", "stroke-dashoffset", "opacity", "color", "stop-color", "stop-opacity",
    "clip-path", "clip-rule", "mask", "marker-start", "marker-mid", "marker-end", "display", "visibility", "style",
    # gradients, patterns, clip, mask, marker
    "offset", "fx", "fy", "gradientUnits", "gradientTransform", "spreadMethod", "patternUnits", "patternContentUnits",
    "patternTransform", "clipPathUnits", "maskUnits", "maskContentUnits", "markerUnits", "markerWidth", "markerHeight",
    "refX", "refY", "orient",
    # text
    "font-family", "font-size", "font-weight", "font-style", "letter-spacing", "word-spacing", "text-anchor", "dx", "dy",
    "textLength",
}
LINK_ELEMENTS = {"use", "linearGradient", "radialGradient", "pattern", "image"}
URL_RE = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I)
DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=\s]+$")
BAD_STYLE_RE = re.compile(r"@import|expression\(|javascript:|behavior\s*:|-moz-binding", re.I)
VIEW_BOX_RE = re.compile(r"\s*-?\d+(\.\d+)?([\s,]+-?\d+(\.\d+)?){3}\s*")
NUMBER_RE = re.compile(r"\d+(\.\d+)?(px)?")


class InvalidSvg(ValueError):
    pass


@dataclass(frozen=True)
class CleanSvg:
    svg: str                     # the cleaned text that is stored
    sha256: str                  # hex SHA-256 of that text (UTF-8)
    view_box: str                # "0 0 512 512"
    removed: tuple[str, ...] = ()   # what was taken out, for example ("<script> x1", "onclick x2"); empty when nothing was


def default_max_bytes() -> int:
    return get_settings().ICON_MAX_UPLOAD_KB * 1024


def _local(name: str) -> tuple[str | None, str]:
    if name.startswith("{"):
        ns, _, local = name[1:].partition("}")
        return ns, local
    return None, name


def _label(name: str) -> str:
    # a name from the uploaded file, safe to show in an answer
    return re.sub(r"[^A-Za-z0-9:_.-]", "", name)[:40] or "?"


def _urls_ok(value: str) -> bool:
    return all(m.group(2).startswith("#") for m in URL_RE.finditer(value))


def _clean_element(el: ET.Element, depth: int, counter: list[int], removed: Counter) -> bool:
    # Cleans el in place (children included). Returns False when el itself must be dropped.
    ns, name = _local(el.tag)
    if ns != SVG_NS or name not in ELEMENTS:
        return False
    counter[0] += 1
    if counter[0] > MAX_ELEMENTS:
        raise InvalidSvg(f"more than {MAX_ELEMENTS} elements")
    if depth > MAX_DEPTH:
        raise InvalidSvg(f"nested deeper than {MAX_DEPTH} levels")

    for attr in list(el.attrib):
        value = el.attrib[attr]
        ans, aname = _local(attr)
        keep = False
        if aname == "href" and ans in (None, XLINK_NS) and name in LINK_ELEMENTS:
            keep = value.startswith("#") or (name == "image" and bool(DATA_IMAGE_RE.match(value)))
        elif ans == XML_NS and aname == "space":
            keep = True
        elif ans is None and aname in ATTRIBUTES:
            if aname == "style":
                keep = not BAD_STYLE_RE.search(value) and _urls_ok(value)
            else:
                keep = _urls_ok(value) and "javascript:" not in value.lower()
        if not keep:
            del el.attrib[attr]
            removed[_label(aname)] += 1
    if name == "image" and not any(_local(a)[1] == "href" for a in el.attrib):
        return False                      # an image without an allowed source is dropped

    for child in list(el):
        if not _clean_element(child, depth + 1, counter, removed):
            removed["<" + _label(_local(child.tag)[1]) + ">"] += 1
            el.remove(child)
    return True


def clean_svg(raw: bytes, max_bytes: int | None = None) -> CleanSvg:
    limit = default_max_bytes() if max_bytes is None else max_bytes
    if len(raw) > limit:
        raise InvalidSvg(f"file larger than {limit // 1024} KB")
    try:
        root = DET.fromstring(raw, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except DefusedXmlException:
        raise InvalidSvg("DOCTYPE, entities and external references are not allowed")
    except ET.ParseError as exc:
        raise InvalidSvg(f"not valid XML: {exc}")
    if _local(root.tag) != (SVG_NS, "svg"):
        raise InvalidSvg("the root element is not <svg> in the SVG namespace")

    removed: Counter = Counter()
    _clean_element(root, 1, [0], removed)
    uses = sum(1 for e in root.iter() if _local(e.tag)[1] == "use")
    if uses > MAX_USE:
        raise InvalidSvg(f"more than {MAX_USE} <use> elements")

    view_box = root.get("viewBox")
    if not view_box:
        w, h = root.get("width", ""), root.get("height", "")
        if NUMBER_RE.fullmatch(w) and NUMBER_RE.fullmatch(h):
            view_box = f"0 0 {w.removesuffix('px')} {h.removesuffix('px')}"
            root.set("viewBox", view_box)
        else:
            raise InvalidSvg("the SVG needs a viewBox (or a numeric width and height)")
    if not VIEW_BOX_RE.fullmatch(view_box):
        raise InvalidSvg("viewBox must be four numbers")

    ET.register_namespace("", SVG_NS)
    ET.register_namespace("xlink", XLINK_NS)
    text = ET.tostring(root, encoding="unicode")
    note = tuple(f"{what} x{n}" for what, n in sorted(removed.items()))
    return CleanSvg(text, hashlib.sha256(text.encode("utf-8")).hexdigest(), " ".join(view_box.replace(",", " ").split()), note)
