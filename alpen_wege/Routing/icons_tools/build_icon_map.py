#!/usr/bin/env python3
"""One-off: writes scripts/icon_sources/icon_map.csv from your icon_names.csv (the answer of icons_list_keys.sql with the names),
the seed data (push_data/*.csv: names in German and Polish, the colour of each value) and icon_mapping.py (the hand-made part).

    python build_icon_map.py ICON_NAMES_CSV ALPEN_REPO LUCIDE_ICONS_DIR OUT_CSV
"""
import csv
import glob
import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import icon_mapping as M

names_csv, repo, lucide_dir, out = sys.argv[1:5]
lucide = {f[:-4] for f in os.listdir(lucide_dir) if f.endswith(".svg")}

# ---- seed data: name (en, de, pl) and colour of every value, by icon text in lower case
seed = defaultdict(list)
for path in sorted(glob.glob(os.path.join(repo, "push_data", "core_ref_*.csv"))):
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        seed[r["icon"].lower()].append(r)

def humanize(key):
    text = re.sub(r"[-_]+", " ", key).strip()
    return text[:1].upper() + text[1:]

def grade_label(name):
    # "SAC T3 – Demanding Mountain Hiking" -> "T3"; "Via Ferrata K1 (A) – Easy" -> "K1"; "UIAA X" -> "X"; "French 8a+ – World Class" -> "8a+"
    head = re.split(r"\s+[–-]\s+", name, maxsplit=1)[0]
    head = re.sub(r"\s*\([^)]*\)", "", head)
    for prefix in ("Alpine ", "Font ", "French ", "MTB ", "SAC ", "Ski ", "UIAA ", "Via Ferrata "):
        if head.startswith(prefix):
            return head[len(prefix):].strip()
    return head.strip()

rows_in = list(csv.DictReader(open(names_csv, encoding="utf-8-sig")))
# how often a glyph is used inside ONE table (the same glyph in two different tables is fine: the screen shows the table)
uses_glyph = Counter()
def first_table(r):
    return r["names"].split(": ", 1)[0]
for r in rows_in:
    glyph = M.LUCIDE.get(r["key"]) or (r["key"] if r["key"] in lucide else None)
    if glyph and r["key"] not in M.GEM:
        uses_glyph[(first_table(r), glyph)] += 1

out_rows = []
for r in rows_in:
    key, n = r["key"], int(r["rows_using"])
    entries = re.split(r"(?:^|, )(?=[a-z_]+: )", r["names"])
    entries = [e for e in entries if e]
    used_by = sorted({e.split(": ", 1)[0] for e in entries})
    first_name = entries[0].split(": ", 1)[1] if n == 1 and entries else None
    row = seed.get(key, [])
    one = row[0] if n == 1 and len(row) == 1 else None
    name = first_name or humanize(key)
    name_de = (one or {}).get("name_de", "") if one else ""
    name_pl = (one or {}).get("name_pl", "") if one else ""
    color = (one or {}).get("color", "") if one else ""
    if key in M.BARS:
        kind, value, quality = "bars", f"{M.BARS[key][0]}/{M.BARS[key][1]}", "generated"
    elif key in M.GEM:
        kind, value, quality = "lucide", "gem", "generated colour"
    elif key.startswith("difficulty_"):
        kind, value, quality = "grade", grade_label(name), "generated"
    elif key in M.LUCIDE or key in lucide:
        glyph = M.LUCIDE.get(key, key)
        kind, value = "lucide", glyph
        if key in lucide and key not in M.LUCIDE:
            quality, color = "exact Lucide name", ""
        else:
            n_same = uses_glyph[(first_table(r), glyph)]
            quality, color = ("same glyph %d times in %s: redraw" % (n_same, first_table(r)) if n_same > 1 else "mapped to Lucide"), ""
    else:
        kind, value, quality = "badge", (re.sub(r"[^A-Za-z0-9]", "", name)[:2] or "?").upper(), "generated"
    if kind == "lucide" and key not in M.GEM:
        color = ""                                  # Lucide icons use currentColor: the screen colours them
    tag = M.TAGS.get(key, "")
    if tag:
        quality = "mapped to Lucide, with a tag"
    out_rows.append({"key": key, "name": name, "name_de": name_de, "name_pl": name_pl, "kind": kind, "value": value, "color": color, "tag": tag,
                     "used_by": ", ".join(used_by), "rows_using": n, "quality": quality})

os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(out_rows[0]))
    w.writeheader()
    w.writerows(out_rows)
print(len(out_rows), "rows;", Counter(r["kind"] for r in out_rows), Counter(r["quality"].split(" (")[0] for r in out_rows))
