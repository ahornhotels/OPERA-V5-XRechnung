"""Fachlicher Zugriff auf OPERA. Alle Abfragen liegen als .sql-Dateien unter
sql/opera/ und koennen dort angepasst werden, ohne den Code anzufassen."""
from __future__ import annotations
import logging
import re
from string import Formatter
from decimal import Decimal
from pathlib import Path

from . import config, db

log = logging.getLogger(__name__)
SQL_DIR = Path(__file__).resolve().parent.parent / "sql" / "opera"
_cache: dict[str, str] = {}


# Das Schema, in dem die OPERA-Tabellen liegen, heisst nicht ueberall OPERA.
# In den Abfragen steht deshalb @SCHEMA@ statt eines festen Namens — genauso,
# wie die Discovery-Skripte es mit &&OPERA_OWNER halten.
#
# Vorher stand in allen 15 Abfragen "opera." fest, waehrend die Konfiguration
# ein Feld "schema" anbot. Das Feld wurde NIRGENDS gelesen: Wer es aenderte,
# bekam keine Fehlermeldung, sondern eine Anwendung, die weiter auf OPERA
# zeigte. Eine Einstellung, die etwas verspricht und nichts tut, ist
# schlimmer als gar keine.
#
# Der Name geht als Text in die Abfrage, nicht als Bindvariable — Oracle
# laesst Schemanamen dort nicht zu. Deshalb wird er geprueft: Was kein
# gueltiger Oracle-Bezeichner ist, kommt nicht in den Abfragetext.
_SCHEMA_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]{0,29}$")
SCHEMA_VORGABE = "OPERA"


def _schema(cfg: dict | None = None) -> str:
    roh = str(((cfg or config.laden()).get("datenbank") or {}).get("schema") or "").strip()
    if not roh:
        return SCHEMA_VORGABE
    if not _SCHEMA_NAME.match(roh):
        log.error("Unzulaessiger Schemaname '%s' in datenbank.schema — erlaubt sind "
                  "Buchstaben, Ziffern, _ $ # (Anfang ein Buchstabe). Es gilt %s.",
                  roh, SCHEMA_VORGABE)
        return SCHEMA_VORGABE
    return roh


def _sql(name: str, cfg: dict | None = None) -> str:
    if name not in _cache:
        _cache[name] = (SQL_DIR / name).read_text(encoding="utf-8")
    return _cache[name].replace("@SCHEMA@", _schema(cfg))


def _zahl(wert) -> float:
    if wert is None:
        return 0.0
    if isinstance(wert, Decimal):
        return float(wert)
    try:
        return float(wert)
    except (TypeError, ValueError):
        return 0.0


def _mit_udf(sql: str, spalte: str) -> str:
    """Den Platzhalter fuer das Kennzeichen durch die konfigurierte Spalte
    ersetzen. Ohne Konfiguration bleibt NULL stehen."""
    spalte = (spalte or "").strip().upper()
    if not spalte:
        return sql
    if spalte not in UDF_SPALTEN:
        log.error("Unzulaessiges benutzerdefiniertes Feld '%s' — die Auswahl "
                  "laeuft ohne Kennzeichen weiter.", spalte)
        return sql
    return sql.replace("NULL AS erechnung_kennzeichen",
                       f"n.{spalte} AS erechnung_kennzeichen")


_FIRMENPROFILE_VORGABE = "('COMPANY', 'TRAVEL_AGENT', 'G', 'S') /*FIRMENPROFILE*/"
_PROFILTYP = re.compile(r"^[A-Z0-9_]{1,30}$")


def _mit_firmenprofilen(sql: str, cfg: dict) -> str:
    """Die Profiltypen, die als Firma gelten, aus auswahl.firmenprofile.

    Die Einstellung stand in der Konfiguration, wurde aber nie gelesen — die
    Liste war in beiden Abfragen fest verdrahtet. Sie geht als Text in die
    Abfrage (eine IN-Liste mit wechselnder Laenge laesst sich nicht binden),
    deshalb nur Grossbuchstaben, Ziffern und Unterstrich."""
    roh = (cfg.get("auswahl") or {}).get("firmenprofile")
    if not roh:
        return sql
    typen = [str(x).strip().upper() for x in roh if str(x).strip()]
    unzulaessig = [x for x in typen if not _PROFILTYP.match(x)]
    if unzulaessig or not typen:
        log.error("Unzulaessige Eintraege in auswahl.firmenprofile: %s — es gilt die "
                  "Vorgabe COMPANY, TRAVEL_AGENT, G, S", ", ".join(unzulaessig) or "(leer)")
        return sql
    return sql.replace(_FIRMENPROFILE_VORGABE,
                       "(" + ", ".join(f"'{x}'" for x in typen) + ")")


# Wie ein Anzahlungsbeleg in OPERA heisst.
#
# Hier stand eine Liste von Umsatzcodes ('8990', '8997', ...), fest verdrahtet
# und in zwei Abfragen doppelt gepflegt. Sie war in jedem anderen Haus falsch
# — und, wie eine Messung an einem Jahr Daten zeigte, in diesem Haus
# UNVOLLSTAENDIG: Die drei haeufigsten Anzahlungscodes standen nicht darin
# — und zwar ausgerechnet die drei haeufigsten. Eine Schlussrechnung, die nur ueber sie
# angezahlt war, galt damit als Nullbeleg und wurde zurueckgelegt.
#
# Der Ersatz braucht gar keine Codes: Anzahlungen sind in OPERA eigene Belege
# mit STATUS = 'DEPOSIT' am selben FOLIO_NO. Die Spalte kennt nur vier Werte
# (OK, DEPOSIT, VOID, ZERO), englisch auch in deutschsprachigen
# Installationen — das sind Systemkonstanten, keine Hauskonfiguration.
#
# Nachgesehen wurde das an EINER Installation. Deshalb laesst sich der Wert
# uebersteuern, falls ihn eine andere OPERA-Version anders schreibt. Er geht
# als Bindvariable in die Abfrage, nicht als Text.
ANZAHLUNG_STATUS_VORGABE = "DEPOSIT"


def anzahlung_status(cfg: dict | None = None) -> str:
    roh = str(((cfg or config.laden()).get("auswahl") or {})
              .get("anzahlung_status") or "").strip().upper()
    return roh or ANZAHLUNG_STATUS_VORGABE


# Die Umsatzcodes der Anzahlungen — nachsehbar und uebersteuerbar.
#
# Entschieden wird ueber den Belegstatus (anzahlung_status), nicht ueber
# Codes. Das Haus muss aber nachpruefen koennen, ob das bei ihm aufgeht, und
# es korrigieren koennen, wenn nicht: Ein Haus, das Anzahlungen nicht als
# eigene Belege fuehrt, sondern innerhalb desselben Belegs umbucht, wird von
# der Statusregel nicht erfasst.
#
# Deshalb hier eine ZUSAETZLICHE Bedingung, keine ersetzende. Steht in
# auswahl.anzahlungscodes etwas, gilt eine Rechnung auch dann als angezahlt,
# wenn sie eine Buchung mit einem dieser Codes traegt. Leer — die Vorgabe —
# laesst die Abfrage unveraendert.
#
# Welche Codes das Haus tatsaechlich benutzt, beantwortet
# anzahlungscodes_ermitteln() aus den eigenen Daten. Geraten wird nichts.
_TRX_CODE = re.compile(r"^[A-Za-z0-9_-]{1,20}$")
_ODER_CODES = "/*ODER_CODES*/"


def _mit_anzahlungscodes(sql: str, cfg: dict) -> str:
    roh = (cfg.get("auswahl") or {}).get("anzahlungscodes")
    if not roh:
        return sql
    codes = [str(x).strip().upper() for x in roh if str(x).strip()]
    unzulaessig = [x for x in codes if not _TRX_CODE.match(x)]
    if unzulaessig or not codes:
        log.error("Unzulaessige Eintraege in auswahl.anzahlungscodes: %s — es bleibt "
                  "bei der Erkennung ueber den Belegstatus.",
                  ", ".join(unzulaessig) or "(leer)")
        return sql
    liste = ", ".join(f"'{x}'" for x in codes)
    return sql.replace(_ODER_CODES,
                       " OR EXISTS (SELECT 1 FROM @SCHEMA@.financial_transactions t"
                       f" WHERE t.bill_no = f.bill_no AND t.resort = f.resort"
                       f" AND t.trx_code IN ({liste}))")


def anzahlungscodes_ermitteln(cfg: dict, tage: int = 365) -> list[dict]:
    """Welche Umsatzcodes stehen im eigenen Haus auf Anzahlungsbelegen?

    Fuer die Einrichtung: Sie zeigt, ob die Erkennung ueber den Belegstatus
    im eigenen Bestand etwas findet, und welche Codes dabei zusammenkommen.
    Findet sie nichts, stimmt die Annahme fuer dieses Haus nicht — dann
    gehoeren die Codes von Hand in die Konfiguration.

    Laeuft ueber ein Jahr und braucht einen Moment. Gehoert auf Knopfdruck,
    nicht in den Seitenaufbau."""
    return db.abfrage(_sql("anzahlungscodes.sql", cfg), {
        "resort": cfg["property"]["resort"],
        "anzahlung_status": anzahlung_status(cfg),
        "tage": int(tage),
    })


def _resort() -> str:
    """Das Resort fuer Abfragen, die ohne Konfiguration aufgerufen werden."""
    return config.laden()["property"]["resort"]


def kandidaten(cfg: dict, tage: int | None = None) -> list[dict]:
    """Rechnungen der letzten n Tage samt Kennzeichen. Zeitraum und Obergrenze
    stehen in der Konfiguration und lassen sich beim Einlesen uebersteuern."""
    s = cfg.get("auswahl") or {}
    return db.abfrage(_mit_anzahlungscodes(_mit_firmenprofilen(_mit_udf(_sql("invoice_list.sql", cfg),
                              (cfg.get("property") or {}).get("udf_erechnung", "")), cfg), cfg), {
        "days": int(tage if tage is not None else s.get("zeitraum_tage", 30)),
        "resort": cfg["property"]["resort"],
        "leitweg_typ": cfg["property"]["mitgliedschaftstyp_leitweg"],
        "erechnung_typ": cfg["property"].get("mitgliedschaftstyp_erechnung") or "-",
        "hoechstens": int(s.get("hoechstens", 2000)),
        # Der Firmenfilter gehoert in die Abfrage, damit die Obergrenze auf die
        # SINNVOLLEN Zeilen wirkt und nicht auf alle Rechnungen des Hauses.
        "nur_firmen": "J" if (cfg.get("automatik") or {}).get("nur_mit_firmenbezug", True) else "N",
        "anzahlung_status": anzahlung_status(cfg),
    })


def pruefung(cfg: dict, bill_no: int) -> dict:
    """Guard: rekonziliieren die Positionen gegen den Kopf?"""
    zeilen = db.abfrage(_mit_anzahlungscodes(_sql("invoice_guard.sql", cfg), cfg),
                        {"bill_no": bill_no, "resort": cfg["property"]["resort"],
                         "anzahlung_status": anzahlung_status(cfg)})
    return zeilen[0] if zeilen else {}


def empfaenger(bill_no: int) -> list[dict]:
    """Alle E-Mail-Adressen, die zu dieser Rechnung gehoeren."""
    return db.abfrage(_sql("invoice_recipients.sql"), {"bill_no": bill_no, "resort": _resort()})


def profil(cfg: dict, bill_no: int) -> dict:
    zeilen = db.abfrage(_sql("invoice_profile.sql", cfg), {
        "bill_no": bill_no,
        "resort": cfg["property"]["resort"],
        "leitweg_typ": cfg["property"]["mitgliedschaftstyp_leitweg"],
        "erechnung_typ": cfg["property"].get("mitgliedschaftstyp_erechnung") or "-",
    })
    return zeilen[0] if zeilen else {}


def suchen(cfg: dict, begriff: str) -> list[dict]:
    """Eine bestimmte Rechnung in OPERA finden — nach Rechnungs- oder
    Belegnummer.

    Damit ist auch eine Rechnung erreichbar, die gar nicht in der Arbeitsliste
    steht: weil sie aelter ist als das eingelesene Fenster, weil sie beim
    Einlesen aussortiert wurde oder weil niemand sie je eingelesen hat.

    Nach Namen wird hier NICHT gesucht — das liefe ohne passenden Index auf
    einen vollen Tabellendurchlauf hinaus. Namen findet man in der
    Arbeitsliste."""
    begriff = (begriff or "").strip()
    if not begriff:
        return []
    nur_ziffern = begriff.isdigit() and len(begriff) <= 18
    return db.abfrage(_mit_firmenprofilen(_sql("invoice_suche.sql", cfg), cfg), {
        "resort": cfg["property"]["resort"],
        "bill_no": int(begriff) if nur_ziffern else None,
        # INVOICE_NO ist in OPERA eine ZAHL. Als Text gebunden liess ein
        # Begriff wie "RE-1400003" die ganze Suche mit ORA-01722 scheitern.
        "invoice_no": int(begriff) if nur_ziffern else None,
    })


# Erlaubte benutzerdefinierte Felder. Der Name geht in den Abfragetext, nicht
# als Bindvariable — Oracle laesst Spaltennamen dort nicht zu. Diese Liste ist
# deshalb keine Bequemlichkeit, sondern die Absicherung.
UDF_SPALTEN = {f"UDFC{n:02d}" for n in range(1, 41)}


def udf_feld(name_id, spalte: str) -> str:
    """Ein benutzerdefiniertes Feld der Kartei lesen. Leer, wenn nichts da ist.

    Traeger fuer die Leitweg-ID an der FIRMENkartei. Mitgliedschaften gibt es
    in OPERA nur an der Individualkartei; ein Kennzeichen, das dort liegt, ist
    fuer Firmenrechnungen wertlos."""
    spalte = (spalte or "").strip().upper()
    if not spalte or not name_id:
        return ""
    if spalte not in UDF_SPALTEN:
        log.error("Unzulaessiges benutzerdefiniertes Feld '%s' — erlaubt sind "
                  "UDFC01 bis UDFC40. Es wird nichts gelesen.", spalte)
        return ""
    try:
        zeilen = db.abfrage(_sql("profil_udf.sql").replace("@SPALTE@", spalte),
                            {"name_id": int(name_id)})
    except Exception:
        log.exception("Benutzerdefiniertes Feld %s nicht lesbar (%s)", spalte, name_id)
        return ""
    return (zeilen[0].get("wert") or "").strip() if zeilen else ""


def udf_uebersicht() -> list[dict]:
    """Welche benutzerdefinierten Felder der Firmenkartei sind frei?

    Fuer die Einrichtung: Sie sagt je Feld, ob es an der Firmenkartei sichtbar
    ist, wie es dort beschriftet ist und wie viele Karteien schon einen Wert
    tragen. Beides zaehlt — ein freies Feld, das auf keinem Formular steht,
    kann niemand pflegen, und ein sichtbares mit Werten darin gehoert schon
    jemandem.

    Laeuft ueber alle Firmenkarteien und braucht deshalb einen Moment. Sie
    gehoert auf Knopfdruck, nicht in den Seitenaufbau."""
    zeilen = db.abfrage(_sql("udf_uebersicht.sql"))
    for z in zeilen:
        z["frei"] = not z.get("belegt")
        z["sichtbar"] = str(z.get("sichtbar") or "N").upper() == "Y"
        z["empfohlen"] = z["frei"] and not z.get("beschriftung")
    return zeilen


def profil_name(name_id: int) -> str:
    """Der Name zu einer Profilnummer. Leerer String, wenn nichts zu holen ist.

    Fuer die Pflegeliste: Auf dem Beleg fehlt COMPANY_NAME haeufig, am Profil
    steht der Name trotzdem. Ohne ihn sucht der Empfang nach einer Nummer."""
    try:
        zeilen = db.abfrage(_sql("profil_name.sql"), {"name_id": int(name_id)})
    except Exception:
        log.exception("Profilname nicht lesbar (%s)", name_id)
        return ""
    return (zeilen[0].get("name") or "").strip() if zeilen else ""


def buchungsfirma(bill_no: int) -> dict:
    """Welche Firma haengt an der Reservierung? Nur fuer die Sichtpruefung
    einer einzelnen Rechnung — die Abfrage geht ueber eine grosse View und
    gehoert nicht in die Liste."""
    zeilen = db.abfrage(_sql("invoice_buchungsfirma.sql"), {"bill_no": bill_no, "resort": _resort()})
    return zeilen[0] if zeilen else {}


# BT-10 traegt eine Referenz, keinen Fliesstext. Die Norm setzt keine Grenze,
# die Empfangssysteme schon — und das Quellfeld FOLIO_TEXT1 fasst 2000 Zeichen.
BT10_LAENGE = 80


# Welche Felder der Buchung in BT-127 duerfen. Die Auswahl steht in der
# Konfiguration, weil verschiedene Haeuser verschiedene Felder fuellen — und
# weil das, was hier hereinkommt, an den Kunden geht.
BEMERKUNGSFELDER = {"remark": "bem_remark", "reference": "bem_reference"}

# Der Name EINES FREMDEN GASTES darf nicht auf die Rechnung.
#
# OPERA schreibt in REFERENCE kein Anwenderfeld, sondern ein Systemprotokoll.
# Bei umgeleiteten Buchungen (Routing) steht dort der Name UND die
# Zimmernummer des Gastes, VON DEM die Buchung kam:
#     [NA P.Room] [Routed From Mustermann Erika Of Room 412]
# An echten Daten gemessen: 14,9 % der belegten REFERENCE-Werte tragen
# diesen Baustein. In der Zielmenge waere jede zwoelfte Firmenrechnung
# betroffen.
# Das ist kein Schoenheitsfehler: Auf einer Firmenrechnung stuende der
# Aufenthalt einer anderen, womoeglich voellig unbeteiligten Person.
#
# Der Filter greift fuer JEDES Bemerkungsfeld, nicht nur fuer 'reference' —
# auch ein von Hand in REMARK kopierter Text ist derselbe Personenbezug.
_ROUTING_KLAMMER = re.compile(r"\[[^\]]*Routed\s+From[^\]]*\]", re.IGNORECASE)
_ROUTING_FREI = re.compile(r"Routed\s+From\b.*?(?:\s+Of\s+Room\s+\S+|$)", re.IGNORECASE)

# Zweiter Personenbezug, gefunden am selben Tag: GEWAEHLTE RUFNUMMERN.
#
# Bei Telefonbuchungen ist das "Supplement", das OPERA anzeigt, genau das
# REFERENCE-Feld (View FT_HBCALLS_VIEW: `ft.reference AS supplement`). Und in
# IFC_CALL_HIST — der Bestandstabelle dahinter — traegt praktisch jede
# Zeile eine Ziffernfolge von mindestens fuenf Stellen: die angerufene
# Nummer, im Schnitt 30 Zeichen mit Uhrzeit und Dauer daneben.
#
# Auf einer Firmenrechnung waere das die Telefonverbindung eines Mitarbeiters.
# Verkehrsdaten wiegen schwerer als ein Name. Dieselbe Regel faengt nebenbei
# Kartennummern ab, falls jemand so etwas in eine Bemerkung tippt.
#
# Die Schaerfe haengt am FELD, nicht am Text — die beiden Spalten tragen
# voellig Verschiedenes:
#
#   REFERENCE ist Systemprotokoll. Was dort an Ziffern steht, hat niemand fuer
#   den Kunden geschrieben; bei Telefonbuchungen ist es die gewaehlte Nummer.
#   Ab fuenf Stellen faellt der Wert weg, und es geht nichts verloren.
#
#   REMARK ist das Anwenderfeld — das "Supplement" der Buchungsmaske, am
#   17.09.2026 vom Haus bestaetigt: Auf der gedruckten Rechnung steht dort
#   "Beamer Raum Lissabon / Muster Pharma GmbH". ENTSCHEIDUNG DES HAUSES: Ist das
#   Feld gefuellt, geht es VOLLSTAENDIG auf die XRechnung. Kein Kuerzen, kein
#   Weglassen von Teilen. Der Text ist fuer den Kunden geschrieben, und wer
#   ihn erfasst, weiss, was er tut.
#
#   Dazu passen die Daten: An 90 Tagen trug kein einziger REMARK-Wert einen
#   Routing-Hinweis, und keine Ziffernfolge sah nach Rufnummer oder Karte aus
#   — es sind Gutscheinnummern ("Voucher 09000001") und Abrechnungsnummern
#   ("Abr. CC'S 230626 HP", "030552"). Genau die Angaben, mit denen der Kunde
#   die Position zuordnet.
#
#   None heisst: kein Ziffernfilter. Still gekuerzt wird hier nichts mehr.
#   Bleibt eine Folge von 13 und mehr Ziffern stehen — Kartenlaenge —, haelt
#   die Vorpruefung den Versand an, statt den Text zu veraendern
#   (xml_build.pruefsummen). Sichtbar anhalten ist etwas anderes als
#   heimlich wegnehmen.
_ZIFFERN_AB = {"bem_reference": 5, "bem_remark": None}
_ZIFFERN_VORGABE = 5


def _ohne_personenbezug(wert: str, ziffern_ab: int | None = _ZIFFERN_VORGABE) -> str:
    """Fremde Gastnamen und Rufnummern aus einem Bemerkungstext entfernen.

    Routing-Hinweise werden herausgeschnitten, der Rest bleibt stehen. Was
    danach noch nach Personenbezug aussieht — ein unbekanntes 'Routed From'
    oder eine lange Ziffernfolge — laesst den GANZEN Wert wegfallen. Halb
    bereinigt geht nichts hinaus; im Zweifel lieber keine Bemerkung."""
    sauber = wert
    if "routed from" in wert.lower():
        sauber = _ROUTING_FREI.sub("", _ROUTING_KLAMMER.sub("", wert))
        sauber = re.sub(r"\s{2,}", " ", sauber).strip(" ·-,;")
        if "routed from" in sauber.lower():
            log.warning("Positionsbemerkung enthaelt einen unbekannten Routing-Hinweis "
                        "und faellt ganz weg — sie nennte einen fremden Gast")
            return ""
    if ziffern_ab and re.search(r"\d{%d,}" % ziffern_ab, sauber):
        log.warning("Positionsbemerkung enthaelt eine Ziffernfolge ab %d Stellen und "
                    "faellt ganz weg — das ist keine Angabe fuer den Kunden "
                    "(Rufnummer, Kartennummer)", ziffern_ab)
        return ""
    return sauber


# ZUM VERANSTALTERNAMEN HINTER DEM SCHRAEGSTRICH — bewusst NICHT gefiltert.
#
# Die Bemerkungen der Tagungsbuchungen haben die Form "<Leistung> / <Firma>":
# "Beamer Raum Lissabon / Muster Pharma GmbH". Kurzzeitig wurde der Teil hinter dem
# Schraegstrich entfernt, sobald ein Beleg mehrere verschiedene Namen trug —
# Beleg 1400001 nennt vier (Muster Pharma GmbH, Muster Technik AG, Reisedienst Nord, Beispiel Chemie GmbH), und sein
# Empfaenger ist ein Reisebuero, also keiner von ihnen.
#
# DAS HAUS HAT DAGEGEN ENTSCHIEDEN (17.09.2026): Ist das Supplement-Feld
# gefuellt, geht es vollstaendig auf die Rechnung. Es steht so auch auf der
# gedruckten Rechnung, die der Kunde heute schon bekommt — eine XRechnung, die
# etwas anderes sagt als das Papier, waere das groessere Uebel.
#
# Die Zahlen zum Mitdenken, falls die Frage wiederkommt (eine Installation,
# ueber ein Quartal gemessen):
# 27 Belege mit Schraegstrich, davon 8 mit mehreren verschiedenen Namen;
# 26 der 27 gehen an einen Firmenempfaenger. Wer den Namen nicht auf fremden
# Rechnungen haben will, aendert das am Empfang — in dem Moment, in dem die
# Bemerkung erfasst wird. Die Software soll den erfassten Text nicht
# umschreiben.


def positionsbemerkung(zeilen: list[dict], p: dict) -> None:
    """BT-127 je Position aus den konfigurierten Feldern zusammensetzen.

    Mehrere Felder werden mit ' · ' verbunden, Doppeltes faellt weg: Steht
    dieselbe Check-Nummer in zwei Feldern, soll sie nicht zweimal auf der
    Rechnung stehen."""
    # Nur ein FEHLENDER Eintrag heisst Vorgabe. Eine leere Liste ist der
    # dokumentierte Ausschalter — mit "or" wurde sie wieder zur Vorgabe, und
    # interne Buchungsnotizen gingen an den Kunden.
    #
    # Die Vorgabe ist 'remark' — DAS ist das Feld, das OPERA in der
    # Buchungsmaske "Supplement" nennt. Belegt an Beleg 1400001: vier
    # Buchungen mit trx_code 2920 "Conference Center technical equipment",
    # und in REMARK steht "Beamer Raum Lissabon / <Firma>". Weder REFERENCE
    # (dort nur "CHECK# 1000001 [1]") noch O_TRX_DESC tragen den Text.
    #
    # Die Vorgabe war zwischendurch leer, weil eine 30-Tage-Stichprobe REMARK
    # mit 3,6 % Fuellung und einem "back" als haeufigstem Wert zeigte. Die
    # Stichprobe war der Fehler: In 30 Tagen Firmenrechnungen dominieren
    # Uebernachtungen, und dort ist REMARK fast immer leer. Bei
    # Konferenzbuchungen ist es zu 41 bis 63 % gefuellt — mit Raumnamen,
    # Ausstattung und Leistungsbezeichnungen (Genf, Beamer, Flipchart,
    # Tagungspauschale). Genau der Text, den die Buchhaltung meint, und
    # genau der Unterschied zwischen "technische Ausstattung 230,00" und
    # "Beamer Raum Lissabon".
    roh = p.get("positionsbemerkung")
    gewaehlt = [str(f).strip().lower() for f in (["remark"] if roh is None else roh)]
    unbekannt = [f for f in gewaehlt if f and f not in BEMERKUNGSFELDER]
    if unbekannt:
        log.error("Unbekannte Felder in property.positionsbemerkung: %s — "
                  "moeglich sind %s", ", ".join(unbekannt),
                  ", ".join(sorted(BEMERKUNGSFELDER)))
    for z in zeilen:
        teile: list[str] = []
        for feld in gewaehlt:
            spalte = BEMERKUNGSFELDER.get(feld, "")
            wert = _ohne_personenbezug(str(z.get(spalte) or "").strip(),
                                       _ZIFFERN_AB.get(spalte, _ZIFFERN_VORGABE))
            if wert and wert not in teile:
                teile.append(wert)
        z["bemerkung"] = " · ".join(teile)


# Wie die Positionen auf der Rechnung stehen — docs/14_POSITIONEN.md.
# Entschieden von der Buchhaltung am 14.09.2026: zwei Arten, fuer
# Einzelrechnungen und fuer Gruppen; an der Position Gastname UND Zimmer; die
# Gastnamen duerfen und muessen auf die Rechnung.
#
# A bleibt waehlbar, ist aber keine Vorbelegung. Er ist der Stand vor der
# Entscheidung und der Rueckweg, falls eine gebuendelte Rechnung nicht aufgeht.
POSITIONSARTEN = {
    "B": "Zusammengefasst nach Leistung und Preis",
    "C": "Je Gast und Zimmer",
    "A": "Jede Buchung einzeln",
}


def positionsart_vorschlag(kopf: dict, zeilen: list[dict]) -> tuple[str, str]:
    """Die Vorbelegung: (Art, Begruendung).

    Gruppe heisst hier: Die Buchungen gehoeren zu mehr als einer Reservierung.
    Das ist unabhaengig davon, wie die Gruppe in OPERA angelegt ist, und es
    kostet keine Abfrage — die Zuordnung steht ohnehin an jeder Zeile.

    Zweiter Fall fuer C: ein Gast an den Buchungen, aber keiner am
    Rechnungskopf. Mit B stuende der Name dann nirgends auf der Rechnung."""
    gaeste = {z.get("gast_resv_name_id") for z in zeilen if z.get("gast_resv_name_id")}
    if len(gaeste) > 1:
        return "C", f"{len(gaeste)} Reservierungen auf dem Beleg"
    if not (kopf.get("gastname") or "").strip() \
            and any((z.get("gast_name") or "").strip() for z in zeilen):
        return "C", "am Rechnungskopf steht kein Gast"
    return "B", "ein Gast auf dem Beleg" if gaeste else "kein Gast an den Buchungen"


def _dezimal(wert) -> Decimal:
    try:
        return Decimal(str(wert if wert is not None else 0))
    except Exception:
        return Decimal(0)


def _menge_ausgeben(menge: Decimal):
    """Ganze Mengen als ganze Zahl — im Dokument soll '10' stehen, nicht '10.000'."""
    return int(menge) if menge == menge.to_integral_value() else float(menge)


def _zimmer_ordnung(zimmer: str):
    """Zimmer 9 vor Zimmer 10. Nicht-numerische Zimmer (Masterkonten, 'PM')
    ans Ende."""
    zimmer = (zimmer or "").strip()
    return (0, int(zimmer), "") if zimmer.isdigit() else (1, 0, zimmer)


def _gastbemerkung(zimmer: str, gast: str) -> str:
    teile = []
    if (zimmer or "").strip():
        teile.append(f"Zi. {zimmer.strip()}")
    if (gast or "").strip():
        teile.append(gast.strip())
    return " · ".join(teile)


def positionen_buendeln(zeilen: list[dict], art: str) -> list[dict]:
    """Die Buchungen zu Positionen zusammenfassen.

      B  je Umsatzcode, Steuersatz und Einzelpreis
      C  zusaetzlich je Gast (Reservierung); Zimmer und Name in BT-127,
         Aufenthalt in BT-134/135
      A  unveraendert — jede Buchung eine Position

    Zusammengefasst wird nur, was denselben BRUTTOpreis auf den Cent traegt:
    PEPPOL-EN16931-R120 rechnet Menge mal Einzelpreis nach, und ein
    Durchschnittspreis geht dabei nicht auf (1.026,27 / 5 = 205,25, mal 5 =
    1.026,25). Summiert werden die UNGERUNDETEN Betraege aus OPERA; gerundet
    wird wie bisher erst in xml_build._normalisieren. Die Summe der Positionen
    ist damit dieselbe wie ohne Buendelung, und die Gegenprobe gegen die
    Steuergruppen aus OPERA prueft unveraendert.

    Heben sich Buchungen auf (Buchung und Storno desselben Preises), faellt die
    Position weg. Ergibt eine Gruppe die Menge null bei einem Betrag, wird sie
    nicht zusammengefasst: Ihre Buchungen stehen dann einzeln da, wie unter A.
    Eine Position, die sich nicht nachrechnen laesst, waere schlimmer als eine
    laengere Rechnung."""
    if art not in ("B", "C"):
        return zeilen
    gruppen: dict[tuple, list[dict]] = {}
    for nr, z in enumerate(zeilen):
        # Menge 0 braucht hier keine eigene Bedingung: Eine Gruppe mit Menge
        # null und Betrag landet unten im Zweig "einzeln", eine mit Menge null
        # und Betrag null faellt weg. Ohne Preis (Menge 0 in der Abfrage,
        # NULLIF) gibt es keinen Schluessel.
        preis = z.get("bruttopreis")
        if preis is None:
            schluessel: tuple = ("einzeln", nr)
        else:
            schluessel = (
                z.get("gast_resv_name_id") if art == "C" else None,
                # Das Zimmer gehoert mit in den Schluessel: Zieht ein Gast um,
                # traegt EINE Reservierung Buchungen aus zwei Zimmern, und die
                # Position nennte sonst nur das erste.
                str(z.get("gast_zimmer") or "") if art == "C" else None,
                str(z.get("itemcode") or ""),
                str(z.get("classifiedtaxcategoryid") or ""),
                str(z.get("classifiedtaxcategorypercent")),
                _dezimal(preis),
            )
        gruppen.setdefault(schluessel, []).append(z)

    aus: list[dict] = []
    for schluessel, teil in gruppen.items():
        # Die Spanne der tatsaechlich berechneten Tage dieser Buchungen.
        tage = sorted(str(z["leistungsdatum"]) for z in teil if z.get("leistungsdatum"))
        menge = sum((_dezimal(z.get("invoicedquantity")) for z in teil), Decimal(0))
        netto = sum((_dezimal(z.get("lineextensionamountnet")) for z in teil), Decimal(0))
        brutto = sum((_dezimal(z.get("lineextensionamount")) for z in teil), Decimal(0))
        if schluessel[0] == "einzeln" or len(teil) == 1:
            neu = [dict(z, buchungen=1,
                        leistung_von=z.get("leistungsdatum"), leistung_bis=z.get("leistungsdatum"))
                   for z in teil]
        elif menge == 0 and netto == 0 and brutto == 0:
            continue                      # Buchung und Storno heben sich auf
        elif menge == 0:
            # Menge null bei einem Betrag laesst sich nicht nachrechnen.
            # (Betrag null bei einer Menge schon: 5 x 0,00 = 0,00 — das sind
            # die Inklusivleistungen, und gerade die sollen zusammengehen.)
            neu = [dict(z, buchungen=1,
                        leistung_von=z.get("leistungsdatum"), leistung_bis=z.get("leistungsdatum"))
                   for z in teil]
        else:
            erste = teil[0]
            bemerkungen: list[str] = []
            for z in teil:
                b = (z.get("bemerkung") or "").strip()
                if b and b not in bemerkungen:
                    bemerkungen.append(b)
            neu = [dict(erste,
                        invoicedquantity=_menge_ausgeben(menge),
                        lineextensionamountnet=float(netto),
                        lineextensionamount=float(brutto),
                        priceamount=None,
                        bemerkung=" · ".join(bemerkungen),
                        buchungen=len(teil),
                        leistung_von=tage[0] if tage else None,
                        leistung_bis=tage[-1] if tage else None)]
        for z in neu:
            if art == "C":
                gast = _gastbemerkung(z.get("gast_zimmer"), z.get("gast_name"))
                # Fuer den Fall, dass die Position zum Abschlag wird
                # (xml_build._normalisieren): Dort gibt es keine Note, der Gast
                # geht in den Grund.
                if gast:
                    z["gast_kennung"] = gast
                eigene = (z.get("bemerkung") or "").strip()
                z["bemerkung"] = " · ".join(t for t in (gast, eigene) if t)
                # Der Zeitraum der Position ist die Spanne der BERECHNETEN Tage
                # (Buchungsdatum). Vorher stand dort der ganze Aufenthalt der
                # Reservierung — bei einem Masterkonto oder einer Dauerbuchung
                # ueber Monate, und der Rechnungszeitraum wurde entsprechend
                # aufgeweitet. Nur ohne Buchungsdatum gilt der Aufenthalt.
                beginn = z.get("leistung_von") or z.get("gast_beginn")
                ende = z.get("leistung_bis") or z.get("gast_ende")
                # BR-30: Ende nicht vor dem Beginn. Ein unvollstaendiger
                # Zeitraum bleibt ganz weg.
                if beginn and ende and str(beginn) <= str(ende):
                    z["zeitraum_beginn"], z["zeitraum_ende"] = beginn, ende
            aus.append(z)
    if art == "C":
        aus.sort(key=lambda z: (_zimmer_ordnung(z.get("gast_zimmer")),
                                (z.get("gast_name") or ""),
                                str(z.get("gast_resv_name_id") or "")))
    return aus


def rechnungszeitraum_erweitern(kopf: dict, zeilen: list[dict]) -> None:
    """BT-73/74 so weit fassen, dass jeder Positionszeitraum hineinpasst.

    PEPPOL-EN16931-R110/R111 (im XRechnung-Regelwerk 3.0.2, fatal): Beginn und
    Ende jeder Position muessen im Rechnungszeitraum liegen. Der Kopf traegt
    den Aufenthalt EINER Reservierung — bei einer Gruppe mit verschiedenen
    Anreisetagen wurde die Rechnung damit abgewiesen. Fuer eine Sammelrechnung
    ist der Leistungszeitraum ohnehin die Spanne aller Aufenthalte.

    Die Gastzeile in BT-22 bleibt davon unberuehrt; sie ist vorher gebaut und
    nennt den Aufenthalt des Gastes am Kopf."""
    beginne = [str(z["zeitraum_beginn"]) for z in zeilen if z.get("zeitraum_beginn")]
    enden = [str(z["zeitraum_ende"]) for z in zeilen if z.get("zeitraum_ende")]
    if not beginne or not enden:
        return
    if kopf.get("startdate"):
        beginne.append(str(kopf["startdate"]))
    if kopf.get("enddate"):
        enden.append(str(kopf["enddate"]))
    kopf["startdate"], kopf["enddate"] = min(beginne), max(enden)


def gastzeile(kopf: dict, p: dict) -> dict:
    """BT-22: die Zeile, die sagt, WER im Haus war.

    Eine Firmenrechnung ueber eine Uebernachtung nennt sonst den Zahler, den
    Zeitraum und die Positionen — aber nicht den Gast. Die Buchhaltung des
    Kunden kann sie damit keiner Reise und keinem Mitarbeiter zuordnen; auf der
    Papierrechnung aus OPERA steht der Gast oben.

    Der Text ist eine Vorlage mit Platzhaltern, weil verschiedene Haeuser dort
    Verschiedenes wollen. Fehlt der Gastname — bei Gruppen haengt keiner an der
    Reservierung —, faellt die Zeile ganz weg. 'Gast: None' waere schlimmer als
    keine Zeile."""
    vorlage = (p.get("gastzeile") or "").strip()
    gast = (kopf.get("gastname") or "").strip()
    if not vorlage or not gast:
        return kopf
    try:
        zeile = vorlage.format(
            gast=gast,
            zimmer=(kopf.get("zimmer") or "").strip(),
            anreise=kopf.get("startdate") or "",
            abreise=kopf.get("enddate") or "",
        ).strip()
    except (KeyError, IndexError, ValueError, AttributeError, TypeError) as e:
        # Eine vertippte Vorlage darf nicht JEDE Rechnung unbaubar machen.
        log.error("property.gastzeile nicht fuellbar (%s) — die Gastzeile entfaellt", e)
        return kopf
    # Gemerkt, damit die Zeile bei einer Gruppenrechnung wieder heraus kann
    # (ablauf.rechnungsdaten): Dort nennte sie nur den Gast der Kopfreservierung.
    kopf["gastzeile_text"] = zeile
    # Ein vorhandener Hinweis bleibt stehen; BT-22 gibt es nur einmal.
    vorher = (kopf.get("note") or "").strip()
    kopf["note"] = f"{vorher} · {zeile}" if vorher else zeile
    return kopf


# Eine Leitweg-ID ist aufgebaut als Grobadressierung, optionale
# Feinadressierung und zweistellige Pruefziffer, getrennt durch Bindestriche,
# hoechstens 46 Zeichen. Geprueft wird das, weil das Traegerfeld an der Kartei
# ein Freitextfeld ist — daneben steht eines, in das heute "BLACKLIST" getippt
# wird. Was dort landet, geht sonst ungeprueft als Behoerdenadresse hinaus.
LEITWEG_MUSTER = re.compile(r"^\d{2,12}(-[0-9A-Za-z]{1,30})?-\d{2}$")


def leitweg_pruefen(wert: str) -> tuple[bool, str]:
    """Sieht der Wert aus wie eine Leitweg-ID? (ja/nein, Begruendung)"""
    wert = (wert or "").strip()
    if not wert:
        return False, "leer"
    if len(wert) > 46:
        return False, f"{len(wert)} Zeichen — eine Leitweg-ID hat hoechstens 46"
    if not LEITWEG_MUSTER.match(wert):
        return False, ("passt nicht zum Aufbau einer Leitweg-ID "
                       "(Grobadressierung-[Feinadressierung-]Pruefziffer)")
    return True, ""


def kuerzen(wert) -> tuple[str, int]:
    """BT-10 auf Referenzlaenge bringen. Gibt (Wert, urspruengliche Laenge)
    zurueck; die Laenge ist 0, wenn nichts gekuerzt wurde.

    Eigene Funktion, weil dieselbe Regel fuer zwei Wege gilt: das Feld an der
    Reservierung und die Eingabe von Hand. Gaelte sie nur fuer einen, waere
    ausgerechnet der Weg ungeprueft, den ein Mensch benutzt."""
    roh = " ".join(str(wert or "").split())
    return roh[:BT10_LAENGE].strip(), len(roh) if len(roh) > BT10_LAENGE else 0


def _vorlage_fuellen(vorlage: str, kopf: dict, p: dict, bill_no: int) -> str:
    """Die Vorlage fuer BT-10 fuellen. Leerer String heisst: nicht verwendbar.

    Fehlt einer der benutzten Werte, wird die Vorlage NICHT genommen — sonst
    stuende auf der Rechnung "… ReservNr.:" ohne Nummer, und das sieht aus wie
    ein Wert. Der Hausname zaehlt dabei nicht als Wert: Eine Kaeuferreferenz,
    die nur den Namen des Hauses traegt, sagt dem Empfaenger nichts."""
    if not vorlage:
        return ""
    werte = {
        "haus": (p.get("haus") or p.get("resort") or "").strip(),
        "reservierungsnummer": str(kopf.get("reservierungsnummer") or "").strip(),
        "rechnungsnummer": str(bill_no or "").strip(),
        "debitor": str(kopf.get("debitorennummer") or "").strip(),
        "kunde": str(kopf.get("customername") or "").strip(),
    }
    try:
        benutzt = {name for _, name, _, _ in Formatter().parse(vorlage) if name}
    except ValueError as e:
        log.error("buyerreference_vorlage ist fehlerhaft (%s)", e)
        return ""
    unbekannt = benutzt - set(werte)
    if unbekannt:
        log.error("Unbekannte Platzhalter in buyerreference_vorlage: %s — "
                  "moeglich sind %s", ", ".join(sorted(unbekannt)),
                  ", ".join(sorted(werte)))
        return ""
    # ALLE benutzten Werte muessen da sein, nicht nur einer: Aus
    # "{kunde} / {debitor}" wurde sonst "Firma GmbH / " — ein halber Wert, der
    # wie ein ganzer aussieht.
    if not benutzt or any(not werte[n] for n in benutzt if n != "haus") \
            or not [n for n in benutzt if n != "haus"]:
        return ""
    try:
        return vorlage.format(**werte).strip()
    except (KeyError, IndexError, ValueError, AttributeError, TypeError) as e:
        log.error("buyerreference_vorlage nicht fuellbar (%s)", e)
        return ""


def kaeuferreferenz(kopf: dict, p: dict, bill_no: int) -> dict:
    """Setzt BT-10 und haelt fest, woher der Wert stammt.

    BR-DE-15 macht BT-10 zur Pflicht, aber eine Leitweg-ID hat nur die
    oeffentliche Verwaltung — bei gewoehnlichen Firmenkunden ist das Feld
    regelmaessig leer, und ein Ersatzwert ist zulaessig. Welcher, ist eine
    fachliche Entscheidung und steht deshalb in der Konfiguration.

    Die Herkunft wird mitgefuehrt: Ein Ersatzwert soll in der Oberflaeche
    sichtbar sein und nicht als echte Referenz des Kaeufers durchgehen.

    Eigene Funktion, damit der Test genau DIESE Kaskade aufrufen kann. Vorher
    baute er sie nach und prueft dann seinen eigenen Nachbau — er waere gruen
    geblieben, egal was hier steht."""
    def gleich(feld: str) -> bool:
        wert = (kopf.get(feld) or "").strip() if isinstance(kopf.get(feld), str) \
            else kopf.get(feld)
        return bool(wert) and str(wert).strip() == str(kopf["buyerreference"]).strip()

    if kopf.get("buyerreference"):
        # FOLIO_TEXT1 ist VARCHAR2(2000) und nimmt ganze Absaetze an. Was der
        # Empfang dort eintraegt, ist als Kaeuferreferenz gedacht, kann aber
        # ein Satz sein. Gekuerzt wird deshalb hier — und der Umstand wird
        # vermerkt, denn ein stillschweigend abgeschnittener Wert waere
        # schlimmer als ein zu langer: Er sieht aus wie eine gueltige Referenz.
        if gleich("buyer_reference1"):
            kopf["buyerreference"], gekuerzt = kuerzen(kopf["buyerreference"])
            kopf["buyerreference_quelle"] = "Buyer Reference aus der Reservierung"
            if gekuerzt:
                kopf["buyerreference_gekuerzt"] = gekuerzt
        elif kopf.get("leitweg_id_vorhanden"):
            kopf["buyerreference_quelle"] = "Leitweg-ID"
        elif gleich("reservierungsnummer"):
            # Unsere Nummer, nicht seine — deshalb ausdruecklich als Ersatzwert.
            kopf["buyerreference_quelle"] = "Ersatzwert: Reservierungsnummer"
        elif gleich("externe_referenz"):
            kopf["buyerreference_quelle"] = "externe Referenz der Reservierung"
        elif gleich("kundenreferenz"):
            kopf["buyerreference_quelle"] = "Kundenreferenz aus der Buchung"
        else:
            kopf["buyerreference_quelle"] = "am Profil hinterlegte Referenz"
    else:
        # Eine Vorlage gewinnt gegen die feste Auswahl: BT-10 ist FREITEXT, nicht
        # numerisch. Die Norm verlangt nur, dass das Feld gefuellt ist
        # (BR-DE-15); Ziffern schreibt sie nirgends vor. Damit kann jedes Haus
        # den Satz hinschreiben, an dem sein Kunde die Rechnung wiedererkennt.
        vorlage = (p.get("buyerreference_vorlage") or "").strip()
        wert = _vorlage_fuellen(vorlage, kopf, p, bill_no)
        if wert:
            kopf["buyerreference"], gekuerzt = kuerzen(wert)
            kopf["buyerreference_quelle"] = "Ersatzwert: Vorlage des Hauses"
            if gekuerzt:
                kopf["buyerreference_gekuerzt"] = gekuerzt
            return kopf
        ersatz = (p.get("buyerreference_ersatz") or "reservierungsnummer").lower()
        # ACCOUNT_NO ist die Debitorennummer der Buchhaltung, ACCOUNT_CODE nur
        # der interne Schluessel der Tabelle — der stand hier bisher.
        if ersatz == "debitorennummer" and kopf.get("debitorennummer"):
            kopf["buyerreference"] = f"Debitor {kopf['debitorennummer']}"
            kopf["buyerreference_quelle"] = "Ersatzwert: Debitorennummer"
        elif ersatz == "kundenname" and kopf.get("customername"):
            kopf["buyerreference"] = kopf["customername"]
            kopf["buyerreference_quelle"] = "Ersatzwert: Kundenname"
        elif ersatz == "reservierungsnummer" and kopf.get("reservierungsnummer"):
            kopf["buyerreference"] = str(kopf["reservierungsnummer"])
            kopf["buyerreference_quelle"] = "Ersatzwert: Reservierungsnummer"
        else:
            kopf["buyerreference"] = str(bill_no)
            kopf["buyerreference_quelle"] = "Ersatzwert: Rechnungsnummer"
    return kopf


def hauskontakt(kopf: dict, p: dict) -> dict:
    """Telefon und E-Mail des Hauses (BT-42, BT-43; die E-Mail auch als
    elektronische Adresse des Verkaeufers, BT-34).

    Die KONFIGURATION geht vor, OPERA ist der Rueckfall. Entscheidung des
    Hauses vom 14.09.2026. In OPERA steht am Resort die allgemeine Nummer und
    Adresse der Rezeption; Rueckfragen zu einer Rechnung gehoeren an die
    Buchhaltung, und genau die traegt die Konfiguration. Vorher war es
    umgekehrt: Ein gepflegter Eintrag in der Konfiguration wirkte nur, solange
    OPERA leer war — also praktisch nie."""
    telefon = str(p.get("kontakt_telefon") or "").strip()
    email = str(p.get("kontakt_email") or "").strip()
    kopf["suppliercontacttelephone"] = telefon or kopf.get("suppliercontacttelephone") or None
    kopf["suppliercontactelectronicmail"] = email or kopf.get("suppliercontactelectronicmail") or None
    return kopf


def rechnung(cfg: dict, bill_no: int) -> dict:
    """Laedt Kopf, Positionen, Steueraufteilung, Summen und Anzahlungsbelege
    und setzt daraus die Struktur zusammen, die der XML-Bau erwartet."""
    p = cfg["property"]
    # Ob eine echte Leitweg-ID vorliegt, wird vor dem Ersatzwert festgehalten.
    kopf_rows = db.abfrage(_sql("invoice_header.sql", cfg), {
        "bill_no": bill_no,
        "leitweg_typ": p["mitgliedschaftstyp_leitweg"],
        "erechnung_typ": p.get("mitgliedschaftstyp_erechnung") or "-",
        # CUSTOM_REFERENCE traegt ueberwiegend Portal-Buchungsnummern, siehe
        # invoice_header.sql. Nur nach ausdruecklicher Freigabe.
        "kundenreferenz_nutzen": "J" if p.get("kundenreferenz_als_buyerreference") else "N",
        # :resort macht die Anzahlungs-Unterabfrage indizierbar, siehe dort.
        "resort": p["resort"],
    })
    if not kopf_rows:
        raise LookupError(f"Rechnung {bill_no} nicht gefunden")
    kopf = kopf_rows[0]

    je_beleg = {"bill_no": bill_no, "resort": p["resort"]}
    zeilen = db.abfrage(_sql("invoice_lines.sql", cfg), je_beleg)
    positionsbemerkung(zeilen, p)
    steuer = db.abfrage(_sql("invoice_tax.sql", cfg), je_beleg)
    # Die Buckets des Rechnungskopfs — die UNABHAENGIGE Gegenprobe zur
    # Steueraufteilung aus den Positionen (xml_build.pruefsummen).
    steuer_kopf = db.abfrage(_sql("invoice_tax_kopf.sql", cfg), je_beleg)
    summen_rows = db.abfrage(_sql("invoice_totals.sql", cfg), je_beleg)
    summen = summen_rows[0] if summen_rows else {}
    # :resort ist fuer den Index noetig, nicht nur fuer die Abgrenzung —
    # siehe invoice_deposits.sql.
    anzahlungen = db.abfrage(_sql("invoice_deposits.sql", cfg),
                             {"bill_no": bill_no, "resort": p["resort"],
                              "anzahlung_status": anzahlung_status(cfg)})

    # --- Konfigurationswerte ergaenzen, die OPERA nicht fuehrt ---------------
    kopf["suppliercompanyid"] = p["ust_id"]
    kopf["suppliercontactname"] = p["kontakt_name"]
    hauskontakt(kopf, p)
    kopf["payeefinancialaccountid"] = p["iban"]
    kopf["payeefinancialaccountbic"] = p["bic"]
    kopf["payeefinancialaccountname"] = p["kontoinhaber"]

    # Leitweg-ID aus dem benutzerdefinierten Feld der FIRMENkartei, sofern
    # eines eingerichtet ist. Ist der Name leer, faellt die Stufe weg und die
    # bisherige Kette gilt unveraendert — ein anderes Haus kann bei den
    # Mitgliedschaften bleiben.
    udf = (p.get("udf_leitweg") or "").strip()
    if udf and not kopf.get("leitweg_id_vorhanden"):
        # customer_name_id — so heisst die Profilnummer in invoice_header.sql.
        # Hier stand name_id, das es dort nicht gibt: Das Feld wurde nie
        # gelesen, und Behoerdenrechnungen gingen mit dem Ersatzwert hinaus.
        wert = udf_feld(kopf.get("customer_name_id"), udf)
        if wert:
            kopf["leitweg_udf"] = wert
            geprueft, grund = leitweg_pruefen(wert)
            if geprueft:
                kopf["buyerreference"] = wert
                kopf["leitweg_id_vorhanden"] = wert
            else:
                kopf["leitweg_udf_fehler"] = grund

    kaeuferreferenz(kopf, p, bill_no)
    # BT-83: Verwendungszweck fuer die Ueberweisung. Rechnungsnummer immer,
    # Debitorennummer dazu, wenn es eine gibt — damit die Buchhaltung des
    # Kunden die Zahlung zuordnen kann, ohne im Betreff zu suchen.
    teile = [f"Rechnung {bill_no}"]
    debitor = str(kopf.get("debitorennummer") or "").strip()
    if debitor:
        teile.append(f"Debitor {debitor}")
    kopf["verwendungszweck"] = ", ".join(teile)
    gastzeile(kopf, p)

    # Faelligkeit aus dem konfigurierten Zahlungsziel
    if not kopf.get("duedate") and kopf.get("issuedate"):
        from datetime import date, timedelta
        d = date.fromisoformat(str(kopf["issuedate"])[:10])
        kopf["duedate"] = (d + timedelta(days=int(p["zahlungsziel_tage"]))).isoformat()

    # --- Anzahlungen: BT-113 und BG-3 --------------------------------------
    # BT-113 ist alles, was bereits geflossen ist: Bar- und Kartenzahlungen auf
    # diesem Beleg sowie die Bruttosummen der DEPOSIT-Belege desselben Folios.
    # Die Kopf-SQL rechnet das zusammen.
    #
    # BT-115 wird daraus ABGELEITET und nicht getrennt bestimmt. Vorher kamen
    # die beiden Werte aus verschiedenen Quellen — prepaid aus der Kopf-SQL,
    # payable aus dem Rechnungsbrutto — und widersprachen sich, sobald eine
    # Anzahlung im Spiel war. BR-CO-16 verlangt genau diesen Zusammenhang:
    # Zahlbetrag = Gesamtbetrag mit USt minus Anzahlung.
    #
    # Der City-Ledger-Betrag zaehlt bewusst NICHT als gezahlt: Er ist die
    # Umbuchung auf das Debitorenkonto, die Rechnung steht dort offen.
    anz_brutto = sum(_zahl(a.get("total_gross")) for a in anzahlungen)

    # Summen fuer die Templates: bei Anzahlungen ist die Zeilensumme massgeblich,
    # der Kopfbetrag ist nur der Rest (siehe docs/06_BEFUNDE_LIVE_DB.md).
    zeilen_netto = sum(_zahl(z.get("lineextensionamountnet")) for z in zeilen)
    zeilen_brutto = sum(_zahl(z.get("lineextensionamount")) for z in zeilen)
    totals = {
        "invoicenet": zeilen_netto if anz_brutto else _zahl(summen.get("invoicenet")),
        "invoicegross": zeilen_brutto if anz_brutto else _zahl(summen.get("invoicegross")),
    }
    totals["invoicetaxtotal"] = round(totals["invoicegross"] - totals["invoicenet"], 2)
    totals["spay_cl"] = _zahl(summen.get("spay_cl"))

    # Erst jetzt, wenn der Gesamtbetrag feststeht: Zahlbetrag daraus ableiten.
    kopf["prepaidamount"] = round(_zahl(kopf.get("prepaidamount")), 2)
    kopf["payableamount"] = round(totals["invoicegross"] - kopf["prepaidamount"], 2)

    return {
        "bill_no": bill_no,
        "header": kopf,
        "lines": zeilen,
        "tax_breakdown": steuer,
        "tax_kopf": steuer_kopf,
        "totals": totals,
        "deposits": anzahlungen,
        # Unabhaengige Vergleichswerte fuer die Vorpruefung: der Rechnungskopf
        # plus die Anzahlungsbelege desselben Folios muss die Zeilensumme ergeben
        # (Folio-Klammer, siehe docs/06_BEFUNDE_LIVE_DB.md).
        "kontrolle": {
            "kopf_netto": _zahl(summen.get("invoicenet")),
            "kopf_brutto": _zahl(summen.get("invoicegross")),
            "anzahlung_netto": sum(_zahl(a.get("total_net")) for a in anzahlungen),
            "anzahlung_brutto": anz_brutto,
        },
    }
