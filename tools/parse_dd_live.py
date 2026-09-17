#!/usr/bin/env python3
"""Parst das Live-Data-Dictionary (Markdown, reference/opera-datadictionary/)
nach reference/dd_json/dd_live.json — gleiche Struktur wie die PDF-Parses."""
import json, re, pathlib, sys

BASE = pathlib.Path(__file__).resolve().parent.parent / "reference" / "opera-datadictionary"
OUT = pathlib.Path(__file__).resolve().parent.parent / "reference" / "dd_json" / "dd_live.json"

H = re.compile(r"^## ([A-Z0-9_\$#]+)\s*$")
META = re.compile(r"^\*(\d+) Spalten - Zeilen laut Statistik: ([\d.,-]+)\*")
ROW = re.compile(r"^\| *(\d+) *\| *`([^`]+)` *\| *([^|]*?) *\| *([^|]*?) *\| *([^|]*?) *\| *(.*?) *\|$")

tables = {}
for f in sorted(BASE.glob("dd-*.md")):
    name = None
    for line in f.read_text(encoding="utf-8").splitlines():
        m = H.match(line)
        if m:
            name = m.group(1)
            tables[name] = {"columns": [], "rows": None, "desc": "", "file": f.name}
            continue
        if not name:
            continue
        m = META.match(line.strip())
        if m:
            tables[name]["rows"] = m.group(2)
            continue
        m = ROW.match(line)
        if m and m.group(2) != "Spalte":
            tables[name]["columns"].append({
                "name": m.group(2), "type": m.group(3),
                "null": m.group(4), "pk": m.group(5), "comment": m.group(6),
            })

print(f"{len(tables)} Tabellen, {sum(len(t['columns']) for t in tables.values())} Spalten", file=sys.stderr)
OUT.write_text(json.dumps(tables, indent=1), encoding="utf-8")
print("->", OUT, file=sys.stderr)
