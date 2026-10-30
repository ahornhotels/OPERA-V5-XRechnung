"""Erklaerungen zu den Einstellungen — fuer die Tooltips der Konfigurationsseite.

Die Texte stehen NICHT hier, sondern in docs/15_EINSTELLUNGEN.md, und werden
von dort gelesen. Dieses Dokument erklaert jede Einstellung (der Selbsttest
stellt sicher, dass keine fehlt). Eine zweite Fassung in der Oberflaeche liefe
mit der Zeit auseinander — die Seite saehe dann anders aus, als das Dokument
sagt, und keiner wuesste, welches stimmt.

Gelesen werden die Tabellen unter den Ueberschriften
    ## `abschnitt` — ...
    | `feld`, `feld2` | Erklaerung |
und daraus wird {"abschnitt.feld": "Erklaerung"}. Markdown wird zu
schlichtem Text, ein Tooltip kann keine Formatierung."""
from __future__ import annotations

import re

from . import pfade

DOKU = pfade.PROGRAMM / "docs" / "15_EINSTELLUNGEN.md"

_ABSCHNITT = re.compile(r"^##\s+`([a-z_]+)`")
_ZEILE = re.compile(r"^\|\s*((?:`[a-z_]+`\s*,?\s*)+)\|(.+)\|\s*$")


def _schlicht(text: str) -> str:
    """Markdown zu Text: Links zu ihrem Wortlaut, ohne ** und Backticks."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return " ".join(text.split())


def erklaerungen(doku=None) -> dict[str, str]:
    """{"mail.bcc": "Blindkopie bei jeder ..."} — leer, wenn das Dokument fehlt.
    Eine fehlende Erklaerung ist kein Grund, die Seite nicht anzuzeigen."""
    try:
        zeilen = (doku or DOKU).read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    aus: dict[str, str] = {}
    abschnitt = None
    for zeile in zeilen:
        kopf = _ABSCHNITT.match(zeile)
        if kopf:
            abschnitt = kopf.group(1)
            continue
        if zeile.startswith("## "):
            abschnitt = None
            continue
        treffer = _ZEILE.match(zeile)
        if abschnitt and treffer:
            text = _schlicht(treffer.group(2))
            for feld in re.findall(r"`([a-z_]+)`", treffer.group(1)):
                aus[f"{abschnitt}.{feld}"] = text
    return aus
