"""Zustandshaltung in SQLite: Rechnungen, Versandprotokoll, Sitzungen."""
from __future__ import annotations
import logging
import sqlite3
from datetime import datetime, timedelta
import os
from pathlib import Path

from . import pfade

# Der Arbeitsstand gehoert zum BESTAND, nicht zum Programm (siehe app/pfade.py).
BASE = pfade.PROGRAMM
DATEN_DIR = pfade.DATEN_DIR
DB_FILE = DATEN_DIR / "status.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rechnungen (
    bill_no        INTEGER PRIMARY KEY,
    resort         TEXT,
    invoice_no     TEXT,
    issuedate      TEXT,
    total_net      REAL,
    total_gross    REAL,
    kunde          TEXT,
    leitweg_id     TEXT,
    firmenbezug    TEXT,
    empfaenger_typ TEXT,
    empfaenger_land TEXT,
    city_ledger    REAL,
    empfaenger     TEXT,
    status         TEXT NOT NULL DEFAULT 'neu',
    xml_pfad       TEXT,
    fehler         TEXT,
    zuerst_gesehen TEXT,
    faellig_ab     TEXT,
    gesendet_am    TEXT
);
CREATE TABLE IF NOT EXISTS protokoll (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    zeit      TEXT NOT NULL,
    bill_no   INTEGER,
    benutzer  TEXT,
    aktion    TEXT NOT NULL,
    erfolg    INTEGER NOT NULL DEFAULT 1,
    text      TEXT
);
CREATE INDEX IF NOT EXISTS protokoll_bill_no ON protokoll (bill_no, id);
CREATE TABLE IF NOT EXISTS sitzungen (
    token    TEXT PRIMARY KEY,
    benutzer TEXT NOT NULL,
    rolle    TEXT NOT NULL,
    laeuft_ab TEXT NOT NULL
);
"""

# status: neu | pruefung | bereit | gesendet | fehler | ignoriert
#
# Gespeichert wird ohne Umlaute, weil der Wert auch in Adresszeilen, Protokoll
# und Dateinamen vorkommt. Was der Anwender SIEHT, ist etwas anderes — dafuer
# gibt es STATUS_NAMEN. Frueher stand in der Oberflaeche schlicht "pruefung".
STATUS_NAMEN = {
    "neu": "Neu",
    "pruefung": "Prüfung",
    "bereit": "Bereit",
    "gesendet": "Gesendet",
    "fehler": "Fehler",
    "ignoriert": "Zurückgelegt",
}
STATUS_REIHE = ["neu", "pruefung", "bereit", "gesendet", "fehler", "ignoriert"]


def status_name(wert: str | None) -> str:
    return STATUS_NAMEN.get((wert or "").strip(), (wert or "").strip())
#   pruefung = nie automatisch versenden, erst nach Sichtpruefung


def verbindung() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_FILE, timeout=15)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


# Was in den Tabellen stehen MUSS. CREATE TABLE IF NOT EXISTS legt eine
# bestehende Tabelle nicht an — eine spaeter hinzugekommene Spalte fehlt dort
# also fuer immer, und der Fehler zeigt sich erst mitten im Betrieb
# ("table rechnungen has no column named city_ledger"). Deshalb wird beim
# Start abgeglichen und additiv nachgezogen; in SQLite ist das gefahrlos.
SOLL_SPALTEN = {
    "rechnungen": {
        "bill_no": "INTEGER", "resort": "TEXT", "invoice_no": "TEXT",
        "issuedate": "TEXT", "total_net": "REAL", "total_gross": "REAL",
        "kunde": "TEXT", "leitweg_id": "TEXT", "firmenbezug": "TEXT",
        "empfaenger_typ": "TEXT", "empfaenger_land": "TEXT", "city_ledger": "REAL",
        "name_id": "INTEGER",
        # Eigene Spalte statt einer Textsuche im Fehlerfeld: Ein Beleg kann
        # gleichzeitig ohne Adresse UND aus einem anderen Grund in der
        # Sichtpruefung sein. Ueber den Text war nur eines von beidem
        # abbildbar — gut ein Drittel der Pflegefaelle fiel deshalb durch.
        "adresse_fehlt": "INTEGER",
        # Von Hand eingetragene Kaeuferreferenz (BT-10). Eine abgerechnete
        # Reservierung laesst sich in OPERA nicht mehr aendern — ohne dieses
        # Feld waere BT-10 fuer jede bereits erstellte Rechnung endgueltig,
        # und die Bestellnummer, die der Kunde nach der Abreise nennt, liesse
        # sich nirgends nachtragen.
        "buyerreference": "TEXT",
        # Wie die Positionen dastehen, von Hand gewaehlt: 'A', 'B' oder 'C'.
        # Leer heisst Vorbelegung (siehe ablauf.positionsart).
        "positionen": "TEXT",
        # In welcher XRechnung-Version die abgelegte Datei erzeugt wurde.
        # Belege von vor der Einfuehrung bleiben leer; sie sind 3.0.2.
        "xrechnung_version": "TEXT",
        # Befunde der letzten Erzeugung (Rechenpruefung und KoSIT). Getrennt vom
        # Feld 'fehler', das die Gruende fuer Sichtpruefung und Zuruecklegen
        # traegt: Vorher ueberschrieb jedes Erzeugen — auch das blosse Ansehen
        # des XML — diese Gruende, und ein Beleg verlor den Vermerk, warum er
        # in der Sichtpruefung stand.
        "pruefbefund": "TEXT",
        # Im Testlauf verarbeitet. Die Automatik nimmt solche Belege im
        # Testlauf nicht erneut: Sonst verarbeitete sie bei jedem Takt dieselben
        # aeltesten zwanzig und kam nie an den Rest.
        "testlauf_am": "TEXT",
        # Wann ein Mensch die Sichtpruefung abgeschlossen hat. Damit darf die
        # Automatik auch eine Gruppenrechnung schicken, deren Gastzuordnung
        # noch nicht an Daten bestaetigt ist — er hat sie ja angesehen.
        "freigabe_am": "TEXT",
        "empfaenger": "TEXT", "status": "TEXT", "xml_pfad": "TEXT",
        "fehler": "TEXT", "zuerst_gesehen": "TEXT", "faellig_ab": "TEXT",
        "gesendet_am": "TEXT",
    },
    "protokoll": {
        "id": "INTEGER", "zeit": "TEXT", "bill_no": "INTEGER", "benutzer": "TEXT",
        "aktion": "TEXT", "erfolg": "INTEGER", "text": "TEXT",
    },
    "sitzungen": {
        "token": "TEXT", "benutzer": "TEXT", "rolle": "TEXT", "laeuft_ab": "TEXT",
    },
}


def wanderung(con: sqlite3.Connection) -> list[str]:
    """Ergaenzt fehlende Spalten. Gibt zurueck, was ergaenzt wurde.
    Laeuft bei jedem Start und tut nichts, wenn alles vorhanden ist —
    auch dann nicht, wenn jemand von Hand nachgezogen hat."""
    ergaenzt = []
    for tabelle, spalten in SOLL_SPALTEN.items():
        vorhanden = {z[1] for z in con.execute(f"PRAGMA table_info({tabelle})")}
        if not vorhanden:
            continue                      # Tabelle gibt es (noch) nicht
        for name, typ in spalten.items():
            if name not in vorhanden:
                con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {name} {typ}")
                ergaenzt.append(f"{tabelle}.{name}")
    return ergaenzt


def init() -> None:
    with verbindung() as con:
        # Der Index im Schema geht nur ueber Spalten, die es in protokoll von
        # Anfang an gibt — er kann also vor der Wanderung angelegt werden.
        con.executescript(SCHEMA)
        ergaenzt = wanderung(con)
    if ergaenzt:
        logging.getLogger(__name__).info(
            "Arbeitsliste erweitert: %s", ", ".join(ergaenzt))
        protokoll("wanderung", "Spalten ergänzt: " + ", ".join(ergaenzt))


def jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


def rechnung_anlegen(row: dict, wartezeit_minuten: int) -> bool:
    """Legt eine noch unbekannte Rechnung an. True, wenn sie neu war."""
    with verbindung() as con:
        vorhanden = con.execute(
            "SELECT 1 FROM rechnungen WHERE bill_no = ?", (row["bill_no"],)
        ).fetchone()
        if vorhanden:
            return False
        faellig = (datetime.now() + timedelta(minutes=wartezeit_minuten)).isoformat(timespec="seconds")
        con.execute(
            """INSERT INTO rechnungen
               (bill_no, resort, invoice_no, issuedate, total_net, total_gross,
                kunde, leitweg_id, firmenbezug, empfaenger_typ, empfaenger_land,
                city_ledger, name_id, status, zuerst_gesehen, faellig_ab)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?, 'neu', ?, ?)""",
            (row["bill_no"], row.get("resort"), row.get("invoice_no"),
             row.get("issuedate"), row.get("total_net"), row.get("total_gross"),
             row.get("kunde"), row.get("leitweg_id"), row.get("firmenbezug"),
             row.get("empfaenger_typ"), row.get("empfaenger_land"),
             row.get("city_ledger"), row.get("name_id"), jetzt(), faellig),
        )
    return True


def rechnung(bill_no: int) -> dict | None:
    with verbindung() as con:
        r = con.execute("SELECT * FROM rechnungen WHERE bill_no = ?", (bill_no,)).fetchone()
    return dict(r) if r else None


# Wonach sich sortieren laesst. Eine Positivliste, keine durchgereichte
# Zeichenkette: Der Spaltenname geht unmaskiert in die Abfrage, alles andere
# waere eine Einschleusung.
SORTIERBAR = {
    "bill_no": "bill_no", "issuedate": "issuedate", "kunde": "kunde",
    "firmenbezug": "firmenbezug", "total_net": "total_net",
    "total_gross": "total_gross", "empfaenger": "empfaenger",
    "status": "status", "faellig_ab": "faellig_ab",
}


def liste(status: str | None = None, limit: int = 300,
          sortieren: str = "", richtung: str = "", suche: str = "") -> list[dict]:
    sql = "SELECT * FROM rechnungen"
    args: list = []
    bedingungen: list[str] = []
    if status:
        bedingungen.append("status = ?")
        args.append(status)
    begriff = (suche or "").strip()
    if begriff:
        # Rechnungsnummer, Belegnummer, Kunde, Empfaenger und Kaeuferreferenz.
        # Wer eine Nummer sucht, hat sie meist vollstaendig; wer einen Namen
        # sucht, selten — deshalb ueberall LIKE.
        felder = ("CAST(bill_no AS TEXT)", "invoice_no", "kunde",
                  "empfaenger", "buyerreference")
        bedingungen.append("(" + " OR ".join(f"{f} LIKE ?" for f in felder) + ")")
        args += [f"%{begriff}%"] * len(felder)
    if bedingungen:
        sql += " WHERE " + " AND ".join(bedingungen)
    spalte = SORTIERBAR.get(sortieren or "")
    ab = "DESC" if (richtung or "ab").lower() != "auf" else "ASC"
    if spalte:
        # Leere Felder ans Ende, egal in welcher Richtung — eine Liste, die
        # mit zwanzig Leerzeilen beginnt, beantwortet keine Frage.
        sql += f" ORDER BY (({spalte} IS NULL) OR ({spalte} = '')), {spalte} {ab}, bill_no DESC"
    else:
        sql += " ORDER BY issuedate DESC, bill_no DESC"
    sql += " LIMIT ?"
    args.append(limit)
    with verbindung() as con:
        return [dict(r) for r in con.execute(sql, args)]


def setzen(bill_no: int, **felder) -> None:
    if not felder:
        return
    zuweisung = ", ".join(f"{k} = ?" for k in felder)
    with verbindung() as con:
        con.execute(f"UPDATE rechnungen SET {zuweisung} WHERE bill_no = ?",
                    (*felder.values(), bill_no))


def faellige(max_anzahl: int, city_ledger: bool = False, testlauf: bool = False) -> list[dict]:
    """Rechnungen, die automatisch versendet werden duerfen.

    City-Ledger-Rechnungen bleiben aussen vor, solange city_ledger nicht
    ausdruecklich gesetzt ist. Sie sind nicht bezahlt, sondern stehen beim
    Debitor offen — sie gehen die Debitorenbuchhaltung an, wo gegen das Konto
    gebucht, gemahnt und verrechnet wird. Dass so eine Rechnung ohne Blick
    hinausgeht, ist etwas anderes als bei einer bezahlten Gastrechnung.
    Von Hand versendbar bleiben sie."""
    bedingung = "" if city_ledger else " AND COALESCE(city_ledger, 0) <= 0"
    if testlauf:
        bedingung += " AND testlauf_am IS NULL"
    with verbindung() as con:
        return [dict(r) for r in con.execute(
            f"""SELECT * FROM rechnungen
                WHERE status IN ('neu', 'bereit')   -- 'pruefung' bewusst NICHT
                  AND faellig_ab <= ?
                  AND empfaenger IS NOT NULL AND empfaenger <> ''
                  {bedingung}
                ORDER BY faellig_ab LIMIT ?""",
            (jetzt(), max_anzahl))]


def protokoll(aktion: str, text: str = "", bill_no: int | None = None,
              benutzer: str = "system", erfolg: bool = True) -> None:
    with verbindung() as con:
        con.execute(
            "INSERT INTO protokoll (zeit, bill_no, benutzer, aktion, erfolg, text) VALUES (?,?,?,?,?,?)",
            (jetzt(), bill_no, benutzer, aktion, 1 if erfolg else 0, text[:4000]),
        )


def protokoll_lesen(limit: int = 200, bill_no: int | None = None) -> list[dict]:
    sql = "SELECT * FROM protokoll"
    args: list = []
    if bill_no:
        sql += " WHERE bill_no = ?"
        args.append(bill_no)
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with verbindung() as con:
        return [dict(r) for r in con.execute(sql, args)]
