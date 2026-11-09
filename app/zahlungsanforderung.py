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
import pathlib
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
    # Die Nummer vergibt der Nummernkreis beim Senden (nummer_ziehen); bis
    # dahin traegt die Eingabe die voraussichtliche (vorbereiten).
    aus["nummer"] = ""
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
    "angaben_titel": "Angaben für Ihre Rechnung",
    "angaben_text": ("Bitte prüfen und ergänzen: direkt im PDF ausfüllen und zurücksenden "
                     "oder einfach per E-Mail antworten."),
    "mail_betreff": "Zahlungsanforderung {nummer} vom {datum}",
    "mail_text": ("Guten Tag,\n\nanbei erhalten Sie unsere Zahlungsanforderung {nummer} über "
                  "{betrag} für: {grund}.\n\nWir bitten um Zahlung bis zum {faellig}. Die "
                  "Bankverbindung steht in der angehängten PDF-Datei.\n\n"
                  "Dies ist keine Rechnung. Nach Zahlungseingang erhalten Sie eine "
                  "Anzahlungsrechnung mit ausgewiesener Umsatzsteuer.\n\n"
                  "Damit diese Rechnung bei Ihnen richtig ankommt, prüfen und ergänzen Sie bitte "
                  "die „Angaben für Ihre Rechnung“ in der PDF-Datei: Firmierung, E-Mail-Adresse "
                  "für die Rechnung, Ihre Bestell- oder Referenznummer und Hinweise für die "
                  "Buchhaltung. Sie können das Formular ausgefüllt zurücksenden oder einfach auf "
                  "diese Mail antworten.\n\n"
                  "Mit freundlichen Grüßen\n{absender}"),
}
# Hoechstlaengen: Das Schreiben hat genau eine Seite.
LAENGEN = {"titel": 60, "einleitung": 500, "zahlungstext": 300, "hinweis": 600,
           "schlusstext": 500, "fusszeile": 400, "angaben_titel": 80, "angaben_text": 400,
           "mail_betreff": 200, "mail_text": 3000}


# Anordnung: feste Wahlmoeglichkeiten statt freier Koordinaten — so koennen
# sich die Teile nicht ueberlappen, und jede Einstellung ergibt eine
# brauchbare Seite. Die Vorgaben ergeben genau das bisherige Bild.
AUSRICHTUNGEN = {"links": "links", "mitte": "mittig", "rechts": "rechts"}
BLOECKE = {"betraege": "Einleitung und Beträge", "zahlung": "Zahlungssatz und Bankverbindung",
           "hinweis": "Hinweis im Kasten", "schluss": "Schlusstext",
           "angaben": "Angaben für die Rechnung (Felder zum Ausfüllen)"}
LAYOUT_VORGABE = {
    "logo_position": "rechts", "logo_breite": 60, "logo_hoehe": 22, "logo_oben": 12,
    "kopf_position": "links",
    "anschrift_seite": "links", "anschrift_oben": 50,
    "titel_ausrichtung": "links", "titel_groesse": 15,
    "einleitung_ausrichtung": "links", "einleitung_groesse": 10,
    "zahlungstext_ausrichtung": "links", "zahlungstext_groesse": 10,
    "hinweis_ausrichtung": "links", "hinweis_groesse": 9.5,
    "schlusstext_ausrichtung": "links", "schlusstext_groesse": 10,
    "fuss_ausrichtung": "mitte", "fuss_groesse": 7.5,
    "reihe_betraege": 1, "reihe_zahlung": 2, "reihe_hinweis": 3, "reihe_schluss": 4,
    "abstand_betraege": 2, "abstand_zahlung": 5, "abstand_hinweis": 6, "abstand_schluss": 6,
    # Die Angaben kamen spaeter dazu: zuletzt, wie ein Rueckantwortteil. So
    # bleibt eine gespeicherte Reihenfolge 1 bis 4 gueltig.
    "angaben_zeigen": "ja", "reihe_angaben": 5, "abstand_angaben": 6,
}
# Je Schluessel: erlaubte Werte oder (kleinster, groesster Wert, Bezeichnung).
LAYOUT_REGELN: dict = {
    "logo_position": AUSRICHTUNGEN, "kopf_position": AUSRICHTUNGEN,
    "anschrift_seite": {"links": "links", "rechts": "rechts"},
    "angaben_zeigen": {"ja": "ja", "nein": "nein"},
    "logo_breite": (15, 90, "Logo, größte Breite (mm)"),
    "logo_hoehe": (8, 45, "Logo, größte Höhe (mm)"),
    "logo_oben": (5, 40, "Logo, Abstand von oben (mm)"),
    "anschrift_oben": (30, 100, "Anschrift, Abstand von oben (mm)"),
    "titel_groesse": (10, 24, "Titel, Schriftgröße"),
    "fuss_groesse": (6, 10, "Fußzeile, Schriftgröße"),
}
for _feld in ("titel", "einleitung", "zahlungstext", "hinweis", "schlusstext", "fuss"):
    LAYOUT_REGELN[f"{_feld}_ausrichtung"] = AUSRICHTUNGEN
for _feld, _name in (("einleitung", "Einleitung"), ("zahlungstext", "Zahlungssatz"),
                     ("hinweis", "Hinweis"), ("schlusstext", "Schlusstext")):
    LAYOUT_REGELN[f"{_feld}_groesse"] = (7, 14, f"{_name}, Schriftgröße")
for _block, _name in BLOECKE.items():
    LAYOUT_REGELN[f"reihe_{_block}"] = (1, len(BLOECKE), f"{_name}, Reihenfolge")
    LAYOUT_REGELN[f"abstand_{_block}"] = (0, 40, f"{_name}, Abstand davor (mm)")
# Nummernkreis: Muster mit {jahr} und {nr}, Stellen der laufenden Nummer, und
# ob jedes Jahr wieder bei 1 begonnen wird. Der Zaehler selbst steht in der
# Datenbank (za_nummernkreis), nicht hier: Er muss beim Ziehen gesperrt werden.
NK_VORGABE = {"nk_muster": "ZA-{jahr}-{nr}", "nk_stellen": 4, "nk_jaehrlich": "ja"}
VORLAGE_VORGABE = {**VORGABE, **LAYOUT_VORGABE, **NK_VORGABE}


def _nk_pruefen(werte: dict) -> tuple[dict, list[str]]:
    aus, fehler = {}, []
    muster = " ".join(str(werte.get("nk_muster", NK_VORGABE["nk_muster"])).split())
    try:
        stellen = int(str(werte.get("nk_stellen", NK_VORGABE["nk_stellen"])).strip())
        if not 1 <= stellen <= 8:
            raise ValueError
    except ValueError:
        fehler.append("Nummernkreis: Stellen zwischen 1 und 8.")
        stellen = NK_VORGABE["nk_stellen"]
    jaehrlich = str(werte.get("nk_jaehrlich", NK_VORGABE["nk_jaehrlich"])).strip()
    if jaehrlich not in ("ja", "nein"):
        fehler.append("Nummernkreis: „jedes Jahr neu“ ist ja oder nein.")
        jaehrlich = "ja"
    if muster.count("{nr}") != 1:
        fehler.append("Nummernkreis: Das Muster braucht genau einmal {nr}.")
    elif re.sub(r"\{(jahr|nr)\}", "", muster).count("{") or \
            re.sub(r"\{(jahr|nr)\}", "", muster).count("}"):
        fehler.append("Nummernkreis: Im Muster gehen nur {jahr} und {nr}.")
    elif not NUMMER_MUSTER.match(muster.replace("{jahr}", "2026").replace("{nr}", "9" * stellen)):
        fehler.append("Nummernkreis: Die Nummer darf nur Buchstaben, Ziffern, Punkt, Binde- und "
                      "Unterstrich enthalten, höchstens 40 Zeichen, und muss mit einem "
                      "Buchstaben oder einer Ziffer beginnen.")
    if jaehrlich == "ja" and "{jahr}" not in muster:
        fehler.append("Nummernkreis: Beginnt er jedes Jahr neu, braucht das Muster {jahr} — "
                      "sonst gäbe es jede Nummer jedes Jahr wieder.")
    aus.update(nk_muster=muster, nk_stellen=stellen, nk_jaehrlich=jaehrlich)
    return aus, fehler


def _layout_wert(schluessel: str, roh):
    """Einen Wert der Anordnung lesen. Wirft ValueError mit verstaendlichem Text."""
    regel = LAYOUT_REGELN[schluessel]
    if isinstance(regel, dict):
        wert = str(roh or "").strip()
        if wert not in regel:
            raise ValueError(f"„{wert}“ ist für {schluessel} nicht möglich.")
        return wert
    klein, gross, name = regel
    try:
        zahl = float(str(roh).replace(",", "."))
    except ValueError:
        raise ValueError(f"{name}: „{roh}“ ist keine Zahl.") from None
    if not (klein <= zahl <= gross):
        raise ValueError(f"{name}: zwischen {klein} und {gross}.")
    return int(zahl) if zahl == int(zahl) else round(zahl, 1)


def _vorlage_pfad():
    return pfade.DATEN_DIR / VORLAGE_DATEI


def vorlage_laden() -> dict:
    """Die Texte des Hauses, ergaenzt um die Vorgaben."""
    werte = dict(VORLAGE_VORGABE)
    try:
        gespeichert = json.loads(_vorlage_pfad().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return werte
    werte.update({k: str(v) for k, v in gespeichert.items() if k in VORGABE})
    for k in LAYOUT_VORGABE:
        if k in gespeichert:
            try:
                werte[k] = _layout_wert(k, gespeichert[k])
            except ValueError:
                pass    # ein unbrauchbarer Wert faellt auf die Vorgabe zurueck
    nk, fehler = _nk_pruefen({k: gespeichert[k] for k in NK_VORGABE if k in gespeichert})
    if not fehler:
        werte.update(nk)
    return werte


def fuellen(text: str, werte: dict) -> str:
    """Platzhalter einsetzen. Unbekannte stehen nie im Text — das prueft
    vorlage_pruefen beim Speichern; geht es trotzdem schief, bleibt der Text."""
    try:
        return str(text or "").format_map({k: werte.get(k, "") for k in PLATZHALTER})
    except (KeyError, IndexError, ValueError, AttributeError):
        return str(text or "")


def vorlage_pruefen(werte: dict) -> dict:
    """Prueft Texte und Anordnung. Wirft Eingabefehler mit allen Maengeln.
    Fehlt ein Wert der Anordnung, gilt die Vorgabe."""
    aus, fehler = {}, []
    probe = {k: "x" for k in PLATZHALTER}
    for feld, name in (("titel", "Titel"), ("einleitung", "Einleitung"),
                       ("zahlungstext", "Zahlungssatz"), ("hinweis", "Hinweis"),
                       ("schlusstext", "Schlusstext"), ("fusszeile", "Fußzeile"),
                       ("angaben_titel", "Überschrift der Angaben"),
                       ("angaben_text", "Text über den Angaben"),
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
    for k in LAYOUT_VORGABE:
        try:
            aus[k] = _layout_wert(k, werte.get(k, LAYOUT_VORGABE[k]))
        except ValueError as e:
            fehler.append(str(e))
    nk, nk_fehler = _nk_pruefen(werte)
    aus.update(nk)
    fehler += nk_fehler
    reihen = [aus.get(f"reihe_{b}") for b in BLOECKE]
    if None not in reihen and sorted(reihen) != list(range(1, len(BLOECKE) + 1)):
        fehler.append(f"Reihenfolge: Jede Zahl von 1 bis {len(BLOECKE)} genau einmal vergeben.")
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
    sind zum Ausprobieren; sonst gilt, was gespeichert ist. Die Anordnung
    steht in der Vorlage (LAYOUT_VORGABE)."""
    p = cfg.get("property") or {}
    heute = heute or date.today()
    v = dict(VORLAGE_VORGABE, **(vorlage or vorlage_laden()))
    werte = platzhalter_werte(eingabe, k, heute, cfg)
    t = _pdf_text
    breite = RECHTS - LINKS
    s = pdf_einfach.Seite()

    def x_fuer(ausrichtung: str) -> float:
        return {"links": LINKS, "mitte": (LINKS + RECHTS) / 2, "rechts": RECHTS}[ausrichtung]

    haus_name = h.get("supplierregistrationname") or h.get("suppliername") or ""
    haus_zeile = " · ".join(x for x in (
        h.get("suppliername"), h.get("supplierstreetname"),
        f"{h.get('supplierpostalzone') or ''} {h.get('suppliercityname') or ''}".strip()) if x)
    kontakt = " · ".join(x for x in (
        str(p.get("kontakt_telefon") or h.get("suppliercontacttelephone") or "").strip(),
        str(p.get("kontakt_email") or h.get("suppliercontactelectronicmail") or "").strip()) if x)

    # Fusszeile zuerst: Sie legt fest, wie weit der Inhalt reichen darf.
    fg = float(v["fuss_groesse"])
    fuss = [haus_name + (f" · USt-IdNr. {p.get('ust_id')}" if p.get("ust_id") else ""),
            haus_zeile, kontakt]
    for z in fuellen(v.get("fusszeile"), werte).split("\n"):
        fuss += pdf_einfach.umbrechen(t(z), breite, fg)
    fuss = [z for z in fuss if z.strip()]
    zeile_fuss = fg * 0.48
    fuss_oben = FUSS_UNTEN - zeile_fuss * len(fuss)
    for i, z in enumerate(fuss):
        s.text(x_fuer(v["fuss_ausrichtung"]), fuss_oben + zeile_fuss * (i + 1) - 0.8, t(z), fg,
               grau=0.35, ausrichtung=v["fuss_ausrichtung"])
    grenze = fuss_oben - 6

    # Logo: links, mittig oder rechts oben; Seitenverhaeltnis bleibt.
    logo_unten = 0.0
    logo_daten = logo if logo is not None else (logo_pfad().read_bytes() if logo_pfad() else None)
    if logo_daten:
        try:
            bild = pdf_einfach.bild_lesen(logo_daten)
            massstab = min(float(v["logo_breite"]) / bild["breite"],
                           float(v["logo_hoehe"]) / bild["hoehe"])
            b, hoehe = bild["breite"] * massstab, bild["hoehe"] * massstab
            lx = {"links": LINKS, "mitte": (LINKS + RECHTS - b) / 2,
                  "rechts": RECHTS - b}[v["logo_position"]]
            s.bild(bild, lx, float(v["logo_oben"]), b, hoehe)
            logo_unten = float(v["logo_oben"]) + hoehe
        except pdf_einfach.BildFehler:
            pass   # beim Hochladen geprueft; ein spaeter beschaedigtes Logo haelt nichts auf

    # Kopf: Haus. Auf derselben Seite wie das Logo rueckt er darunter.
    ky = 20.0
    if logo_unten and v["kopf_position"] == v["logo_position"]:
        ky = logo_unten + 6
    kx = x_fuer(v["kopf_position"])
    s.text(kx, ky, t(h.get("suppliername") or ""), 13, fett=True, ausrichtung=v["kopf_position"])
    s.text(kx, ky + 5, t(haus_zeile), 8, grau=0.35, ausrichtung=v["kopf_position"])
    kopf_unten = ky + 5

    # Anschrift und Angaben: die eine Seite, die andere Seite.
    oben = max(float(v["anschrift_oben"]), kopf_unten + 10, logo_unten + 6)
    if v["anschrift_seite"] == "links":
        ax, aw, lx_, vx = LINKS, 95.0, 124.0, 150.0
    else:
        ax, aw, lx_, vx = 118.0, RECHTS - 118.0, LINKS, LINKS + 26
    y = oben
    land = str(k.get("country") or "").strip().upper()
    for z in (k.get("legal_company") or k.get("name"), k.get("address1"), k.get("address2"),
              f"{k.get('zip_code') or ''} {k.get('city') or ''}".strip(),
              land if land and land != str(h.get("supplieridentificationcode") or "DE").upper() else ""):
        if z:
            for teil in pdf_einfach.umbrechen(t(z), aw, 10):
                s.text(ax, y, teil, 10)
                y += 5
    anschrift_unten = y
    y = oben
    angaben = [("Nummer", eingabe["nummer"]), ("Datum", werte["datum"])]
    if k.get("debitorennummer"):
        angaben.append(("Kundennummer", str(k["debitorennummer"])))
    if eingabe.get("referenz"):
        angaben.append(("Ihre Referenz", eingabe["referenz"]))
    werte_breite = (RECHTS - vx) if v["anschrift_seite"] == "links" else (ax - 6 - vx)
    for name, wert in angaben:
        s.text(lx_, y, name, 9)
        for teil in pdf_einfach.umbrechen(t(wert), werte_breite, 9, fett=True):
            s.text(vx, y, teil, 9, fett=True)
            y += 5
    y = max(anschrift_unten, y) + 12

    def absatz(text: str, ausrichtung: str, groesse: float, fett: bool = False,
               abstand: float = 2) -> None:
        nonlocal y
        text = fuellen(text, werte).strip()
        if not text:
            return
        for z in pdf_einfach.umbrechen(t(text), breite, groesse, fett):
            s.text(x_fuer(ausrichtung), y, z, groesse, fett=fett, ausrichtung=ausrichtung)
            y += groesse * 0.5
        y += abstand

    # Titel, Grund, Leistungszeitraum
    tg = float(v["titel_groesse"])
    s.text(x_fuer(v["titel_ausrichtung"]), y, t(fuellen(v["titel"], werte)), tg, fett=True,
           ausrichtung=v["titel_ausrichtung"])
    y += tg * 0.6
    absatz(f"Anzahlung für: {eingabe['grund']}", v["titel_ausrichtung"], 10, abstand=0)
    if eingabe.get("von") and eingabe.get("bis"):
        absatz(f"Leistungszeitraum: {datum(eingabe['von'])} bis {datum(eingabe['bis'])}",
               v["titel_ausrichtung"], 10, abstand=0)

    def betraege() -> None:
        nonlocal y
        absatz(v["einleitung"], v["einleitung_ausrichtung"], float(v["einleitung_groesse"]),
               abstand=3)
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
        y += 6

    def zahlung() -> None:
        nonlocal y
        absatz(v["zahlungstext"], v["zahlungstext_ausrichtung"], float(v["zahlungstext_groesse"]),
               abstand=1.5)
        for name, wert in (("Kontoinhaber", p.get("kontoinhaber") or haus_name),
                           ("IBAN", p.get("iban")), ("BIC", p.get("bic")),
                           ("Verwendungszweck", verwendungszweck(eingabe, k))):
            if wert:
                s.text(LINKS, y, name, 10)
                s.text(LINKS + 38, y, t(wert), 10, fett=True)
                y += 5.5

    def hinweis() -> None:
        nonlocal y
        hg = float(v["hinweis_groesse"])
        zeile = hg * 0.505
        zeilen = pdf_einfach.umbrechen(t(fuellen(v["hinweis"], werte)), breite - 6, hg, fett=True)
        oben_kasten = y - 4
        s.flaeche(LINKS - 1, oben_kasten, breite + 2, len(zeilen) * zeile + 5)
        a = v["hinweis_ausrichtung"]
        hx = {"links": LINKS + 2, "mitte": (LINKS + RECHTS) / 2, "rechts": RECHTS - 2}[a]
        for z in zeilen:
            s.text(hx, y + 0.5, z, hg, fett=True, ausrichtung=a)
            y += zeile
        y = oben_kasten + len(zeilen) * zeile + 5 + 4

    def schluss() -> None:
        absatz(v.get("schlusstext") or "", v["schlusstext_ausrichtung"],
               float(v["schlusstext_groesse"]))

    def angaben() -> None:
        nonlocal y
        if v["angaben_zeigen"] != "ja":
            return
        titel = fuellen(v.get("angaben_titel") or "", werte).strip()
        if titel:
            s.linie(LINKS, y - 4.5, RECHTS, y - 4.5, grau=0.75)
            s.text(LINKS, y + 0.5, t(titel), 10.5, fett=True)
            y += 5
        absatz(v.get("angaben_text") or "", "links", 8.5, abstand=2)
        luecke = 4.0
        for zeile in angaben_felder(eingabe, k):
            frei = breite - luecke * (len(zeile) - 1)
            x = LINKS
            hoehe = max(f["hoehe"] for f in zeile)
            for f in zeile:
                b_ = frei * f["anteil"]
                s.text(x, y, t(f["beschriftung"]), 7, grau=0.35)
                s.feld(f["name"], x, y + 1, b_, f["hoehe"], t(f["wert"]), groesse=9,
                       mehrzeilig=f["hoehe"] > 8)
                x += b_ + luecke
            y += 1 + hoehe + 3.8

    teile = {"betraege": betraege, "zahlung": zahlung, "hinweis": hinweis, "schluss": schluss,
             "angaben": angaben}
    for block in sorted(BLOECKE, key=lambda b_: int(v[f"reihe_{b_}"])):
        if block == "angaben" and v["angaben_zeigen"] != "ja":
            continue
        y += float(v[f"abstand_{block}"])
        teile[block]()

    if y > grenze:
        raise ZuLang("Der Inhalt passt nicht auf eine Seite. Bitte Texte, Schriftgrößen oder "
                     "Abstände verkleinern"
                     + (" oder die Angaben für die Rechnung abschalten (Vorlage anpassen)."
                        if v["angaben_zeigen"] == "ja" else "."))
    return s.pdf(titel=t(f"{fuellen(v['titel'], werte)} {eingabe['nummer']}"),
                 autor=t(h.get("suppliername") or ""), komprimieren=komprimieren)


# Profiltypen, deren Name eine Firmierung ist. Gruppen und Quellen tragen
# Kuerzel oder Veranstaltungsnamen; dort bleibt das Feld leer.
FIRMIERUNG_TYPEN = ("COMPANY", "TRAVEL_AGENT")


def angaben_felder(eingabe: dict, k: dict) -> list[list[dict]]:
    """Die Felder, die der Kunde ausfuellt, Zeile fuer Zeile. Vorbelegt ist
    nur, was wir sicher wissen: die Firmierung am Firmenprofil und die
    Referenz, die bei der Anforderung eingetragen wurde. Was der Kunde
    zurueckmeldet, gehoert danach in OPERA: Firmierung und Mailadresse an das
    Profil, die Referenz vor dem Check-out in das Reservierungsfeld fuer die
    Kaeuferreferenz (BT-10)."""
    firma = k.get("legal_company") or (
        k.get("name") if str(k.get("name_type") or "").upper() in FIRMIERUNG_TYPEN else "")
    return [
        [{"name": "firmierung", "anteil": 0.64, "hoehe": 6.0, "wert": firma or "",
          "beschriftung": "Rechnungsempfänger: exakte Firmierung, wie im Handelsregister"},
         {"name": "ust_id", "anteil": 0.36, "hoehe": 6.0, "wert": "",
          "beschriftung": "USt-IdNr."}],
        [{"name": "email", "anteil": 0.5, "hoehe": 6.0, "wert": "",
          "beschriftung": "E-Mail-Adresse für die Rechnung, etwa Ihrer Buchhaltung"},
         {"name": "referenz", "anteil": 0.5, "hoehe": 6.0, "wert": eingabe.get("referenz") or "",
          "beschriftung": "Ihre Bestell- oder Referenznummer (bei Behörden: Leitweg-ID)"}],
        [{"name": "hinweise", "anteil": 1.0, "hoehe": 9.0, "wert": "",
          "beschriftung": "Sonstige Hinweise für unsere Buchhaltung, etwa abweichende "
                          "Rechnungsanschrift, Kostenstelle oder Ansprechpartner"}],
    ]


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
    kennung      TEXT,
    referenz     TEXT
)"""

# Spalten, die nach der ersten Fassung dazugekommen sind. Ein bestehender
# Bestand bekommt sie beim ersten Zugriff nachgetragen; alte Saetze bleiben
# dort leer.
NACHGETRAGEN = {"referenz": "TEXT"}


def _verbindung() -> sqlite3.Connection:
    con = store.verbindung()
    con.execute(TABELLE)
    con.execute(KREIS_TABELLE)
    da = {z[1] for z in con.execute("PRAGMA table_info(zahlungsanforderungen)")}
    for spalte, typ in NACHGETRAGEN.items():
        if spalte not in da:
            con.execute(f"ALTER TABLE zahlungsanforderungen ADD COLUMN {spalte} {typ}")
    return con


def satz_lesen(nummer: str) -> dict | None:
    with _verbindung() as con:
        z = con.execute("SELECT * FROM zahlungsanforderungen WHERE nummer = ?", (nummer,)).fetchone()
    return dict(z) if z else None


def liste(limit: int = 100) -> list[dict]:
    with _verbindung() as con:
        return [dict(z) for z in con.execute(
            "SELECT * FROM zahlungsanforderungen ORDER BY erstellt_am DESC LIMIT ?", (limit,))]


SUCHE_HOECHSTENS = 200
# Worin der Suchbegriff gesucht wird, in dieser Reihenfolge angezeigt.
SUCHFELDER = ("nummer", "kunde", "grund", "referenz", "empfaenger")
STATUS_WAHL = {"gesendet": "gesendet", "abgelegt": "abgelegt, nicht versendet",
               "begonnen": "Versand nicht bestätigt"}


def suchen(begriff: str = "", von: str = "", bis: str = "", status: str = "",
           hoechstens: int = SUCHE_HOECHSTENS) -> tuple[list[dict], bool]:
    """Die abgelegten Zahlungsanforderungen, gefiltert. Gibt (Treffer, mehr)
    zurueck; mehr = es gab mehr als hoechstens.

    Der Begriff wird in Nummer, Kunde, Grund, Referenz und Empfaenger
    gesucht, jedes Wort fuer sich (alle muessen vorkommen), ohne Ruecksicht
    auf Gross- und Kleinschreibung. Das geschieht in Python und nicht per
    LIKE: SQLite faltet nur ASCII, "müller" faende "Müller" nicht. Die
    Tabelle ist klein (eine Zahlungsanforderung je Anfrage, nicht je Beleg).
    Ein Begriff, der ein Betrag ist ("1.250,00"), trifft ausserdem den
    Gesamtbetrag; die Kundennummer aus OPERA trifft genau."""
    sql, werte = "SELECT * FROM zahlungsanforderungen WHERE 1 = 1", []
    for spalte, wert, op in (("datum", von, ">="), ("datum", bis, "<=")):
        if wert:
            date.fromisoformat(wert)            # wirft bei Unsinn, statt still nichts zu finden
            sql += f" AND {spalte} {op} ?"
            werte.append(wert)
    if status:
        if status not in STATUS_WAHL:
            raise ValueError(f"Unbekannter Status: {status}")
        sql += " AND status = ?"
        werte.append(status)
    sql += " ORDER BY erstellt_am DESC"
    with _verbindung() as con:
        saetze = [dict(z) for z in con.execute(sql, werte)]
    begriff = " ".join(str(begriff or "").split())
    if begriff:
        try:
            als_betrag = betrag(begriff) if re.fullmatch(r"[\d.,\s]+", begriff) else None
        except Eingabefehler:
            als_betrag = None
        woerter = begriff.casefold().split()

        def trifft(s: dict) -> bool:
            if als_betrag is not None and abs(Decimal(str(s.get("gesamt") or 0)) - als_betrag) < Decimal("0.005"):
                return True
            if begriff.isdigit() and str(s.get("name_id") or "") == begriff:
                return True
            text = " ".join(str(s.get(f) or "") for f in SUCHFELDER).casefold()
            return all(w in text for w in woerter)
        saetze = [s for s in saetze if trifft(s)]
    return saetze[:hoechstens], len(saetze) > hoechstens


def pdf_datei(cfg: dict, nummer: str, satz: dict | None = None):
    """Die abgelegte Datei zu einer Nummer, oder None. Zuerst der gespeicherte
    Pfad, sonst die Ablage nach heutiger Konfiguration: Zieht der Bestand um
    (neuer Server, anderer Archivordner), stimmt der alte absolute Pfad nicht
    mehr, die Datei liegt aber unter ihrer Nummer im neuen Ordner."""
    if not NUMMER_MUSTER.match(nummer or ""):
        return None
    satz = satz or satz_lesen(nummer)
    if not satz:
        return None
    if satz.get("pdf_pfad"):
        p = pathlib.Path(satz["pdf_pfad"])
        if p.is_file():
            return p
    p = ordner(cfg) / f"{satz['nummer']}.pdf"
    return p if p.is_file() else None


# ------------------------------------------------------------------ Nummernkreis
KREIS_TABELLE = ("CREATE TABLE IF NOT EXISTS za_nummernkreis "
                 "(kreis TEXT PRIMARY KEY, naechste INTEGER NOT NULL)")


def _kreis(v: dict, heute: date) -> str:
    return str(heute.year) if v["nk_jaehrlich"] == "ja" else "fortlaufend"


def nummer_bilden(v: dict, heute: date, zahl: int) -> str:
    return (v["nk_muster"].replace("{jahr}", str(heute.year))
            .replace("{nr}", str(zahl).zfill(int(v["nk_stellen"]))))


def _zaehler(con, kreis: str) -> int:
    z = con.execute("SELECT naechste FROM za_nummernkreis WHERE kreis = ?", (kreis,)).fetchone()
    return int(z[0]) if z else 1


def _frei(con, cfg: dict, v: dict, heute: date, zahl: int) -> tuple[int, str]:
    """Ab zahl die erste Nummer, die weder vergeben ist noch in der Ablage
    liegt — etwa nach einem von Hand zurueckgesetzten Zaehler."""
    for _ in range(100_000):
        nummer = nummer_bilden(v, heute, zahl)
        belegt = con.execute("SELECT 1 FROM zahlungsanforderungen WHERE nummer = ?",
                             (nummer,)).fetchone()
        if not belegt and not (ordner(cfg) / f"{nummer}.pdf").exists():
            return zahl, nummer
        zahl += 1
    raise ValueError("Im Nummernkreis ist keine freie Nummer zu finden.")


def naechste_nummer(cfg: dict, heute: date | None = None, v: dict | None = None) -> str:
    """Die Nummer, die die naechste Zahlungsanforderung bekaeme. Vergibt nichts."""
    heute, v = heute or date.today(), v or vorlage_laden()
    with _verbindung() as con:
        return _frei(con, cfg, v, heute, _zaehler(con, _kreis(v, heute)))[1]


def naechste_zahl(heute: date | None = None, v: dict | None = None) -> int:
    heute, v = heute or date.today(), v or vorlage_laden()
    with _verbindung() as con:
        return _zaehler(con, _kreis(v, heute))


def naechste_setzen(zahl, heute: date | None = None) -> None:
    """Den Zaehler des laufenden Kreises setzen — etwa um an eine bisherige
    Zaehlung anzuschliessen. Schon vergebene Nummern werden beim Ziehen
    uebersprungen, doppelt vergeben wird also nie."""
    heute, v = heute or date.today(), vorlage_laden()
    try:
        zahl = int(str(zahl).strip())
    except ValueError:
        raise Eingabefehler("Die nächste Nummer muss eine ganze Zahl sein.") from None
    if not 1 <= zahl < 10 ** int(v["nk_stellen"]):
        raise Eingabefehler(f"Die nächste Nummer liegt zwischen 1 und {10 ** int(v['nk_stellen']) - 1}.")
    with _verbindung() as con:
        con.execute("INSERT INTO za_nummernkreis (kreis, naechste) VALUES (?, ?) "
                    "ON CONFLICT(kreis) DO UPDATE SET naechste = excluded.naechste",
                    (_kreis(v, heute), zahl))


def nummer_ziehen(cfg: dict, satz: dict, heute: date | None = None) -> tuple[str, str, int]:
    """Vergibt die naechste Nummer und legt die Zahlungsanforderung damit an —
    in EINER Transaktion unter Schreibsperre. Zwei gleichzeitige Versuche
    bekommen so nie dieselbe Nummer. Liefert (nummer, kreis, zahl)."""
    heute, v = heute or date.today(), vorlage_laden()
    kreis = _kreis(v, heute)
    con = _verbindung()
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        zahl, nummer = _frei(con, cfg, v, heute, _zaehler(con, kreis))
        daten = dict(satz, nummer=nummer)
        spalten = list(daten)
        con.execute(f"INSERT INTO zahlungsanforderungen ({', '.join(spalten)}) "
                    f"VALUES ({', '.join('?' for _ in spalten)})", [daten[s] for s in spalten])
        con.execute("INSERT INTO za_nummernkreis (kreis, naechste) VALUES (?, ?) "
                    "ON CONFLICT(kreis) DO UPDATE SET naechste = excluded.naechste",
                    (kreis, zahl + 1))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    return nummer, kreis, zahl


def nummer_freigeben(nummer: str, kreis: str, zahl: int) -> None:
    """Nach einem Versand, der nachweislich nicht hinausging: Satz weg, und war
    es die zuletzt gezogene Nummer, wird sie wieder die naechste. So entsteht
    keine Luecke im Nummernkreis."""
    con = _verbindung()
    con.isolation_level = None
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute("DELETE FROM zahlungsanforderungen WHERE nummer = ?", (nummer,))
        con.execute("UPDATE za_nummernkreis SET naechste = ? WHERE kreis = ? AND naechste = ?",
                    (zahl, kreis, zahl + 1))
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()


def _setzen(nummer: str, **felder) -> None:
    with _verbindung() as con:
        con.execute(f"UPDATE zahlungsanforderungen SET {', '.join(f'{k} = ?' for k in felder)} "
                    "WHERE nummer = ?", [*felder.values(), nummer])




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
    # Voraussichtlich: Vergeben wird erst beim Senden, unter Sperre.
    eingabe["nummer"] = naechste_nummer(cfg)
    return eingabe, k, h, befunde


def versenden(cfg: dict, form: dict, name_id: int, benutzer: str,
              mit_mail: bool = True) -> str:
    """Baut die Zahlungsanforderung, legt sie ab und verschickt sie.
    mit_mail=False legt sie nur ab. Gibt 'gesendet', 'abgelegt' oder
    'testlauf' zusammen mit der Nummer zurueck; wirft bei jedem Hindernis,
    ohne etwas zu hinterlassen — auch die Nummer ist dann wieder frei."""
    if not ablauf._versand_sperre.acquire(timeout=2):
        raise ablauf.Beschaeftigt("Gerade wird eine Rechnung versendet (Automatiklauf). "
                                  "Bitte einen Moment warten und es erneut versuchen.")
    try:
        eingabe, k, h, befunde = vorbereiten(cfg, form, name_id)
        an = eingabe["empfaenger"]
        if mit_mail and not an:
            befunde.append("Es ist keine Empfängeradresse gewählt.")
        if befunde:
            raise ValueError("Nicht erstellt: " + " ".join(befunde))
        pdf(cfg, eingabe, k, h)   # vorab: passt es auf die Seite? (ZuLang)
        if (cfg.get("automatik") or {}).get("testlauf"):
            store.protokoll("testlauf", f"Zahlungsanforderung (voraussichtlich "
                            f"{eingabe['nummer']}) über {euro(eingabe['gesamt'])}: keine Nummer "
                            f"vergeben, nichts abgelegt, nichts versendet (Testlauf aktiv). Ziel "
                            f"wäre {an or '-'}", benutzer=benutzer)
            return "testlauf", eingabe["nummer"]
        satz = {"name_id": int(name_id), "kunde": k.get("name"),
                "datum": date.today().isoformat(), "faellig": eingabe["faellig"],
                "brutto_7": float(eingabe["brutto_7"]), "brutto_19": float(eingabe["brutto_19"]),
                "gesamt": float(eingabe["gesamt"]), "grund": eingabe["grund"],
                "empfaenger": an or None, "referenz": eingabe["referenz"] or None,
                "status": "begonnen", "erstellt_von": benutzer,
                "erstellt_am": store.jetzt()}
        nummer, kreis, zahl = nummer_ziehen(cfg, satz)
        eingabe["nummer"] = nummer
        # Erst ablegen, dann senden. 'x' legt nur neu an — eine gleichnamige
        # Datei bleibt unberuehrt.
        datei = ordner(cfg) / f"{nummer}.pdf"
        try:
            dokument = pdf(cfg, eingabe, k, h)
            with open(datei, "xb") as f:
                f.write(dokument)
        except (OSError, Eingabefehler) as e:
            nummer_freigeben(nummer, kreis, zahl)
            raise ValueError(f"Nicht erstellt: {e}") from e
        _setzen(nummer, pdf_pfad=str(datei))
        if not mit_mail:
            _setzen(nummer, status="abgelegt")
            store.protokoll("zahlungsanforderung", f"Zahlungsanforderung {nummer} über "
                            f"{euro(eingabe['gesamt'])} an {k.get('name')} abgelegt, nicht "
                            "versendet", benutzer=benutzer)
            return "abgelegt", nummer
        try:
            betreff, text = mail(cfg, eingabe, k)
            kennung = mailer.senden(
                cfg, an=an, bill_no=nummer, issuedate=datum(satz["datum"]),
                xml=None, xml_name="", pdf=datei, vorlage=(betreff, text))
        except mailer.MailFehler as e:
            # Nichts ging hinaus: Nummer und Ablage wieder frei.
            datei.unlink(missing_ok=True)
            nummer_freigeben(nummer, kreis, zahl)
            store.protokoll("zahlungsanforderung", f"Zahlungsanforderung {nummer}: Versand an "
                            f"{an} fehlgeschlagen: {e}", benutzer=benutzer, erfolg=False)
            raise
        _setzen(nummer, status="gesendet", gesendet_am=store.jetzt(), kennung=str(kennung))
        bcc = ", ".join(mailer.blindkopien(cfg, False)) or "-"
        store.protokoll("zahlungsanforderung", f"Zahlungsanforderung {nummer} über "
                        f"{euro(eingabe['gesamt'])} an {an}, BCC {bcc}, {kennung}",
                        benutzer=benutzer)
        return "gesendet", nummer
    finally:
        ablauf._versand_sperre.release()


# ------------------------------------------------------------------ Muster
MUSTER_KUNDE = {"name": "Muster & Söhne AG", "name_type": "COMPANY", "legal_company": None,
                "address1": "Hauptstraße 1",
                "address2": None, "zip_code": "80331", "city": "München", "country": "DE",
                "debitorennummer": "4711"}
MUSTER_EINGABE = {"brutto_7": "12.450,00", "brutto_19": "3.980,50",
                  "grund": "Tagung Frühjahrsklausur, 40 Zimmer, Tagungspauschale",
                  "referenz": "PO-0815"}


def muster(cfg: dict, vorlage: dict | None = None) -> bytes:
    """Ein Muster-PDF mit erfundenem Kunden, fuer die Seite der Vorlage. Die
    Hausdaten kommen aus OPERA; ist die Datenbank nicht erreichbar, aus der
    Konfiguration."""
    heute = date.today()
    eingabe = eingabe_pruefen(dict(MUSTER_EINGABE, faellig=faellig_vorgabe(cfg, heute)), heute)
    eingabe["nummer"] = nummer_bilden(dict(VORLAGE_VORGABE, **(vorlage or vorlage_laden())),
                                      heute, 1)
    try:
        h = haus(cfg)
    except Exception:
        p = cfg.get("property") or {}
        h = {"suppliername": p.get("haus") or p.get("resort") or "Ihr Haus",
             "supplierstreetname": "", "suppliercityname": "", "supplierpostalzone": ""}
    return pdf(cfg, eingabe, MUSTER_KUNDE, h, heute, vorlage=vorlage)
