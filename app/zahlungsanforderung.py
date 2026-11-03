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

import json
import re
import sqlite3
import unicodedata
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from . import ablauf, db, mailer, opera, pdf_einfach, pfade, store

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


# ------------------------------------------------------------------ Zeichen
# Die PDF-Schrift (Helvetica, app/pdf_einfach.py) kennt nur Latin-1. Was darueber hinausgeht,
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


# ------------------------------------------------------------------ Vorlage
# Was das Haus am Schreiben selbst gestalten kann: Logo, Texte, Fusszeile und
# die Mail. Gespeichert im BESTAND (data/, branding/), nicht im Programm —
# eine Aktualisierung tauscht das Programm aus und darf die Gestaltung des
# Hauses nicht mitnehmen. Fehlt die Datei, gelten die Vorgaben unten.
VORLAGE_DATEI = "zahlungsanforderung_vorlage.json"
LOGO_NAME = "logo_zahlungsanforderung"
LOGO_HOECHSTENS = 2 * 1024 * 1024
PLATZHALTER = {
    "nummer": "Nummer der Zahlungsanforderung",
    "datum": "Datum der Zahlungsanforderung",
    "faellig": "Zahlbar bis",
    "betrag": "Betrag, etwa 1.234,50 EUR",
    "kunde": "Name des Kunden",
    "kundennummer": "Kundennummer (Debitor), sonst leer",
    "grund": "Grund der Anzahlung",
    "absender": "Absendername aus der Mail-Konfiguration",
}
VORGABE = {
    "titel": "Zahlungsanforderung",
    "einleitung": "Wir bitten Sie um folgende Anzahlung:",
    "zahlungstext": "Bitte überweisen Sie den Betrag bis zum {faellig} auf folgendes Konto:",
    "hinweis": HINWEIS_KEINE_RECHNUNG,
    "schlusstext": "",
    "fusszeile": "",
    "mail_betreff": "Zahlungsanforderung {nummer} vom {datum}",
    "mail_text": ("Guten Tag,\n\nanbei erhalten Sie unsere Zahlungsanforderung {nummer} über "
                  "{betrag} für: {grund}.\n\nWir bitten um Zahlung bis zum {faellig}. Die "
                  "Bankverbindung steht in der angehängten PDF-Datei.\n\n"
                  "Dies ist keine Rechnung. Nach Zahlungseingang erhalten Sie eine "
                  "Anzahlungsrechnung mit ausgewiesener Umsatzsteuer.\n\n"
                  "Mit freundlichen Grüßen\n{absender}"),
}
# Hoechstlaengen: Das Schreiben hat genau eine Seite.
LAENGEN = {"titel": 60, "einleitung": 500, "zahlungstext": 300, "hinweis": 600,
           "schlusstext": 500, "fusszeile": 400, "mail_betreff": 200, "mail_text": 3000}


def _vorlage_pfad():
    return pfade.DATEN_DIR / VORLAGE_DATEI


def vorlage_laden() -> dict:
    """Die Texte des Hauses, ergaenzt um die Vorgaben."""
    werte = dict(VORGABE)
    try:
        gespeichert = json.loads(_vorlage_pfad().read_text(encoding="utf-8"))
        werte.update({k: str(v) for k, v in gespeichert.items() if k in VORGABE})
    except (OSError, ValueError):
        pass
    return werte


def fuellen(text: str, werte: dict) -> str:
    """Platzhalter einsetzen. Unbekannte stehen nie im Text — das prueft
    vorlage_pruefen beim Speichern; geht es trotzdem schief, bleibt der Text."""
    try:
        return str(text or "").format_map({k: werte.get(k, "") for k in PLATZHALTER})
    except (KeyError, IndexError, ValueError, AttributeError):
        return str(text or "")


def vorlage_pruefen(werte: dict) -> dict:
    """Prueft die eingegebenen Texte. Wirft Eingabefehler mit allen Maengeln."""
    aus, fehler = {}, []
    probe = {k: "x" for k in PLATZHALTER}
    for feld, name in (("titel", "Titel"), ("einleitung", "Einleitung"),
                       ("zahlungstext", "Zahlungssatz"), ("hinweis", "Hinweis"),
                       ("schlusstext", "Schlusstext"), ("fusszeile", "Fußzeile"),
                       ("mail_betreff", "Betreff der Mail"), ("mail_text", "Text der Mail")):
        text = str(werte.get(feld) or "").replace("\r\n", "\n").strip()
        if feld == "mail_betreff":
            text = " ".join(text.split())
        if len(text) > LAENGEN[feld]:
            fehler.append(f"{name}: höchstens {LAENGEN[feld]} Zeichen.")
        try:
            text.format_map(probe)
        except KeyError as e:
            fehler.append(f"{name}: Den Platzhalter {{{e.args[0]}}} gibt es nicht. Möglich sind "
                          + ", ".join("{" + p + "}" for p in PLATZHALTER) + ".")
        except (IndexError, ValueError):
            fehler.append(f"{name}: Geschweifte Klammern gehören nur um einen Platzhalter. "
                          "Für eine Klammer im Text bitte {{ oder }} schreiben.")
        aus[feld] = text
    for feld in ("titel", "hinweis", "mail_betreff", "mail_text"):
        if not aus[feld]:
            fehler.append(f"{feld.replace('_', ' ').capitalize()} darf nicht leer sein.")
    if "keine rechnung" not in aus["hinweis"].lower():
        fehler.append("Der Hinweis muss sagen, dass das Schreiben keine Rechnung ist "
                      "(„keine Rechnung“). Sonst kann es als Rechnung gelten.")
    if fehler:
        raise Eingabefehler(" ".join(fehler))
    return aus


def vorlage_speichern(werte: dict) -> None:
    geprueft = vorlage_pruefen(werte)
    pfad = _vorlage_pfad()
    pfad.parent.mkdir(parents=True, exist_ok=True)
    zwischen = pfad.with_suffix(".neu")
    zwischen.write_text(json.dumps(geprueft, ensure_ascii=False, indent=2), encoding="utf-8")
    zwischen.replace(pfad)


def logo_pfad():
    """Die Logodatei, falls eine hinterlegt ist."""
    for endung in (".png", ".jpg"):
        p = pfade.BRANDING_DIR / (LOGO_NAME + endung)
        if p.is_file():
            return p
    return None


def logo_speichern(daten: bytes) -> None:
    """Ein Logo hinterlegen (PNG oder JPG). Wirft Eingabefehler."""
    if not daten:
        raise Eingabefehler("Es wurde keine Datei gewählt.")
    if len(daten) > LOGO_HOECHSTENS:
        raise Eingabefehler("Das Logo ist größer als 2 MB.")
    try:
        bild = pdf_einfach.bild_lesen(daten)
    except pdf_einfach.BildFehler as e:
        raise Eingabefehler(f"Das Logo lässt sich nicht verwenden: {e}") from e
    if not (bild["breite"] and bild["hoehe"]):
        raise Eingabefehler("Das Logo hat keine Größe.")
    endung = ".jpg" if daten[:3] == b"\xff\xd8\xff" else ".png"
    pfade.BRANDING_DIR.mkdir(parents=True, exist_ok=True)
    logo_entfernen()
    (pfade.BRANDING_DIR / (LOGO_NAME + endung)).write_bytes(daten)


def logo_entfernen() -> None:
    for endung in (".png", ".jpg"):
        (pfade.BRANDING_DIR / (LOGO_NAME + endung)).unlink(missing_ok=True)


def platzhalter_werte(eingabe: dict, k: dict, heute: date, cfg: dict | None = None) -> dict:
    return {"absender": ((cfg or {}).get("mail") or {}).get("absender_name") or "",
            "nummer": eingabe["nummer"], "datum": datum(heute.isoformat()),
            "faellig": datum(eingabe["faellig"]), "betrag": euro(eingabe["gesamt"]),
            "kunde": k.get("name") or "", "kundennummer": str(k.get("debitorennummer") or ""),
            "grund": eingabe["grund"]}


# ------------------------------------------------------------------ PDF
LINKS, RECHTS = 22.0, 190.0
FUSS_UNTEN = 287.0


class ZuLang(Eingabefehler):
    """Der Inhalt passt nicht auf eine Seite."""


def pdf(cfg: dict, eingabe: dict, k: dict, h: dict, heute: date | None = None,
        komprimieren: bool = True, vorlage: dict | None = None, logo: bytes | None = None) -> bytes:
    """Die Zahlungsanforderung als PDF (A4, eine Seite). vorlage und logo
    sind zum Ausprobieren; sonst gilt, was gespeichert ist."""
    p = cfg.get("property") or {}
    heute = heute or date.today()
    v = vorlage or vorlage_laden()
    werte = platzhalter_werte(eingabe, k, heute, cfg)
    t = _pdf_text
    breite = RECHTS - LINKS
    s = pdf_einfach.Seite()

    haus_name = h.get("supplierregistrationname") or h.get("suppliername") or ""
    haus_zeile = " · ".join(x for x in (
        h.get("suppliername"), h.get("supplierstreetname"),
        f"{h.get('supplierpostalzone') or ''} {h.get('suppliercityname') or ''}".strip()) if x)
    kontakt = " · ".join(x for x in (
        str(p.get("kontakt_telefon") or h.get("suppliercontacttelephone") or "").strip(),
        str(p.get("kontakt_email") or h.get("suppliercontactelectronicmail") or "").strip()) if x)

    # Fusszeile zuerst: Sie legt fest, wie weit der Inhalt reichen darf.
    fuss = [haus_name + (f" · USt-IdNr. {p.get('ust_id')}" if p.get("ust_id") else ""),
            haus_zeile, kontakt]
    for z in fuellen(v.get("fusszeile"), werte).split("\n"):
        fuss += pdf_einfach.umbrechen(t(z), breite, 7.5)
    fuss = [z for z in fuss if z.strip()]
    fuss_oben = FUSS_UNTEN - 3.6 * len(fuss)
    for i, z in enumerate(fuss):
        s.text(105, fuss_oben + 3.6 * (i + 1) - 0.8, t(z), 7.5, grau=0.35, ausrichtung="mitte")
    grenze = fuss_oben - 6

    # Logo rechts oben, hoechstens 60 x 22 mm, Seitenverhaeltnis bleibt.
    logo_daten = logo if logo is not None else (logo_pfad().read_bytes() if logo_pfad() else None)
    if logo_daten:
        try:
            bild = pdf_einfach.bild_lesen(logo_daten)
            massstab = min(60 / bild["breite"], 22 / bild["hoehe"])
            b, hoehe = bild["breite"] * massstab, bild["hoehe"] * massstab
            s.bild(bild, RECHTS - b, 12, b, hoehe)
        except pdf_einfach.BildFehler:
            pass   # beim Hochladen geprueft; ein spaeter beschaedigtes Logo haelt nichts auf

    # Kopf: Haus
    s.text(LINKS, 20, t(h.get("suppliername") or ""), 13, fett=True)
    s.text(LINKS, 25, t(haus_zeile), 8, grau=0.35)

    # Anschrift links, Angaben rechts
    y = 50.0
    land = str(k.get("country") or "").strip().upper()
    for z in (k.get("legal_company") or k.get("name"), k.get("address1"), k.get("address2"),
              f"{k.get('zip_code') or ''} {k.get('city') or ''}".strip(),
              land if land and land != str(h.get("supplieridentificationcode") or "DE").upper() else ""):
        if z:
            for teil in pdf_einfach.umbrechen(t(z), 95, 10):
                s.text(LINKS, y, teil, 10)
                y += 5
    links_unten = y
    y = 50.0
    angaben = [("Nummer", eingabe["nummer"]), ("Datum", werte["datum"])]
    if k.get("debitorennummer"):
        angaben.append(("Kundennummer", str(k["debitorennummer"])))
    if eingabe.get("referenz"):
        angaben.append(("Ihre Referenz", eingabe["referenz"]))
    for name, wert in angaben:
        s.text(124, y, name, 9)
        for teil in pdf_einfach.umbrechen(t(wert), RECHTS - 150, 9, fett=True):
            s.text(150, y, teil, 9, fett=True)
            y += 5
    y = max(links_unten, y) + 12

    # Titel und Text
    s.text(LINKS, y, t(fuellen(v["titel"], werte)), 15, fett=True)
    y += 9

    def absatz(text: str, groesse: float = 10, fett: bool = False, abstand: float = 2) -> None:
        nonlocal y
        text = fuellen(text, werte).strip()
        if not text:
            return
        for z in pdf_einfach.umbrechen(t(text), breite, groesse, fett):
            s.text(LINKS, y, z, groesse, fett=fett)
            y += groesse * 0.5
        y += abstand

    absatz(f"Anzahlung für: {eingabe['grund']}", abstand=0)
    if eingabe.get("von") and eingabe.get("bis"):
        absatz(f"Leistungszeitraum: {datum(eingabe['von'])} bis {datum(eingabe['bis'])}", abstand=0)
    y += 2
    absatz(v["einleitung"], abstand=3)

    # Betraege
    for satz in SAETZE:
        wert = eingabe[f"brutto_{satz}"]
        if wert:
            s.text(LINKS, y, t(f"Anzahlung auf Leistungen mit {satz} % Umsatzsteuer"), 10)
            s.text(RECHTS, y, euro(wert), 10, ausrichtung="rechts")
            y += 6
    s.linie(LINKS, y - 3, RECHTS, y - 3)
    y += 3
    s.text(LINKS, y, "Zu zahlen", 11, fett=True)
    s.text(RECHTS, y, euro(eingabe["gesamt"]), 11, fett=True, ausrichtung="rechts")
    y += 11

    # Zahlung
    absatz(v["zahlungstext"], abstand=1.5)
    for name, wert in (("Kontoinhaber", p.get("kontoinhaber") or haus_name),
                       ("IBAN", p.get("iban")), ("BIC", p.get("bic")),
                       ("Verwendungszweck", verwendungszweck(eingabe, k))):
        if wert:
            s.text(LINKS, y, name, 10)
            s.text(LINKS + 38, y, t(wert), 10, fett=True)
            y += 5.5
    y += 6

    # Hinweis im Kasten
    zeilen = pdf_einfach.umbrechen(t(fuellen(v["hinweis"], werte)), breite - 6, 9.5, fett=True)
    hoehe = len(zeilen) * 4.8 + 5
    s.flaeche(LINKS - 1, y - 4, breite + 2, hoehe)
    for z in zeilen:
        s.text(LINKS + 2, y + 0.5, z, 9.5, fett=True)
        y += 4.8
    y += 10

    absatz(v.get("schlusstext") or "")
    if y > grenze:
        raise ZuLang("Der Inhalt passt nicht auf eine Seite. Bitte Grund, Einleitung, "
                     "Schlusstext oder Fußzeile kürzen.")
    return s.pdf(titel=t(f"{fuellen(v['titel'], werte)} {eingabe['nummer']}"),
                 autor=t(h.get("suppliername") or ""), komprimieren=komprimieren)


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
def mail(cfg: dict, eingabe: dict, k: dict, heute: date | None = None) -> tuple[str, str]:
    """Betreff und Text der Mail, Platzhalter eingesetzt. Klammern werden fuer
    mailer.senden verdoppelt: Der setzt seinerseits Platzhalter ein, und ein
    Grund wie "Raum {A}" liesse ihn sonst stolpern."""
    v = vorlage_laden()
    werte = platzhalter_werte(eingabe, k, heute or date.today(), cfg)
    return tuple(fuellen(v[f], werte).replace("{", "{{").replace("}", "}}")
                 for f in ("mail_betreff", "mail_text"))


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
        dokument = pdf(cfg, eingabe, k, h)   # ZuLang ist ein Eingabefehler
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
            betreff, text = mail(cfg, eingabe, k)
            kennung = mailer.senden(
                cfg, an=an, bill_no=nummer, issuedate=datum(satz["datum"]),
                xml=None, xml_name="", pdf=datei, vorlage=(betreff, text))
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


# ------------------------------------------------------------------ Muster
MUSTER_KUNDE = {"name": "Muster & Söhne AG", "legal_company": None, "address1": "Hauptstraße 1",
                "address2": None, "zip_code": "80331", "city": "München", "country": "DE",
                "debitorennummer": "4711"}
MUSTER_EINGABE = {"nummer": "ZA-MUSTER-001", "brutto_7": "12.450,00", "brutto_19": "3.980,50",
                  "grund": "Tagung Frühjahrsklausur, 40 Zimmer, Tagungspauschale",
                  "referenz": "PO-0815"}


def muster(cfg: dict, vorlage: dict | None = None) -> bytes:
    """Ein Muster-PDF mit erfundenem Kunden, fuer die Seite der Vorlage. Die
    Hausdaten kommen aus OPERA; ist die Datenbank nicht erreichbar, aus der
    Konfiguration."""
    heute = date.today()
    eingabe = eingabe_pruefen(dict(MUSTER_EINGABE, faellig=faellig_vorgabe(cfg, heute)), heute)
    try:
        h = haus(cfg)
    except Exception:
        p = cfg.get("property") or {}
        h = {"suppliername": p.get("haus") or p.get("resort") or "Ihr Haus",
             "supplierstreetname": "", "suppliercityname": "", "supplierpostalzone": ""}
    return pdf(cfg, eingabe, MUSTER_KUNDE, h, heute, vorlage=vorlage)
