"""The SVG cleaner (app/assets/services/icon_svg.py): it must not damage the real flags and it must remove every attack."""
# Standard library
import glob
import os
from io import BytesIO
from pathlib import Path

# Third-party
import cairosvg
import pytest
from PIL import Image, ImageChops

# Local application
from app.assets.services.icon_svg import InvalidSvg, clean_svg, default_max_bytes
from app.assets.services.icon_upload import key_from_filename

ROOT = Path(__file__).resolve().parents[1]
FLAGS = sorted(glob.glob(str(ROOT / "app" / "compendium" / "cards" / "flags" / "*.svg")))
NS = 'xmlns="http://www.w3.org/2000/svg"'
XL = 'xmlns:xlink="http://www.w3.org/1999/xlink"'


def render(svg, px: int = 96) -> Image.Image:
    data = svg.encode() if isinstance(svg, str) else svg
    return Image.open(BytesIO(cairosvg.svg2png(bytestring=data, output_width=px, output_height=px))).convert("RGBA")


def svg(body: str, extra: str = "") -> bytes:
    return f'<svg {NS} {XL} viewBox="0 0 10 10" {extra}>{body}</svg>'.encode()


def text_of(raw: bytes) -> str:
    return clean_svg(raw).svg


# ---------------------------------------------------------------- the real flags
def test_the_flags_are_found():
    assert len(FLAGS) >= 250


@pytest.mark.parametrize("path", FLAGS, ids=[os.path.basename(p) for p in FLAGS])
def test_a_flag_survives_cleaning_pixel_for_pixel(path):
    raw = open(path, "rb").read()
    out = clean_svg(raw)
    assert ImageChops.difference(render(raw), render(out.svg)).getbbox() is None, f"{os.path.basename(path)} looks different after cleaning"
    assert out.view_box == "0 0 512 512" and out.removed == ()      # nothing was taken out of a real flag


def test_cleaning_twice_changes_nothing_and_the_hash_is_of_the_text():
    import hashlib

    once = clean_svg(open(FLAGS[0], "rb").read())
    again = clean_svg(once.svg.encode())
    assert again.svg == once.svg and once.sha256 == hashlib.sha256(once.svg.encode()).hexdigest()


def test_the_largest_flag_is_inside_the_default_limit():
    assert max(os.path.getsize(p) for p in FLAGS) < default_max_bytes()      # 184 KB against 300 KB


# ---------------------------------------------------------------- attacks
def test_script_element_removed():
    assert "script" not in text_of(svg('<script>alert(1)</script><circle r="3"/>'))


def test_event_handler_removed():
    out = text_of(svg('<circle r="3" onclick="alert(1)" onload="x()"/>', 'onload="alert(1)"'))
    assert "onclick" not in out and "onload" not in out and "alert" not in out


def test_foreign_object_removed():
    assert "foreignObject" not in text_of(svg('<foreignObject><div>hi</div></foreignObject><circle r="3"/>'))


def test_style_element_removed():
    assert "<style" not in text_of(svg('<style>@import url(http://evil/x.css);</style><circle r="3"/>'))


def test_animation_removed():
    out = text_of(svg('<circle r="3"><animate attributeName="r" to="9"/><set attributeName="href" to="javascript:alert(1)"/></circle>'))
    assert "animate" not in out and "<set" not in out


def test_javascript_href_removed():
    out = text_of(svg('<a href="javascript:alert(1)"><circle r="3"/></a><use href="javascript:alert(1)"/>'))
    assert "javascript" not in out and "<a" not in out


def test_external_href_removed():
    out = text_of(svg('<use href="http://evil/x.svg#a"/><use xlink:href="//evil/x.svg#a"/><image href="https://evil/x.png"/>'))
    assert "evil" not in out and "<image" not in out


def test_internal_href_kept():
    assert 'href="#a"' in text_of(svg('<defs><circle id="a" r="3"/></defs><use href="#a"/>'))


def test_data_png_image_kept_but_data_svg_image_removed():
    assert "<image" in text_of(svg('<image href="data:image/png;base64,iVBORw0KGgo=" width="5" height="5"/>'))
    assert "<image" not in text_of(svg('<image href="data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+" width="5" height="5"/>'))


def test_external_url_in_attribute_or_style_removed():
    out = text_of(svg('<circle r="3" fill="url(http://evil/x#a)" style="fill:url(http://evil/y)"/><rect width="2" height="2" fill="url(#g)"/>'))
    assert "evil" not in out and "url(#g)" in out


def test_style_attribute_with_import_removed_plain_style_kept():
    out = text_of(svg('<circle r="3" style="fill:red"/><circle r="4" style="@import url(#x)"/>'))
    assert "fill:red" in out and "@import" not in out


def test_other_namespaces_removed():
    raw = (f'<svg {NS} xmlns:inkscape="http://www.inkscape.org/namespaces/inkscape" '
           f'xmlns:sodipodi="http://sodipodi.sourceforge.net/DTD/sodipodi-0.dtd" viewBox="0 0 10 10">'
           f'<sodipodi:namedview inkscape:zoom="2"/><metadata>x</metadata><circle r="3" inkscape:label="a"/></svg>').encode()
    out = text_of(raw)
    assert "inkscape" not in out and "sodipodi" not in out and "metadata" not in out and "<circle" in out


def test_doctype_and_entity_bomb_rejected():
    bomb = (b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY a "aaaaaaaaaa"><!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">'
            b'<!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">]>' + svg('<text>&c;</text>'))
    with pytest.raises(InvalidSvg):
        clean_svg(bomb)


def test_external_entity_rejected():
    with pytest.raises(InvalidSvg):
        clean_svg(b'<?xml version="1.0"?><!DOCTYPE s [<!ENTITY x SYSTEM "file:///etc/passwd">]>' + svg('<text>&x;</text>'))


def test_not_svg_rejected():
    for raw in (b"<html><body/></html>", b"not xml at all", b"<svg><circle/></svg>", b"\x89PNG\r\n"):
        with pytest.raises(InvalidSvg):
            clean_svg(raw)


def test_foreign_root_with_viewbox_and_script_rejected():
    # a root that is not <svg> must be refused even when it carries a viewBox; its children are never cleaned
    for raw in (f'<html {NS} viewBox="0 0 1 1"><script>alert(1)</script></html>'.encode(),
                f'<g {NS} viewBox="0 0 1 1"><script>alert(1)</script></g>'.encode(),
                b'<svg xmlns="http://evil.example/ns" viewBox="0 0 1 1"><script/></svg>'):
        with pytest.raises(InvalidSvg):
            clean_svg(raw)


def test_too_large_rejected_by_the_setting():
    with pytest.raises(InvalidSvg):
        clean_svg(svg("<!--" + "x" * (default_max_bytes() + 10) + "-->"))
    clean_svg(svg("<!--" + "x" * 1000 + "-->"), max_bytes=2000)
    with pytest.raises(InvalidSvg):
        clean_svg(svg("<!--" + "x" * 1000 + "-->"), max_bytes=500)


def test_too_many_elements_rejected():
    with pytest.raises(InvalidSvg):
        clean_svg(svg('<circle r="1"/>' * 20001), max_bytes=10_000_000)


def test_too_deep_rejected():
    with pytest.raises(InvalidSvg):
        clean_svg(svg('<g>' * 40 + '</g>' * 40))


def test_too_many_use_rejected():
    with pytest.raises(InvalidSvg):
        clean_svg(svg('<defs><circle id="a" r="1"/></defs>' + '<use href="#a"/>' * 1001))


def test_viewbox_required_or_derived_and_checked():
    assert clean_svg(f'<svg {NS} width="24" height="24"><circle r="3"/></svg>'.encode()).view_box == "0 0 24 24"
    assert clean_svg(f'<svg {NS} width="24px" height="12px"><circle r="3"/></svg>'.encode()).view_box == "0 0 24 12"
    for raw in (f'<svg {NS}><circle r="3"/></svg>', f'<svg {NS} viewBox="0 0 a b"/>', f'<svg {NS} viewBox="0 0 1"/>'):
        with pytest.raises(InvalidSvg):
            clean_svg(raw.encode())


def test_a_typical_outline_icon_is_kept():
    raw = (f'<svg {NS} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
           f'stroke-linecap="round" stroke-linejoin="round"><path d="m8 3 4 8 5-5 5 15H2L8 3z"/></svg>').encode()
    out = clean_svg(raw)
    assert 'stroke="currentColor"' in out.svg and "<path" in out.svg and out.removed == ()


# ---------------------------------------------------------------- what was removed is reported
def test_removed_lists_what_was_taken_out_and_how_often():
    out = clean_svg(svg('<script>1</script><script>2</script><circle r="3" onclick="a()" onmouseover="b()"/><rect width="1" height="1" onclick="c()"/>'))
    assert out.removed == ("<script> x2", "onclick x2", "onmouseover x1")


def test_removed_is_empty_when_nothing_was_taken_out_and_names_are_safe_to_show():
    assert clean_svg(svg('<circle r="3"/>')).removed == ()
    out = clean_svg(svg('<circle r="3" a-very-long-attribute-name-that-goes-on-and-on-and-on-and-on="x"/><é-x/><long-element-name-that-goes-on-and-on-and-on-and-on-and-on/>'))
    assert out.removed and all(len(item) < 60 for item in out.removed) and all(item.isascii() for item in out.removed)


# ---------------------------------------------------------------- the key from a file name
@pytest.mark.parametrize("name, key", [
    ("Flag AT.svg", "flag_at"), ("sport_hiking.SVG", "sport_hiking"), ("ferris-wheel.svg", "ferris-wheel"),
    ("C:\\icons\\Ship.svg", "ship"), ("/tmp/x/a b.c.svg", "a_b.c"), ("  .svg", ""), (None, ""), ("???.svg", ""),
])
def test_key_from_filename(name, key):
    assert key_from_filename(name) == key
