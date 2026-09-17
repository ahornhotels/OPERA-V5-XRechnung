#!/usr/bin/env python3
"""Prueft die Abfragen in sql/opera/ gegen das Data Dictionary — ohne Datenbank.

Anlass: ORA-00904 "N"."NAME": invalid identifier. Die Tabelle NAME hat keine
Spalte NAME (sondern LAST, FIRST, COMPANY). Solche Fehler zeigen sich sonst
erst an der Live-Datenbank, und dort nur auf der Seite, die gerade jemand
aufruft.

Erkannt werden Tabellenaliase aus FROM/JOIN und daraufhin alle Verweise
<alias>.<spalte>. Unbekannte Aliase (Unterabfragen, dual) werden uebersprungen.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parent.parent
SQL_DIR = BASIS / "sql" / "opera"
DD = BASIS / "reference" / "dd_json"

# In der Datenbank heissen die Tabellen ..._E, die Anwendung nutzt die
# gleichnamigen Views ohne Suffix.
def dictionary() -> dict[str, set[str]]:
    aus: dict[str, set[str]] = {}
    for datei in ("dd_live.json", "dd_tables_2010.json", "dd_views.json"):
        pfad = DD / datei
        if not pfad.exists():
            continue
        for name, inhalt in json.loads(pfad.read_text(encoding="utf-8")).items():
            spalten = {c["name"].upper() for c in inhalt["columns"]}
            for schluessel in (name.upper(), name.upper().removesuffix("_E")):
                aus.setdefault(schluessel, set()).update(spalten)
    return aus


ALIAS = re.compile(r"\b(?:FROM|JOIN)\s+opera\.([A-Za-z0-9_$#]+)\s+([A-Za-z][A-Za-z0-9_]*)",
                   re.IGNORECASE)
VERWEIS = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*)\.([A-Za-z][A-Za-z0-9_]*)\b")
SCHLUESSELWORT = {"on", "and", "or", "where", "select", "from", "join", "left",
                  "as", "case", "when", "then", "else", "end", "opera"}


def pruefe_datei(pfad: Path, dd: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """Gibt (Fehler, Hinweise) zurueck. Hinweise sind Tabellen, die das
    Dictionary nicht kennt — der Live-Auszug enthaelt bewusst keine Views."""
    text = pfad.read_text(encoding="utf-8")
    ohne_kommentar = "\n".join(z.split("--")[0] for z in text.splitlines())

    # Ein Alias kann in verschiedenen Unterabfragen fuer verschiedene Tabellen
    # stehen — Oracle trennt die Gueltigkeitsbereiche, dieser Pruefer nicht.
    # Deshalb wird eine Spalte akzeptiert, wenn sie in EINER der Tabellen
    # vorkommt, fuer die der Alias im selben Text steht.
    aliase: dict[str, set[str]] = {}
    for tabelle, alias in ALIAS.findall(ohne_kommentar):
        aliase.setdefault(alias.lower(), set()).add(tabelle.upper())

    fehler, hinweise = [], []
    gesehen = set()
    for alias, spalte in VERWEIS.findall(ohne_kommentar):
        if alias.lower() in SCHLUESSELWORT or alias.lower() not in aliase:
            continue
        tabellen = aliase[alias.lower()]
        unbekannt = [t for t in tabellen if t not in dd]
        for t in unbekannt:
            if t not in gesehen:
                gesehen.add(t)
                hinweise.append(f"opera.{t} steht nicht im Dictionary (vermutlich eine View) "
                                "— Spalten dieser Tabelle ungeprueft")
        bekannte = [t for t in tabellen if t in dd]
        if not bekannte:
            continue
        if any(spalte.upper() in dd[t] for t in bekannte):
            continue
        t = bekannte[0]
        aehnlich = sorted(s for s in dd[t] if s.startswith(spalte.upper()[:4]))[:4]
        fehler.append(f"{'/'.join(bekannte)}.{spalte} gibt es nicht (Alias {alias})"
                      + (f" — vielleicht: {', '.join(aehnlich)}" if aehnlich else ""))
    return fehler, sorted(set(hinweise))


# Zwei Muster, die keine Spaltenfehler sind, aber jedes Mal einen vollen
# Tabellendurchlauf ausloesen. Beide sind hier schon aufgetreten und haben
# zusammen aus 0.15 Sekunden je Rechnung zwei Sekunden gemacht — messbar nur
# an der Anlage, ablesbar aber an der Abfrage.
# Spalten, ueber die in FOLIO$_TAX und FINANCIAL_TRANSACTIONS indiziert wird.
# Nur fuer diese lohnt die Warnung; bei einer nicht indizierten Spalte aendert
# eine Funktion nichts.
INDIZIERTE_SPALTEN = {"resort", "bill_no", "folio_no", "name_id", "payee_name_id",
                      "account_code", "invoice_no", "bill_generation_date",
                      "business_date", "trx_code"}


def pruefe_folio_zugriff(text: str) -> list[str]:
    """FOLIO$_TAX_E hat 19 Indizes, aber keinen auf FOLIO_NO."""
    beanstandet = []
    ohne_kommentare = "\n".join(z.split("--")[0] for z in text.splitlines())

    # 1. Direkte Suche ueber FOLIO_NO statt ueber FOLIOS
    for treffer in re.finditer(r"(?is)\bfrom\s+opera\.folio\$_tax\s+(\w+)(.{0,600})",
                               ohne_kommentare):
        alias, rumpf = treffer.group(1), treffer.group(2)
        if re.search(rf"(?is)\bwhere\b[^;]{{0,300}}?\b{alias}\.folio_no\s*=", rumpf):
            beanstandet.append(
                f"sucht ueber {alias}.folio_no in FOLIO$_TAX — dort gibt es keinen Index. "
                "Ueber opera.folios auf die BILL_NO gehen (1546 ms gegen 1.4 ms).")

    # 2. Korrelierte Folionummer: der Wert steht erst zur Laufzeit fest,
    #    dann kann Oracle den Index nicht mehr ansetzen (1928 ms gegen 0.7 ms).
    for treffer in re.finditer(r"(?is)opera\.folios\s+(\w+)(.{0,300})", ohne_kommentare):
        rumpf = treffer.group(2)
        bezug = re.search(r"(?is)\.folio_no\s*=\s*(\w+)\.folio_no", rumpf)
        if bezug:
            beanstandet.append(
                f"vergleicht folio_no mit {bezug.group(1)}.folio_no aus der aeusseren "
                "Abfrage. Korreliert wird die Unterabfrage nicht indiziert — die "
                "Folionummer ueber eine eigene Unterabfrage auf :bill_no holen.")
    # 3. Funktion auf der SPALTE statt auf dem Vergleichswert. Sobald die
    #    Spalte in einem Ausdruck steckt, ist der Index draussen. Der
    #    Unterschied ist wichtig: TRUNC(SYSDATE) - :days ist richtig, dort
    #    steht die Funktion auf der anderen Seite.
    for treffer in re.finditer(
            r"(?is)\b(UPPER|LOWER|TRUNC|SUBSTR|TO_CHAR|NVL)\s*\(\s*(\w+)\.(\w+)[^)]*\)"
            r"\s*(=|<|>|<=|>=|\bLIKE\b|\bIN\b|\bBETWEEN\b)", ohne_kommentare):
        funktion, alias, spalte = treffer.group(1), treffer.group(2), treffer.group(3)
        if spalte.lower() in INDIZIERTE_SPALTEN:
            beanstandet.append(
                f"{funktion}({alias}.{spalte}) steht auf der Spaltenseite eines Vergleichs. "
                "Damit faellt der Index aus — die Funktion gehoert auf den Vergleichswert.")
    return beanstandet


def main() -> int:
    dd = dictionary()
    if not dd:
        print("Kein Data Dictionary unter reference/dd_json/ — Pruefung uebersprungen.")
        return 0
    gesamt = 0
    for pfad in sorted(SQL_DIR.glob("*.sql")):
        fehler, hinweise = pruefe_datei(pfad, dd)
        fehler += pruefe_folio_zugriff(pfad.read_text(encoding="utf-8"))
        gesamt += len(fehler)
        if fehler or hinweise:
            print(f"\n{pfad.name}")
            for f in fehler:
                print("   FEHLER ", f)
            for h in hinweise:
                print("   Hinweis", h)
        else:
            print(f"{pfad.name}: in Ordnung")
    print()
    print(f"{gesamt} Beanstandung(en)" if gesamt else "Alle Abfragen passen zum Dictionary.")
    return 1 if gesamt else 0


if __name__ == "__main__":
    sys.exit(main())
