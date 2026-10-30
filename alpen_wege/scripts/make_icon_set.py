#!/usr/bin/env python3
"""
Makes the SVG graphic of every icon in scripts/icon_sources/icon_map.csv and writes a CSV that carries the graphics, ready to load
into the database (seed_icons.py --csv). Python standard library only, so it runs on any machine.

    python scripts/make_icon_set.py --out icons_import.csv                    # the CSV with the SVG text of every icon
    python scripts/make_icon_set.py --out icons_import.csv --svg-dir svg      # also one .svg file per icon (file name = key)
    python scripts/make_icon_set.py --out icons_import.csv --preview preview.html   # also a page that shows every icon

icon_map.csv (edit it in Excel, save as CSV UTF-8) has one row per icon key:
    key, name, name_de, name_pl   the icon's names
    kind, value, color, tag        the graphic:
        lucide  value = a Lucide icon name (the file is in scripts/icon_sources/lucide/); color = fixed colour (empty: the screen colours it);
                tag = up to 3 letters in a small label in the corner
        grade   value = the text of a difficulty grade (T3, IV, WI4): a rounded square in the colour `color` with that text
        bars    value = "3/7": 3 of 7 bars filled, in the colour `color` (difficulty and visibility scales)
        badge   value = 1 to 3 letters on a round badge in `color` (the fallback when nothing fits)
    used_by, rows_using, quality   information for you (ignored here)

Lucide (https://lucide.dev, ISC licence, licence text in scripts/icon_sources/lucide/LICENSE) is the source of most glyphs. To use another
glyph: put its SVG into scripts/icon_sources/lucide/ (any file name) and write that name in `value`.
"""
import argparse
import csv
import html
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "icon_sources"
SVG_HEAD = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"'
KINDS = ("lucide", "grade", "bars", "badge")
KEY_RE = re.compile(r"^[a-z0-9_.-]{1,100}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
GREY = "#CBD5E1"


def esc(text: str) -> str:
    return html.escape(text, quote=True)


def luminance(color: str) -> float:
    r, g, b = (int(color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    lin = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def text_color(background: str) -> str:
    # white on a dark colour, near black on a light one (the better contrast of the two)
    return "#FFFFFF" if luminance(background) < 0.4 else "#1F2937"


def font_size(label: str, wide: float = 14.0) -> float:
    return round(max(5.0, min(11.0, wide * 1.55 / max(len(label), 1))), 1)


def lucide_inner(name: str, folder: Path) -> str:
    path = folder / f"{name}.svg"
    if not path.is_file():
        raise ValueError(f"the Lucide icon {name!r} is not in {folder}")
    text = path.read_text(encoding="utf-8")
    inner = re.search(r"<svg[^>]*>(.*)</svg>", text, flags=re.S).group(1)
    return " ".join(inner.split()).replace("> <", "><")


def corner_tag(tag: str) -> str:
    width = 4.4 * len(tag) + 3.2
    x = 23.5 - width
    return (f'<rect x="{x:.1f}" y="14.2" width="{width:.1f}" height="9" rx="2.4" fill="currentColor" stroke="none"/>'
            f'<text x="{x + width / 2:.1f}" y="21" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="6.4" '
            f'font-weight="700" fill="#FFFFFF" stroke="none">{esc(tag)}</text>')


def svg_lucide(row, folder):
    color = row["color"] or "currentColor"
    inner = lucide_inner(row["value"], folder)
    tag = corner_tag(row["tag"]) if row.get("tag") else ""
    return (f'{SVG_HEAD} fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
            f'<title>{esc(row["name"])}</title>{inner}{tag}</svg>')


def svg_grade(row):
    color, label = row["color"], row["value"]
    return (f'{SVG_HEAD}><title>{esc(row["name"])}</title><rect x="1" y="4" width="22" height="16" rx="4" fill="{color}"/>'
            f'<text x="12" y="{12 + font_size(label) * 0.36:.1f}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="{font_size(label)}" font-weight="700" fill="{text_color(color)}">{esc(label)}</text></svg>')


def svg_bars(row):
    filled, total = (int(x) for x in row["value"].split("/"))
    gap = 1.0
    width = (20 - gap * (total - 1)) / total
    parts = []
    for i in range(total):
        height = 4 + 14 * i / max(total - 1, 1)
        parts.append(f'<rect x="{2 + i * (width + gap):.2f}" y="{21 - height:.2f}" width="{width:.2f}" height="{height:.2f}" rx="0.6" '
                     f'fill="{row["color"] if i < filled else GREY}"/>')
    return f'{SVG_HEAD}><title>{esc(row["name"])}</title>{"".join(parts)}</svg>'


def svg_badge(row):
    color, label = row["color"], row["value"]
    return (f'{SVG_HEAD}><title>{esc(row["name"])}</title><circle cx="12" cy="12" r="11" fill="{color}"/>'
            f'<text x="12" y="{12 + font_size(label, 12) * 0.36:.1f}" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" '
            f'font-size="{font_size(label, 12)}" font-weight="700" fill="{text_color(color)}">{esc(label)}</text></svg>')


def check_row(row, folder):
    # returns the problems of a map row (empty list = fine)
    key, kind, value, color = row["key"], row["kind"], row["value"], row["color"]
    problems = []
    if not KEY_RE.match(key):
        problems.append("the key must be lower case letters, digits and _ . - (1 to 100)")
    if not row["name"].strip():
        problems.append("name is empty")
    if kind not in KINDS:
        return problems + [f"kind must be one of {', '.join(KINDS)}"]
    if color and not HEX_RE.match(color):
        problems.append("color must look like #2ECC71 (or be empty for a Lucide icon)")
    if kind in ("grade", "bars", "badge") and not color:
        problems.append(f"kind {kind} needs a color")
    if kind == "lucide" and not (folder / f"{value}.svg").is_file():
        problems.append(f"the Lucide icon {value!r} is not in scripts/icon_sources/lucide/")
    if kind == "bars" and not re.fullmatch(r"[1-9]\d?/[1-9]\d?", value):
        problems.append('value of bars must look like "3/7"')
    elif kind == "bars" and int(value.split("/")[0]) > int(value.split("/")[1]):
        problems.append("more bars filled than there are")
    if kind in ("grade", "badge") and not (1 <= len(value) <= 4):
        problems.append("the text on a grade or badge is 1 to 4 characters")
    if row.get("tag") and (kind != "lucide" or not 1 <= len(row["tag"]) <= 3):
        problems.append("a tag is 1 to 3 characters and only for kind lucide")
    return problems


def make_svg(row, folder=SOURCES / "lucide"):
    return {"lucide": lambda: svg_lucide(row, folder), "grade": lambda: svg_grade(row), "bars": lambda: svg_bars(row),
            "badge": lambda: svg_badge(row)}[row["kind"]]()


def summary_of(row):
    return {"lucide": f"Lucide icon {row['value']} (ISC licence)", "grade": f"Grade badge {row['value']}",
            "bars": f"Scale: {row['value'].replace('/', ' of ')} bars", "badge": f"Badge {row['value']}"}[row["kind"]]


def read_map(path):
    with open(path, encoding="utf-8-sig", newline="") as fh:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(fh)]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", default=str(SOURCES / "icon_map.csv"), help="the icon map (default: scripts/icon_sources/icon_map.csv)")
    ap.add_argument("--lucide", default=str(SOURCES / "lucide"), help="folder with the Lucide SVG files")
    ap.add_argument("--out", required=True, help="the CSV to write: key,name,name_de,name_pl,summary,svg")
    ap.add_argument("--svg-dir", help="also write one <key>.svg per icon into this folder")
    ap.add_argument("--preview", help="also write an HTML page that shows every icon")
    a = ap.parse_args(argv)
    folder = Path(a.lucide)
    rows = read_map(a.map)
    problems, seen = [], set()
    for i, row in enumerate(rows, start=2):
        for p in check_row(row, folder):
            problems.append(f"row {i} ({row['key']}): {p}")
        if row["key"] in seen:
            problems.append(f"row {i}: the key {row['key']} is there twice")
        seen.add(row["key"])
    if problems:
        print("The map has problems, nothing was written:")
        print("\n".join("  " + p for p in problems))
        return 1
    out_rows = [{"key": r["key"], "name": r["name"], "name_de": r["name_de"], "name_pl": r["name_pl"], "summary": summary_of(r),
                 "svg": make_svg(r, folder)} for r in rows]
    with open(a.out, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["key", "name", "name_de", "name_pl", "summary", "svg"])
        writer.writeheader()
        writer.writerows(out_rows)
    if a.svg_dir:
        Path(a.svg_dir).mkdir(parents=True, exist_ok=True)
        for r in out_rows:
            (Path(a.svg_dir) / f"{r['key']}.svg").write_text(r["svg"], encoding="utf-8")
    if a.preview:
        cards = "".join(f'<figure title="{esc(r["summary"])}"><div class="i">{r["svg"]}</div><b>{esc(r["key"])}</b><span>{esc(r["name"])}</span></figure>' for r in out_rows)
        Path(a.preview).write_text(
            "<!doctype html><meta charset='utf-8'><title>Icons</title><style>body{font:13px Arial;margin:16px;color:#1f2937}"
            "main{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}figure{margin:0;border:1px solid #e5e7eb;border-radius:8px;"
            "padding:10px;text-align:center}.i svg{width:48px;height:48px;color:#111827}b{display:block;word-break:break-all;margin-top:6px;font-size:11px}"
            f"span{{color:#6b7280}}</style><h2>{len(out_rows)} icons</h2><main>{cards}</main>", encoding="utf-8")
    print(f"{len(out_rows)} icons written to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
