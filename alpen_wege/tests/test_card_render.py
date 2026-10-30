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
    assert m["difficulty_sport"]["short"] == "SAC T3"
    assert m["difficulty_level"] is None
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
    assert render.flag_href("CH").startswith("data:image/png;base64,")
    assert render.flag_href("../") is None
    assert render.flag_href("ZZ") is None


def test_flags_are_png_not_nested_svg():
    # an SVG inside an <image> is dropped by many viewers: the flag circles stayed empty in a downloaded file
    svg = render.render_svg(model())
    assert "data:image/png;base64," in svg
    assert "image/svg+xml" not in svg


def test_every_bundled_flag_converts():
    import base64
    from io import BytesIO
    from PIL import Image
    for path in sorted(render.FLAG_DIR.glob("??.svg")):          # two-letter country codes; arab, eu-style files are not countries
        href = render.flag_href(path.stem)
        assert href is not None, path.name
        assert Image.open(BytesIO(base64.b64decode(href.split(",", 1)[1]))).size == (render.FLAG_PX, render.FLAG_PX), path.name


@pytest.mark.parametrize("number,label", [(1, "No 00001"), (13, "No 00013"), (99999, "No 99999"), (123456, "No 123456")])
def test_card_number_has_five_digits(number, label):
    assert f">{label}</text>" in render.render_svg(model(make_card(card_number=number)))


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


# ------------------------------------------------------------------ language of the texts

def test_requested_language_wins_over_the_card_in_another_language():
    # a German card shows the German POI name, not the English name written on the card
    card = make_card(name="Pfanni")
    card.poi.name_de = "Pfannenstock (DE)"
    assert model(card, lang="de")["name"] == "Pfannenstock (DE)"
    assert model(card, lang="en")["name"] == "Pfanni"


def test_card_text_in_the_language_wins_over_the_poi():
    card = make_card(name_de="Pfanni DE")
    card.poi.name_de = "Pfannenstock (DE)"
    assert model(card, lang="de")["name"] == "Pfanni DE"


def test_empty_language_falls_back_to_the_next_language_that_has_text():
    card = make_card()
    card.poi.name, card.poi.name_de, card.poi.name_pl = "", None, "Pfannenstock PL"
    assert model(card, lang="en")["name"] == "Pfannenstock PL"     # en empty, de empty -> pl
    assert model(card, lang="de")["name"] == "Pfannenstock PL"


def test_whitespace_counts_as_empty():
    card = make_card(name="   ", description=" \n ")
    assert model(card)["name"] == "Pfannenstock"
    assert model(card)["description"].startswith("Pfannenstock lies")


def test_description_order_in_the_requested_language():
    card = make_card(summary="Card summary EN")
    card.poi.description_pl = "Opis POI po polsku"
    assert model(card, lang="pl")["description"] == "Opis POI po polsku"   # POI text in Polish beats card text in English
    assert model(card, lang="en")["description"] == "Card summary EN"


def test_country_name_is_translated():
    card = make_card()
    c = card.poi.main_region.country
    c.name_common_de, c.name_pl = "Schweiz", "Szwajcaria"
    assert model(card, lang="de")["country"] == "Schweiz"
    assert model(card, lang="pl")["country"] == "Szwajcaria"       # name_common_pl empty, name_pl set
    assert model(card, lang="en")["country"] == "Switzerland"


def test_country_name_falls_back_when_no_translation():
    assert model(lang="pl")["country"] == "Switzerland"


def test_every_language_is_part_of_the_freshness_hash():
    card = make_card()
    before = service.models_hash({lang: model(card, lang=lang) for lang in service.LANGS})
    card.poi.name_pl = "Pfannenstock PL"
    after = service.models_hash({lang: model(card, lang=lang) for lang in service.LANGS})
    assert before != after


# ------------------------------------------------------------------ ratio and bleed

@pytest.mark.parametrize("value,expected", [
    (None, (63, 88)), ("63:88", (63, 88)), ("1:1", (1, 1)), ("16:9", (16, 9)), ("9:16", (9, 16)),
    (" 4 : 5 ", (4, 5)), ("3x2", (3, 2)), ("5:2", (5, 2)), ("2:5", (2, 5)),
])
def test_ratio_accepted(value, expected):
    assert render.parse_ratio(value) == expected


@pytest.mark.parametrize("value", ["100:1", "1:100", "3:1", "1:3", "0:5", "16/9", "abc", "1.5:1", "1000:999", "-1:1"])
def test_ratio_rejected(value):
    with pytest.raises(ValueError):
        render.parse_ratio(value)


# ------------------------------------------------------------------ style

@pytest.mark.parametrize("value,expected", [
    (None, "standard"), ("", "standard"), ("standard", "standard"), ("3d", "3d"), (" 3D ", "3d"), ("Standard", "standard"),
])
def test_style_accepted(value, expected):
    assert render.parse_style(value) == expected


@pytest.mark.parametrize("value", ["old", "card", "../standard", "standard.svg.j2", "3d/../standard", "x" * 50])
def test_style_rejected(value):
    with pytest.raises(ValueError):
        render.parse_style(value)


@pytest.mark.parametrize("style", render.STYLES)
def test_every_style_has_a_template_and_draws_valid_svg(style):
    assert (render._HERE / "templates" / f"{style}.svg.j2").is_file()
    root = ElementTree.fromstring(render.render_svg(model(), None, (63, 88), style))
    assert root.tag == f"{SVG_NS}svg"
    assert root.get("viewBox") == "-30 -30 690 940"


@pytest.mark.parametrize("ratio", [(63, 88), (1, 1), (16, 9)])
def test_3d_style_follows_the_ratio_and_differs_from_standard(ratio):
    standard = render.render_svg(model(), None, ratio, "standard")
    raised = render.render_svg(model(), None, ratio, "3d")
    assert standard != raised
    assert 'id="bevel"' in raised and 'id="bevel"' not in standard
    assert ElementTree.fromstring(raised).get("viewBox") == ElementTree.fromstring(standard).get("viewBox")


def test_default_style_is_standard():
    assert render.render_svg(model()) == render.render_svg(model(), None, render.DEFAULT_RATIO, "standard")


@pytest.mark.parametrize("ratio,size", [((63, 88), (630, 880)), ((1, 1), (630, 630)), ((16, 9), (1120, 630)), ((9, 16), (630, 1120))])
def test_shorter_side_stays_63_mm(ratio, size):
    assert render.card_size(ratio) == size
    root = ElementTree.fromstring(render.render_svg(model(), None, ratio))
    w, h = size
    assert root.get("viewBox") == f"-30 -30 {w + 60} {h + 60}"
    assert root.get("width") == f"{(w + 60) / 10}mm"


@pytest.mark.parametrize("ratio", [(63, 88), (1, 1), (4, 5), (9, 16), (2, 5), (3, 2), (16, 9), (5, 2)])
def test_every_box_stays_inside_the_card(ratio):
    long_text = "Pfannenstock mountain lies within the canton of Schwyz, amidst a vast karst landscape. " * 8
    L = render._layout(model(make_card(description=long_text)), ratio)
    W, H = L["W"], L["H"]
    assert 0 < L["px"] and L["px"] + L["pw"] < W and 0 < L["py"] and L["py"] + L["ph"] < H
    assert L["desc_h"] > 60 and L["desc_x"] + L["desc_w"] < W and L["desc_y"] + L["desc_h"] < H
    for c in L["stats"]:
        assert c["x"] + c["w"] <= W - 17
        assert render.text_width(c["value"], c["size"], True) <= c["w"] - 2 * render.PAD
    last_line_y = L["desc_y"] + L["desc_top"] + (len(L["desc_lines"]) - 1) * L["desc_lh"]
    assert last_line_y <= L["desc_y"] + L["desc_h"] - 6
    for line in L["desc_lines"]:
        assert render.text_width(line, L["desc_size"]) <= L["desc_w"] - 44


def test_wide_cards_put_the_photo_on_the_left():
    assert render._layout(model(), (16, 9))["landscape"] is True
    assert render._layout(model(), (1, 1))["landscape"] is False


def test_bleed_is_dark_and_body_has_the_rarity_colour():
    root = ElementTree.fromstring(render.render_svg(model()))
    bleed = next(r for r in root.iter(f"{SVG_NS}rect") if r.get("x") == "-30")
    assert bleed.get("fill") == render.BAND
    body = next(g for g in root.iter(f"{SVG_NS}linearGradient") if g.get("id") == "body")
    p = render.palette("#3498DB")
    assert [st.get("stop-color") for st in body] == [p["body_top"], p["body_bottom"]]


RARITIES = ["#95A5A6", "#2ECC71", "#3498DB", "#9B59B6", "#F1C40F", "#C0392B", "#FFFFFF", "#000000", "#808080", "#FF00FF"]


@pytest.mark.parametrize("color", RARITIES)
def test_text_is_readable_on_every_body(color):
    p = render.palette(color)
    for bg in (p["body_top"], p["body_bottom"]):
        assert render.contrast(render.mix(bg, p["panel"], p["panel_op"]), p["text"]) >= render.MIN_PANEL_CONTRAST - 0.05
    assert p["text"] in (render.TEXT_DARK, render.TEXT_LIGHT)


def test_light_rarity_gets_dark_text_and_dark_rarity_white_text():
    assert render.palette("#F1C40F")["text"] == render.TEXT_DARK
    assert render.palette("#C0392B")["text"] == render.TEXT_LIGHT


def test_inner_ring_is_between_rarity_and_band():
    p = render.palette("#3498DB")
    assert render.luminance(render.BAND) < render.luminance(p["ring"]) < render.luminance("#3498DB")


def test_sport_difficulty_is_plain_text_with_its_colour_as_diamond_before_the_number():
    svg = render.render_svg(model())
    root = ElementTree.fromstring(svg)
    chip_value = [t for t in root.iter(f"{SVG_NS}text") if t.text == "SAC T3"]
    assert chip_value and chip_value[0].get("fill") in (render.TEXT_DARK, render.TEXT_LIGHT)
    L = render._layout(model())
    assert L["diamond"] == "#F1C40F" and L["number_x"] == 45
    diamond = next(p for p in root.iter(f"{SVG_NS}path") if p.get("fill") == "#F1C40F")
    assert diamond.get("d").startswith("M0 -9")


def test_no_diamond_without_sport_difficulty():
    L = render._layout(model(make_card(difficulty_sport=None)))
    assert L["diamond"] is None and L["number_x"] == 18


def test_bad_difficulty_colour_draws_no_diamond():
    L = render._layout(model(make_card(difficulty_sport=ref("SAC T3 – x", color="red;x"))))
    assert L["diamond"] is None


def test_level_difficulty_follows_the_rarity_in_the_footer():
    card = make_card(difficulty_level=ref("Easy", rank=2, color="#2ECC71", name_de="Leicht"))
    assert render._layout(model(card))["rarity_label"] == "RARE / EASY"
    assert render._layout(model(card, lang="de"))["rarity_label"] == "RARE / LEICHT"
    assert ">RARE / EASY</text>" in render.render_svg(model(card))


def test_footer_without_level_shows_only_the_rarity():
    assert render._layout(model())["rarity_label"] == "RARE"


def test_level_and_sport_can_both_be_set():
    card = make_card(difficulty_level=ref("Moderate", rank=3, color="#F1C40F"))
    m = model(card)
    assert m["difficulty_sport"]["short"] == "SAC T3" and m["difficulty_level"]["name"] == "Moderate"


def test_every_text_on_the_body_uses_the_palette_text_colour():
    svg = render.render_svg(model(make_card(rarity=ref("Legendary", rank=5, color="#F1C40F"))))
    assert 'fill="#E7ECF2"' not in svg
    assert svg.count(f'fill="{render.TEXT_DARK}"') >= 5


def test_png_width_follows_the_ratio():
    pytest.importorskip("cairosvg")
    from io import BytesIO
    from PIL import Image
    png = render.svg_to(render.render_svg(model(), None, (16, 9)), "png", dpi=100)
    assert Image.open(BytesIO(png)).size == (465, 272)     # (112 + 6) mm and (63 + 6) mm at 100 dpi


@pytest.mark.parametrize("fmt", ["png", "jpg"])
@pytest.mark.parametrize("dpi,size", [(72, (196, 266)), (150, (407, 555)), (300, (815, 1110)), (600, (1630, 2220))])
def test_dpi_sets_the_pixels(fmt, dpi, size):
    pytest.importorskip("cairosvg")
    from io import BytesIO
    from PIL import Image
    img = Image.open(BytesIO(render.svg_to(render.render_svg(model()), fmt, dpi)))
    assert img.size[0] == size[0] and abs(img.size[1] - size[1]) <= 1    # 63:88 card with bleed: 69 x 94 mm (height rounds by 1 px)
    if fmt == "jpg":
        assert img.info["dpi"] == (dpi, dpi)                     # the file says how large it prints


def test_dpi_follows_the_ratio_and_is_ignored_by_vector_formats():
    pytest.importorskip("cairosvg")
    from io import BytesIO
    from PIL import Image
    svg = render.render_svg(model(), None, (16, 9))
    assert Image.open(BytesIO(render.svg_to(svg, "png", 254))).size == (1180, 690)    # (112 + 6) x (63 + 6) mm at 254 dpi
    assert render.svg_to(svg, "svg", 600) == svg.encode()
    assert render.picture_px((16, 9), 254) == (1180, 690)
    assert render.svg_to(svg, "pdf", 600).startswith(b"%PDF")


def test_picture_px_matches_what_is_drawn():
    pytest.importorskip("cairosvg")
    from io import BytesIO
    from PIL import Image
    for ratio in ((63, 88), (1, 1), (16, 9)):
        img = Image.open(BytesIO(render.svg_to(render.render_svg(model(), None, ratio), "png", 200)))
        assert abs(img.size[0] - render.picture_px(ratio, 200)[0]) <= 1
        assert abs(img.size[1] - render.picture_px(ratio, 200)[1]) <= 1


def test_dpi_limit_depends_on_the_shape():
    render.check_dpi((63, 88), 300)
    render.check_dpi((63, 88), render.MAX_DPI)                   # 5433 x 7400 px, within the pixel limit
    with pytest.raises(ValueError, match=r"Use up to \d+ dpi"):
        render.check_dpi((5, 2), render.MAX_DPI)                 # a wide card has far more pixels at the same dpi
    top = int(str(pytest.raises(ValueError, render.check_dpi, (5, 2), render.MAX_DPI).value).rsplit("up to ", 1)[1].split(" ")[0])
    render.check_dpi((5, 2), top)                                # the highest dpi named in the message is accepted
    with pytest.raises(ValueError):
        render.check_dpi((5, 2), top + 20)


# ------------------------------------------------------------------ stat chips and their icons

def test_chip_icons_follow_the_content_not_the_position():
    no_altitude = render._layout(model(make_card(poi=NS(**{**make_card().poi.__dict__, "altitude_m": None}))))
    assert [s["icon"] for s in no_altitude["stats"]] == ["type", "difficulty"]
    assert [s["icon"] for s in render._layout(model())["stats"]] == ["type", "altitude", "difficulty"]


@pytest.mark.parametrize("style", render.STYLES)
@pytest.mark.parametrize("lang", ["en", "de", "pl"])
@pytest.mark.parametrize("ratio", [(63, 88), (1, 1), (16, 9), (2, 5)])
def test_chip_label_never_reaches_the_icon_or_the_edge(style, lang, ratio):
    # the icon sits left of the label, so the label only has to stay inside its chip, one CHIP_LABEL_RIGHT from the edge
    L = render._layout(model(lang=lang), ratio)
    for s in L["stats"]:
        label = s["label"].upper()
        end = L["chip_label_x"] + render.text_width(label, s["label_size"], True) + 0.12 * s["label_size"] * len(label)
        assert end <= s["w"] - render.CHIP_LABEL_RIGHT + 0.01, (s["label"], s["w"])
        assert render.text_width(s["value"], s["size"], True) <= s["w"] - 2 * render.PAD     # the same PAD on both sides
    root = ElementTree.fromstring(render.render_svg(model(lang=lang), None, ratio, style))
    icons = [g for g in root.iter(f"{SVG_NS}g") if g.get("transform", "").endswith("scale(0.8333)")
             and g.get("stroke-opacity") is None]                 # the pressed-in copy of the 3d style has a stroke-opacity
    assert len(icons) == len(L["stats"])
    for g in icons:
        assert len(list(g)) >= 2                                 # an icon was drawn (known key), not an empty space
        assert g.get("stroke") == render.palette(model()["rarity"]["color"])["text"]    # plain, in the colour of the text


@pytest.mark.parametrize("style", render.STYLES)
def test_icons_have_no_circle_behind_them(style):
    svg = render.render_svg(model(), None, (63, 88), style)
    root = ElementTree.fromstring(svg)
    for g in root.iter(f"{SVG_NS}g"):
        if g.get("transform", "").endswith("scale(0.8333)"):
            assert all(child.tag != f"{SVG_NS}circle" or child.get("r") == "1.4" or child.get("r") == "1.3" for child in g)   # only the details of an icon
    assert 'r="12"' not in svg


@pytest.mark.parametrize("lang", ["en", "de"])
def test_label_is_centred_on_the_icon_at_every_label_size(lang):
    L = render._layout(model(lang=lang), (16, 9))                  # narrow chips: the German label shrinks
    sizes = {s["label_size"] for s in L["stats"]}
    for s in L["stats"]:
        middle_of_capitals = s["label_y"] - 0.73 * s["label_size"] / 2
        assert abs(middle_of_capitals - render.CHIP_ICON_CY) < 0.2
    assert L["chip_icon_y"] + render.ICON / 2 == render.CHIP_ICON_CY and sizes


def test_short_description_gets_a_larger_size():
    short = render._layout(model(make_card(description="Short.")))
    long_text = render._layout(model(make_card(description="Pfannenstock mountain lies within the canton of Schwyz. " * 12)))
    assert short["desc_size"] == 24 and long_text["desc_size"] < 21


# ------------------------------------------------------------------ one spacing system

@pytest.mark.parametrize("ratio", [(63, 88), (1, 1), (4, 5), (9, 16), (3, 2), (16, 9)])
def test_boxes_share_one_gap_and_one_padding(ratio):
    L = render._layout(model(), ratio)
    E, P = render.EDGE, render.PAD
    first = L["stats"][0]
    assert first["x"] == (L["px"] if not L["landscape"] else L["desc_x"])
    assert L["desc_y"] - (first["y"] + render.CHIP_H) == E                       # chips to description
    if not L["landscape"]:
        assert first["y"] - (L["py"] + L["ph"]) == E                             # photo to chips
        assert L["px"] == E and L["W"] - (L["px"] + L["pw"]) == E                # margin of the card
    else:
        assert L["desc_x"] - (L["px"] + L["pw"]) == E                            # photo to the boxes
    for a, b in zip(L["stats"], L["stats"][1:]):
        assert b["x"] - (a["x"] + a["w"]) == E                                   # chip to chip
    assert L["stats"][-1]["x"] + L["stats"][-1]["w"] == L["desc_x"] + L["desc_w"]  # the chip row is as wide as the description
    assert L["desc_top"] - round(0.73 * L["desc_size"]) == P                     # space above the text = space at the left
    assert L["footer_x"] == L["desc_x"] + P                                      # footer starts where the description text starts
    assert L["footer_right"] == L["desc_x"] + L["desc_w"] - P if not L["landscape"] else True
    assert L["flag_x"] + 22 == L["px"] + L["pw"] - P                              # flags end one PAD from the photo edge


@pytest.mark.parametrize("style", render.STYLES)
def test_every_box_has_the_same_corner_radius(style):
    root = ElementTree.fromstring(render.render_svg(model(), None, (63, 88), style))
    radii = {r.get("rx") for r in root.iter(f"{SVG_NS}rect")
             if r.get("rx") not in (None, "30", "27", "22", "23", "28.5", "20", "10") or r.get("rx") == "18"}
    assert radii == {"18"}, radii


@pytest.mark.parametrize("style", render.STYLES)
def test_texts_on_the_photo_start_at_the_pad_of_the_number_pill(style):
    L = render._layout(model())
    root = ElementTree.fromstring(render.render_svg(model(), None, (63, 88), style))
    name_x = {t.get("x") for t in root.iter(f"{SVG_NS}text") if t.text == "Pfannenstock"}
    assert name_x == {str(L["px"] + render.PAD)}


def test_number_pill_has_18_of_room_on_both_ends():
    L = render._layout(model())
    assert L["diamond_x"] - 9 == 18                                              # left edge of the diamond
    assert L["number_x"] == L["diamond_x"] + 9 + 9                               # then 9 to the number
    no_diamond = render._layout(model(make_card(difficulty_sport=None)))
    assert no_diamond["number_x"] == 18
    label = no_diamond["number_label"]
    assert no_diamond["pill_w"] - 18 == round(render.text_width(label, 20, True) + 1.5 * len(label) + 18)


def test_default_picture_is_300_dpi():
    pytest.importorskip("cairosvg")
    from io import BytesIO
    from PIL import Image
    assert Image.open(BytesIO(render.svg_to(render.render_svg(model()), "png"))).size == (815, 1110)


# ------------------------------------------------------------------ justified description

def test_justified_lines_fill_the_width_except_the_last():
    text = "Pfannenstock mountain lies within the canton of Schwyz, in the municipality of Muotathal, amidst a vast karst landscape."
    size, width = 20, 400
    lines = render.wrap(text, size, width)
    rows = render.justify(lines, size, width)
    assert [" ".join(w for _, w in r) for r in rows] == lines
    space = render.text_width(" ", size)
    justified = 0
    for line, row in zip(lines[:-1], rows[:-1]):
        words = line.split()
        needed = (width - sum(render.text_width(w, size) for w in words)) / (len(words) - 1) / space
        x, word = row[-1]
        end = x + render.text_width(word, size)
        if needed <= render.MAX_JUSTIFY_STRETCH:
            assert abs(end - width) < 0.05
            justified += 1
        else:
            assert end < width          # would need too wide gaps: stays left-aligned
    assert justified >= 1
    last_x, last_word = rows[-1][-1]
    assert last_x + render.text_width(last_word, size) < width


def test_a_line_that_would_need_huge_gaps_stays_left():
    rows = render.justify(["a b", "c"], 20, 500)
    assert rows[0][1][0] < 50


def test_one_word_line_is_not_stretched():
    assert render.justify(["Supercalifragilistic", "end"], 20, 500)[0] == [(0.0, "Supercalifragilistic")]


def test_svg_has_one_tspan_per_word_in_the_description():
    card = make_card(description="alpha beta gamma delta")
    svg = render.render_svg(model(card))
    assert svg.count(">alpha</tspan>") == 1 and svg.count(">delta</tspan>") == 1
