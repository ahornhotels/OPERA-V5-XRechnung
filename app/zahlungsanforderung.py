"""Zahlungsanforderung fuer eine Anzahlung — ohne Beleg in OPERA.

Im Haus werden Anzahlungen bisher in Excel angefordert. Hier entsteht die
Anforderung aus wenigen Angaben: dem Kundenprofil aus OPERA (Anschrift,
Debitorennummer, Mailadressen), dem Betrag je Steuersatz, einer Nummer, dem
Zahlungsziel und dem Grund. Absender und Bankverbindung kommen wie bei jeder
Rechnung aus OPERA (Tabelle RESORT) und der Konfiguration. Hinaus geht sie
als PDF.

KEINE RECHNUNG, mit Absicht (Entscheidung des Hauses vom 03.11.2026). Die
Anforderung weist keine Umsatzsteuer aus und sagt das ausdruecklich. Die
Rechnung ueber die Anzahlung entsteht erst nach dem Zahlungseingang: Das Haus
bucht die Anzahlung in OPERA, OPERA legt einen Anzahlungsbeleg an, und die
Anwendung schickt ihn als Anzahlungsrechnung (XRechnung) hinaus. Die
Schlussrechnung zieht genau diesen Beleg ab. So gibt es ueber eine Zahlung
genau eine Rechnung mit Steuer — eine XRechnung aus dieser Maske stuende
daneben, und die Steuer stuende zweimal auf einer Rechnung (§ 14c UStG).

Die Betraege werden BRUTTO eingegeben, getrennt nach dem Steuersatz der
Leistung, auf die angezahlt wird. Die Aufteilung steht auf der Anforderung,
die Steuerbetraege nicht."""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import ablauf, db, mailer, opera, store

CENT = Decimal("0.01")
SAETZE = (Decimal(7), Decimal(19))
# Nummer: wird Dateiname und steht im Betreff. Buchstaben, Ziffern und die
# ueblichen Trenner; kein Schraegstrich, kein Leerzeichen.
NUMMER_MUSTER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\-]{0,39}$")
GRUND_LAENGE = 200
REFERENZ_LAENGE = 80
SUCHE_MINDESTENS = 2
HINWEIS_KEINE_RECHNUNG = (
    "Dies ist keine Rechnung. Die Umsatzsteuer wird hier nicht ausgewiesen. Nach "
    "Zahlungseingang erhalten Sie eine Anzahlungsrechnung mit ausgewiesener Umsatzsteuer; "
    "sie wird mit der späteren Rechnung verrechnet.")


class Eingabefehler(ValueError):
    """Die Angaben reichen nicht. Der Text sagt, was fehlt."""


def _rund(wert: Decimal) -> Decimal:
    return wert.quantize(CENT, rounding=ROUND_HALF_UP)


def euro(wert) -> str:
    """1234.5 -> '1.234,50 EUR'. EUR statt €: Die PDF-Schrift kennt das
    Zeichen nicht (siehe _pdf_text)."""
    text = f"{Decimal(str(wert)):,.2f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


def datum(iso: str) -> str:
    """'2026-11-03' -> '03.11.2026'."""
    try:
        return date.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return str(iso or "")


def betrag(text) -> Decimal:
    """Einen eingegebenen Betrag lesen: '1.234,50', '1234,5', '1234.50'.
    Leer ist 0. Wirft Eingabefehler bei allem anderen."""
    roh = str(text or "").strip().replace(" ", "").replace("€", "").replace("EUR", "")
    if not roh:
        return Decimal(0)
    if "," in roh:
        roh = roh.replace(".", "").replace(",", ".")
    elif roh.count(".") > 1:
        roh = roh.replace(".", "")
    try:
        wert = Decimal(roh)
    except InvalidOperation:
        raise Eingabefehler(f"„{text}“ ist kein Betrag.") from None
    if not wert.is_finite():
        raise Eingabefehler(f"„{text}“ ist kein Betrag.")
    if wert < 0:
        raise Eingabefehler("Beträge dürfen nicht negativ sein.")
    if wert != _rund(wert):
        raise Eingabefehler(f"„{text}“ hat mehr als zwei Nachkommastellen.")
    return wert


# ------------------------------------------------------------------ OPERA
def kunden_suchen(cfg: dict, begriff: str) -> list[dict]:
    """Profile, deren Name (bei Firmen der Firmenname, bei Personen der
    Nachname) mit dem Begriff beginnt. Hoechstens 50."""
    # Gross schreibt Oracle (UPPER in der Abfrage), nicht Python: 'ß' wird
    # in Python zu 'SS', in Oracle nicht. Vorne nicht kuerzen — SNAME behaelt
    # fuehrende Leerzeichen des Originals (profil_suche.sql).
    praefix = (begriff or "").rstrip()
    # LIKE-Zeichen im Begriff gelten woertlich nicht — sie wuerden nur die
    # Suche verbreitern. Weglassen ist einfacher als ESCAPE.
    praefix = praefix.replace("%", "").replace("_", "")
    if len(praefix.strip()) < SUCHE_MINDESTENS:
        return []
    return db.abfrage(opera._sql("profil_suche.sql", cfg),
                      {"praefix": praefix, "resort": cfg["property"]["resort"]})


def kunde(cfg: dict, name_id: int) -> dict:
    """Profil mit Anschrift, Debitorennummer und Mailadressen."""
    p = cfg["property"]
    zeilen = db.abfrage(opera._sql("profil_anschrift.sql", cfg),
                        {"name_id": int(name_id), "resort": p["resort"]})
    if not zeilen:
        raise LookupError(f"Profil {name_id} nicht gefunden.")
    k = zeilen[0]
    mails: list[dict] = []
    for m in db.abfrage(opera._sql("profil_mails.sql", cfg),
                        {"name_id": int(name_id), "resort": p["resort"]}):
        adresse = str(m.get("email") or "").strip()
        if adresse and adresse.lower() not in [x["email"].lower() for x in mails]:
            mails.append({**m, "email": adresse})
    k["mails"] = mails
    return k


def haus(cfg: dict) -> dict:
    zeilen = db.abfrage(opera._sql("resort_stammdaten.sql", cfg),
                        {"resort": cfg["property"]["resort"]})
    if not zeilen:
        raise LookupError(f"Resort {cfg['property']['resort']} nicht in OPERA gefunden.")
    return zeilen[0]


# ------------------------------------------------------------------ Eingabe
def faellig_vorgabe(cfg: dict, heute: date | None = None) -> str:
    tage = int((cfg.get("property") or {}).get("zahlungsziel_tage") or 14)
    return ((heute or date.today()) + timedelta(days=tage)).isoformat()


def eingabe_pruefen(e: dict, heute: date | None = None) -> dict:
    """Prueft und vereinheitlicht die Angaben aus der Maske. Wirft
    Eingabefehler mit allen Maengeln auf einmal."""
    heute = heute or date.today()
    fehler: list[str] = []
    aus: dict = {}
    nummer = str(e.get("nummer") or "").strip()
    if not nummer:
        fehler.append("Die Nummer fehlt.")
    elif not NUMMER_MUSTER.match(nummer):
        fehler.append("Die Nummer darf nur Buchstaben, Ziffern, Punkt, Binde- und "
                      "Unterstrich enthalten (höchstens 40 Zeichen, kein Leerzeichen).")
    aus["nummer"] = nummer
    for satz in SAETZE:
        schluessel = f"brutto_{satz}"
        try:
            aus[schluessel] = betrag(e.get(schluessel))
        except Eingabefehler as f:
            fehler.append(f"Betrag {satz} %: {f}")
            aus[schluessel] = Decimal(0)
    if not any(aus[f"brutto_{s}"] for s in SAETZE):
        fehler.append("Es ist kein Betrag eingetragen.")
    aus["gesamt"] = sum((aus[f"brutto_{s}"] for s in SAETZE), Decimal(0))
    grund = " ".join(str(e.get("grund") or "").split())
    if not grund:
        fehler.append("Der Grund der Anzahlung fehlt.")
    elif len(grund) > GRUND_LAENGE:
        fehler.append(f"Der Grund ist länger als {GRUND_LAENGE} Zeichen.")
    aus["grund"] = grund
    faellig = str(e.get("faellig") or "").strip()
    try:
        if date.fromisoformat(faellig) < heute:
            fehler.append("Das Zahlungsziel liegt in der Vergangenheit.")
    except ValueError:
        fehler.append("Das Zahlungsziel fehlt oder ist kein Datum.")
    aus["faellig"] = faellig
    von, bis = str(e.get("von") or "").strip(), str(e.get("bis") or "").strip()
    if von or bis:
        try:
            if not (von and bis):
                raise ValueError
            if date.fromisoformat(bis) < date.fromisoformat(von):
                fehler.append("Der Leistungszeitraum endet vor seinem Beginn.")
        except ValueError:
            fehler.append("Leistungszeitraum: bitte beide Daten eintragen oder beide leer lassen.")
    aus["von"], aus["bis"] = von, bis
    aus["referenz"] = " ".join(str(e.get("referenz") or "").split())[:REFERENZ_LAENGE]
    aus["empfaenger"] = str(e.get("empfaenger") or "").strip()
    if fehler:
        raise Eingabefehler(" ".join(fehler))
    return aus


def maengel(cfg: dict, k: dict, h: dict) -> list[str]:
    """Was an Stammdaten fehlt, damit die Anforderung vollstaendig ist."""
    p = cfg.get("property") or {}
    fehler = []
    if not (k.get("name") and k.get("city")):
        fehler.append("Am Profil fehlt der Ort — bitte in OPERA ergänzen und den Kunden neu "
                      "auswählen.")
    if not str(p.get("iban") or "").strip():
        fehler.append("Die IBAN des Hauses fehlt (Konfiguration).")
    if not (h.get("suppliername") and h.get("suppliercityname")):
        fehler.append("Name oder Ort des Hauses fehlen in OPERA (Tabelle RESORT).")
    return fehler


# ------------------------------------------------------------------ PDF
# Die eingebaute Schrift (Helvetica) kennt nur Latin-1. Was darueber hinausgeht,
# wird in die naechstliegende Form gebracht, statt den Bau scheitern zu lassen:
# typografische Zeichen ersetzt, Akzente abgetrennt (Łódź -> Lodz). Eine
# eigene Schriftdatei mitzuliefern waere die Alternative; fuer Namen in
# lateinischer Schrift reicht das hier.
_ERSATZ = {"€": "EUR", "–": "-", "—": "-", "„": '"', "“": '"', "”": '"', "‚": "'",
           "‘": "'", "’": "'", "…": "...", "•": "-", " ": " ", "Ł": "L", "ł": "l",
           "Đ": "D", "đ": "d", "Œ": "OE", "œ": "oe", "ı": "i"}


def _pdf_text(text) -> str:
    aus = []
    for z in str(text or ""):
        z = _ERSATZ.get(z, z)
        try:
            z.encode("latin-1")
        except UnicodeEncodeError:
            z = "".join(c for c in unicodedata.normalize("NFKD", z)
                        if not unicodedata.combining(c))
            try:
                z.encode("latin-1")
            except UnicodeEncodeError:
                z = "?"
        aus.append(z)
    return "".join(aus)


def pdf(cfg: dict, eingabe: dict, k: dict, h: dict, heute: date | None = None,
        komprimieren: bool = True) -> bytes:
    """Die Zahlungsanforderung als PDF (A4)."""
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    p = cfg.get("property") or {}
    heute = heute or date.today()
    t = _pdf_text
    haus_name = h.get("supplierregistrationname") or h.get("suppliername") or ""
    haus_zeile = " · ".join(x for x in (
        h.get("suppliername"), h.get("supplierstreetname"),
        f"{h.get('supplierpostalzone') or ''} {h.get('suppliercityname') or ''}".strip()) if x)
    kontakt = " · ".join(x for x in (
        str(p.get("kontakt_telefon") or h.get("suppliercontacttelephone") or "").strip(),
        str(p.get("kontakt_email") or h.get("suppliercontactelectronicmail") or "").strip()) if x)

    class Blatt(FPDF):
        def footer(self):
            self.set_y(-22)
            self.set_font("helvetica", size=7.5)
            self.set_text_color(90, 90, 90)
            zeilen = [haus_name + (f" · USt-IdNr. {p.get('ust_id')}" if p.get("ust_id") else ""),
                      haus_zeile.replace(" · ", ", ", 1) if haus_zeile else "", kontakt]
            for z in zeilen:
                if z:
                    self.cell(0, 3.6, t(z), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    doc = Blatt(format="A4")
    doc.set_compression(komprimieren)
    doc.set_title(t(f"Zahlungsanforderung {eingabe['nummer']}"))
    doc.set_author(t(h.get("suppliername") or ""))
    doc.set_margins(22, 18, 20)
    doc.set_auto_page_break(True, margin=28)
    doc.add_page()
    breite = doc.w - doc.l_margin - doc.r_margin

    # Kopf: Haus
    doc.set_font("helvetica", "B", 13)
    doc.cell(0, 6, t(h.get("suppliername") or ""), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.set_font("helvetica", size=8)
    doc.set_text_color(90, 90, 90)
    doc.cell(0, 4, t(haus_zeile), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.set_text_color(0, 0, 0)

    # Anschrift links, Angaben rechts
    oben = doc.get_y() + 12
    doc.set_xy(doc.l_margin, oben)
    doc.set_font("helvetica", size=10)
    land = str(k.get("country") or "").strip().upper()
    anschrift = [k.get("legal_company") or k.get("name"), k.get("address1"), k.get("address2"),
                 f"{k.get('zip_code') or ''} {k.get('city') or ''}".strip(),
                 land if land and land != str(h.get("supplieridentificationcode") or "DE").upper() else ""]
    for z in anschrift:
        if z:
            doc.cell(95, 5, t(z), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    links_unten = doc.get_y()
    angaben = [("Nummer", eingabe["nummer"]), ("Datum", datum(heute.isoformat()))]
    if k.get("debitorennummer"):
        angaben.append(("Kundennummer", str(k["debitorennummer"])))
    if eingabe.get("referenz"):
        angaben.append(("Ihre Referenz", eingabe["referenz"]))
    doc.set_xy(doc.l_margin + 110, oben)
    for name, wert in angaben:
        doc.set_x(doc.l_margin + 110)
        doc.set_font("helvetica", size=9)
        doc.cell(28, 5, t(name))
        doc.set_font("helvetica", "B", 9)
        doc.cell(0, 5, t(wert), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.set_y(max(links_unten, doc.get_y()) + 14)

    # Titel und Text
    doc.set_font("helvetica", "B", 15)
    doc.cell(0, 8, "Zahlungsanforderung", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(2)
    doc.set_font("helvetica", size=10)
    doc.multi_cell(breite, 5, t(f"Anzahlung für: {eingabe['grund']}"),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    if eingabe.get("von") and eingabe.get("bis"):
        doc.multi_cell(breite, 5, t(f"Leistungszeitraum: {datum(eingabe['von'])} bis "
                                    f"{datum(eingabe['bis'])}"),
                       new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(2)
    doc.multi_cell(breite, 5, "Wir bitten Sie um folgende Anzahlung:",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(2)

    # Betraege
    for satz in SAETZE:
        wert = eingabe[f"brutto_{satz}"]
        if wert:
            doc.cell(breite - 45, 6, t(f"Anzahlung auf Leistungen mit {satz} % Umsatzsteuer"))
            doc.cell(45, 6, t(euro(wert)), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.set_draw_color(120, 120, 120)
    doc.line(doc.l_margin, doc.get_y() + 1, doc.l_margin + breite, doc.get_y() + 1)
    doc.ln(2.5)
    doc.set_font("helvetica", "B", 11)
    doc.cell(breite - 45, 7, "Zu zahlen")
    doc.cell(45, 7, t(euro(eingabe["gesamt"])), align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(5)

    # Zahlung
    doc.set_font("helvetica", size=10)
    doc.multi_cell(breite, 5, t(f"Bitte überweisen Sie den Betrag bis zum {datum(eingabe['faellig'])} "
                                "auf folgendes Konto:"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(1)
    zweck = verwendungszweck(eingabe, k)
    for name, wert in (("Kontoinhaber", p.get("kontoinhaber") or haus_name),
                       ("IBAN", p.get("iban")), ("BIC", p.get("bic")),
                       ("Verwendungszweck", zweck)):
        if wert:
            doc.set_font("helvetica", size=10)
            doc.cell(38, 5.5, t(name))
            doc.set_font("helvetica", "B", 10)
            doc.cell(0, 5.5, t(wert), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    doc.ln(7)

    # Hinweis
    doc.set_fill_color(242, 239, 232)
    doc.set_font("helvetica", "B", 9.5)
    doc.multi_cell(breite, 5, t(HINWEIS_KEINE_RECHNUNG), fill=True, padding=3, align="L",
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    return bytes(doc.output())


def verwendungszweck(eingabe: dict, k: dict) -> str:
    teile = [f"Zahlungsanforderung {eingabe['nummer']}"]
    if k.get("debitorennummer"):
        teile.append(f"Kunde {k['debitorennummer']}")
    return ", ".join(teile)


# ------------------------------------------------------------------ Ablage
# Eigene Tabelle in der Bestandsdatenbank: Die Nummer vergibt der Anwender und
# muss keine Zahl sein. Eindeutig ohne Ruecksicht auf Gross- und
# Kleinschreibung — "za-1" und "ZA-1" waeren beim Kunden dieselbe
# Anforderung und auf einem Mac dieselbe Datei.
#
# status: 'begonnen' (abgelegt, Versand laeuft oder ist nicht bestaetigt),
# 'gesendet', 'abgelegt' (ohne Mail).
TABELLE = """
CREATE TABLE IF NOT EXISTS zahlungsanforderungen (
    nummer       TEXT PRIMARY KEY COLLATE NOCASE,
    name_id      INTEGER,
    kunde        TEXT,
    datum        TEXT,
    faellig      TEXT,
    brutto_7     REAL,
    brutto_19    REAL,
    gesamt       REAL,
    grund        TEXT,
    empfaenger   TEXT,
    status       TEXT NOT NULL,
    pdf_pfad     TEXT,
    erstellt_von TEXT,
    erstellt_am  TEXT,
    gesendet_am  TEXT,
    kennung      TEXT
)"""


def _verbindung() -> sqlite3.Connection:
    con = store.verbindung()
    con.execute(TABELLE)
    return con


def satz_lesen(nummer: str) -> dict | None:
    with _verbindung() as con:
        z = con.execute("SELECT * FROM zahlungsanforderungen WHERE nummer = ?", (nummer,)).fetchone()
    return dict(z) if z else None


def liste(limit: int = 100) -> list[dict]:
    with _verbindung() as con:
        return [dict(z) for z in con.execute(
            "SELECT * FROM zahlungsanforderungen ORDER BY erstellt_am DESC LIMIT ?", (limit,))]


def _anlegen(satz: dict) -> bool:
    """Legt die Nummer an. False, wenn es sie schon gibt — die Nummer ist
    damit vergeben, auch bei zwei gleichzeitigen Versuchen."""
    spalten = list(satz)
    try:
        with _verbindung() as con:
            con.execute(f"INSERT INTO zahlungsanforderungen ({', '.join(spalten)}) "
                        f"VALUES ({', '.join('?' for _ in spalten)})", [satz[s] for s in spalten])
        return True
    except sqlite3.IntegrityError:
        return False


def _setzen(nummer: str, **felder) -> None:
    with _verbindung() as con:
        con.execute(f"UPDATE zahlungsanforderungen SET {', '.join(f'{k} = ?' for k in felder)} "
                    "WHERE nummer = ?", [*felder.values(), nummer])


def _entfernen(nummer: str) -> None:
    """Nur fuer einen Versand, der nachweislich nicht hinausging."""
    with _verbindung() as con:
        con.execute("DELETE FROM zahlungsanforderungen WHERE nummer = ?", (nummer,))


def ordner(cfg: dict):
    """Ablage: ein Unterordner des Archivs. Getrennt von den Rechnungen, weil
    eine Zahlungsanforderung keine ist."""
    pfad = ablauf._ordner(cfg, "archiv_ordner") / "zahlungsanforderungen"
    pfad.mkdir(parents=True, exist_ok=True)
    return pfad


# ------------------------------------------------------------------ Versand
MAIL_BETREFF = "Zahlungsanforderung {bill_no} vom {issuedate}"
MAIL_TEXT = ("Guten Tag,\n\nanbei erhalten Sie unsere Zahlungsanforderung {bill_no} über "
             "{betrag} für: {grund}.\n\nWir bitten um Zahlung bis zum {faellig}. Die "
             "Bankverbindung steht in der angehängten PDF-Datei.\n\n"
             "Dies ist keine Rechnung. Nach Zahlungseingang erhalten Sie eine "
             "Anzahlungsrechnung mit ausgewiesener Umsatzsteuer.\n\n"
             "Mit freundlichen Gruessen\n{absender_name}")


def vorbereiten(cfg: dict, form: dict, name_id: int,
                heute: date | None = None) -> tuple[dict, dict, dict, list[str]]:
    """Liest Profil und Hausdaten und prueft die Angaben. Liefert (eingabe,
    kunde, haus, befunde). Schreibt nichts. Wirft Eingabefehler, wenn die
    Angaben nicht reichen."""
    eingabe = eingabe_pruefen(form, heute)
    k = kunde(cfg, name_id)
    h = haus(cfg)
    befunde = maengel(cfg, k, h)
    vorhanden = satz_lesen(eingabe["nummer"])
    if vorhanden:
        befunde.append(f"Die Nummer {eingabe['nummer']} ist bereits vergeben "
                       f"(Zahlungsanforderung vom {datum(vorhanden.get('datum'))} an "
                       f"{vorhanden.get('kunde')}).")
    elif (ordner(cfg) / f"{eingabe['nummer']}.pdf").exists():
        befunde.append(f"In der Ablage liegt schon eine Zahlungsanforderung "
                       f"{eingabe['nummer']} — bitte eine andere Nummer wählen.")
    return eingabe, k, h, befunde


def versenden(cfg: dict, form: dict, name_id: int, benutzer: str,
              mit_mail: bool = True) -> str:
    """Baut die Zahlungsanforderung, legt sie ab und verschickt sie.
    mit_mail=False legt sie nur ab. Gibt 'gesendet', 'abgelegt' oder
    'testlauf' zurueck; wirft bei jedem Hindernis, ohne etwas zu hinterlassen."""
    if not ablauf._versand_sperre.acquire(timeout=2):
        raise ablauf.Beschaeftigt("Gerade wird eine Rechnung versendet (Automatiklauf). "
                                  "Bitte einen Moment warten und es erneut versuchen.")
    try:
        eingabe, k, h, befunde = vorbereiten(cfg, form, name_id)
        nummer, an = eingabe["nummer"], eingabe["empfaenger"]
        if mit_mail and not an:
            befunde.append("Es ist keine Empfängeradresse gewählt.")
        if befunde:
            raise ValueError("Nicht erstellt: " + " ".join(befunde))
        dokument = pdf(cfg, eingabe, k, h)
        if (cfg.get("automatik") or {}).get("testlauf"):
            store.protokoll("testlauf", f"Zahlungsanforderung {nummer} über "
                            f"{euro(eingabe['gesamt'])}: nicht abgelegt und nicht versendet "
                            f"(Testlauf aktiv). Ziel wäre {an or '-'}", benutzer=benutzer)
            return "testlauf"
        satz = {"nummer": nummer, "name_id": int(name_id), "kunde": k.get("name"),
                "datum": date.today().isoformat(), "faellig": eingabe["faellig"],
                "brutto_7": float(eingabe["brutto_7"]), "brutto_19": float(eingabe["brutto_19"]),
                "gesamt": float(eingabe["gesamt"]), "grund": eingabe["grund"],
                "empfaenger": an or None, "status": "begonnen", "erstellt_von": benutzer,
                "erstellt_am": store.jetzt()}
        if not _anlegen(satz):
            raise ValueError(f"Die Nummer {nummer} ist inzwischen vergeben.")
        # Erst ablegen, dann senden. 'x' legt nur neu an — eine gleichnamige
        # Datei bleibt unberuehrt.
        datei = ordner(cfg) / f"{nummer}.pdf"
        try:
            with open(datei, "xb") as f:
                f.write(dokument)
        except OSError as e:
            _entfernen(nummer)
            raise ValueError(f"Nicht erstellt: Die Ablage ließ sich nicht schreiben ({e}).") from e
        _setzen(nummer, pdf_pfad=str(datei))
        if not mit_mail:
            _setzen(nummer, status="abgelegt")
            store.protokoll("zahlungsanforderung", f"Zahlungsanforderung {nummer} über "
                            f"{euro(eingabe['gesamt'])} an {k.get('name')} abgelegt, nicht "
                            "versendet", benutzer=benutzer)
            return "abgelegt"
        try:
            kennung = mailer.senden(
                cfg, an=an, bill_no=nummer, issuedate=datum(satz["datum"]),
                xml=None, xml_name="", pdf=datei,
                vorlage=(MAIL_BETREFF, MAIL_TEXT),
                werte_dazu={"betrag": euro(eingabe["gesamt"]), "faellig": datum(eingabe["faellig"]),
                            "grund": eingabe["grund"]})
        except mailer.MailFehler as e:
            # Nichts ging hinaus: Nummer und Ablage wieder frei.
            datei.unlink(missing_ok=True)
            _entfernen(nummer)
            store.protokoll("zahlungsanforderung", f"Zahlungsanforderung {nummer}: Versand an "
                            f"{an} fehlgeschlagen: {e}", benutzer=benutzer, erfolg=False)
            raise
        _setzen(nummer, status="gesendet", gesendet_am=store.jetzt(), kennung=str(kennung))
        bcc = ", ".join(mailer.blindkopien(cfg, False)) or "-"
        store.protokoll("zahlungsanforderung", f"Zahlungsanforderung {nummer} über "
                        f"{euro(eingabe['gesamt'])} an {an}, BCC {bcc}, {kennung}",
                        benutzer=benutzer)
        return "gesendet"
    finally:
        ablauf._versand_sperre.release()
