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

# Standard library
import json
import os
import re
import sys
from collections import defaultdict
import heapq

# Third-party
import psycopg2

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_USER = os.environ.get("DB_USER", "alpenwege")
DB_PASS = os.environ.get("DB_PASS", "alpenwege")
DB_NAME = os.environ.get("DB_NAME", "alpenwege")
SCHEMA = os.environ.get("SCHEMA", "public")

EXCLUDE = {"spatial_ref_sys"}
EXCLUDE |= {t.strip() for t in os.environ.get("EXCLUDE", "").split(",") if t.strip()}

DOMAIN_PRIORITY = {
    "core": 1,
    "asset": 2,
    "compendium": 3,
    "explorer": 4,
    "profile": 5,
    "social": 6,
}
KIND_PRIORITY = {"usr": 0, "ref": 0, "cat": 0, "sub": 0, "agg": 1, "m2m": 2}

TYPE_ALIASES = {
    "timestamp with time zone": "timestamptz",
    "timestamp without time zone": "timestamp",
}

# Reusable section-separator bar for the generated SQL comments.
BAR = "-- " + "=" * 76

# Open a read-only, autocommit connection to the live database for catalog queries.
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname=DB_NAME
)
conn.set_session(readonly=True, autocommit=True)
cur = conn.cursor()


def query_json(sql):
    # Run a SQL query whose single result cell is a JSON array, and return it.
    # Params:
    #   sql: the SQL statement to execute (expected to SELECT one json_agg column).
    # Returns: the decoded list, or an empty list if the result is NULL/empty.
    cur.execute(sql)
    row = cur.fetchone()
    if row and row[0]:
        # psycopg2 may hand back an already-parsed list or a JSON string.
        return row[0] if isinstance(row[0], list) else json.loads(row[0])
    return []


def domain_of(t):
    # Extract the domain prefix of a table name (text before the first underscore).
    # Params:
    #   t: the table name, e.g. "explorer_agg_track".
    # Returns: the domain segment, e.g. "explorer".
    return t.split("_", 1)[0]


def kind_of(t):
    # Extract the "kind" segment of a table name (the second underscore-part).
    # Params:
    #   t: the table name, e.g. "explorer_agg_track".
    # Returns: the kind segment (e.g. "agg"), or "" if there is none.
    p = t.split("_")
    return p[1] if len(p) > 1 else ""


def fmt_type(t):
    # Normalize a PostgreSQL type name for display.
    # Params:
    #   t: the raw type string from the catalog.
    # Returns: the aliased type with a space added inside numeric(p,s) specifiers.
    t = TYPE_ALIASES.get(t, t)
    return re.sub(r"\(([A-Za-z]+),(\d+)\)", r"(\1, \2)", t)


# --------------------------------------------------------------------------- #
# 1. Pull catalog
# --------------------------------------------------------------------------- #
# Shared WHERE fragment: restrict to ordinary tables ('r') in the target schema.
FILTER = f"n.nspname = '{SCHEMA}' AND c.relkind = 'r'"

# All base table names in the schema, minus the excluded set.
tables = [
    t
    for t in query_json(f"""
SELECT coalesce(json_agg(c.relname ORDER BY c.relname), '[]')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE {FILTER};""")
    if t not in EXCLUDE
]
tset = set(tables)

# Per-column metadata (name, type, NOT NULL, default) for every table.
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

# All PK/UNIQUE/CHECK/FK constraints, including the columns and referenced table.
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

# Indexes that are NOT the implicit ones backing a PK/UNIQUE constraint.
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

# User-defined (non-internal) triggers on each table.
triggers = query_json(f"""
SELECT coalesce(json_agg(json_build_object(
    'tbl', t.relname, 'name', tg.tgname, 'def', pg_get_triggerdef(tg.oid)
  ) ORDER BY t.relname, tg.tgname), '[]')
FROM pg_trigger tg JOIN pg_class t ON t.oid = tg.tgrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
WHERE n.nspname = '{SCHEMA}' AND NOT tg.tgisinternal;""")

# Installed extensions (excluding the always-present plpgsql).
extensions = query_json("""
SELECT coalesce(json_agg(extname ORDER BY extname), '[]')
FROM pg_extension WHERE extname <> 'plpgsql';""")

# All catalog data is loaded; close the DB connection.
cur.close()
conn.close()

# Bucket the flat catalog lists by table name for quick per-table lookup.
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

# Lookup of (table, column) -> NOT NULL flag, used to detect nullable FKs.
notnull = {(c["tbl"], c["name"]): c["notnull"] for c in columns}


def fk_nullable(con):
    # Decide whether a foreign-key constraint is a single, nullable column.
    # Params:
    #   con: a constraint dict from the catalog query.
    # Returns: True if it is a one-column FK whose column allows NULLs.
    return con["ncols"] == 1 and not notnull.get((con["tbl"], con["cols"][0]), True)


# --------------------------------------------------------------------------- #
# 2. Break cycles, then Kahn sort
# --------------------------------------------------------------------------- #
# Build the FK dependency graph (table -> set of tables it references).
# fk_by_edge keeps the actual constraints behind each edge for later deferral.
deps = defaultdict(set)
fk_by_edge = defaultdict(list)
for c in constraints:
    # Only real FK edges between two distinct in-scope tables form dependencies.
    if (
        c["contype"] == "f"
        and c["tbl"] in tset
        and c["reftbl"] in tset
        and not c["is_self"]
    ):
        deps[c["tbl"]].add(c["reftbl"])
        fk_by_edge[(c["tbl"], c["reftbl"])].append(c)

# Names of FK constraints that will be emitted later as ALTER TABLE (to break cycles).
deferred_names = set()


def pick_edge_to_defer(a, b):
    # Break a dependency cycle between tables a and b by deferring one FK edge.
    # Params:
    #   a, b: the two table names forming a back-edge (a currently depends on b).
    # Returns: nothing; records the chosen FK in deferred_names and drops the dep edge.
    # Prefer to defer a nullable reciprocal FK (b -> a) so ordering stays natural.
    recips = fk_by_edge.get((b, a), [])
    nn_recip = [c for c in recips if fk_nullable(c)]
    if nn_recip:
        for c in nn_recip:
            deferred_names.add(c["name"])
        deps[b].discard(a)
        return
    # Otherwise defer the forward FK (a -> b) instead.
    for c in fk_by_edge.get((a, b), []):
        deferred_names.add(c["name"])
    deps[a].discard(b)


# DFS coloring states for cycle detection.
WHITE, GRAY, BLACK = 0, 1, 2
color = {t: WHITE for t in tables}


def sort_key(t):
    # Deterministic ordering key: domain priority, then kind priority, then name.
    # Params:
    #   t: the table name.
    # Returns: a tuple used to order tables (user tables sort first via domain -1).
    dom = -1 if kind_of(t) == "usr" else DOMAIN_PRIORITY.get(domain_of(t), 99)
    return (dom, KIND_PRIORITY.get(kind_of(t), 1), t)


def dfs(root):
    # Iterative depth-first search that detects and breaks FK dependency cycles.
    # Params:
    #   root: the starting table for this traversal.
    # Returns: nothing; mutates `color` and calls pick_edge_to_defer on back-edges.
    # Explicit stack of (node, iterator over its sorted neighbors).
    stack = [(root, iter(sorted(deps[root], key=sort_key)))]
    color[root] = GRAY
    while stack:
        node, it = stack[-1]
        advanced = False
        for nb in it:
            # Skip neighbors that are neither tracked nodes nor colored.
            if nb not in deps and nb not in color:
                continue
            if color.get(nb, BLACK) == GRAY:
                # A GRAY neighbor means a back-edge -> a cycle to break here.
                pick_edge_to_defer(node, nb)
            elif color.get(nb, BLACK) == WHITE:
                # Descend into the first unvisited neighbor.
                color[nb] = GRAY
                stack.append((nb, iter(sorted(deps[nb], key=sort_key))))
                advanced = True
                break
        if not advanced:
            # All neighbors processed: finalize this node.
            color[node] = BLACK
            stack.pop()


# Run DFS from every still-unvisited table to break all cycles.
for t in sorted(tables, key=sort_key):
    if color[t] == WHITE:
        dfs(t)

# Compute in-degrees and reverse edges for a Kahn topological sort.
indeg = {t: 0 for t in tables}
dependents = defaultdict(set)
for t, refs in deps.items():
    for r in refs:
        if r != t:
            dependents[r].add(t)
            indeg[t] += 1

# Seed a priority heap with all tables that have no remaining dependencies.
heap = [(sort_key(t), t) for t in tables if indeg[t] == 0]
heapq.heapify(heap)
order, seen = [], set()
while heap:
    # Emit the highest-priority ready table, then relax its dependents.
    _, t = heapq.heappop(heap)
    if t in seen:
        continue
    seen.add(t)
    order.append(t)
    for d in sorted(dependents[t]):
        indeg[d] -= 1
        if indeg[d] == 0 and d not in seen:
            heapq.heappush(heap, (sort_key(d), d))
# Append any tables left over (e.g. inside unresolved cycles) to keep output complete.
for t in tables:
    if t not in seen:
        order.append(t)
        seen.add(t)
# Map each table to its final position, used to decide inline vs deferred FKs.
pos = {t: i for i, t in enumerate(order)}


# --------------------------------------------------------------------------- #
# 3. Render
# --------------------------------------------------------------------------- #
def references_clause(fk_def):
    # Extract and tidy the "REFERENCES ..." tail of a foreign-key definition.
    # Params:
    #   fk_def: the full FK constraint definition string from the catalog.
    # Returns: the REFERENCES clause with a space inserted before the column list.
    m = re.match(r"FOREIGN KEY \([^)]*\) (REFERENCES .*)$", fk_def)
    clause = m.group(1) if m else fk_def
    return re.sub(r"REFERENCES (\w+)\(", r"REFERENCES \1 (", clause)


# Accumulators: `deferred` holds FKs emitted after the tables; `out` is the SQL lines.
deferred = []
out = [BAR, f"-- {DB_NAME} — full schema (generated from live catalog)", BAR, ""]
# Emit CREATE EXTENSION lines first so dependent types exist.
for ext in extensions:
    out.append(f"CREATE EXTENSION IF NOT EXISTS {ext};")
out.append("")

# Walk tables in dependency order, printing a header whenever the domain changes.
current_domain = None
for t in order:
    dom = domain_of(t)
    if dom != current_domain:
        current_domain = dom
        out += [BAR, f"-- {dom}", BAR, ""]

    # Identify the primary key; a single-column PK is rendered inline on its column.
    cons = cons_by[t]
    pk = next((c for c in cons if c["contype"] == "p"), None)
    pk_single = pk["cols"][0] if pk and pk["ncols"] == 1 else None

    # Sort constraints into inline (per-column) vs table-level vs deferred.
    inline_unique = set()
    inline_fk = {}
    table_level = []
    for c in cons:
        ct = c["contype"]
        if ct == "p":
            # Composite PKs can't be inline; render them as a table-level line.
            if c["ncols"] > 1:
                table_level.append(c["def"])
        elif ct == "u":
            # Simple single-column UNIQUE goes inline; anything fancier is table-level.
            if c["ncols"] == 1 and "NULLS NOT DISTINCT" not in c["def"]:
                inline_unique.add(c["cols"][0])
            else:
                table_level.append(c["def"])
        elif ct == "c":
            # CHECK constraints are always table-level.
            table_level.append(c["def"])
        elif ct == "f":
            # FKs flagged for cycle-breaking are deferred to an ALTER TABLE later.
            if c["name"] in deferred_names:
                deferred.append((t, c))
                continue
            # A FK can be inline/table-level only if its target is already emitted.
            ref_ok = c["is_self"] or (c["reftbl"] in pos and pos[c["reftbl"]] <= pos[t])
            if c["ncols"] == 1 and ref_ok:
                inline_fk[c["cols"][0]] = references_clause(c["def"])
            elif ref_ok:
                table_level.append(c["def"])
            else:
                # Target not yet emitted -> defer this FK too.
                deferred.append((t, c))

    # Render the column lines, aligning names to the widest column name.
    cols = cols_by[t]
    name_w = max((len(c["name"]) for c in cols), default=0)
    body = []
    for c in cols:
        # Build the trailing modifiers (PK/NOT NULL/DEFAULT/UNIQUE/inline FK) for the column.
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
    # Append any table-level constraint lines after the columns.
    for dfn in table_level:
        body.append(f"    {dfn}")

    # Assemble the CREATE TABLE statement for this table.
    out.append(f"CREATE TABLE {t} (")
    out.append(",\n".join(body))
    out.append(");")
    out.append("")

# Emit the deferred FKs (the ones that broke cycles) as ALTER TABLE statements.
if deferred:
    out += [BAR, "-- deferred foreign keys (break dependency cycles)", BAR, ""]
    for t, c in deferred:
        out.append(f"ALTER TABLE {t}")
        out.append(f"    ADD CONSTRAINT {c['name']} {c['def']};")
        out.append("")

# Helper to strip the schema prefix from generated index/trigger definitions.
_deschema = lambda d: d.replace(SCHEMA + ".", "")
# Emit non-constraint indexes, in table order.
idx_lines = [f"{_deschema(i['def'])};" for t in order for i in idx_by[t]]
if idx_lines:
    out += [BAR, "-- indexes", BAR, ""] + idx_lines + [""]

# Emit user-defined triggers, in table order.
trg_lines = [f"{_deschema(tg['def'])};" for t in order for tg in trg_by[t]]
if trg_lines:
    out += [BAR, "-- triggers", BAR, ""] + trg_lines + [""]

# Write the assembled DDL to stdout, trimming trailing whitespace.
sys.stdout.write("\n".join(out).rstrip() + "\n")
