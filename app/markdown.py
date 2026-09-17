"""Kleiner Markdown-Darsteller für die Hilfeseiten.

Bewusst keine Fremdbibliothek: die Anwendung stellt nur die eigenen beiden
Handbücher dar, und deren Umfang ist bekannt — Überschriften, Absätze, Listen,
Tabellen, Codeblöcke, Zitate, Trennlinien, fett, kursiv, Code und Links.
Alles wird escaped, bevor Formatierungen eingesetzt werden."""
from __future__ import annotations
import html
import re

_FETT = re.compile(r"\*\*(.+?)\*\*")
_KURSIV = re.compile(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])")
_CODE = re.compile(r"`([^`]+?)`")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")


def _inline(text: str) -> str:
    t = html.escape(text, quote=False)
    t = _CODE.sub(lambda m: f"<code>{m.group(1)}</code>", t)
    t = _FETT.sub(lambda m: f"<strong>{m.group(1)}</strong>", t)
    t = _KURSIV.sub(lambda m: f"<em>{m.group(1)}</em>", t)

    def _link(m: re.Match) -> str:
        ziel, beschriftung = m.group(2), m.group(1)
        if ziel.endswith(".md"):          # Verweise zwischen den Handbüchern
            ziel = "/hilfe/" + ziel[:-3].lower()
        elif not ziel.startswith(("http://", "https://", "#", "/")):
            return beschriftung           # Dateipfade nicht verlinken
        extern = ' target="_blank" rel="noopener"' if ziel.startswith("http") else ""
        return f'<a href="{html.escape(ziel, quote=True)}"{extern}>{beschriftung}</a>'

    return _LINK.sub(_link, t)


def _anker(text: str) -> str:
    roh = re.sub(r"<[^>]+>", "", text).lower()
    roh = re.sub(r"[^a-z0-9äöüß ]+", "", roh).strip().replace(" ", "-")
    return roh[:60]


def rendern(quelle: str) -> tuple[str, list[tuple[int, str, str]]]:
    """Gibt (HTML, Inhaltsverzeichnis) zurück.
    Das Verzeichnis ist eine Liste aus (Ebene, Text, Anker)."""
    zeilen = quelle.replace("\r\n", "\n").split("\n")
    aus: list[str] = []
    verzeichnis: list[tuple[int, str, str]] = []
    i = 0
    in_liste = ""     # "ul", "ol" oder ""

    def liste_schliessen() -> None:
        nonlocal in_liste
        if in_liste:
            aus.append(f"</{in_liste}>")
            in_liste = ""

    while i < len(zeilen):
        zeile = zeilen[i]
        blank = zeile.strip()

        if blank.startswith("```"):                       # Codeblock
            liste_schliessen()
            i += 1
            block = []
            while i < len(zeilen) and not zeilen[i].strip().startswith("```"):
                block.append(html.escape(zeilen[i]))
                i += 1
            aus.append("<pre><code>" + "\n".join(block) + "</code></pre>")
            i += 1
            continue

        if not blank:                                     # Leerzeile
            liste_schliessen()
            i += 1
            continue

        if re.match(r"^-{3,}$", blank):                   # Trennlinie
            liste_schliessen()
            aus.append("<hr>")
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", blank)         # Überschrift
        if m:
            liste_schliessen()
            ebene, text = len(m.group(1)), _inline(m.group(2))
            anker = _anker(text)
            if ebene <= 3:
                verzeichnis.append((ebene, re.sub(r"<[^>]+>", "", text), anker))
            aus.append(f'<h{ebene} id="{anker}">{text}</h{ebene}>')
            i += 1
            continue

        if blank.startswith("|") and i + 1 < len(zeilen) \
                and re.match(r"^\|[\s:|-]+\|$", zeilen[i + 1].strip()):
            liste_schliessen()                            # Tabelle
            def spalten(z: str) -> list[str]:
                return [s.strip() for s in z.strip().strip("|").split("|")]
            kopf = spalten(zeile)
            i += 2
            aus.append('<div class="tabelle"><table><tr>'
                       + "".join(f"<th>{_inline(s)}</th>" for s in kopf) + "</tr>")
            while i < len(zeilen) and zeilen[i].strip().startswith("|"):
                aus.append("<tr>" + "".join(f"<td>{_inline(s)}</td>"
                                            for s in spalten(zeilen[i])) + "</tr>")
                i += 1
            aus.append("</table></div>")
            continue

        if blank.startswith(">"):                         # Zitat
            liste_schliessen()
            block = []
            while i < len(zeilen) and zeilen[i].strip().startswith(">"):
                block.append(zeilen[i].strip().lstrip(">").strip())
                i += 1
            aus.append(f"<blockquote>{_inline(' '.join(block))}</blockquote>")
            continue

        m_ol = re.match(r"^(\d+)\.\s+(.*)$", blank)       # nummerierte Liste
        m_ul = re.match(r"^[-*]\s+(.*)$", blank)          # Aufzaehlung
        if m_ol or m_ul:
            art = "ol" if m_ol else "ul"
            if in_liste != art:
                liste_schliessen()
                aus.append(f"<{art}>")
                in_liste = art
            # Fortsetzungszeilen ZUERST einsammeln und erst dann formatieren.
            # Sonst zerreisst eine ueber den Zeilenumbruch laufende Auszeichnung
            # wie **fett** in zwei Haelften und bleibt unverarbeitet stehen —
            # jede Haelfte fuer sich ergibt kein vollstaendiges Paar.
            teile = [m_ol.group(2) if m_ol else m_ul.group(1)]
            i += 1
            while i < len(zeilen) and zeilen[i].strip() and not re.match(
                    r"^(#{1,6}\s|[-*]\s|\d+\.\s|\||>|```|-{3,}$)", zeilen[i].strip()):
                teile.append(zeilen[i].strip())
                i += 1
            aus.append(f"<li>{_inline(' '.join(teile))}</li>")
            continue
            continue

        absatz = [blank]                                  # Absatz
        i += 1
        while i < len(zeilen) and zeilen[i].strip() and not re.match(
                r"^(#{1,6}\s|[-*]\s|\d+\.\s|\||>|```|-{3,}$)", zeilen[i].strip()):
            absatz.append(zeilen[i].strip())
            i += 1
        aus.append(f"<p>{_inline(' '.join(absatz))}</p>")

    liste_schliessen()
    return "\n".join(aus), verzeichnis
