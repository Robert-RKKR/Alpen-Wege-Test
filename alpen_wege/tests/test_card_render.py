from types import SimpleNamespace as NS
from xml.etree import ElementTree

import pytest

from app.compendium.cards import render, service

SVG_NS = "{http://www.w3.org/2000/svg}"


def ref(name, rank=1, color="#3498DB", **kw):
    return NS(name=name, name_de=kw.pop("name_de", None), name_pl=None, rank=rank, color=color, point_factor=2.0, **kw)


def country(iso, name):
    return NS(iso_code=iso, name=name, name_de=None, name_pl=None, name_common=name, name_common_de=None, name_common_pl=None)


def make_card(**over):
    region = NS(name="Schwyz", name_de=None, name_pl=None, country=country("CH", "Switzerland"))
    poi = NS(
        name="Pfannenstock", name_de=None, name_pl=None, altitude_m=2572, main_region=region,
        compendium_type=ref("Mountain peak", name_de="Berggipfel"), main_photo_id=None,
        description="Pfannenstock lies in the canton of Schwyz.", description_de=None, description_pl=None,
        summary=None, summary_de=None, summary_pl=None,
    )
    card = NS(
        id="c0ffee00-0000-0000-0000-000000000013", card_number=13, poi=poi,
        name=None, name_de=None, name_pl=None, description=None, description_de=None, description_pl=None,
        summary=None, summary_de=None, summary_pl=None,
        compendium_type=None, rarity=ref("Rare", rank=3), main_photo=None,
        difficulty_sport=ref("SAC T3 – Demanding Mountain Hiking", rank=3, color="#F1C40F"), difficulty_level=None,
    )
    for k, v in over.items():
        setattr(card, k, v)
    return card


def model(card=None, links=(), lang="en"):
    return service.build_render_model(card or make_card(), list(links), lang)


def test_model_falls_back_to_poi_and_shortens_grade():
    m = model()
    assert m["number"] == 13
    assert m["name"] == "Pfannenstock"
    assert m["country"] == "Switzerland" and m["region"] == "Schwyz"
    assert m["flags"] == [{"iso": "CH", "name": "Switzerland"}]
    assert m["difficulty"]["short"] == "SAC T3"
    assert m["rarity"]["color"] == "#3498DB"
    assert m["description"].startswith("Pfannenstock")


def test_model_translates_with_english_fallback():
    m = model(lang="de")
    assert m["type"] == "Berggipfel"
    assert m["region"] == "Schwyz"
    assert m["labels"]["altitude"] == "Höhe"


def test_flags_of_extra_regions_are_unique_and_ordered():
    at = NS(region=NS(country=country("AT", "Austria")))
    ch_again = NS(region=NS(country=country("CH", "Switzerland")))
    m = model(links=[ch_again, at])
    assert [f["iso"] for f in m["flags"]] == ["CH", "AT"]


def test_card_name_overrides_poi_name():
    assert model(make_card(name="Pfanni"))["name"] == "Pfanni"


def test_svg_is_valid_xml_and_escapes_text():
    card = make_card(name='<script>alert(1)</script> & "x"', description="a < b & c")
    svg = render.render_svg(model(card))
    root = ElementTree.fromstring(svg)
    assert root.tag == f"{SVG_NS}svg"
    assert root.find(f".//{SVG_NS}script") is None
    assert "&lt;script&gt;" in svg


def test_bad_colour_from_reference_table_is_not_emitted():
    card = make_card(rarity=ref("Odd", color='red" onload="x'))
    svg = render.render_svg(model(card))
    assert "onload" not in svg
    assert render.FALLBACK_RARITY["color"] in svg


def test_difficulty_chip_hidden_without_difficulty():
    svg = render.render_svg(model(make_card(difficulty_sport=None)))
    assert "DIFFICULTY" not in svg
    assert "SAC T3" not in svg


def test_card_without_rarity_still_renders():
    ElementTree.fromstring(render.render_svg(model(make_card(rarity=None))))


def test_long_description_is_shrunk_then_cut():
    text = "word " * 600
    svg = render.render_svg(model(make_card(description=text)))
    assert "…" in svg


def test_wrapped_lines_fit_the_box():
    text = "Pfannenstock mountain lies within the canton of Schwyz, in the municipality of Muotathal, amidst a vast karst landscape. " * 3
    for line in render.wrap(text, 20, 550):
        assert render.text_width(line, 20) <= 550


def test_flag_lookup_rejects_paths():
    assert render.flag_href("CH").startswith("data:image/svg+xml;base64,")
    assert render.flag_href("../") is None
    assert render.flag_href("ZZ") is None


def test_hash_changes_with_content_and_template_version(monkeypatch):
    a = render.render_hash(model())
    assert a == render.render_hash(model())
    assert a != render.render_hash(model(make_card(card_number=14)))
    monkeypatch.setattr(render, "TEMPLATE_VERSION", render.TEMPLATE_VERSION + 1)
    assert a != render.render_hash(model())


def test_photo_outside_storage_dir_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: NS(PHOTO_STORAGE_DIR=str(tmp_path), CARD_FOOTER=""))
    (tmp_path / "ok.jpg").write_bytes(b"\xff\xd8\xff")
    assert service.photo_data_uri({"photo": {"path": "ok.jpg"}}).startswith("data:image/jpeg;base64,")
    assert service.photo_data_uri({"photo": {"path": "../../etc/passwd"}}) is None
    assert service.photo_data_uri({"photo": {"path": "missing.jpg"}}) is None
    assert service.photo_data_uri({"photo": None}) is None


@pytest.mark.parametrize("fmt,magic", [("png", b"\x89PNG"), ("pdf", b"%PDF"), ("jpg", b"\xff\xd8\xff")])
def test_raster_and_pdf_output(fmt, magic):
    pytest.importorskip("cairosvg")
    assert render.svg_to(render.render_svg(model()), fmt).startswith(magic)
