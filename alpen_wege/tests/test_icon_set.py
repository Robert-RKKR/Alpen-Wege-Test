"""The icon set: scripts/icon_sources/icon_map.csv, the generator scripts/make_icon_set.py and the CSV mode of scripts/seed_icons.py."""
# Standard library
import csv
import glob
import importlib.util
import re
from io import BytesIO
from pathlib import Path

# Third-party
import cairosvg
import pytest
from PIL import Image

# Local application
from app.assets.services.icon_svg import clean_svg

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ROOT / "scripts" / "icon_sources"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


make = _load("make_icon_set_for_test", ROOT / "scripts" / "make_icon_set.py")
seed = _load("seed_icons_for_test", ROOT / "scripts" / "seed_icons.py")
ROWS = make.read_map(SOURCES / "icon_map.csv")


# ---------------------------------------------------------------- the map covers every icon the seed data names
def _seed_icon_ids():
    ids = set()
    for path in glob.glob(str(ROOT / "push_data" / "core_ref_*.csv")):
        with open(path, encoding="utf-8-sig") as fh:
            ids |= {r["icon_id"] for r in csv.DictReader(fh)}
    return ids


def test_the_map_has_an_icon_for_every_icon_id_of_the_seed_data_and_the_resource_types():
    from app.assets.services.icon_csv import icon_id

    by_id = {str(icon_id(r["key"])): r["key"] for r in ROWS}
    missing = _seed_icon_ids() - set(by_id)
    assert not missing, f"push_data names icons that icon_map.csv does not make: {sorted(missing)[:10]}"
    init_seed = _load("init_seed_for_icon_set_test", ROOT / "scripts" / "init_seed.py")
    keys = {r["key"] for r in ROWS}
    assert not [k for *_, k in init_seed.RESOURCE_TYPES if k not in keys]
    assert all(init_seed.icon_id(k) == str(icon_id(k)) for k in keys), "init_seed.py and the app compute the icon id differently"


def test_the_shipped_icons_import_csv_has_every_key_of_the_map():
    shipped = {r["key"] for r in seed.read_csv_rows(ROOT / "Routing" / "icons_import" / "icons_import.csv")}
    assert {r["key"] for r in ROWS} <= shipped


def test_the_map_is_valid_and_has_no_key_twice():
    folder = SOURCES / "lucide"
    problems = [(r["key"], p) for r in ROWS for p in make.check_row(r, folder)]
    assert not problems, problems
    keys = [r["key"] for r in ROWS]
    assert len(keys) == len(set(keys)) and keys == sorted(keys)
    assert len(ROWS) >= 437


def test_the_vendored_lucide_folder_holds_exactly_the_icons_the_map_uses_and_the_licence():
    used = {r["value"] for r in ROWS if r["kind"] == "lucide"}
    have = {p.stem for p in (SOURCES / "lucide").glob("*.svg")}
    assert used == have, f"unused: {sorted(have - used)}, missing: {sorted(used - have)}"
    licence = (SOURCES / "lucide" / "LICENSE").read_text(encoding="utf-8")
    assert "ISC License" in licence and "Lucide Icons and Contributors" in licence


def test_every_map_row_has_names_and_the_used_by_column_is_filled():
    assert all(r["name"] and r["used_by"] and r["rows_using"].isdigit() for r in ROWS)
    assert sum(1 for r in ROWS if r["name_de"]) > 300        # the German names come from the seed data


# ---------------------------------------------------------------- every generated graphic is clean and draws something
@pytest.mark.parametrize("row", ROWS, ids=[r["key"] for r in ROWS])
def test_the_graphic_passes_the_cleaner_unchanged_and_is_not_blank(row):
    svg = make.make_svg(row)
    cleaned = clean_svg(svg.encode("utf-8"))
    assert cleaned.removed == (), f"{row['key']}: the cleaner removed {cleaned.removed}"
    png = cairosvg.svg2png(bytestring=svg.replace("currentColor", "#000000").encode("utf-8"), output_width=48, output_height=48)
    alpha = Image.open(BytesIO(png)).convert("RGBA").getchannel("A")
    assert alpha.getextrema()[1] > 0, f"{row['key']} draws nothing"


# ---------------------------------------------------------------- the pieces of the generator
def test_text_colour_is_the_one_with_the_better_contrast():
    assert make.text_color("#F1C40F") == "#1F2937"       # yellow: dark text
    assert make.text_color("#8E44AD") == "#FFFFFF"       # purple: white text
    assert make.text_color("#D6EAF8") == "#1F2937" and make.text_color("#1B4F72") == "#FFFFFF"


def test_a_grade_badge_carries_its_text_and_colour():
    row = {"key": "k", "name": "SAC T3", "kind": "grade", "value": "T3", "color": "#F1C40F", "tag": ""}
    svg = make.make_svg(row)
    assert ">T3</text>" in svg and 'fill="#F1C40F"' in svg and 'fill="#1F2937"' in svg


def test_bars_fill_the_asked_number_and_grey_out_the_rest():
    svg = make.make_svg({"key": "k", "name": "x", "kind": "bars", "value": "3/7", "color": "#2ECC71", "tag": ""})
    assert svg.count('fill="#2ECC71"') == 3 and svg.count(f'fill="{make.GREY}"') == 4


def test_a_tag_is_drawn_in_the_corner_and_a_fixed_colour_replaces_currentColor():
    row = {"key": "k", "name": "x", "kind": "lucide", "value": "gem", "color": "#9B59B6", "tag": "XC"}
    svg = make.make_svg(row)
    assert 'stroke="#9B59B6"' in svg and ">XC</text>" in svg
    assert 'stroke="currentColor"' in make.make_svg({**row, "color": "", "tag": ""})


def test_names_with_markup_are_escaped():
    svg = make.make_svg({"key": "k", "name": 'A <b> & "c"', "kind": "badge", "value": "AB", "color": "#336699", "tag": ""})
    assert "<b>" not in svg and "&lt;b&gt;" in svg and clean_svg(svg.encode()).removed == ()


@pytest.mark.parametrize("change, message", [
    ({"key": "Bad Key"}, "lower case"), ({"kind": "wat"}, "kind must be"), ({"color": "red"}, "color must look like"),
    ({"kind": "grade", "value": "T3", "color": ""}, "needs a color"), ({"kind": "lucide", "value": "no-such-icon"}, "not in scripts/icon_sources"),
    ({"kind": "bars", "value": "8/7", "color": "#112233"}, "more bars"), ({"kind": "bars", "value": "x", "color": "#112233"}, "3/7"),
    ({"kind": "grade", "value": "TOOLONG", "color": "#112233"}, "1 to 4"), ({"tag": "ABCD"}, "tag"), ({"name": " "}, "name is empty"),
])
def test_a_wrong_map_row_is_named(change, message):
    row = {"key": "k", "name": "n", "kind": "lucide", "value": "gem", "color": "", "tag": "", **change}
    assert any(message in p for p in make.check_row(row, SOURCES / "lucide")), make.check_row(row, SOURCES / "lucide")


# ---------------------------------------------------------------- the whole run
def test_the_run_writes_a_csv_a_folder_and_a_preview_and_is_repeatable(tmp_path):
    args = ["--out", str(tmp_path / "a.csv"), "--svg-dir", str(tmp_path / "svg"), "--preview", str(tmp_path / "p.html")]
    assert make.main(args) == 0
    assert make.main(["--out", str(tmp_path / "b.csv")]) == 0
    assert (tmp_path / "a.csv").read_bytes() == (tmp_path / "b.csv").read_bytes()          # the same input gives the same file
    assert len(list((tmp_path / "svg").glob("*.svg"))) == len(ROWS) and "<svg" in (tmp_path / "p.html").read_text(encoding="utf-8")
    rows = seed.read_csv_rows(tmp_path / "a.csv")
    assert [r["key"] for r in rows] == [r["key"] for r in ROWS] and all(r["svg"].startswith("<svg") for r in rows)


def test_a_broken_map_writes_nothing_and_says_what_is_wrong(tmp_path, capsys):
    bad = tmp_path / "map.csv"
    bad.write_text("key,name,name_de,name_pl,kind,value,color,tag\nok,Ok,,,badge,AB,#112233,\nok,Twice,,,badge,AB,#112233,\nx,X,,,lucide,missing-one,,\n", encoding="utf-8")
    assert make.main(["--map", str(bad), "--out", str(tmp_path / "o.csv")]) == 1
    text = capsys.readouterr().out
    assert "twice" in text and "missing-one" in text and not (tmp_path / "o.csv").exists()


# ---------------------------------------------------------------- the CSV mode of the importer
def test_csv_rows_are_read_with_or_without_the_excel_bom_and_a_missing_column_is_named(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"><path d="M0 0h1v1z"/></svg>'
    for bom in ("", "﻿"):
        f = tmp_path / f"i{bom!r}.csv"
        with open(f, "w", encoding="utf-8", newline="") as fh:                       # the quotes inside the SVG are doubled, as Excel writes them
            fh.write(bom)
            csv.writer(fh).writerows([["key", "name", "svg"], ["ship", "Ship", svg]])
        assert seed.read_csv_rows(f) == [{"key": "ship", "name": "Ship", "svg": svg}]
    (tmp_path / "no.csv").write_text("key,name\nship,Ship\n", encoding="utf-8")
    with pytest.raises(ValueError, match="svg"):
        seed.read_csv_rows(tmp_path / "no.csv")


def test_prepare_csv_rows_cleans_names_and_rejects_by_row_number():
    good = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M0 0h24v24z" onclick="x()"/></svg>'
    rows = [
        {"key": "Ship", "svg": good, "name": "", "name_de": "Schiff"},                      # upper case key is lower-cased, name defaults to the key
        {"key": "has space", "svg": good},                                               # bad key
        {"key": "ship", "svg": good},                                                    # the same key again
        {"key": "dirty", "svg": '<html><script>1</script></html>'},                      # not an SVG
        {"key": "ok2", "svg": good, "name": "Two", "summary": "s"},
    ]
    prepared, rejected, notes = seed.prepare_csv_rows(rows)
    assert [p["key"] for p in prepared] == ["ship", "ok2"]
    assert prepared[0]["name"] == "ship" and prepared[0]["name_de"] == "Schiff" and prepared[0]["name_pl"] is None
    assert "onclick" not in prepared[0]["svg"] and len(prepared[0]["sha"]) == 64
    assert [r[0] for r in rejected] == ["row 3 (has space)", "row 4 (ship)", "row 5 (dirty)"]
    assert "twice" in rejected[1][1] and {n[0] for n in notes} == {"ship", "ok2"} and "onclick" in notes[0][1]
