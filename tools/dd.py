#!/usr/bin/env python3
"""Nachschlagewerkzeug fuer das geparste OPERA-Data-Dictionary.

  python3 tools/dd.py FOLIO_DETAIL              # Spalten einer Tabelle/View
  python3 tools/dd.py -s TAX_PERC               # Spalten suchen (Regex)
  python3 tools/dd.py -t FOLIO                  # Tabellen-/Viewnamen suchen
  python3 tools/dd.py FOLIO_DETAIL -f TAX       # Spalten filtern

Quellen (in dieser Reihenfolge):
  1. reference/dd_json/dd_live.json — Live-Schema der eigenen Installation (OPERA 19c,
     mehrere tausend Tabellen, mit Zeilenzahlen), aus tools/parse_dd_live.py
  2. dd_tables_2010.json / dd_views.json — die PDF-Dictionaries von 2010,
     nur noch als Rueckfall (Beschreibungstexte, Views)
Keine DB-Verbindung noetig.
"""
import json, re, sys, argparse, pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent / "reference" / "dd_json"

def load():
    """Das eigene Live-Schema hat Vorrang, danach die PDF-Dictionaries
    von 2010 als Rueckfall fuer Beschreibungen und Views."""
    d = {}
    for f, kind in (("dd_live.json", "LIVE"),
                    ("dd_tables_2010.json", "DOC-2010"),
                    ("dd_views.json", "VIEW-2010")):
        path = BASE / f
        if not path.exists():
            continue
        for name, body in json.loads(path.read_text(encoding="utf-8")).items():
            d.setdefault(name, {**body, "kind": kind})
    return d

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?")
    ap.add_argument("-s", "--search-column")
    ap.add_argument("-t", "--search-table")
    ap.add_argument("-f", "--filter")
    a = ap.parse_args()
    d = load()

    if a.search_table:
        rx = re.compile(a.search_table, re.I)
        for n in sorted(d):
            if rx.search(n):
                rows = d[n].get("rows") or "-"
                print(f"{d[n]['kind']:9} {n:40} {len(d[n]['columns']):4} Sp.  {rows:>12} Zeilen")
        return
    if a.search_column:
        rx = re.compile(a.search_column, re.I)
        for n in sorted(d):
            hits = [c["name"] for c in d[n]["columns"] if rx.search(c["name"])]
            if hits:
                print(f"{n}: {', '.join(hits[:15])}{' …' if len(hits) > 15 else ''}")
        return
    if not a.name:
        print(f"{len(d)} Objekte im Dictionary. -h fuer Hilfe."); return
    t = d.get(a.name.upper())
    if not t:
        print("nicht gefunden — mit -t suchen"); sys.exit(1)
    rows = t.get("rows")
    print(f"== {a.name.upper()} ({t['kind']}) — {len(t['columns'])} Spalten"
          + (f", {rows} Zeilen" if rows else ""))
    if t["desc"].strip():
        print(re.sub(r"\s+", " ", t["desc"])[:600], "\n")
    rx = re.compile(a.filter, re.I) if a.filter else None
    for c in t["columns"]:
        if rx and not rx.search(c["name"]):
            continue
        pk = f"PK{c['pk']}" if c.get("pk") else ""
        print(f"  {c['name']:35} {c['type']:20} {c['null']:4} {pk:4} {c.get('comment','')}")

if __name__ == "__main__":
    main()
