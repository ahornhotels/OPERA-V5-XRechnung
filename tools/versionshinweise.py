# -*- coding: utf-8 -*-
"""Gibt den Abschnitt einer Version aus CHANGELOG.md aus.

    python3 tools/versionshinweise.py v1.0.0     # oder 1.0.0

Der GitHub-Workflow .github/workflows/release.yml macht daraus den Text des
Releases. Fehlt der Abschnitt, endet das Werkzeug mit Rueckgabewert 1 - dann
entsteht kein Release ohne Beschreibung.

EINE NEUE VERSION, Schritt fuer Schritt:
  1. VERSION hochzaehlen und in CHANGELOG.md oben einen Abschnitt
     "## [x.y.z] – JJJJ-MM-TT" anlegen. Der Selbsttest prueft, dass beide
     zusammenpassen.
  2. Committen und pushen wie immer.
  3. Im veroeffentlichten Repository: git tag -a vx.y.z -m "OPERA XRechnung x.y.z"
     und git push origin main --follow-tags
  4. Den Rest macht GitHub: Der Workflow prueft Tag gegen VERSION und legt
     das Release mit diesem Abschnitt an.
"""
from __future__ import annotations
import pathlib
import re
import sys

BASIS = pathlib.Path(__file__).resolve().parent.parent
KOPF = re.compile(r"^## \[(\d+\.\d+\.\d+)\]")


def abschnitte(text: str) -> list[tuple[str, str]]:
    """[(version, inhalt), ...] in der Reihenfolge der Datei."""
    ergebnis: list[tuple[str, list[str]]] = []
    for zeile in text.splitlines():
        treffer = KOPF.match(zeile)
        if treffer:
            ergebnis.append((treffer.group(1), []))
        elif zeile.startswith("## "):
            ergebnis.append(("", []))
        elif ergebnis:
            ergebnis[-1][1].append(zeile)
    return [(v, "\n".join(z).strip()) for v, z in ergebnis if v]


def hinweise(version: str, text: str | None = None) -> str | None:
    version = version.strip().removeprefix("v")
    if text is None:
        text = (BASIS / "CHANGELOG.md").read_text(encoding="utf-8")
    return next((inhalt for v, inhalt in abschnitte(text) if v == version), None)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    inhalt = hinweise(sys.argv[1])
    if not inhalt:
        sys.exit(f"In CHANGELOG.md steht kein Abschnitt fuer {sys.argv[1]}.")
    print(inhalt)
