"""Wo liegt was — Programm oder Bestand?

Solange alles in einem flachen Verzeichnis lag, war die Frage nicht zu
stellen: Programmdateien und Bestand hatten dieselbe Wurzel. Mit
Freigabeverzeichnissen (siehe docs/12_AKTUALISIERUNG.md) fallen die beiden
auseinander, und dann muss jede Stelle einzeln beantworten, wogegen sie
aufloest.

    PROGRAMM  wechselt bei jeder Aktualisierung.
              Vorlagen, SQL-Dateien, Handbuch, VERSION.

    BASIS     bleibt ueber Aktualisierungen hinweg stehen.
              config/, data/, logs/, validation/ — alles, was der Betrieb
              angesammelt hat oder was zu gross fuers Repository ist.

Der Unterschied ist nicht theoretisch. Die Ablage der erzeugten Rechnungen
steht als RELATIVER Pfad in der Konfiguration ("data/xml"). Loeste der gegen
das Programmverzeichnis auf, laegen die Rechnungen in der Freigabe — und das
Aufraeumen alter Freigaben loeschte sie nach der dritten Aktualisierung.
Aufbewahrungspflichtige Belege, still, ohne Fehlermeldung.

Aus __file__ laesst sich BASIS nicht zurueckgewinnen: Ein Symlink auf das
Arbeitsverzeichnis taucht dort nicht auf, weder mit noch ohne resolve(). Die
Angabe muss von aussen kommen — deshalb die Umgebungsvariablen. Fehlen sie,
gilt der flache Aufbau von frueher, und alles bleibt, wie es war.
"""
from __future__ import annotations
import os
from pathlib import Path

# Die Wurzel des Programms: das Verzeichnis ueber app/.
PROGRAMM = Path(__file__).resolve().parent.parent

# Die Wurzel der Installation. Ohne Angabe dieselbe wie das Programm.
BASIS = Path(os.environ.get("XRECHNUNG_BASIS") or PROGRAMM)

CONFIG_DIR = Path(os.environ.get("XRECHNUNG_CONFIG_DIR") or (BASIS / "config"))
# Das Erscheinungsbild des Hauses. Gehoert in den BESTAND, nicht ins Programm:
# Es ist Eigentum des Hauses, nicht Teil der Anwendung — und es soll eine
# Aktualisierung ueberstehen, ohne dass jemand daran denken muss. Liegt hier
# eine stil.css, wird sie NACH der mitgelieferten geladen und ueberschreibt,
# was sie ueberschreiben will. Schriften gehoeren daneben.
BRANDING_DIR = Path(os.environ.get("XRECHNUNG_BRANDING_DIR") or (BASIS / "branding"))
DATEN_DIR = Path(os.environ.get("XRECHNUNG_DATEN_DIR") or (BASIS / "data"))
LOG_DIR = Path(os.environ.get("XRECHNUNG_LOG_DIR") or (BASIS / "logs"))


def im_bestand(wert: str | os.PathLike) -> Path:
    """Einen Pfad aus der Konfiguration aufloesen. Relative Angaben gelten
    gegenueber der INSTALLATION, nicht gegenueber dem Programm."""
    p = Path(wert)
    return p if p.is_absolute() else BASIS / p
