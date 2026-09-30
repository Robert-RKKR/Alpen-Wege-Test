#!/usr/bin/env python3
"""
generate_schema.py

Reconstructs a clean, grouped, dependency-ordered DDL for the Alpenwege / EXPLORER
database — the way the hand-written schema reads, not the way pg_dump prints it:

  * one CREATE TABLE per table, column names aligned, single-column FKs inline
  * composite PK / UNIQUE / CHECK / multi-column FK rendered as table-level lines
  * tables emitted in FK-dependency order, grouped by domain with section headers
  * dependency cycles (e.g. user.avatar_photo_id <-> photo.created_by) broken by
    deferring a nullable FK to an ALTER TABLE ... ADD CONSTRAINT after the tables
  * indexes (excluding those backing PK/UNIQUE) and triggers in their own sections
  * CREATE EXTENSION lines for installed extensions

Connects directly to PostgreSQL via psycopg2 (TCP).

Usage:
    python3 generate_schema.py > explorer_schema_dump.sql

Config via env:
    DB_HOST     (default: localhost)
    DB_PORT     (default: 5432)
    DB_USER     (default: alpenwege)
    DB_PASS     (default: alpenwege)
    DB_NAME     (default: alpenwege)
    SCHEMA      (default: public)
    EXCLUDE     comma-separated extra table names to skip (spatial_ref_sys always skipped)
"""

import json
import os
import re
import sys
from collections import defaultdict
import heapq

import psycopg2

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "alpenwege")
DB_PASS = os.environ.get("DB_PASS", "alpenwege")
DB_NAME = os.environ.get("DB_NAME", "alpenwege")
SCHEMA = os.environ.get("SCHEMA", "public")

EXCLUDE = {"spatial_ref_sys"}
EXCLUDE |= {t.strip() for t in os.environ.get("EXCLUDE", "").split(",") if t.strip()}

DOMAIN_PRIORITY = {"core": 1, "asset": 2, "compendium": 3, "explorer": 4,
                   "profile": 5, "social": 6}
KIND_PRIORITY = {"usr": 0, "ref": 0, "cat": 0, "sub": 0, "agg": 1, "m2m": 2}

TYPE_ALIASES = {
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp",
}

BAR = "-- " + "=" * 76

conn = psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER,
                        password=DB_PASS, dbname=DB_NAME)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()


def query_json(sql):
    cur.execute(sql)
    row = cur.fetchone()
    if row and row[0]:
        return row[0] if isinstance(row[0], list) else json.loads(row[0])
    return []


def domain_of(t):
    return t.split("_", 1)[0]


def kind_of(t):
    p = t.split("_")
    return p[1] if len(p) > 1 else ""


def fmt_type(t):
    t = TYPE_ALIASES.get(t, t)
    return re.sub(r"\(([A-Za-z]+),(\d+)\)", r"(\1, \2)", t)


# --------------------------------------------------------------------------- #
# 1. Pull catalog
# --------------------------------------------------------------------------- #
FILTER = f"n.nspname = '{SCHEMA}' AND c.relkind = 'r'"

tables = [t for t in query_json(f"""
SELECT coalesce(json_agg(c.relname ORDER BY c.relname), '[]')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE {FILTER};""") if t not in EXCLUDE]
tset = set(tables)

columns = query_json(f"""
SELECT coalesce(json_agg(json_build_object(
    'tbl', c.relname, 'attnum', a.attnum, 'name', a.attname,
    'type', format_type(a.atttypid, a.atttypmod),
    'notnull', a.attnotnull, 'default', pg_get_expr(ad.adbin, ad.adrelid)
  ) ORDER BY c.relname, a.attnum), '[]')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
JOIN pg_attribute a ON a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
LEFT JOIN pg_attrdef ad ON ad.adrelid = a.attrelid AND ad.adnum = a.attnum
WHERE {FILTER};""")

constraints = query_json(f"""
SELECT coalesce(json_agg(json_build_object(
    'tbl', cl.relname, 'contype', con.contype, 'name', con.conname,
    'def', pg_get_constraintdef(con.oid),
    'cols', (SELECT array_agg(att.attname ORDER BY x.ord)
             FROM unnest(con.conkey) WITH ORDINALITY AS x(attnum, ord)
             JOIN pg_attribute att ON att.attrelid = con.conrelid AND att.attnum = x.attnum),
    'ncols', coalesce(array_length(con.conkey, 1), 0),
    'reftbl', cf.relname, 'is_self', (con.confrelid = con.conrelid),
    'confdeltype', con.confdeltype
  )), '[]')
FROM pg_constraint con
JOIN pg_class cl ON cl.oid = con.conrelid
JOIN pg_namespace n ON n.oid = cl.relnamespace
LEFT JOIN pg_class cf ON cf.oid = con.confrelid
WHERE n.nspname = '{SCHEMA}' AND con.contype IN ('p','u','c','f');""")

indexes = query_json(f"""
SELECT coalesce(json_agg(json_build_object(
    'tbl', t.relname, 'name', ic.relname, 'def', pg_get_indexdef(i.indexrelid)
  ) ORDER BY t.relname, ic.relname), '[]')
FROM pg_index i
JOIN pg_class ic ON ic.oid = i.indexrelid
JOIN pg_class t ON t.oid = i.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = '{SCHEMA}' AND t.relkind = 'r'
  AND NOT EXISTS (SELECT 1 FROM pg_constraint con WHERE con.conindid = i.indexrelid);""")

triggers = query_json(f"""
SELECT coalesce(json_agg(json_build_object(
    'tbl', t.relname, 'name', tg.tgname, 'def', pg_get_triggerdef(tg.oid)
  ) ORDER BY t.relname, tg.tgname), '[]')
FROM pg_trigger tg JOIN pg_class t ON t.oid = tg.tgrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = '{SCHEMA}' AND NOT tg.tgisinternal;""")

extensions = query_json("""
SELECT coalesce(json_agg(extname ORDER BY extname), '[]')
FROM pg_extension WHERE extname <> 'plpgsql';""")

cur.close()
conn.close()

cols_by = defaultdict(list)
for c in columns:
    if c["tbl"] in tset:
        cols_by[c["tbl"]].append(c)
cons_by = defaultdict(list)
for c in constraints:
    if c["tbl"] in tset:
        cons_by[c["tbl"]].append(c)
idx_by = defaultdict(list)
for i in indexes:
    if i["tbl"] in tset:
        idx_by[i["tbl"]].append(i)
trg_by = defaultdict(list)
for t in triggers:
    if t["tbl"] in tset:
        trg_by[t["tbl"]].append(t)

notnull = {(c["tbl"], c["name"]): c["notnull"] for c in columns}


def fk_nullable(con):
    return con["ncols"] == 1 and not notnull.get((con["tbl"], con["cols"][0]), True)


# --------------------------------------------------------------------------- #
# 2. Break cycles, then Kahn sort
# --------------------------------------------------------------------------- #
deps = defaultdict(set)
fk_by_edge = defaultdict(list)
for c in constraints:
    if c["contype"] == "f" and c["tbl"] in tset and c["reftbl"] in tset and not c["is_self"]:
        deps[c["tbl"]].add(c["reftbl"])
        fk_by_edge[(c["tbl"], c["reftbl"])].append(c)

deferred_names = set()


def pick_edge_to_defer(a, b):
    recips = fk_by_edge.get((b, a), [])
    nn_recip = [c for c in recips if fk_nullable(c)]
    if nn_recip:
        for c in nn_recip:
            deferred_names.add(c["name"])
        deps[b].discard(a)
        return
    for c in fk_by_edge.get((a, b), []):
        deferred_names.add(c["name"])
    deps[a].discard(b)


WHITE, GRAY, BLACK = 0, 1, 2
color = {t: WHITE for t in tables}


def sort_key(t):
    dom = -1 if kind_of(t) == "usr" else DOMAIN_PRIORITY.get(domain_of(t), 99)
    return (dom, KIND_PRIORITY.get(kind_of(t), 1), t)


def dfs(root):
    stack = [(root, iter(sorted(deps[root], key=sort_key)))]
    color[root] = GRAY
    while stack:
        node, it = stack[-1]
        advanced = False
        for nb in it:
            if nb not in deps and nb not in color:
                continue
            if color.get(nb, BLACK) == GRAY:
                pick_edge_to_defer(node, nb)
            elif color.get(nb, BLACK) == WHITE:
                color[nb] = GRAY
                stack.append((nb, iter(sorted(deps[nb], key=sort_key))))
                advanced = True
                break
        if not advanced:
            color[node] = BLACK
            stack.pop()


for t in sorted(tables, key=sort_key):
    if color[t] == WHITE:
        dfs(t)

indeg = {t: 0 for t in tables}
dependents = defaultdict(set)
for t, refs in deps.items():
    for r in refs:
        if r != t:
            dependents[r].add(t)
            indeg[t] += 1

heap = [(sort_key(t), t) for t in tables if indeg[t] == 0]
heapq.heapify(heap)
order, seen = [], set()
while heap:
    _, t = heapq.heappop(heap)
    if t in seen:
        continue
    seen.add(t)
    order.append(t)
    for d in sorted(dependents[t]):
        indeg[d] -= 1
        if indeg[d] == 0 and d not in seen:
            heapq.heappush(heap, (sort_key(d), d))
for t in tables:
    if t not in seen:
        order.append(t)
        seen.add(t)
pos = {t: i for i, t in enumerate(order)}


# --------------------------------------------------------------------------- #
# 3. Render
# --------------------------------------------------------------------------- #
def references_clause(fk_def):
    m = re.match(r"FOREIGN KEY \([^)]*\) (REFERENCES .*)$", fk_def)
    clause = m.group(1) if m else fk_def
    return re.sub(r"REFERENCES (\w+)\(", r"REFERENCES \1 (", clause)


deferred = []
out = [BAR, f"-- {DB_NAME} — full schema (generated from live catalog)", BAR, ""]
for ext in extensions:
    out.append(f"CREATE EXTENSION IF NOT EXISTS {ext};")
out.append("")

current_domain = None
for t in order:
    dom = domain_of(t)
    if dom != current_domain:
        current_domain = dom
        out += [BAR, f"-- {dom}", BAR, ""]

    cons = cons_by[t]
    pk = next((c for c in cons if c["contype"] == "p"), None)
    pk_single = pk["cols"][0] if pk and pk["ncols"] == 1 else None

    inline_unique = set()
    inline_fk = {}
    table_level = []
    for c in cons:
        ct = c["contype"]
        if ct == "p":
            if c["ncols"] > 1:
                table_level.append(c["def"])
        elif ct == "u":
            if c["ncols"] == 1 and "NULLS NOT DISTINCT" not in c["def"]:
                inline_unique.add(c["cols"][0])
            else:
                table_level.append(c["def"])
        elif ct == "c":
            table_level.append(c["def"])
        elif ct == "f":
            if c["name"] in deferred_names:
                deferred.append((t, c))
                continue
            ref_ok = c["is_self"] or (c["reftbl"] in pos and pos[c["reftbl"]] <= pos[t])
            if c["ncols"] == 1 and ref_ok:
                inline_fk[c["cols"][0]] = references_clause(c["def"])
            elif ref_ok:
                table_level.append(c["def"])
            else:
                deferred.append((t, c))

    cols = cols_by[t]
    name_w = max((len(c["name"]) for c in cols), default=0)
    body = []
    for c in cols:
        tail = []
        if c["name"] == pk_single:
            tail.append("PRIMARY KEY")
        elif c["notnull"]:
            tail.append("NOT NULL")
        if c["default"] is not None:
            tail.append(f"DEFAULT {c['default']}")
        if c["name"] in inline_unique:
            tail.append("UNIQUE")
        if c["name"] in inline_fk:
            tail.append(inline_fk[c["name"]])
        line = f"    {c['name'].ljust(name_w)}  {fmt_type(c['type'])}"
        if tail:
            line += " " + " ".join(tail)
        body.append(line.rstrip())
    for dfn in table_level:
        body.append(f"    {dfn}")

    out.append(f"CREATE TABLE {t} (")
    out.append(",\n".join(body))
    out.append(");")
    out.append("")

if deferred:
    out += [BAR, "-- deferred foreign keys (break dependency cycles)", BAR, ""]
    for t, c in deferred:
        out.append(f"ALTER TABLE {t}")
        out.append(f"    ADD CONSTRAINT {c['name']} {c['def']};")
        out.append("")

_deschema = lambda d: d.replace(SCHEMA + ".", "")
idx_lines = [f"{_deschema(i['def'])};" for t in order for i in idx_by[t]]
if idx_lines:
    out += [BAR, "-- indexes", BAR, ""] + idx_lines + [""]

trg_lines = [f"{_deschema(tg['def'])};" for t in order for tg in trg_by[t]]
if trg_lines:
    out += [BAR, "-- triggers", BAR, ""] + trg_lines + [""]

sys.stdout.write("\n".join(out).rstrip() + "\n")
