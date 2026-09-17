# -*- coding: utf-8 -*-
"""Baut aus diesem Repository den Abzug, der veroeffentlicht wird.

WARUM EIN WERKZEUG UND NICHT EINMAL VON HAND:

Die Historie dieses Repositorys ist nicht veroeffentlichbar. Nicht wegen
Zugangsdaten — die wurden nie committet —, sondern wegen der Commit-Texte:
Sie nennen echte Belegnummern und die Namen von vier Tagungskunden. Dazu
traegt jeder Commit die Dienstadresse des Autors. Ein Umschalten auf
"oeffentlich" wuerde all das mitnehmen.

Der Abzug ist deshalb ein Schnappschuss OHNE Historie. Und weil das nicht
einmal passiert, sondern bei jeder Fortschreibung wieder, gehoert der
Vorgang in ein Werkzeug: Was ausgelassen wird, steht dann an einer Stelle
und laesst sich lesen, statt beim naechsten Mal neu erinnert zu werden.

    python3 tools/oeffentlich.py <zielverzeichnis>

Das Ziel muss leer sein oder nicht existieren. Geschrieben wird nur dorthin.
"""
from __future__ import annotations
import pathlib
import re
import subprocess
import sys
import zipfile

BASIS = pathlib.Path(__file__).resolve().parent.parent

# Was NICHT mitgeht. Jede Zeile mit Begruendung — wer etwas streichen will,
# soll die Begruendung widerlegen muessen.
AUSGELASSEN = {
    # Projektchronik und Messungen am Produktivsystem. Fuer einen fremden
    # Leser ohne Wert und voller Interna: Anschrift des Rechtstraegers,
    # Bankverbindung, Belege mit echten Betraegen, Geschaeftszahlen bis hin
    # zum hochgerechneten Jahresumsatz.
    "docs/00_STATUS.md": "Projekttagebuch",
    "docs/04_OPERA_OFFENE_PUNKTE.md": "abgearbeiteter Fragenkatalog",
    "docs/06_BEFUNDE_LIVE_DB.md": "Messprotokoll am Produktivsystem",
    "docs/07_UMSETZUNGSPLAN.md": "ueberholt, 01_ARCHITEKTUR deckt es ab",
    "docs/09_UDF_LEITWEG_ID.md": "Konfigurationsanalyse des Hauses, fachlich ueberholt",
    "docs/11_RECHTLICHER_RAHMEN.md": "enthaelt Geschaeftszahlen des Hauses",
    "docs/13_WUENSCHE.md": "Wunschliste mit Bearbeitungsstand",
    # Entscheidungsvorlage fuer die Buchhaltung eines Hauses.
    "docs/praesentation/XRechnung_Positionen_Buchhaltung.pptx": "interne Entscheidungsvorlage",
    "docs/praesentation/erzeugen.py": "erzeugt ebendiese Vorlage",
}

# Verzeichnisse, die gar nicht erst versioniert sind, aber im Arbeitsbaum
# liegen — zur Sicherheit noch einmal ausdruecklich.
NIEMALS = ("config/app.json", "config/users.json", "config/secret.key",
           "data/", "logs/", "reference/", "branding/", "validation/")

# Dieselbe Suche wie im Selbsttest, Abschnitt 12. Sie steht hier ein zweites
# Mal, weil der Abzug auch dann geprueft werden soll, wenn jemand ihn ohne
# vorherigen Selbsttest baut.
VERBOTEN = [
    (r"(?i)\bcp-berli[n]\.com\b", "Domain des Hauses"),
    (r"(?i)\bahorn-hotel[s]\.de\b", "Domain der Gruppe"),
    (r"(?i)\bbsh[g]\.com\b", "Domain eines Kunden"),
    (r"(?i)\b(crown[e]\s*plaza|alb[e]ck|zehde[n])\b", "Name des Hauses"),
    (r"(?i)\b(sophi[a]\s+genetics|dertou[r]|pfize[r])\b", "Name eines Kunden"),
    (r"(?i)\brocky\.berc[c]|heberccsvrdb[0]", "interner Hostname"),
    (r"\b10\.49\.\d{1,3}\.\d{1,3}\b", "interne IP-Adresse"),
    (r"\bBEVODEB[B]\b", "BIC des Hauses"),
    (r"\bDE81\s?1009\s?00", "IBAN des Hauses"),
    (r"\b1(2[6-9]|3[01])\d{4}\b", "Belegnummer aus dem Produktivbestand"),
    (r"\b199[5-6]\d{4}\b", "Buchungsnummer aus dem Produktivbestand"),
]
OHNE_INHALT = {".pdf", ".png", ".jpg", ".ico", ".woff2"}
ALS_ZIP = {".pptx", ".docx", ".xlsx"}


def text_von(p: pathlib.Path) -> str:
    """Der lesbare Text einer Datei — auch aus einem Office-Archiv.

    Ein .pptx ist ein ZIP mit XML darin. Frueher wurde es uebersprungen, und
    genau darin ueberlebten vier Kundennamen eine Bereinigung, die jede
    Textdatei erwischt hatte."""
    if p.suffix in ALS_ZIP:
        try:
            with zipfile.ZipFile(p) as z:
                roh = "".join(z.read(n).decode("utf-8", "ignore")
                              for n in z.namelist() if n.endswith(".xml"))
        except (zipfile.BadZipFile, OSError):
            return ""
        # NUR den Text, nicht das rohe XML. Eine Spaltenbreite wie
        # <a:gridCol w="..."/> steht dort als siebenstellige Zahl und sah
        # wie eine Belegnummer aus. Eine Pruefung, die Fehlalarm gibt, wird
        # frueher oder spaeter abgeschaltet — und das ist schlimmer als gar
        # keine Pruefung.
        #
        # (Die Zahl steht hier bewusst nicht ausgeschrieben: Sie faellt sonst
        # der eigenen Suche zum Opfer. Derselbe Grund wie bei den Mustern in
        # Abschnitt 12 des Selbsttests.)
        return " ".join(re.findall(r"<(?:a|w):t[^>]*>([^<]*)</(?:a|w):t>", roh))
    try:
        return p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""


def pruefen(wurzel: pathlib.Path) -> list[str]:
    befunde = []
    for p in sorted(wurzel.rglob("*")):
        if not p.is_file() or ".git" in p.parts or p.suffix in OHNE_INHALT:
            continue
        t = text_von(p)
        for muster, was in VERBOTEN:
            m = re.search(muster, t)
            if m:
                befunde.append(f"{p.relative_to(wurzel)}: {was} ({m.group(0)[:40]})")
    return befunde


def main(ziel: pathlib.Path) -> int:
    if ziel.exists() and any(ziel.iterdir()):
        print(f"FEHLER: {ziel} ist nicht leer.")
        return 2
    dateien = subprocess.run(["git", "ls-files"], cwd=BASIS,
                             capture_output=True, text=True, check=True).stdout.split()
    kopiert = ausgelassen = 0
    for rel in dateien:
        if rel in AUSGELASSEN:
            print(f"  ausgelassen  {rel}  ({AUSGELASSEN[rel]})")
            ausgelassen += 1
            continue
        if any(rel.startswith(n) for n in NIEMALS):
            print(f"  ausgelassen  {rel}  (Bestand, nie versioniert)")
            ausgelassen += 1
            continue
        quelle = BASIS / rel
        if not quelle.exists():
            continue
        zielweg = ziel / rel
        zielweg.parent.mkdir(parents=True, exist_ok=True)
        zielweg.write_bytes(quelle.read_bytes())
        kopiert += 1

    print(f"\n{kopiert} Dateien uebernommen, {ausgelassen} ausgelassen.")

    # Tote Verweise: Ein Link auf ein ausgelassenes Dokument ist schlimmer
    # als kein Link — der Leser sucht eine Datei, die es nie geben wird.
    tot = []
    namen = [pathlib.Path(a).name for a in AUSGELASSEN]
    for p in sorted(ziel.rglob("*.md")):
        t = p.read_text(encoding="utf-8")
        for name in namen:
            if name in t:
                tot.append(f"{p.relative_to(ziel)} verweist auf {name}")
    befunde = pruefen(ziel)

    if tot:
        print(f"\n{len(tot)} toter Verweis(e) auf ausgelassene Dokumente:")
        for z in tot:
            print("  -", z)
    if befunde:
        print(f"\n{len(befunde)} Fund(e) echter Daten Dritter:")
        for z in befunde:
            print("  -", z)
    if tot or befunde:
        print("\nDer Abzug ist NICHT fertig. Erst die Funde beheben.")
        return 1
    print("Keine toten Verweise, keine echten Daten Dritter gefunden.")
    print(f"\nNaechster Schritt — Historie beginnt neu, das ist Absicht:\n"
          f"  cd {ziel} && git init && git add -A && git commit")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(pathlib.Path(sys.argv[1]).expanduser().resolve()))
