"""Funktionstest ohne Datenbank: startet die Anwendung, meldet sich an und
ruft alle Seiten auf. Faengt Vorlagen- und Verdrahtungsfehler ab.

ERFUNDENE TESTDATEN
Alle Belege, Namen und Betraege hier sind erfunden. Das war einmal anders:
Drei Belege trugen echte Betraege aus einem Produktivbestand, und dieser Test
fiel rot aus, sobald jemand im Haus einen davon stornierte — ohne dass am Code
etwas falsch gewesen waere. Die Zahlenverhaeltnisse sind erhalten geblieben,
damit die Rundungspruefungen weiter greifen; die Herkunft ist es nicht.
"""

import json, os, pathlib, shutil, sys, tempfile
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

# Der Test arbeitet auf KOPIEN von Konfiguration und Bestandsdatenbank.
# Vorher lief er auf den echten Dateien und hinterliess dort seine Testwerte:
# Blindkopie ueberschrieben, Mailversand abgeschaltet, Rechnungen im Bestand.
# Beim naechsten Lauf fielen dann Pruefungen rot aus, obwohl am Code nichts
# fehlte — der Test hatte sich seine eigene Grundlage zerschossen.
# Das Umlenken muss VOR dem ersten Import von app.config geschehen.
_echt = pathlib.Path(__file__).resolve().parent.parent
_sandkasten = pathlib.Path(tempfile.mkdtemp(prefix="xrechnung-test-"))
shutil.copytree(_echt / "config", _sandkasten / "config")
(_sandkasten / "data").mkdir()
# Der Sandkasten enthaelt eine KOPIE von secret.key, users.json und app.json —
# also den Schluessel und die damit entschluesselbaren Zugangsdaten. Er lag
# nach jedem Lauf dauerhaft in /tmp, waehrend die Schlusszeile meldete, die
# echte Konfiguration sei unberuehrt geblieben. Das stimmte, sagte aber nicht
# alles.
import atexit as _atexit
_atexit.register(lambda: shutil.rmtree(_sandkasten, ignore_errors=True))
os.chmod(_sandkasten, 0o700)
os.environ["XRECHNUNG_BASIS"] = str(_sandkasten)
os.environ["XRECHNUNG_CONFIG_DIR"] = str(_sandkasten / "config")
os.environ["XRECHNUNG_DATEN_DIR"] = str(_sandkasten / "data")
os.environ["XRECHNUNG_LOG_DIR"] = str(_sandkasten / "logs")

try:
    from fastapi.testclient import TestClient
except RuntimeError as e:
    # httpx steht bewusst nicht in requirements.txt — es braucht nur der Test.
    # Auf einer Anlage, die genau danach eingerichtet wurde, brach der Test
    # hier mit einer Meldung ab, die nicht sagt, was zu tun ist.
    print("Der Selbsttest braucht httpx, die Anwendung selbst nicht.\n"
          f"  Meldung: {e}\n"
          "  Auf einem Entwicklungsrechner:  pip install -r requirements-dev.txt\n"
          "  Auf einer Produktivanlage NICHT ins venv installieren, sondern daneben:\n"
          "      pip install --target /tmp/testwerkzeug httpx\n"
          "      PYTHONPATH=/tmp/testwerkzeug python tools/smoketest.py")
    sys.exit(2)
from app import auth, config, opera, store, xml_build

BASE = pathlib.Path(__file__).resolve().parent.parent
fehler = []

def pruefe(bedingung, text):
    print(("  ok   " if bedingung else "  FEHL ") + text)
    if not bedingung:
        fehler.append(text)

print("Testdaten sind erfunden — keine Datenbank noetig.\n")
from app import updater, validate
import os as _os, stat as _stat
print("1) Konfiguration")
cfg = config.laden()
pruefe(isinstance(cfg.get("property", {}).get("resort"), str) and cfg["property"]["resort"],
       f"app.json geladen (Resort {cfg.get('property', {}).get('resort')})")
oeff = config.oeffentlich(cfg)
pruefe(oeff["mail"]["passwort"] in ("", "gesetzt"), "Passwoerter erscheinen nie im Klartext")

# Der Schluessel entschluesselt die Zugangsdaten zu OPERA und zum Mailserver,
# die Benutzerdatei traegt die Passwort-Hashes. Beide lagen mit der
# Standardmaske auf der Platte — weltweit lesbar, geschuetzt nur durch ein
# 'chmod 700' auf den Ordner, das genau ein Zweig genau eines
# Installationsskripts setzt.
if hasattr(_os, "geteuid"):
    config._key()          # legt an oder zieht die Rechte nach
    auth.benutzer_laden()
    for _datei in (config.KEY_FILE, auth.USER_DATEI):
        _rechte = _stat.S_IMODE(_datei.stat().st_mode)
        pruefe(_rechte & 0o077 == 0,
               f"{_datei.name} ist nur fuer den Eigentuemer lesbar ({oct(_rechte)})")
    # Auch eine von Hand danebengelegte Sicherung. Sie traegt denselben Inhalt
    # wie app.json — die naechste koennte Zugangsdaten enthalten.
    _sicherung = config.CONFIG_DIR / "app.json.vor_irgendwas"
    _sicherung.write_text("{}", encoding="utf-8")
    _os.chmod(_sicherung, 0o644)
    _angefasst = config.ordner_absichern()
    pruefe(_sicherung.name in _angefasst,
           f"eine offene Handsicherung wird zugezogen ({_angefasst})")
    pruefe(_stat.S_IMODE(_sicherung.stat().st_mode) & 0o077 == 0,
           "und liegt danach nur noch fuer den Eigentuemer offen")
    pruefe("app.example.json" not in config.ordner_absichern(),
           "die Vorlage bleibt ausgenommen — sie enthaelt keine Geheimnisse")
    _sicherung.unlink()

# Die folgenden Vorgaben gehoeren zum PROGRAMM, nicht zur Anlage. Sie deshalb
# gegen die Vorlage pruefen: Wer sie gegen die geladene Konfiguration prueft,
# meldet einem zweiten Haus mit anderem Kuerzel einen Fehler im Code — und
# uebersieht umgekehrt, dass die Vorlage falsche Vorgaben traegt.
_vorlage = json.loads((BASE / "config" / "app.example.json").read_text(encoding="utf-8"))
pruefe("keine zusaetzliche Rechnung" in _vorlage["mail"]["text"],
       "Vorlage: Mailtext stellt klar: dieselbe Rechnung, keine zweite Forderung")
import re as _re0
pruefe("{bill_no}" in _vorlage["mail"]["betreff"], "Vorlage: Betreff traegt die Rechnungsnummer")
# Geprueft wird die FORM, nicht der Name. Vorher stand hier der Name des
# Repositorys fest — und damit fiel dieser Test bei jedem Abzweig rot aus,
# ohne dass etwas falsch gewesen waere. Wer die Anwendung forkt, traegt sein
# eigenes Repository ein; genau dafuer ist die Einstellung da.
pruefe(_re0.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", _vorlage["update"]["repo"] or ""),
       f"Vorlage: Update-Vorgabe ist ein Repository in der Form Konto/Name "
       f"({_vorlage['update']['repo']})")
pruefe(_vorlage["update"]["zweig"] == "main",
       "Vorlage: Update-Vorgabe zeigt auf den Standardzweig main")
# Und in der geladenen Konfiguration nur das, was jede Anlage braucht.
for _feld in ("repo", "zweig"):
    pruefe(bool((cfg.get("update") or {}).get(_feld)),
           f"die Anlage hat update.{_feld} gesetzt ({(cfg.get('update') or {}).get(_feld)})")

print("1b) Aktualisierung darf die Konfiguration nicht ueberschreiben")
import json as _json
# Alle Dateipfade hier zeigen in den Sandkasten (config.CONFIG_DIR), nicht in
# den Betriebsordner. Dieser Block schreibt eine Wegwerf-Konfiguration und
# LOESCHT sie danach — auf der echten Datei war das ein Datenverlust.
eigene = config.CONFIG_DIR / "app.json"
# Eine Konfiguration wie nach einem Update: eigene Werte, aber alte Struktur
alt = {
    "server": {"port": 9999},                       # eigener Wert, weicht ab
    "property": {"resort": "MEINHAUS", "ust_id": "DE999999999"},
    "mail": {"bcc": "chef@meinhaus.de", "aktiv": False},
}
eigene.write_text(_json.dumps(alt, indent=2), encoding="utf-8")
frisch = config.laden()
pruefe(frisch["server"]["port"] == 9999, "eigener Port bleibt erhalten")
pruefe(frisch["property"]["resort"] == "MEINHAUS", "eigenes Resort bleibt erhalten")
pruefe(frisch["property"]["ust_id"] == "DE999999999", "eigene USt-IdNr. bleibt erhalten")
pruefe(frisch["mail"]["bcc"] == "chef@meinhaus.de", "eigener BCC bleibt erhalten")
pruefe(frisch["mail"]["aktiv"] is False, "eigener Schalter bleibt aus (nicht durch Vorgabe ueberschrieben)")
pruefe("auswahl" in frisch and "firmenprofile" in frisch["auswahl"],
       "neue Einstellungen kommen aus der Vorlage dazu")
pruefe("validierung" in frisch and "update" in frisch,
       "auch ganze neue Abschnitte werden ergaenzt")
pruefe(frisch["automatik"]["testlauf"] is True, "Vorgabe fuer Unbekanntes greift")
# Zweiter Lauf darf nichts mehr veraendern
zweiter = config.laden()
pruefe(zweiter["server"]["port"] == 9999 and zweiter["property"]["resort"] == "MEINHAUS",
       "wiederholtes Laden bleibt stabil")
kopie = config.sichern()
pruefe(kopie is not None and kopie.exists(), "Konfiguration laesst sich sichern")
kopie.unlink()
eigene.unlink()

print("1c) Nicht schreibbare Konfiguration darf nicht stumm scheitern")
import os as _os, stat as _stat
# root ignoriert 0555 auf einem Verzeichnis und schreibt trotzdem. Der Block
# pruefte damit nicht die Anwendung, sondern die Identitaet des Aufrufers —
# und haette einen echten Fehler in config.schreibbar() gar nicht finden
# koennen. Ein uebersprungener Test, der es sagt, ist ehrlicher als ein roter.
_als_root = hasattr(_os, "geteuid") and _os.geteuid() == 0
if _als_root:
    print("  ---  uebersprungen: als root ausgefuehrt, Dateirechte greifen nicht")
if not _als_root:
    eigene = config.CONFIG_DIR / "app.json"
    eigene.write_text(_json.dumps({"mail": {"bcc": "vorher@beispiel.de"}}, indent=2), encoding="utf-8")
    config.laden()
    moeglich, _ = config.schreibbar()
    pruefe(moeglich, "beschreibbare Konfiguration wird als solche erkannt")
    # Eine schreibgeschuetzte Datei allein blockiert NICHT: Geschrieben wird ueber
    # eine temporaere Datei mit anschliessendem Umbenennen, und das haengt an den
    # Rechten des Verzeichnisses.
    _os.chmod(eigene, 0o444)
    try:
        cfg_test = config.laden()
        cfg_test["mail"]["bcc"] = "trotzdem@beispiel.de"
        config.speichern(cfg_test)
        pruefe(config.laden()["mail"]["bcc"] == "trotzdem@beispiel.de",
               "schreibgeschuetzte Datei in beschreibbarem Ordner laesst sich ersetzen")
    except config.KonfigFehler:
        pruefe(False, "schreibgeschuetzte Datei in beschreibbarem Ordner laesst sich ersetzen")
    finally:
        if eigene.exists():
            _os.chmod(eigene, 0o644)

    # Der Fall, der wirklich blockiert: das VERZEICHNIS ist nicht beschreibbar
    _os.chmod(config.CONFIG_DIR, 0o555)
    try:
        moeglich, grund = config.schreibbar()
        pruefe(not moeglich, "nicht beschreibbares Verzeichnis wird erkannt")
        pruefe("chown" in grund, f"die Meldung nennt den Weg zur Loesung: {grund[:55]}...")
        try:
            cfg_test = config.laden()
            cfg_test["mail"]["bcc"] = "geht-nicht@beispiel.de"
            config.speichern(cfg_test)
            pruefe(False, "Speichern wirft dann KonfigFehler statt HTTP 500")
        except config.KonfigFehler as e:
            pruefe("chown" in str(e), "Speichern wirft KonfigFehler mit Loesungshinweis")
        pruefe(config.laden()["mail"]["bcc"] == "trotzdem@beispiel.de",
               "Laden funktioniert weiter, auch wenn nicht geschrieben werden kann")
    finally:
        _os.chmod(config.CONFIG_DIR, 0o755)
        eigene.unlink(missing_ok=True)

print("1c2) Programm oder Bestand — wogegen loesen Pfade auf?")
# Der Unterschied entscheidet ueber aufbewahrungspflichtige Belege. In der
# Konfiguration steht "data/xml". Loeste das gegen das PROGRAMM auf, laegen die
# erzeugten Rechnungen in der Freigabe — und das Aufraeumen alter Freigaben
# loeschte sie nach der dritten Aktualisierung. Still, ohne Fehlermeldung.
from app import ablauf, pfade, validate as _val
pruefe(pfade.BASIS == _sandkasten,
       f"die Installation liegt, wo XRECHNUNG_BASIS sagt ({pfade.BASIS})")
pruefe(pfade.PROGRAMM == BASE,
       "das Programm bleibt, wo der Code liegt — Handbuch und SQL gehoeren dorthin")
pruefe(pfade.BASIS != pfade.PROGRAMM,
       "und beide sind im Test wirklich verschieden, sonst prueft das hier nichts")

_cfg_pfade = json.loads(json.dumps(cfg))
_cfg_pfade["ablage"] = {"xml_ordner": "data/xml", "archiv_ordner": "data/archiv"}
for _schluessel in ("xml_ordner", "archiv_ordner"):
    _ziel = ablauf._ordner(_cfg_pfade, _schluessel)
    pruefe(_sandkasten in _ziel.parents or _ziel.parent == _sandkasten / "data",
           f"{_schluessel} liegt im Bestand, nicht im Programm ({_ziel})")
    pruefe(pfade.PROGRAMM not in _ziel.parents,
           f"{_schluessel} liegt NICHT unter dem Programmverzeichnis")
_cfg_pfade["validierung"] = dict(cfg["validierung"],
                                 kosit_jar="validation/validationtool.jar")
_z = _val.zustand(_cfg_pfade)
pruefe(str(_sandkasten) in _z["jar"],
       f"auch der Validator wird gegen den Bestand aufgeloest ({_z['jar']})")
pruefe(str(pfade.im_bestand("/tmp/absolut")) == "/tmp/absolut",
       "ein absoluter Pfad bleibt absolut")
# Und die Logs: sie gehoeren zum Betrieb, nicht zum Programm.
pruefe(pfade.LOG_DIR == _sandkasten / "logs", "die Logs liegen im Bestand")

print("1d) Alle Abfragen gegen das Data Dictionary")
import subprocess as _sp
lauf = _sp.run([sys.executable, str(BASE / "tools" / "sql_pruefen.py")],
               capture_output=True, text=True, cwd=str(BASE))
pruefe(lauf.returncode == 0,
       "sql/opera/*.sql verwenden nur Spalten, die es wirklich gibt")
# Zwei Formen, die keine Spaltenfehler sind, aber jede Abfrage von
# Millisekunden auf Sekunden ziehen — beide sind hier vorgekommen. Geprueft
# wird, dass die Regel sie FINDET; eine Regel, von der man nicht gesehen hat,
# dass sie anschlagen kann, ist eine Behauptung.
sys.path.insert(0, str(BASE / "tools"))
from sql_pruefen import pruefe_folio_zugriff as _folio
pruefe(len(_folio("FROM opera.folio$_tax d WHERE d.folio_no = 4711")) == 1,
       "die Regel findet die direkte Suche ueber FOLIO_NO")
pruefe(len(_folio("FROM opera.folios fo WHERE fo.folio_no = f.folio_no")) == 1,
       "die Regel findet die korrelierte Folionummer")
pruefe(all(not _folio(q.read_text(encoding="utf-8"))
           for q in (BASE / "sql" / "opera").glob("*.sql")),
       "und keine der heutigen Abfragen faellt darunter")
if lauf.returncode != 0:
    for zeile in lauf.stdout.splitlines():
        if "FEHLER" in zeile:
            print("        ", zeile.strip())

print("1d2) Die Obergrenze darf nicht vor dem Firmenfilter greifen")
sql_liste = (BASE / "sql" / "opera" / "invoice_list.sql").read_text(encoding="utf-8")
pos_filter = sql_liste.find(":nur_firmen")
pos_grenze = sql_liste.find("FETCH FIRST")
pruefe(pos_filter != -1, "der Firmenfilter steht in der Abfrage")
pruefe(pos_filter < pos_grenze,
       "der Firmenfilter steht VOR der Obergrenze — sonst schneidet sie ungefiltert ab")
pruefe(sql_liste.count("SELECT * FROM (") == 1,
       "die Abfrage filtert in einer aeusseren Huelle")
vorlage = _json.loads((config.CONFIG_DIR / "app.example.json").read_text(encoding="utf-8"))
pruefe(vorlage["auswahl"]["hoechstens"] >= 2000,
       f"die Obergrenze deckt mehr als ein paar Tage ab ({vorlage['auswahl']['hoechstens']})")

print("1e) Schema-Wanderung: alte Arbeitsliste bekommt neue Spalten")
import sqlite3 as _sq
_alt_db = store.DB_FILE
# Im Sandkasten, nicht unter BASE/data: Dort blieben -shm und -wal der
# Wegwerf-Datenbank im echten Datenordner der Anlage liegen.
store.DB_FILE = store.DATEN_DIR / "wanderung_test.sqlite"
store.DB_FILE.unlink(missing_ok=True)
_c = _sq.connect(store.DB_FILE)
_c.executescript("""CREATE TABLE rechnungen (bill_no INTEGER PRIMARY KEY, resort TEXT,
     status TEXT, kunde TEXT, zuerst_gesehen TEXT);
   INSERT INTO rechnungen VALUES (4711,'IHRHAUS','neu','Alte GmbH','2026-09-01');""")
_c.commit(); _c.close()
try:
    store.init()
    _c = _sq.connect(store.DB_FILE)
    spalten = {z[1] for z in _c.execute("PRAGMA table_info(rechnungen)")}
    daten = _c.execute("SELECT kunde, status FROM rechnungen").fetchall()
    _c.close()
    pruefe("city_ledger" in spalten, "fehlende Spalte wird beim Start ergaenzt")
    pruefe("firmenbezug" in spalten and "empfaenger" in spalten,
           "auch aeltere Erweiterungen werden nachgezogen")
    pruefe(daten == [("Alte GmbH", "neu")], "vorhandene Daten bleiben erhalten")
    store.init()   # zweiter Lauf muss folgenlos bleiben
    pruefe(True, "wiederholter Start ergaenzt nichts mehr")
finally:
    for _endung in ("", "-shm", "-wal"):
        pathlib.Path(str(store.DB_FILE) + _endung).unlink(missing_ok=True)
    store.DB_FILE = _alt_db
pruefe(str(_alt_db).startswith(str(_sandkasten)),
       "die Arbeitsliste des Tests liegt im Sandkasten, nicht im Datenordner der Anlage")

print("2) Anmeldung")
store.init()
auth.anlegen("pruefer", "Geheim!123", "verwalten")
pruefe(auth.anmelden("pruefer", "falsch", "127.0.0.1") is None, "falsches Passwort wird abgelehnt")
token = auth.anmelden("pruefer", "Geheim!123", "127.0.0.1")
pruefe(bool(token), "richtiges Passwort meldet an")
pruefe(auth.netz_erlaubt("10.0.5.7", ["10.0.0.0/8"]), "Netzfilter laesst Hausnetz durch")
pruefe(not auth.netz_erlaubt("8.8.8.8", ["10.0.0.0/8"]), "Netzfilter sperrt fremdes Netz")

print("3) XML-Bau mit Beispieldaten (Beleg 1400003 aus der Live-Pruefung)")
rechnung = {
    "bill_no": 1400003,
    "header": {
        "id": 1400003, "issuedate": "2026-07-13", "duedate": "2026-07-27",
        "invoicetypecode": "380", "documentcurrencycode": "EUR",
        "buyerreference": "991-33333TEST-33",
        "startdate": "2026-07-08", "enddate": "2026-07-13",
        "suppliername": "Musterhotel", "supplierregistrationname": "Musterhotel GmbH",
        "supplierstreetname": "Musterstrasse 1", "suppliercityname": "Berlin",
        "supplierpostalzone": "10787", "supplieridentificationcode": "DE",
        "suppliercompanyid": "DE123456789", "suppliercontactname": "Buchhaltung",
        "suppliercontacttelephone": "+49 30 000000", "suppliercontactelectronicmail": "buchhaltung@example.com",
        "customername": "Beispiel GmbH", "customerregistrationname": "Beispiel GmbH",
        "customerstreetname": "Musterweg 1", "customercityname": "Berlin",
        "customerpostalzone": "10115", "customeridentificationcode": "DE",
        "customerendpointid": "rechnung@beispiel.de",
        "payeefinancialaccountid": "DE02120300000000202051", "payeefinancialaccountbic": "BYLADEM1001",
        "payeefinancialaccountname": "Musterhotel GmbH",
        "prepaidamount": 0.0, "payableamount": 3688.57,
    },
    "lines": [
        {"itemname": "Accommodation 7%", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 2748.18, "lineextensionamount": 2940.55,
         "priceamount": 2748.18, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7},
        {"itemname": "Breakfast 7%", "itemcode": "2000", "invoicedquantity": 1,
         "lineextensionamountnet": 139.72, "lineextensionamount": 149.50,
         "priceamount": 139.72, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7},
        {"itemname": "City Tax 7%", "itemcode": "7600", "invoicedquantity": 1,
         "lineextensionamountnet": 206.14, "lineextensionamount": 220.57,
         "priceamount": 206.14, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7},
        {"itemname": "Breakfast beverages 19%", "itemcode": "2004", "invoicedquantity": 1,
         "lineextensionamountnet": 12.56, "lineextensionamount": 14.95,
         "priceamount": 12.56, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19},
        {"itemname": "Parking 19%", "itemcode": "5200", "invoicedquantity": 1,
         "lineextensionamountnet": 100.84, "lineextensionamount": 120.00,
         "priceamount": 100.84, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19},
        {"itemname": "Late Cancellation fee 0%", "itemcode": "5410", "invoicedquantity": 1,
         "lineextensionamountnet": 243.00, "lineextensionamount": 243.00,
         "priceamount": 243.00, "classifiedtaxcategoryid": "Z", "classifiedtaxcategorypercent": 0},
    ],
    "tax_breakdown": [
        {"taxcategorypercent": 7, "taxcategoryid": "S", "taxableamount": 3094.04, "taxamount": 216.58},
        {"taxcategorypercent": 19, "taxcategoryid": "S", "taxableamount": 113.40, "taxamount": 21.55},
        {"taxcategorypercent": 0, "taxcategoryid": "Z", "taxableamount": 243.00, "taxamount": 0.00},
    ],
    "totals": {"invoicenet": 3450.44, "invoicegross": 3688.57, "invoicetaxtotal": 238.13, "spay_cl": 3688.57},
    "deposits": [],
    "kontrolle": {"kopf_netto": 3450.44, "kopf_brutto": 3688.57,
                  "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0},
}
hinweise = xml_build.pruefsummen(rechnung)
pruefe(not hinweise, f"Vorpruefung sauber ({hinweise})")
xml = xml_build.bauen(rechnung)
text = xml.decode()
for muss in ("<cbc:BuyerReference>991-33333TEST-33", "<cbc:CustomizationID>",
             "3450.44", "3688.57", "<cbc:Percent>19.00", "<cbc:ID>Z</cbc:ID>"):
    pruefe(muss in text, f"XML enthaelt {muss[:40]}")
(BASE / "data").mkdir(exist_ok=True)
(BASE / "data" / "beispiel.xml").write_bytes(xml)
# Die versionierte Beispieldatei ist der erste Pruefling fuer den
# KoSIT-Validator. Sie muss zum aktuellen Erzeuger passen, sonst prueft
# jemand eine veraltete Datei.
beispiel = BASE / "beispiele" / "rechnung_beispiel.xml"
pruefe(beispiel.exists(), "beispiele/rechnung_beispiel.xml ist im Repository")
if beispiel.exists():
    pruefe(beispiel.read_bytes() == xml,
           "die Beispieldatei entspricht dem aktuellen Stand (sonst neu erzeugen)")
    inhalt = beispiel.read_text(encoding="utf-8")
    # Die Beispieldatei liegt IM Repository. Sie darf nichts aus der echten
    # Konfiguration tragen — kein Hausname, keine USt-IdNr., keine Bankdaten.
    #
    # Frueher standen hier vier feste Suchwoerter: die echte BIC, der Anfang
    # der echten IBAN und der Name des Rechtstraegers. Die Pruefung, die das
    # Durchsickern verhindern sollte, schrieb die Werte damit selbst ins
    # Repository — und sie fing nur genau dieses eine Haus.
    #
    # Jetzt kommen die Suchwoerter aus config/app.json, die nicht versioniert
    # ist. Damit prueft sie bei JEDEM Haus die dortigen Werte. Fehlt die
    # Datei (frischer Klon), bleibt die Pruefung ohne Befund — dann gibt es
    # auch keine echten Werte, die durchsickern koennten.
    _echte = BASE / "config" / "app.json"
    _verraeter = []
    if _echte.exists():
        _e = json.loads(_echte.read_text(encoding="utf-8"))
        _p, _m = _e.get("property") or {}, _e.get("mail") or {}
        _verraeter = [str(w).strip() for w in (
            _p.get("haus"), _p.get("ust_id"), _p.get("iban"), _p.get("bic"),
            _p.get("kontakt_email"), _p.get("kontakt_telefon"), _p.get("resort"),
            _m.get("absender"), _m.get("bcc"),
        ) if str(w or "").strip() and len(str(w).strip()) >= 4]
    _drin = [w for w in _verraeter if w in inhalt]
    pruefe(not _drin,
           f"die Beispieldatei enthaelt keine Werte aus der echten Konfiguration ({_drin})")

print("4) Anzahlungsfall: Rechnungsbezug BG-3 und Anzahlungsbetrag BT-113")
mit_anz = json.loads(json.dumps(rechnung))
mit_anz["deposits"] = [{"billingreferenceid": 1400005, "billingreferenceissuedate": "2026-07-28",
                        "total_net": 500.0, "total_gross": 535.0}]
mit_anz["header"]["prepaidamount"] = 535.0
# BR-CO-16: Zahlbetrag = Brutto minus Anzahlung. Die neue Regel deckt auf,
# wenn eine dieser drei Zahlen nicht zu den anderen passt.
mit_anz["header"]["payableamount"] = 3688.57 - 535.00
mit_anz["kontrolle"]["kopf_netto"] = 2950.44
mit_anz["kontrolle"]["anzahlung_netto"] = 500.0
xml2 = xml_build.bauen(mit_anz).decode()
pruefe("<cac:BillingReference>" in xml2 and "1400005" in xml2, "BG-3 Rechnungsbezug erzeugt")
pruefe("<cbc:PrepaidAmount" in xml2 and "535.00" in xml2, "BT-113 Anzahlungsbetrag erzeugt")
pruefe(not xml_build.pruefsummen(mit_anz), "Folio-Klammer geht auf")

print("3b) Kaeuferreferenz BT-10 ohne Leitweg-ID")
# BR-DE-15 macht BT-10 zur Pflicht, aber nur Behoerden haben eine Leitweg-ID.
# Ohne Ersatzwert waere jede Rechnung an einen gewoehnlichen Firmenkunden
# unerzeugbar — das betraefe die gesamte Zielmenge.
ohne_ref = json.loads(json.dumps(rechnung))
ohne_ref["header"]["buyerreference"] = ""
pruefe(any("BR-DE-15" in h for h in xml_build.pruefsummen(ohne_ref)),
       "eine leere Kaeuferreferenz wird erkannt")
# Die Leitweg-ID kommt aus einem FREITEXTFELD der Firmenkartei. Daneben steht
# eines, in das heute "BLACKLIST" getippt wird — was dort landet, darf nicht
# ungeprueft als Behoerdenadresse hinausgehen.
for _wert, _gilt in (("991-33333TEST-33", True),
                     ("04011000-1234512345-06", True),
                     ("991-12345-33", True),
                     ("BLACKLIST", False),
                     ("030 123456", False),
                     ("", False),
                     ("9" * 50, False)):
    _ja, _grund = opera.leitweg_pruefen(_wert)
    pruefe(_ja is _gilt,
           f"Leitweg-Pruefung: '{_wert[:22]}' -> {'gilt' if _ja else _grund}")

# Und der Spaltenname geht in den Abfragetext, nicht als Bindvariable. Was
# nicht auf der Liste steht, darf gar nicht erst zu einer Abfrage werden.
_echt_abf = opera.db.abfrage
_gestellte_sql = []
opera.db.abfrage = lambda sql, parameter=None: (_gestellte_sql.append(sql), [{"wert": "X"}])[1]
try:
    pruefe(opera.udf_feld(4711, "UDFC05") == "X", "ein erlaubtes Feld wird gelesen")
    pruefe("n.UDFC05" in _gestellte_sql[0], "und steht im Abfragetext")
    for _boese in ("UDFC41", "PASSWORT", "UDFC05; DROP TABLE name--", "1=1"):
        _gestellte_sql.clear()
        pruefe(opera.udf_feld(4711, _boese) == "" and not _gestellte_sql,
               f"'{_boese}' fuehrt zu gar keiner Abfrage")
finally:
    opera.db.abfrage = _echt_abf

# Geprueft wird opera.kaeuferreferenz() selbst. Vorher baute dieser Block die
# Kaskade nach und prueft dann seinen eigenen Nachbau — er waere gruen
# geblieben, egal was in opera.py steht.
for ersatz, erwartet in (("rechnungsnummer", "1400003"),
                         ("debitorennummer", "Debitor 4711"),
                         ("kundenname", "Beispiel GmbH"),
                         ("unbekannter_wert", "1400003"),
                         ("", "1400003")):
    # debitorennummer ist ACCOUNT_NO (die Nummer der Buchhaltung). Der Test
    # gab hier frueher account_code vor — und schrieb damit genau den Fehler
    # fest, dass der interne Tabellenschluessel als Debitorennummer hinausging.
    kopf = opera.kaeuferreferenz(
        {"buyerreference": None, "account_code": 99, "debitorennummer": "4711",
         "customername": "Beispiel GmbH"},
        {"buyerreference_ersatz": ersatz}, 1400003)
    pruefe(kopf["buyerreference"] == erwartet,
           f"Ersatzwert '{ersatz}' ergibt {erwartet} (ist {kopf['buyerreference']})")
    pruefe(kopf["buyerreference_quelle"].startswith("Ersatzwert"),
           f"Ersatzwert '{ersatz}' ist als solcher gekennzeichnet")
# Fehlt die Grundlage fuer den gewuenschten Ersatzwert, faellt er auf die
# Rechnungsnummer zurueck statt leer zu bleiben — BT-10 ist Pflicht.
for ersatz, fehlt in (("debitorennummer", "debitorennummer"), ("kundenname", "customername")):
    kopf = opera.kaeuferreferenz(
        {"buyerreference": None, "account_code": 99, "debitorennummer": "4711",
         "customername": "Beispiel GmbH", fehlt: None}, {"buyerreference_ersatz": ersatz}, 1400003)
    pruefe(kopf["buyerreference"] == "1400003",
           f"'{ersatz}' ohne {fehlt} faellt auf die Rechnungsnummer zurueck")
# Und die Herkunft echter Werte wird richtig benannt — daran haengt, ob die
# Oberflaeche einen Ersatzwert als solchen ausweist.
for kopf, erwartet in (
        ({"buyerreference": "991-33333TEST-33", "leitweg_id_vorhanden": 1}, "Leitweg-ID"),
        ({"buyerreference": "BST-4711", "kundenreferenz": "BST-4711"},
         "Kundenreferenz aus der Buchung"),
        ({"buyerreference": "PO-2026-88", "buyer_reference1": "PO-2026-88"},
         "Buyer Reference aus der Reservierung"),
        ({"buyerreference": "0815ABC", "reservierungsnummer": "0815ABC"},
         "Ersatzwert: Reservierungsnummer"),
        ({"buyerreference": "irgendwas"}, "am Profil hinterlegte Referenz")):
    pruefe(opera.kaeuferreferenz(kopf, {}, 1400003)["buyerreference_quelle"] == erwartet,
           f"Herkunft wird als '{erwartet}' benannt")

# Die vom Haus entschiedene Reihenfolge: Leitweg, dann Buyer Reference1, dann
# die Reservierungsnummer. Geprueft wird an der Stelle, an der sie WIRKT — in
# der Abfrage —, denn dort steht sie, nicht in Python.
_kopf_sql = (BASE / "sql" / "opera" / "invoice_header.sql").read_text(encoding="utf-8")
_kette = _kopf_sql[_kopf_sql.index("COALESCE("):_kopf_sql.index("AS buyerreference")]
_ohne_kommentar_kette = "\n".join(z.split("--")[0] for z in _kette.splitlines())
_stellen = [(_ohne_kommentar_kette.index(f), f) for f in (":leitweg_typ", "resv.folio_text1")]
pruefe(_stellen == sorted(_stellen), "BT-10: Leitweg-ID vor Buyer Reference1")
# Die Reservierungsnummer darf NICHT in der Kette der Abfrage stehen: Sie ist
# immer gefuellt, BT-10 war damit nie leer, und die Vorlage des Hauses griff
# nie. Sie ist der Rueckfall der Vorlage in app/opera.py.
pruefe("confirmation_no" not in _ohne_kommentar_kette,
       "die Reservierungsnummer steht nicht mehr in der Kette — sonst greift die Vorlage nie")
pruefe(_kette.index("resv.folio_text1") < _kette.index(":kundenreferenz_nutzen"),
       "und Buyer Reference1 vor der Kundenreferenz")

# BT-10 ist FREITEXT, nicht numerisch — die Norm verlangt nur, dass das Feld
# gefuellt ist. Das Haus kann deshalb einen Satz hinschreiben, an dem sein
# Kunde die Rechnung wiedererkennt.
_haus_p = {"haus": "Musterhotel Berlin",
           "buyerreference_vorlage": "{haus} ReservNr.: {reservierungsnummer}",
           "buyerreference_ersatz": "reservierungsnummer"}
_k = opera.kaeuferreferenz(
    {"buyerreference": None, "reservierungsnummer": "3000001"}, _haus_p, 1400019)
pruefe(_k["buyerreference"] == "Musterhotel Berlin ReservNr.: 3000001",
       f"die Vorlage des Hauses wird gefuellt ({_k['buyerreference']})")
pruefe(_k["buyerreference_quelle"].startswith("Ersatzwert"),
       "und bleibt als Ersatzwert gekennzeichnet")
# Fehlt der eingesetzte Wert, wird die Vorlage NICHT genommen: "ReservNr.:"
# ohne Nummer sieht aus wie ein Wert und ist keiner.
_k = opera.kaeuferreferenz(
    {"buyerreference": None, "reservierungsnummer": None}, _haus_p, 1400019)
pruefe(_k["buyerreference"] == "1400019",
       f"ohne Reservierungsnummer faellt sie auf den festen Ersatzwert zurueck "
       f"({_k['buyerreference']})")
# Eine Vorlage, die NUR den Hausnamen traegt, sagt dem Empfaenger nichts.
pruefe(opera._vorlage_fuellen("{haus}", {}, _haus_p, 1) == "",
       "eine Vorlage aus nur dem Hausnamen wird nicht verwendet")
pruefe(opera._vorlage_fuellen("{unsinn}", {}, _haus_p, 1) == "",
       "ein unbekannter Platzhalter fuehrt nicht zu einem halben Satz")
pruefe(json.loads((BASE / "config" / "app.example.json").read_text(
           encoding="utf-8"))["property"]["buyerreference_vorlage"]
       == "{haus} ReservNr.: {reservierungsnummer}",
       "die Vorlage steht so in der Konfigurationsvorlage")

# FOLIO_TEXT1 fasst 2000 Zeichen. Ein Satz darin ist als Kaeuferreferenz
# unbrauchbar — gekuerzt wird, aber nie stillschweigend.
_lang = "Bestellung des Kunden vom 3. September 2026, " * 5
_k = opera.kaeuferreferenz({"buyerreference": _lang, "buyer_reference1": _lang}, {}, 1)
pruefe(len(_k["buyerreference"]) <= opera.BT10_LAENGE,
       f"ein zu langer Eintrag wird gekuerzt ({len(_k['buyerreference'])} Zeichen)")
pruefe(_k.get("buyerreference_gekuerzt") == len(" ".join(_lang.split())),
       "und die urspruengliche Laenge wird festgehalten")
_mit = json.loads(json.dumps(rechnung))
_mit["header"]["buyerreference_gekuerzt"] = 230
pruefe(any("BT-10 war 230 Zeichen" in h for h in xml_build.pruefsummen(_mit)),
       "die Vorpruefung sagt es, statt es zu verschweigen")
_zeilen = opera.kaeuferreferenz(
    {"buyerreference": "PO 4711\nAbteilung Einkauf", "buyer_reference1": "PO 4711\nAbteilung Einkauf"},
    {}, 1)["buyerreference"]
pruefe("\n" not in _zeilen and _zeilen == "PO 4711 Abteilung Einkauf",
       f"Zeilenumbrueche werden zu Leerzeichen ({_zeilen!r})")

# CUSTOM_REFERENCE traegt ueberwiegend Portal-Buchungsnummern (242 von 320
# Werten sind reine 9- bis 10-stellige Ziffernfolgen). Sie darf deshalb nur
# nach ausdruecklicher Freigabe in BT-10 landen. Geprueft wird, was die
# Abfrage bekommt — der Schalter wirkt in der SQL, nicht in Python.
_gestellt = {}


def _abfrage_stub(sql, parameter=None):
    _gestellt[sql.splitlines()[0][:40]] = dict(parameter or {})
    return [{}]


_echt_abfrage = opera.db.abfrage
opera.db.abfrage = _abfrage_stub
try:
    for _wert, _erwartet in ((None, "N"), (False, "N"), (True, "J")):
        _gestellt.clear()
        _cfg = json.loads(json.dumps(cfg))
        if _wert is None:
            _cfg["property"].pop("kundenreferenz_als_buyerreference", None)
        else:
            _cfg["property"]["kundenreferenz_als_buyerreference"] = _wert
        try:
            opera.rechnung(_cfg, 1400003)
        except Exception:
            pass  # ohne echte Daten bricht es spaeter ab, der Parameter ist gestellt
        _param = next(iter(_gestellt.values()), {})
        pruefe(_param.get("kundenreferenz_nutzen") == _erwartet,
               f"Kundenreferenz-Schalter {_wert} ergibt '{_erwartet}' "
               f"(ist '{_param.get('kundenreferenz_nutzen')}')")
finally:
    opera.db.abfrage = _echt_abfrage
_kopf_sql = (BASE / "sql" / "opera" / "invoice_header.sql").read_text(encoding="utf-8")
pruefe("CASE WHEN :kundenreferenz_nutzen = 'J' THEN resv.custom_reference END" in _kopf_sql,
       "die Abfrage nimmt CUSTOM_REFERENCE nur bei Freigabe")
pruefe(_kopf_sql.index("resv.external_reference") < _kopf_sql.index("CASE WHEN :kundenreferenz_nutzen"),
       "EXTERNAL_REFERENCE steht in der Kette VOR der Kundenreferenz")
pruefe(json.loads((BASE / "config" / "app.example.json").read_text(
           encoding="utf-8"))["property"]["kundenreferenz_als_buyerreference"] is False,
       "die Vorlage laesst die Kundenreferenz ausgeschaltet")

# --- Wer war im Haus? BT-22 und BT-70 ---------------------------------------
# Eine Firmenrechnung nennt sonst nur den Zahler. Der Gast haengt an der
# RESERVIERUNG, der Zahler am Folio — bei genau diesen Rechnungen fallen die
# beiden auseinander (1400019: Gast Mustermann, Zahler Beispiel Industrie GmbH).
_gast_p = {"gastzeile": "Gast: {gast}, Zimmer {zimmer}, {anreise} bis {abreise}"}
_k = opera.gastzeile({"gastname": "Mustermann, Erika", "zimmer": "641",
                      "startdate": "2026-08-30", "enddate": "2026-09-09"}, _gast_p)
pruefe(_k["note"] == "Gast: Mustermann, Erika, Zimmer 641, 2026-08-30 bis 2026-09-09",
       f"die Gastzeile wird aus der Vorlage gebaut ({_k['note']})")
# Bei Gruppen haengt kein einzelner Gast an der Reservierung (1400017).
pruefe("note" not in opera.gastzeile({"gastname": None, "zimmer": "9033"}, _gast_p),
       "ohne Gast faellt die Zeile weg statt 'Gast: None' zu schreiben")
pruefe("note" not in opera.gastzeile({"gastname": "Mustermann, Erika"}, {"gastzeile": ""}),
       "und eine leere Vorlage schaltet sie ab")
_vorhanden = opera.gastzeile({"gastname": "Mustermann", "note": "Bereits bezahlt"}, _gast_p)
pruefe(_vorhanden["note"].startswith("Bereits bezahlt"),
       f"ein vorhandener Hinweis bleibt stehen — BT-22 gibt es nur einmal ({_vorhanden['note']})")

# Die beiden Fehler, die diese Zeile im Echtbetrieb mitgebracht hat, an der
# Stelle geprueft, an der sie entstehen — in der ABFRAGE.
_kopf_sql = (BASE / "sql" / "opera" / "invoice_header.sql").read_text(encoding="utf-8")
pruefe("NVL(resv.begin_date, f.bill_start_date)" in _kopf_sql
       and "NVL(resv.end_date,   f.business_date)" in _kopf_sql,
       "der Zeitraum kommt aus der Reservierung, nicht aus dem Folio")
pruefe("AS startdate" in _kopf_sql and "f.bill_start_date, 'YYYY-MM-DD')               AS folio_beginn"
       in _kopf_sql, "der Folio-Zeitraum bleibt daneben stehen, als Rueckfall und zur Probe")
# Ohne Kommentare vergleichen: Dort steht g.company als BEGRUENDUNG, warum es
# nicht verwendet wird — der Test haette den Kommentar mitgelesen.
_ohne_kommentar = "\n".join(z.split("--")[0] for z in _kopf_sql.splitlines())
_gast_teil = _ohne_kommentar[:_ohne_kommentar.index("AS gastname")][-400:]
pruefe("g.company" not in _gast_teil,
       f"der Gastname faellt NICHT auf die Firma zurueck — dort stehen Gruppenkuerzel")

# Sonderzeichen aus OPERA: Ein Gastname wie "Meyer & Soehne GmbH" kommt
# unveraendert aus der Datenbank. Ohne Maskierung ist die Rechnung nicht
# baubar — und zwar dauerhaft, weil der Name sich nicht aendert.
_zeichen = json.loads(json.dumps(rechnung))
_zeichen["header"].update(gastname="Meyer & Söhne GmbH <Hauptsitz>",
                          note="Gast: Meyer & Söhne GmbH",
                          customername="Meyer & Söhne GmbH",
                          customerendpointid="a&b@firma.de")
_z = xml_build.bauen(_zeichen).decode()
pruefe("&amp;" in _z and "Meyer & Söhne GmbH <Haupt" not in _z,
       "das kaufmaennische Und wird maskiert, nicht roh eingesetzt")
pruefe("&lt;Hauptsitz&gt;" in _z, "spitze Klammern ebenfalls")
pruefe("a&amp;b@firma.de" in _z, "auch in der elektronischen Adresse")
from lxml import etree as _et2
_et2.fromstring(_z.encode())   # wirft, wenn es nicht wohlgeformt ist
pruefe(True, "und das Dokument bleibt wohlgeformt")

# Fehlende Werte duerfen nicht als Zeichenkette "None" im Dokument stehen —
# das sieht nach einem Wert aus und ist keiner. Ein Laenderkennzeichen "None"
# ist kein ISO-Code, ein currencyID="None" keine Waehrung.
# XRechnung verbietet LEERE Elemente (KoSIT R008). Die Vorlage schrieb jedes
# Feld hin, auch ein optionales ohne Wert: Fehlte am Profil nur die Strasse,
# entstand <cbc:StreetName></cbc:StreetName> und die Rechnung wurde
# zurueckgewiesen — obwohl BT-50 optional ist und sie ohne das Element gueltig
# waere. Blockiert aus dem falschen Grund, und die Meldung nannte das Element
# nicht einmal.
_ohne_strasse = json.loads(json.dumps(rechnung))
_ohne_strasse["header"]["customerstreetname"] = None
_os_xml = xml_build.bauen(_ohne_strasse).decode()
import re as _re4
pruefe(_re4.findall(r"<([a-z]+:[A-Za-z]+)[^>]*></\1>", _os_xml) == [],
       f"kein leeres Element im Dokument "
       f"({_re4.findall(r'<([a-z]+:[A-Za-z]+)[^>]*></.1>', _os_xml)[:2]})")
pruefe("<cbc:CityName>" in _os_xml and "<cbc:PostalZone>" in _os_xml,
       "die vorhandenen Anschriftfelder bleiben stehen")
pruefe(xml_build.pruefsummen(_ohne_strasse) == [],
       f"und eine fehlende Strasse blockiert die Rechnung nicht "
       f"({xml_build.pruefsummen(_ohne_strasse)})")

_luecken = json.loads(json.dumps(rechnung))
_luecken["header"].update(customerstreetname=None, customerpostalzone=None,
                          customercityname=None, customeridentificationcode=None,
                          documentcurrencycode=None)
_l = xml_build.bauen(_luecken).decode()
pruefe(">None<" not in _l and 'currencyID="None"' not in _l,
       f"fehlende Werte bleiben leer, statt 'None' zu schreiben "
       f"({[z.strip() for z in _l.splitlines() if 'None' in z][:2]})")
_lh = xml_build.pruefsummen(_luecken)
for _feld in ("BT-5", "BT-52", "BT-55"):
    pruefe(any(_feld in h for h in _lh), f"und die Vorpruefung nennt {_feld}")
_falschesland = json.loads(json.dumps(rechnung))
_falschesland["header"]["customeridentificationcode"] = "Deutschland"
pruefe(any("BR-CL-14" in h for h in xml_build.pruefsummen(_falschesland)),
       "ein Land, das kein Zwei-Buchstaben-Code ist, faellt auf")

# Wuensche aus dem Haus: Bemerkung je Buchung (BT-127), Debitorennummer als
# unsere Kennung des Kunden (BT-46) und als Verwendungszweck (BT-83).
_referenzen = json.loads(json.dumps(rechnung))
_referenzen["header"].update(debitorennummer="4711",
                             verwendungszweck="Rechnung 1400003, Debitor 4711")
_referenzen["lines"][0]["bemerkung"] = "Check 88421, Tisch 12"
_r = xml_build.bauen(_referenzen).decode()
pruefe("<cbc:Note>Check 88421, Tisch 12</cbc:Note>" in _r,
       "BT-127: die Bemerkung steht an der Position")
pruefe(_r.index("<cbc:Note>Check 88421") > _r.index("<cac:InvoiceLine>"),
       "und zwar innerhalb der Position, nicht am Kopf")
_zeile = _r[_r.index("<cac:InvoiceLine>"):_r.index("</cac:InvoiceLine>")]
pruefe(_zeile.index("<cbc:Note>") < _zeile.index("<cbc:InvoicedQuantity"),
       "UBL-Reihenfolge: ID, Note, Menge")
pruefe("<cac:PartyIdentification>" in _r and "<cbc:ID>4711</cbc:ID>" in _r,
       "BT-46: die Debitorennummer steht am Kunden")
_kunde = _r[_r.index("AccountingCustomerParty"):_r.index("</cac:AccountingCustomerParty>")]
pruefe("<cac:PartyIdentification>" in _kunde,
       "und beim KUNDEN, nicht beim Lieferanten")
pruefe("<cbc:PaymentID>Rechnung 1400003, Debitor 4711</cbc:PaymentID>" in _r,
       "BT-83: Verwendungszweck mit Rechnungs- und Debitorennummer")
# Ohne Debitorenkonto bleibt beides weg bzw. nennt nur die Rechnung.
_ohne_ar = json.loads(json.dumps(rechnung))
_ohne_ar["header"].update(debitorennummer=None, verwendungszweck="Rechnung 1400003")
_oa = xml_build.bauen(_ohne_ar).decode()
pruefe("<cac:PartyIdentification>" not in _oa,
       "ohne Debitorenkonto entsteht keine leere Kennung")
pruefe("<cbc:PaymentID>Rechnung 1400003</cbc:PaymentID>" in _oa,
       "und der Verwendungszweck nennt dann nur die Rechnung")

_mit_gast = json.loads(json.dumps(rechnung))
_mit_gast["header"].update(gastname="Mustermann, Erika",
                           note="Gast: Mustermann, Erika, Zimmer 641")
_g = xml_build.bauen(_mit_gast).decode()
pruefe("<cbc:Note>Gast: Mustermann, Erika, Zimmer 641</cbc:Note>" in _g,
       "BT-22 steht im Dokument")
pruefe("<cbc:Name>Mustermann, Erika</cbc:Name>" in _g and "<cac:Delivery>" in _g,
       "BT-70 traegt den Namen strukturiert")
# UBL-Reihenfolge, an der die BillingReference schon einmal gescheitert ist:
pruefe(_g.index("<cbc:Note>") < _g.index("<cbc:DocumentCurrencyCode>"),
       "BT-22 steht vor DocumentCurrencyCode")
pruefe(_g.index("</cac:AccountingCustomerParty>") < _g.index("<cac:Delivery>")
       < _g.index("<cac:PaymentMeans>"),
       "Delivery steht nach AccountingCustomerParty und vor PaymentMeans")
_ohne = json.loads(json.dumps(rechnung))
_ohne["header"]["gastname"] = None
pruefe("<cac:Delivery>" not in xml_build.bauen(_ohne).decode(),
       "ohne Gast bleibt der Block ganz weg, statt leer zu erscheinen")

print("4b) Echte Gegenprobe: Beleg 1400017 mit zwei Anzahlungen (Zahlen aus der Live-DB)")
anz = {
    "bill_no": 1400017,
    "header": dict(rechnung["header"], id=1400017, issuedate="2026-09-08",
                   prepaidamount=29613.18, payableamount=2188.40),
    "lines": [
        {"itemname": "Leistungen 7 %", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 7850.47, "lineextensionamount": 8400.00,
         "priceamount": 7850.47, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7},
        {"itemname": "Leistungen 19 %", "itemcode": "5200", "invoicedquantity": 1,
         "lineextensionamountnet": 19665.19, "lineextensionamount": 23401.58,
         "priceamount": 19665.19, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19},
    ],
    "tax_breakdown": [
        {"taxcategorypercent": 7, "taxcategoryid": "S", "taxableamount": 7850.47, "taxamount": 549.53},
        {"taxcategorypercent": 19, "taxcategoryid": "S", "taxableamount": 19665.19, "taxamount": 3736.39},
    ],
    "totals": {"invoicenet": 27515.66, "invoicegross": 31801.58, "invoicetaxtotal": 4285.92},
    "deposits": [
        {"billingreferenceid": 1400006, "billingreferenceissuedate": "2026-08-03",
         "total_net": 13256.45, "total_gross": 15775.18},
        {"billingreferenceid": 1400012, "billingreferenceissuedate": "2026-08-25",
         "total_net": 12278.85, "total_gross": 13838.00},
    ],
    "kontrolle": {"kopf_netto": 1980.36, "kopf_brutto": 2188.40,
                  "anzahlung_netto": 25535.30, "anzahlung_brutto": 29613.18},
}
pruefe(not xml_build.pruefsummen(anz), f"Vorpruefung sauber ({xml_build.pruefsummen(anz)})")
x = xml_build.bauen(anz).decode()
pruefe("1400006" in x and "1400012" in x, "beide Anzahlungsbelege als BG-3 referenziert")
pruefe("<cbc:PrepaidAmount currencyID=\"EUR\">29613.18" in x, "BT-113 ist der BRUTTO-Betrag")
pruefe("<cbc:PayableAmount currencyID=\"EUR\">2188.40" in x,
       "BT-115 entspricht dem Kopfbetrag der Schlussrechnung")
# Der gefaehrliche Fehler: Netto statt Brutto als Anzahlung
falsch = json.loads(json.dumps(anz))
falsch["header"]["prepaidamount"] = 25535.30
pruefe(any("BT-113" in h or "BR-CO-16" in h for h in xml_build.pruefsummen(falsch)),
       "Netto statt Brutto bei BT-113 wird erkannt")

print("4c) Durchlaufende Posten: Beleg 1400002 (Zahlen aus der Live-DB)")
paid = {
    "bill_no": 1400002,
    "header": dict(rechnung["header"], id=1400002, prepaidamount=0.0, payableamount=1217.42),
    "lines": [
        {"itemname": "Paid out", "itemcode": "8000", "invoicedquantity": 1,
         "lineextensionamountnet": 114.00, "lineextensionamount": 114.00,
         "priceamount": 114.00, "classifiedtaxcategoryid": "Z", "classifiedtaxcategorypercent": 0},
        {"itemname": "Leistungen 7 %", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 86.38, "lineextensionamount": 92.43,
         "priceamount": 86.38, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7},
        {"itemname": "Leistungen 19 %", "itemcode": "5200", "invoicedquantity": 1,
         "lineextensionamountnet": 849.57, "lineextensionamount": 1010.99,
         "priceamount": 849.57, "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19},
    ],
    "tax_breakdown": [
        {"taxcategorypercent": 0, "taxcategoryid": "Z", "taxableamount": 114.00, "taxamount": 0.00},
        {"taxcategorypercent": 7, "taxcategoryid": "S", "taxableamount": 86.38, "taxamount": 6.05},
        {"taxcategorypercent": 19, "taxcategoryid": "S", "taxableamount": 849.57, "taxamount": 161.42},
    ],
    "totals": {"invoicenet": 1049.95, "invoicegross": 1217.42, "invoicetaxtotal": 167.47},
    "deposits": [],
    "kontrolle": {"kopf_netto": 1049.95, "kopf_brutto": 1217.42,
                  "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0},
}
pruefe(not xml_build.pruefsummen(paid), f"Vorpruefung sauber ({xml_build.pruefsummen(paid)})")
y = xml_build.bauen(paid).decode()
pruefe(y.count("<cbc:ID>Z</cbc:ID>") >= 2, "durchlaufende Posten als Kategorie Z, 0 %")

print("5) Fehlerfall wird erkannt")
kaputt = json.loads(json.dumps(rechnung))
kaputt["lines"][0]["lineextensionamountnet"] = 9999.99
# Seit die Normalisierung die Summen selbst bildet, ist das Dokument mit einer
# falschen Position IN SICH stimmig — BR-CO-10 kann das nicht mehr melden.
# Auffallen muss es am Vergleich mit OPERA, und genau darauf wird geprueft.
_gemeldet = xml_build.pruefsummen(kaputt)
pruefe(any("Steuergruppe" in h for h in _gemeldet),
       f"falsche Positionssumme faellt gegen die OPERA-Zahlen auf ({_gemeldet})")
pruefe(any("Folio-Klammer" in h for h in _gemeldet),
       "und die Folio-Klammer meldet sie ebenfalls")
null = json.loads(json.dumps(rechnung))
null["totals"] = {"invoicenet": 0.0, "invoicegross": 0.0, "invoicetaxtotal": 0.0}
null["lines"] = []
null["tax_breakdown"] = []
null["kontrolle"] = {"kopf_netto": 0.0, "kopf_brutto": 0.0,
                     "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}
pruefe(any("Nullbeleg" in h for h in xml_build.pruefsummen(null)),
       "Nullbeleg (Gesamtbetrag 0,00) wird abgelehnt")
negativ = json.loads(json.dumps(rechnung))
negativ["totals"]["invoicegross"] = -703.05
pruefe(any("Gutschrift" in h for h in xml_build.pruefsummen(negativ)),
       "negativer Gesamtbetrag verlangt Gutschrift 381")

ohne_leitweg = json.loads(json.dumps(rechnung))
ohne_leitweg["header"]["buyerreference"] = ""
pruefe(any("BR-DE-15" in h for h in xml_build.pruefsummen(ohne_leitweg)), "fehlende Leitweg-ID faellt auf")

print("6) Sicherheitsnetz Empfaenger")
from app import mailer
cfg_test = json.loads(json.dumps(cfg))
cfg_test["mail"]["erlaubte_empfaenger"] = ["@musterhotel.example", "chef@beispielgruppe.example"]
# Der Test setzt seine Voraussetzung selbst. Vorher hing er daran, dass in der
# geladenen Konfiguration der Versand eingeschaltet war — stand er aus, lief er
# in die Meldung 'Versand abgeschaltet' und meldete faelschlich, die Sperre
# gegen fremde Adressen greife nicht.
cfg_test["mail"]["aktiv"] = True
pruefe(mailer.empfaenger_erlaubt(cfg_test, "test@musterhotel.example"), "eigene Domain ist erlaubt")
pruefe(mailer.empfaenger_erlaubt(cfg_test, "chef@beispielgruppe.example"), "einzelne Adresse ist erlaubt")
pruefe(not mailer.empfaenger_erlaubt(cfg_test, "gast@fremde-firma.de"),
       "fremde Adresse wird abgelehnt")
cfg_frei = json.loads(json.dumps(cfg))
cfg_frei["mail"]["erlaubte_empfaenger"] = []
pruefe(mailer.empfaenger_erlaubt(cfg_frei, "gast@fremde-firma.de"),
       "leere Liste hebt die Beschraenkung auf")
try:
    mailer.senden(cfg_test, an="gast@fremde-firma.de", bill_no=1, issuedate="2026-01-01",
                  xml=b"<x/>", xml_name="x.xml")
    pruefe(False, "Versand an fremde Adresse wird verweigert")
except mailer.MailFehler as e:
    pruefe("nicht auf der Liste" in str(e), "Versand an fremde Adresse wird verweigert")

print("5b) Auswahlregeln — wer kommt in die Liste, wer in die Pruefung")
from app import ablauf
import sqlite3
store.init()
with store.verbindung() as con:
    con.execute("DELETE FROM rechnungen")
kandidaten = [
    # Empfaenger ist eine Firma -> darf automatisch laufen
    {"bill_no": 900001, "issuedate": "2026-09-01", "total_gross": 400.0, "total_net": 350.0,
     "company_name": "Beispiel GmbH", "payee_name": "Beispiel GmbH", "account_code": 4711,
     "empfaenger_typ": "COMPANY", "empfaenger_land": "DE", "firmenbezug": "EMPFAENGER",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "1"},
    # Firma nur an der Reservierung -> Pruefung
    {"bill_no": 900002, "issuedate": "2026-09-01", "total_gross": 300.0, "total_net": 260.0,
     "company_name": "Beispiel GmbH", "payee_name": "Herr Schulz", "account_code": None,
     "empfaenger_typ": "D", "empfaenger_land": "DE", "firmenbezug": "RESERVIERUNG",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "2"},
    # Auslaendischer Empfaenger -> gar nicht aufnehmen
    {"bill_no": 900003, "issuedate": "2026-09-01", "total_gross": 900.0, "total_net": 800.0,
     "company_name": "Foreign Inc", "payee_name": "Foreign Inc", "account_code": 4712,
     "empfaenger_typ": "COMPANY", "empfaenger_land": "US", "firmenbezug": "EMPFAENGER",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "3"},
    # Privatgast ohne Firmenbezug -> gar nicht aufnehmen
    {"bill_no": 900004, "issuedate": "2026-09-01", "total_gross": 200.0, "total_net": 180.0,
     "company_name": None, "payee_name": "Frau Meier", "account_code": None,
     "empfaenger_typ": "D", "empfaenger_land": "DE", "firmenbezug": "-",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "4"},
    # Kleinbetrag mit Firmenbezug -> mitnehmen (keine Betragsgrenze gesetzt)
    {"bill_no": 900005, "issuedate": "2026-09-01", "total_gross": 120.0, "total_net": 100.0,
     "company_name": "Kleine GmbH", "payee_name": "Kleine GmbH", "account_code": 4713,
     "empfaenger_typ": "COMPANY", "empfaenger_land": "DE", "firmenbezug": "EMPFAENGER",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "5"},
    # Negativer Kopfbetrag OHNE Anzahlung -> sichtbar zuruecklegen.
    # Mit der Vorgabe mindestbetrag_brutto=0 fiel er vorher schon an der
    # Betragsgrenze heraus: unsichtbar, in keinem Status, gezaehlt unter einer
    # Regel, die niemand gesetzt hat.
    {"bill_no": 900007, "issuedate": "2026-09-01", "total_gross": -703.05, "total_net": -586.75,
     "company_name": "Gutschrift GmbH", "payee_name": "Gutschrift GmbH", "account_code": 4715,
     "empfaenger_typ": "COMPANY", "empfaenger_land": "DE", "firmenbezug": "EMPFAENGER",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "7", "ohne_anzahlung": "J"},
    # Negativer Kopfbetrag MIT Anzahlung -> das ist keine Gutschrift, sondern
    # der Rest. Beleg 1400015: -703,05 im Kopf, 9.353,09 in den Zeilen.
    {"bill_no": 900008, "issuedate": "2026-09-01", "total_gross": -703.05, "total_net": -586.75,
     "company_name": "Anzahlung GmbH", "payee_name": "Anzahlung GmbH", "account_code": 4716,
     "empfaenger_typ": "COMPANY", "empfaenger_land": "DE", "firmenbezug": "EMPFAENGER",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "8", "ohne_anzahlung": "N"},
    # Firmenprofil ohne Land -> aufnehmen, aber pruefen
    {"bill_no": 900006, "issuedate": "2026-09-01", "total_gross": 500.0, "total_net": 450.0,
     "company_name": None, "payee_name": "Ohne Land GmbH", "account_code": 4714,
     "empfaenger_typ": "COMPANY", "empfaenger_land": None, "firmenbezug": "EMPFAENGER",
     "leitweg_id": None, "kennzeichen": 0, "invoice_no": "6"},
]
echt = opera.kandidaten
opera.kandidaten = lambda cfg, tage=30: kandidaten
# Adressen mitspielen lassen: 900001 hat eine, 900005 keine, und bei 900002
# faellt die Abfrage aus. Ohne diesen Unterschied laesst sich nicht pruefen,
# ob eine Stoerung anders behandelt wird als ein Pflegefall.
_echt_empf = opera.empfaenger


def _empfaenger_stub(bill_no):
    if bill_no == 900002:
        raise RuntimeError("ORA-12170: TNS:Connect timeout occurred")
    if bill_no == 900005:
        return []
    return [{"email": f"rechnung{bill_no}@beispiel.de", "quelle": "Profil"}]


opera.empfaenger = _empfaenger_stub
try:
    zahlen = ablauf.einlesen(cfg, tage=30)
    aufgenommen = zahlen["neu"]
finally:
    opera.kandidaten = echt
    opera.empfaenger = _echt_empf
liste = {r["bill_no"]: r for r in store.liste()}
pruefe(aufgenommen == 6, f"6 von 8 Rechnungen aufgenommen (waren {aufgenommen})")
pruefe(zahlen["gelesen"] == 8, "die Aufstellung nennt die gelesene Menge")
pruefe(zahlen["zu_klein"] == 0,
       f"ein negativer Beleg zaehlt NICHT als 'unter dem Mindestbetrag' ({zahlen})")
pruefe(900007 in liste and liste[900007]["status"] == "ignoriert",
       "ein negativer Beleg ohne Anzahlung wird sichtbar zurueckgelegt")
pruefe(900008 in liste and liste[900008]["status"] == "pruefung"
       and "Anzahlungen" in (liste[900008].get("fehler") or ""),
       f"mit Anzahlung kommt er in die Pruefung, nicht in den Papierkorb "
       f"({liste.get(900008, {}).get('fehler')})")
pruefe(zahlen["ausland"] == 1 and zahlen["ohne_firmenbezug"] == 1,
       "die Aufstellung nennt die Gruende fuer das Aussortieren")
pruefe("gelesen" in ablauf.bericht(zahlen) and "aufgenommen" in ablauf.bericht(zahlen),
       f"der Bericht ist lesbar: {ablauf.bericht(zahlen)}")
pruefe(900001 in liste and liste[900001]["status"] == "neu", "Firma als Empfaenger: laeuft normal")
pruefe(900002 in liste and liste[900002]["status"] == "pruefung",
       "Firma nur an der Reservierung: Sichtpruefung")
pruefe(900003 not in liste, "auslaendischer Empfaenger wird nicht aufgenommen")
pruefe(900004 not in liste, "Privatgast ohne Firmenbezug wird nicht aufgenommen")
pruefe(900005 in liste, "Kleinbetrag mit Firmenbezug kommt mit (keine Betragsgrenze)")
# Profil ohne Mailadresse: sichtbar zurueckgelegt, nicht erst beim Versand.
pruefe(liste[900005]["status"] == "pruefung" and "E-Mail" in (liste[900005]["fehler"] or ""),
       f"Profil ohne Mailadresse kommt in die Pruefung ({liste[900005]['fehler']})")
pruefe((liste[900001].get("empfaenger") or "") == "rechnung900001@beispiel.de",
       "gefundene Adresse wird uebernommen")
# Und eine gestoerte Abfrage ist KEIN Pflegefall: 900002 steht wegen der
# Reservierungsfirma in der Pruefung, nicht wegen der Adresse.
pruefe("E-Mail" not in (liste[900002]["fehler"] or ""),
       f"Datenbankstoerung wird nicht als fehlende Adresse ausgelegt ({liste[900002]['fehler']})")
pruefe(900006 in liste and liste[900006]["status"] == "pruefung",
       "fehlendes Land fuehrt zur Pruefung statt zum stillen Verschwinden")
# Ein ZWEITES Einlesen darf bekannte Belege mit neuen Erkenntnissen versorgen,
# ohne die Handarbeit des Anwenders anzutasten. Vorher stand ein Beleg auf ewig
# in der Fassung des Tages, an dem er eingelesen wurde: Weder eine inzwischen
# gepflegte Adresse noch eine verbesserte Suche kamen je bei ihm an.
store.setzen(900001, empfaenger="", status="pruefung",
             fehler=ablauf.HINWEIS_OHNE_ADRESSE)
# Ein Beleg mit ZWEI Gruenden: Die geloeste Adressfrage darf den anderen nicht
# mitnehmen — sonst holt sie einen Beleg aus der Sichtpruefung, den jemand aus
# einem anderen Grund ansehen soll.
# (900002 nicht: dort bricht im Stub die Abfrage ab, dann wird zu Recht
# nichts geaendert.)
store.setzen(900006, empfaenger="", status="pruefung",
             fehler=ablauf.hinweis_dazu("Am Empfängerprofil ist kein Land gepflegt",
                                        ablauf.HINWEIS_OHNE_ADRESSE))
store.setzen(900005, empfaenger="handarbeit@beispiel.de", status="bereit")
opera.kandidaten = lambda cfg, tage=30: kandidaten
opera.empfaenger = _empfaenger_stub
try:
    _zweit = ablauf.einlesen(cfg, tage=30)
finally:
    opera.kandidaten, opera.empfaenger = echt, _echt_empf
_nachher = {r["bill_no"]: r for r in store.liste()}
pruefe(_zweit["neu"] == 0 and _zweit["bekannt"] > 0,
       f"zweites Einlesen legt nichts neu an ({_zweit})")
pruefe((_nachher[900001].get("empfaenger") or "") == "rechnung900001@beispiel.de",
       f"die inzwischen gefundene Adresse kommt an ({_nachher[900001].get('empfaenger')})")
pruefe("E-Mail" not in (_nachher[900001].get("fehler") or ""),
       "und der Hinweis, der einmal richtig war, verschwindet")
pruefe(_nachher[900001]["status"] == "neu",
       f"der Beleg verlaesst die Sichtpruefung ({_nachher[900001]['status']})")
pruefe(_nachher[900006]["status"] == "pruefung"
       and "kein Land" in (_nachher[900006].get("fehler") or "")
       and ablauf.HINWEIS_OHNE_ADRESSE not in (_nachher[900006].get("fehler") or ""),
       f"der andere Pruefgrund bleibt stehen ({_nachher[900006].get('fehler')})")
# Und die Gegenrichtung: Ein Beleg, der schon aus einem anderen Grund in der
# Sichtpruefung steht, bekommt den Adresshinweis DAZU. Frueher wurde er nur
# gesetzt, wenn das Feld leer war — 47 von 126 Pflegefaellen blieben deshalb
# unmarkiert und tauchten in der Uebersicht nicht auf.
pruefe(_nachher[900005].get("adresse_fehlt") == 1,
       f"das Fehlen der Adresse steht in der eigenen Spalte "
       f"({_nachher[900005].get('adresse_fehlt')})")
pruefe(ablauf.HINWEIS_OHNE_ADRESSE in (_nachher[900002].get("fehler") or "")
       or _nachher[900002].get("adresse_fehlt") is None,
       "eine gestoerte Abfrage aendert am Adressvermerk nichts")
pruefe(_nachher[900005].get("empfaenger") == "handarbeit@beispiel.de"
       and _nachher[900005]["status"] == "bereit",
       "eine von Hand eingetragene Adresse wird NICHT ueberschrieben")
pruefe("E-Mail" in (_nachher[900005].get("fehler") or "")
       or not (_nachher[900005].get("fehler") or ""),
       "und der Status des Anwenders bleibt stehen")

# City Ledger geht NICHT automatisch hinaus. Diese Rechnungen sind nicht
# bezahlt, sondern stehen beim Debitor offen — sie gehen die
# Debitorenbuchhaltung an. Von Hand versendbar bleiben sie.
store.rechnung_anlegen({"bill_no": 900009, "resort": "IHRHAUS", "invoice_no": "CL",
                        "issuedate": "2026-09-01", "total_net": 100.0,
                        "total_gross": 119.0, "kunde": "Debitor GmbH",
                        "city_ledger": 119.0, "firmenbezug": "EMPFAENGER"}, 0)
store.setzen(900009, empfaenger="debitor@beispiel.de", status="bereit")
pruefe(900009 not in [r["bill_no"] for r in store.faellige(50)],
       "eine City-Ledger-Rechnung greift die Automatik nicht auf")
pruefe(900009 in [r["bill_no"] for r in store.faellige(50, city_ledger=True)],
       "mit ausdruecklicher Freigabe schon")
pruefe(json.loads((BASE / "config" / "app.example.json").read_text(
           encoding="utf-8"))["automatik"]["city_ledger_versenden"] is False,
       "die Vorlage laesst sie ausgeschaltet")
# Das Kennzeichen an der Firmenkartei: Was ein Eintrag BEDEUTET, entscheidet
# das Haus. Bei 93.042 Karteien ist "erlaubt" erst praktikabel, wenn jemand sie
# gepflegt hat — sonst geht gar nichts hinaus. Deshalb beide Richtungen.
_mit_kennzeichen = json.loads(json.dumps(kandidaten))
_mit_kennzeichen[0]["erechnung_kennzeichen"] = "X"
_echt_k2 = opera.kandidaten
opera.kandidaten = lambda cfg, tage=30: json.loads(json.dumps(_mit_kennzeichen))
opera.empfaenger = _empfaenger_stub
try:
    for _bedeutung, _drin in (("schliesst_aus", False), ("erlaubt", True)):
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen")
        _cfg_k = json.loads(json.dumps(cfg))
        _cfg_k["property"]["udf_erechnung"] = "UDFC05"
        _cfg_k["property"]["udf_erechnung_bedeutung"] = _bedeutung
        ablauf.einlesen(_cfg_k, tage=30)
        _da = 900001 in {r["bill_no"] for r in store.liste()}
        pruefe(_da is _drin,
               f"'{_bedeutung}': die gekennzeichnete Kartei ist "
               f"{'dabei' if _da else 'draussen'}")
    # Ohne Feldnamen faellt die Stufe weg — die Auswahl gilt wie bisher.
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen")
    _cfg_k = json.loads(json.dumps(cfg))
    _cfg_k["property"]["udf_erechnung"] = ""
    ablauf.einlesen(_cfg_k, tage=30)
    pruefe(900001 in {r["bill_no"] for r in store.liste()},
           "ohne Feldnamen wird das Kennzeichen gar nicht erst betrachtet")
    # Und der Spaltenname geht nur nach Positivliste in die Abfrage.
    _sql_roh = (BASE / "sql" / "opera" / "invoice_list.sql").read_text(encoding="utf-8")
    pruefe("n.UDFC05 AS erechnung_kennzeichen" in opera._mit_udf(_sql_roh, "UDFC05"),
           "ein erlaubtes Feld wird eingesetzt")
    pruefe("NULL AS erechnung_kennzeichen" in opera._mit_udf(_sql_roh, "UDFC99; DROP--"),
           "ein unerlaubtes nicht — der Platzhalter bleibt stehen")
finally:
    opera.kandidaten, opera.empfaenger = _echt_k2, _echt_empf
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen")

faellig = [r["bill_no"] for r in store.faellige(50)]
pruefe(900002 not in faellig and 900006 not in faellig,
       "Pruefungsfaelle werden von der Automatik nie aufgegriffen")
with store.verbindung() as con:
    con.execute("DELETE FROM rechnungen")

print("6a) Handbuch in der Oberflaeche")
from app import markdown as md
for datei in ("HANDBUCH.md", "INSTALLATION.md"):
    quelle = (BASE / datei).read_text(encoding="utf-8")
    html_text, verzeichnis = md.rendern(quelle)
    pruefe(len(verzeichnis) >= 8, f"{datei}: Inhaltsverzeichnis mit {len(verzeichnis)} Eintraegen")
    pruefe("<table>" in html_text, f"{datei}: Tabellen werden dargestellt")
    pruefe("|---" not in html_text and "**" not in html_text,
           f"{datei}: keine unverarbeiteten Markdown-Reste")
pruefe("&lt;script&gt;" in md.rendern("<script>alert(1)</script>")[0],
       "HTML in der Quelle wird entschaerft")
# Auszeichnung ueber einen Zeilenumbruch hinweg: Markdown-Quellen sind
# umbrochen, und eine je Zeile verarbeitete Liste zerreisst **fett** in zwei
# Haelften, von denen keine ein vollstaendiges Paar ergibt.
umbruch, _ = md.rendern("- Anfang **ueber zwei\n  Zeilen** Ende\n- zweiter Punkt")
pruefe("<strong>ueber zwei Zeilen</strong>" in umbruch,
       "Auszeichnung ueber einen Zeilenumbruch wird zusammengefuehrt")
pruefe(umbruch.count("<li>") == 2, "die Fortsetzungszeile bleibt Teil derselben Position")

print("6a2) Beide Plattformen")
import os, stat
for name in ("install/INSTALLIEREN.cmd", "install/installieren.ps1", "install/dienst_einrichten.cmd",
             "install/dienst_entfernen.cmd", "run.cmd"):
    pruefe((BASE / name).exists(), f"Windows: {name} vorhanden")
for name in ("install/installieren.sh", "install/dienst_einrichten.sh",
             "install/dienst_entfernen.sh", "install/xrechnung.service", "run.sh"):
    pfad = BASE / name
    pruefe(pfad.exists(), f"Linux: {name} vorhanden")
    if pfad.exists() and name.endswith(".sh"):
        pruefe(bool(pfad.stat().st_mode & stat.S_IXUSR), f"Linux: {name} ist ausfuehrbar")
dienst = (BASE / "install/xrechnung.service").read_text(encoding="utf-8")
for platzhalter in ("@BASIS@", "@BENUTZER@", "@PORT@"):
    pruefe(platzhalter in dienst, f"systemd-Vorlage enthaelt {platzhalter}")
pruefe("Restart=always" in dienst, "systemd startet den Dienst nach einem Absturz neu")
# Java-Suche muss auf diesem System eine Antwort geben (Pfad oder None), nie krachen
java = validate.java_pfad({"validierung": {"java": "java"}})
pruefe(java is None or isinstance(java, str), f"Java-Suche laeuft auf {os.name}: {java or 'nicht gefunden'}")
pruefe("java.exe" not in (java or "") or os.name == "nt",
       "kein java.exe-Pfad auf einem Nicht-Windows-System")
# Ein gefundener Pfad beweist nicht, dass Java laeuft — macOS liefert einen
# Platzhalter unter /usr/bin/java. Die Probe muss das auseinanderhalten.
if java:
    version = validate.java_laeuft(java)
    pruefe(version is None or isinstance(version, str),
           f"Java-Startprobe: {version or 'startet nicht (Platzhalter)'}")
pruefe(validate.java_laeuft("/gibt/es/nicht/java") is None,
       "nicht vorhandenes Java wird als nicht lauffaehig erkannt")

print("6b) Validierung und Aktualisierung")
z = validate.zustand(cfg)
pruefe("bereit" in z and isinstance(z["fehlt"], list), "Validator meldet seinen Zustand")
# Die Voraussetzung setzt der Test selbst. Vorher stand hier schlicht
# `not z["bereit"]` — das war nur auf einem Rechner gruen, auf dem der
# Validator FEHLT, also auf dem Entwicklungsrechner. Auf jeder korrekt
# eingerichteten Anlage war es rot, und ein zustand(), das faelschlich immer
# False meldet, waere unentdeckt geblieben.
_ohne = _json.loads(_json.dumps(cfg))
_ohne["validierung"] = dict(_ohne.get("validierung") or {},
                            jar=str(BASE / "gibt-es-nicht" / "validator.jar"),
                            szenarien=str(BASE / "gibt-es-nicht" / "szenarien.xml"))
_z_ohne = validate.zustand(_ohne)
pruefe(not _z_ohne["bereit"], "ohne installiertes JAR meldet er sich als nicht einsatzbereit")
pruefe(any("gibt-es-nicht" in m or "jar" in m.lower() for m in _z_ohne["fehlt"]),
       f"und nennt, was fehlt: {_z_ohne['fehlt']}")
if z["bereit"]:
    print(f"  ---  auf dieser Anlage ist der Validator eingerichtet: {z.get('jar')}")

# Der Daemon spart den Regelaufbau (rund zwoelf Sekunden je Rechnung). Er darf
# aber nie zur Bedingung werden: Laeuft er nicht, muss der Einzelaufruf
# uebernehmen. Geprueft wird deshalb der Rueckfall, nicht der Gutfall — den
# kann nur eine Anlage mit installiertem Validator zeigen.
pruefe(validate.daemon_zustand()["laeuft"] is False,
       "ohne gestarteten Daemon meldet er sich als nicht laufend")
_kaputt = dict(z, java=str(BASE / "gibt-es-nicht" / "java"), jar="/nichts.jar",
               szenarien=str(BASE / "gibt-es-nicht" / "scenarios.xml"))
pruefe(validate._daemon_starten(_kaputt, wartezeit=3) == 0,
       "ein Daemon, der sich nicht starten laesst, meldet 0 statt zu blockieren")
pruefe(validate._ueber_daemon(_kaputt, b"<x/>") is None,
       "und der Aufrufer bekommt None — Zeichen, den Einzelaufruf zu nehmen")
pruefe(validate.daemon_zustand()["laeuft"] is False,
       "der fehlgeschlagene Start hinterlaesst keinen halben Zustand")
validate.daemon_stoppen()   # darf auch ohne laufenden Daemon nicht werfen

# Der GUTFALL, ohne Java: ein Schein-Daemon, der antwortet wie der echte.
# Vorher prueste dieser Block nur den Rueckfall — und genau deshalb blieb ein
# Absturz unentdeckt, der JEDE Rechnung ueber den Daemon-Weg getroffen haette:
# etree.fromstring() liefert ein Element, _bericht_auswerten() ruft aber
# getroot() auf, das nur ein Baum hat. Ein Test, der nur prueft, dass der
# schnelle Weg NICHT genommen wird, sagt nichts ueber den schnellen Weg.
import http.server as _hs
import threading as _th

_ANGENOMMEN = b"""<?xml version="1.0" encoding="UTF-8"?>
<report xmlns="http://www.xoev.de/de/validator/varl/1" valid="true">
  <message level="warning" code="PEPPOL-EN16931-R120">Menge mal Preis</message>
</report>"""
_ABGELEHNT = b"""<?xml version="1.0" encoding="UTF-8"?>
<report xmlns="http://www.xoev.de/de/validator/varl/1" valid="false">
  <message level="error" code="PEPPOL-EN16931-R010">BT-49 fehlt</message>
</report>"""


class _ScheinDaemon(_hs.BaseHTTPRequestHandler):
    def do_POST(self):
        koerper = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        # Der echte Daemon signalisiert das Urteil ueber den HTTP-Status und
        # legt den Bericht in BEIDEN Faellen in den Koerper.
        abgelehnt = b"ABLEHNEN" in koerper
        antwort = _ABGELEHNT if abgelehnt else _ANGENOMMEN
        self.send_response(406 if abgelehnt else 200)
        self.send_header("Content-Type", "application/xml")
        self.send_header("Content-Length", str(len(antwort)))
        self.end_headers()
        self.wfile.write(antwort)

    def log_message(self, *_):
        pass


_server = _hs.HTTPServer(("127.0.0.1", 0), _ScheinDaemon)
_th.Thread(target=_server.serve_forever, daemon=True).start()
_port = _server.server_address[1]
try:
    _roh = validate.anfrage_an_daemon(_port, b"<Invoice/>")
    pruefe(_roh is not None and b"valid=" in _roh, "der Daemon-Weg holt einen Bericht ab")
    from lxml import etree as _et
    _f, _w = validate._bericht_auswerten(_et.ElementTree(_et.fromstring(_roh)))
    pruefe(_f == [] and any("R120" in x for x in _w),
           f"angenommene Rechnung: keine Fehler, die Warnung bleibt erhalten ({_f}, {_w})")
    # HTTP 406 ist das Urteil "abgelehnt", nicht ein Fehler des Weges. Wer nur
    # 200 gelten laesst, schickt jede abgelehnte Rechnung in den langsamen
    # Einzelaufruf — und merkt es nie, weil das Ergebnis stimmt.
    _roh = validate.anfrage_an_daemon(_port, b"<Invoice>ABLEHNEN</Invoice>")
    pruefe(_roh is not None and b'valid="false"' in _roh,
           "auch bei HTTP 406 kommt der Bericht durch, nicht der Rueckfall")
    _f, _w = validate._bericht_auswerten(_et.ElementTree(_et.fromstring(_roh)))
    pruefe(any("R010" in x for x in _f), f"abgelehnte Rechnung nennt ihren Grund ({_f})")
finally:
    _server.shutdown()
    # server_close() nicht vergessen: Ohne das bleibt der lauschende Socket
    # offen, die naechste Anfrage wird angenommen und nie beantwortet — der
    # Test lief in den 120-Sekunden-Zeitablauf.
    _server.server_close()
# Und ein Port, auf dem nichts lauscht, gibt sauber None zurueck.
pruefe(validate.anfrage_an_daemon(_port, b"<x/>") is None,
       "ein toter Port fuehrt zum Rueckfall, nicht zum Abbruch")

# Der Weg, den die Anwendung wirklich geht — pruefen_ausfuehrlich() mit
# antwortendem Daemon. Die Pruefungen oben werten den Bericht selbst aus und
# haetten den Absturz NICHT gefunden: Er lag darin, wie validate.py das
# Ergebnis weiterreicht, nicht darin, wie es ausgewertet wird.
_echt_daemon, _echt_zustand = validate._ueber_daemon, validate.zustand
validate._ueber_daemon = lambda z, xml: _ABGELEHNT if b"ABLEHNEN" in xml else _ANGENOMMEN
validate.zustand = lambda cfg: {"bereit": True, "fehlt": [], "java": "java",
                                "jar": "x.jar", "szenarien": "s.xml"}
try:
    _cfg_d = json.loads(json.dumps(cfg))
    _cfg_d["validierung"]["daemon"] = True
    _f, _w = validate.pruefen_ausfuehrlich(_cfg_d, b"<Invoice/>")
    pruefe(_f == [] and any("R120" in x for x in _w),
           f"ueber den Daemon: angenommen, mit Warnung ({_f}, {_w})")
    _f, _w = validate.pruefen_ausfuehrlich(_cfg_d, b"<Invoice>ABLEHNEN</Invoice>")
    pruefe(any("R010" in x for x in _f),
           f"ueber den Daemon: abgelehnt, mit Grund ({_f})")
    pruefe(validate.pruefen(_cfg_d, b"<Invoice/>") == [],
           "und pruefen() liefert weiterhin nur die Fehler")
    # Ein unerwarteter Fehler im Validator darf die Erzeugung nicht
    # abbrechen — aber auch nicht durchgehen. Genau das war der Absturz:
    # Er lief bis zum Aufrufer durch und riss die ganze Erzeugung mit.
    validate._ueber_daemon = lambda z, xml: (_ for _ in ()).throw(
        AttributeError("'_Element' object has no attribute 'getroot'"))
    from app import ablauf as _abl
    _echt_rd = _abl.rechnungsdaten
    _abl.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(rechnung))
    try:
        _cfg_d["validierung"]["aktiv"] = True
        _, _, _h = _abl.xml_erzeugen(_cfg_d, 1400003)
        pruefe(any("unerwarteter Fehler" in x for x in _h),
               f"ein Absturz im Validator sperrt den Versand, statt alles mitzureissen ({_h})")
    except Exception as e:
        pruefe(False, f"ein Absturz im Validator reisst die Erzeugung mit: {e!r}")
    finally:
        _abl.rechnungsdaten = _echt_rd
finally:
    validate._ueber_daemon, validate.zustand = _echt_daemon, _echt_zustand
pruefe(updater.version() != "", f"Version gelesen: {updater.version()}")
p_update = updater.pruefen({"update": {"aktiv": False}})
pruefe(p_update["moeglich"] is False, "abgeschaltete Aktualisierung meldet sich als abgeschaltet")

# Der Austausch laeuft Bereich fuer Bereich: loeschen, neu schreiben, naechster.
# Scheitert er in der Mitte, ist die Installation halb ersetzt und es gibt
# keinen Rueckweg. Auf dem Server ist genau das passiert — der Dienst durfte im
# Programmverzeichnis nicht schreiben. Deshalb wird VOR dem ersten Loeschen
# gefragt.
if not _als_root:
    _gesperrt = BASE / "data" / "nur_lesen_test"
    _gesperrt.mkdir(parents=True, exist_ok=True)
    _os.chmod(_gesperrt, 0o555)
    try:
        _echt_base = updater.BASE
        updater.BASE = _gesperrt
        pruefe(updater.schreibrechte_pruefen() != [],
               "ein nicht beschreibbares Programmverzeichnis wird erkannt")
        updater.BASE = _echt_base
        pruefe(updater.schreibrechte_pruefen() == [],
               "und ein beschreibbares nicht faelschlich beanstandet")
    finally:
        updater.BASE = _echt_base
        _os.chmod(_gesperrt, 0o755)
        _gesperrt.rmdir()
else:
    print("  ---  uebersprungen: als root greifen Dateirechte nicht")

# Der Quellverweis: Die systemd-Unit muss gegen config/app.json GEWINNEN.
# Auf dem Server ist das nicht zu beobachten, weil beide dasselbe Repository
# nennen — dort waere der Vorrang nur behauptet. Hier stehen sie deshalb
# absichtlich gegeneinander.
_cfg_q = json.loads(json.dumps(cfg))
_cfg_q["update"] = dict(_cfg_q.get("update") or {},
                        repo="aus/app-json", zweig="aus-app-json")
for _var in ("XRECHNUNG_UPDATE_REPO", "XRECHNUNG_UPDATE_ZWEIG"):
    os.environ.pop(_var, None)
_repo, _zweig, _fest = updater.quelle(_cfg_q)
pruefe((_repo, _zweig, _fest) == ("aus/app-json", "aus-app-json", False),
       f"ohne Unit-Vorgabe gilt app.json ({_repo}, {_zweig}, festgenagelt={_fest})")
os.environ["XRECHNUNG_UPDATE_REPO"] = "aus/der-unit"
os.environ["XRECHNUNG_UPDATE_ZWEIG"] = "aus-der-unit"
try:
    _repo, _zweig, _fest = updater.quelle(_cfg_q)
    pruefe((_repo, _zweig) == ("aus/der-unit", "aus-der-unit"),
           f"die Unit gewinnt gegen app.json ({_repo}, {_zweig})")
    pruefe(_fest is True, "und die Oberflaeche erfaehrt, dass sie festgenagelt ist")
    # Ein uebernommener Dienst koennte app.json schreiben — das darf folgenlos
    # bleiben. Genau dafuer steht der Zeiger in der root-eigenen Unit.
    _cfg_q["update"]["repo"] = "angreifer/boeses-repo"
    pruefe(updater.quelle(_cfg_q)[0] == "aus/der-unit",
           "ein veraenderter Eintrag in app.json bleibt wirkungslos")
finally:
    for _var in ("XRECHNUNG_UPDATE_REPO", "XRECHNUNG_UPDATE_ZWEIG"):
        os.environ.pop(_var, None)

# --- Freigaben: umschalten, aufraeumen, zurueckgehen ----------------------
# Der Umschalter ist der einzige Schritt, der die laufende Installation
# beruehrt. Geprueft wird deshalb genau das: dass er in EINEM Schritt passiert
# und dass das Aufraeumen nie das loescht, worauf 'aktuell' zeigt.
_fr_basis = _sandkasten / "programm"
_echt_dirs = (updater.PROGRAMM_DIR, updater.FREIGABEN, updater.AKTUELL)
updater.PROGRAMM_DIR = _fr_basis
updater.FREIGABEN = _fr_basis / "freigaben"
updater.AKTUELL = _fr_basis / "aktuell"
try:
    updater.FREIGABEN.mkdir(parents=True, exist_ok=True)
    for _name in ("20260908-100000-aaaaaaaa", "20260909-100000-bbbbbbbb",
                  "20260910-100000-cccccccc", "20260910-110000-dddddddd"):
        (updater.FREIGABEN / _name).mkdir()
        (updater.FREIGABEN / _name / "VERSION").write_text(_name, encoding="utf-8")
    pruefe(updater.freigabenbetrieb(), "der Freigabenbetrieb wird erkannt")
    _neueste = updater.freigaben()[0]
    updater.umschalten(_neueste)
    pruefe(updater.AKTUELL.is_symlink(), "'aktuell' ist ein Symlink")
    pruefe(updater.AKTUELL.resolve().name == _neueste.name,
           f"und zeigt auf die neueste Freigabe ({updater.AKTUELL.resolve().name})")
    # Zweimal umschalten muss gehen — beim zweiten Mal liegt der Symlink schon da.
    updater.umschalten(updater.freigaben()[1])
    pruefe(updater.AKTUELL.resolve().name == "20260910-100000-cccccccc",
           "erneutes Umschalten ersetzt den Symlink, statt daran zu scheitern")
    pruefe(not (updater.AKTUELL.with_name("aktuell.neu")).exists(),
           "und laesst keinen Hilfsnamen liegen")
    # Aufraeumen: die aktive Freigabe ist aelter als die neueste. Sie zu
    # loeschen hiesse, dem laufenden Dienst den Boden wegzuziehen.
    _weg = updater.aufraeumen(behalten=2)
    _uebrig = {f.name for f in updater.freigaben()}
    pruefe("20260910-100000-cccccccc" in _uebrig,
           f"die laufende Freigabe bleibt, auch wenn sie alt ist ({sorted(_uebrig)})")
    pruefe("20260908-100000-aaaaaaaa" not in _uebrig,
           f"die aelteste wird entfernt ({_weg})")
    # Zurueckgehen: der Verweis wandert, nichts wird kopiert.
    # Der Weg, den die Oberflaeche nimmt. Auf dem Produktivserver wurde er
    # bewusst NICHT ausgeloest — zurueckzurollen, nur um zu sehen ob es geht,
    # ist dort der falsche Ort. Also hier.
    # Zurueckgesetzt wird auf die Freigabe VOR der laufenden. Vorher nahm
    # zuruecksetzen() ohne Namen die neueste — von der aeltesten aus ging es
    # damit nach VORN, obwohl der Knopf "zurueck" heisst.
    updater.umschalten(updater.FREIGABEN / "20260910-110000-dddddddd")
    _vorher = updater.AKTUELL.resolve().name
    _meldung = updater.zuruecksetzen()
    pruefe(updater.AKTUELL.resolve().name == "20260910-100000-cccccccc",
           f"Zurücksetzen hängt den Verweis auf die vorherige Freigabe ({_meldung})")
    pruefe(all((updater.FREIGABEN / f).exists() for f in _uebrig),
           "und laesst alle Freigaben stehen — es wird nichts zurueckkopiert")
    # DER FALL, FUER DEN DER RUECKWEG GEBAUT IST: Nach dem Zuruecksetzen muss
    # sich wieder nach vorn kommen lassen. Vorher schrieb nur anwenden() den
    # Stand — nach einem Zuruecksetzen stand dort weiterhin die NEUERE Freigabe,
    # pruefen() verglich die Spitze dagegen und meldete "Bereits aktuell". Wer
    # zurueckgegangen war, kam ueber die Oberflaeche nicht wieder heraus.
    # Verzeichnisname und Kennung muessen zusammenpassen — sonst prueft der
    # verkuerzte Vergleich unten etwas anderes, als er zu pruefen scheint.
    _voll_a = "cccccccc" + "1" * 32
    _voll_b = "dddddddd" + "2" * 32
    for _f, _sha in ((updater.FREIGABEN / "20260910-100000-cccccccc", _voll_a),
                     (updater.FREIGABEN / "20260910-110000-dddddddd", _voll_b)):
        (_f / updater.FREIGABE_STAND).write_text(
            json.dumps({"sha": _sha, "datum": "", "eingespielt": ""}), encoding="utf-8")
    updater.umschalten(updater.FREIGABEN / "20260910-110000-dddddddd")
    pruefe(updater.stand().get("sha") == _voll_b,
           f"der Stand kommt aus der laufenden Freigabe ({updater.stand().get('sha', '')[:8]})")
    updater.zuruecksetzen()
    pruefe(updater.stand().get("sha") == _voll_a,
           "und wandert beim Zuruecksetzen mit — ohne dass jemand ihn nachfuehrt")
    # Damit meldet pruefen() die neuere Fassung wieder als verfuegbar.
    _echt_anfrage = updater._anfrage
    updater._anfrage = lambda url, token="", roh=False: {
        "sha": _voll_b, "commit": {"author": {"date": "2026-09-10"}, "message": "neu"}}
    try:
        _p = updater.pruefen({"update": {"aktiv": True, "repo": "a/b", "zweig": "main"}})
        pruefe(_p["moeglich"] is True,
               f"nach dem Zuruecksetzen laesst sich wieder nach vorn ({_p['text']})")
        updater.umschalten(updater.FREIGABEN / "20260910-110000-dddddddd")
        _p = updater.pruefen({"update": {"aktiv": True, "repo": "a/b", "zweig": "main"}})
        pruefe(_p["moeglich"] is False,
               f"und auf dem neuesten Stand meldet er 'bereits aktuell' ({_p['text']})")
        # Eine Freigabe ohne eigenen Vermerk: der Verzeichnisname reicht.
        (updater.FREIGABEN / "20260910-110000-dddddddd" / updater.FREIGABE_STAND).unlink()
        pruefe(updater.stand().get("sha") == "dddddddd",
               f"ohne Vermerk liefert der Verzeichnisname die Kennung ({updater.stand()})")
        _p = updater.pruefen({"update": {"aktiv": True, "repo": "a/b", "zweig": "main"}})
        pruefe(_p["moeglich"] is False,
               "und der verkuerzte Wert gilt trotzdem als derselbe Stand")
        # Anzeige und Entscheidung muessen aus DERSELBEN Rechnung kommen.
        # Vorher verglich der Text exakt und moeglich praefixbewusst: Bei einer
        # Freigabe ohne eigenen Vermerk meldete die Oberflaeche "Neuer Stand
        # verfuegbar" und weigerte sich zugleich, ihn einzuspielen.
        pruefe(_p["text"] == "Bereits aktuell",
               f"und die Meldung sagt dasselbe wie der Knopf ({_p['text']})")
        (updater.FREIGABEN / "20260910-110000-dddddddd" / updater.FREIGABE_STAND
         ).write_text(json.dumps({"sha": _voll_b}), encoding="utf-8")
        _p = updater.pruefen({"update": {"aktiv": True, "repo": "a/b", "zweig": "main"}})
        pruefe(_p["text"] == "Bereits aktuell" and _p["moeglich"] is False,
               "mit Vermerk ebenso")
        updater.umschalten(updater.FREIGABEN / "20260910-100000-cccccccc")
        _p = updater.pruefen({"update": {"aktiv": True, "repo": "a/b", "zweig": "main"}})
        pruefe(_p["moeglich"] is True and _p["text"] == "Neuer Stand verfügbar",
               f"und auf einem aelteren Stand sagen beide, dass es etwas gibt ({_p['text']})")
    finally:
        updater._anfrage = _echt_anfrage

    # Auf der aeltesten Freigabe gibt es nichts mehr davor: Das sagt die
    # Meldung, und der Verweis bleibt, wo er ist. Vorher sprang er nach vorn.
    updater.umschalten(updater.FREIGABEN / "20260910-100000-cccccccc")
    _nach_erstem = updater.AKTUELL.resolve().name
    _m2 = updater.zuruecksetzen()
    pruefe(updater.AKTUELL.resolve().name == _nach_erstem and "keine frühere" in _m2,
           f"auf der aeltesten Freigabe bleibt der Verweis stehen ({_m2})")
    # Auf eine bestimmte Freigabe zeigen — und ein Fehlgriff bleibt folgenlos.
    _ziel = sorted(_uebrig)[0]
    updater.zuruecksetzen(_ziel)
    pruefe(updater.AKTUELL.resolve().name == _ziel,
           f"eine benannte Freigabe laesst sich ansteuern ({_ziel})")
    _stand = updater.AKTUELL.resolve().name
    _m = updater.zuruecksetzen("gibt-es-nicht")
    pruefe("gibt es nicht" in _m and updater.AKTUELL.resolve().name == _stand,
           f"ein unbekannter Name aendert nichts ({_m})")
    # Der Name kommt aus einem Formular. 'ist ein Verzeichnis' genuegt als
    # Bedingung NICHT: '../../data/boese' erfuellt das auch, und data/ kann der
    # Dienst selbst befuellen. 'aktuell' haette dann auf selbst geschriebenen
    # Code gezeigt — neustartfest, ohne Token, ohne Repository.
    _ausbruch = _sandkasten / "data" / "boese"
    _ausbruch.mkdir(parents=True, exist_ok=True)
    for _versuch in ("../../data/boese", "../..", "/etc",
                     "20260910-100000-cccccccc/../../../data/boese"):
        _m = updater.zuruecksetzen(_versuch)
        pruefe(updater.AKTUELL.resolve().name == _stand,
               f"'{_versuch}' fuehrt nicht aus den Freigaben heraus ({_m[:40]})")
    # Und die Absicherung eine Ebene tiefer greift auch bei direktem Aufruf.
    try:
        updater.umschalten(_ausbruch)
        pruefe(False, "umschalten() nimmt ein Ziel ausserhalb der Freigaben an")
    except ValueError:
        pruefe(True, "umschalten() lehnt ein Ziel ausserhalb der Freigaben ab")
finally:
    updater.PROGRAMM_DIR, updater.FREIGABEN, updater.AKTUELL = _echt_dirs

# Shell-Skripte: eine Fehlerklasse, die 'bash -n' NICHT findet.
# Ein Heredoc in einer Kommandosubstitution vertraegt sich nicht mit einem
# '[[ ]] &&' davor — Bash schiebt beim erneuten Parsen das '|| true' hinter den
# Heredoc-Koerper. Der Syntaxfehler entsteht erst beim AUSFUEHREN, weil der
# Inhalt einer Substitution erst dann geparst wird. Genau das hat die
# Umstellung auf dem Server beim ersten Versuch abbrechen lassen.
import re as _re3
import shutil as _sh


def _heredoc_in_substitution(text: str) -> list[str]:
    """Zeilen, die eine Kommandosubstitution mit Heredoc UND einer
    Und/Oder-Verkettung mischen."""
    treffer = []
    for nr, zeile in enumerate(text.splitlines(), 1):
        if "$(" in zeile and "<<" in zeile and ("||" in zeile or "&&" in zeile):
            treffer.append(f"Zeile {nr}: {zeile.strip()[:90]}")
    return treffer


_kaputt = (
    'SHA="$( [[ -f x ]] && python3 - x <<\'PY\' 2>/dev/null || true\n'
    'print(1)\nPY\n)"')
pruefe(_heredoc_in_substitution(_kaputt) != [],
       "die Regel findet ein Heredoc in einer Substitution mit || davor")
pruefe(_heredoc_in_substitution('X="$(python3 - x <<\'PY\'\nprint(1)\nPY\n)"') == [],
       "und beanstandet die unkritische Form nicht")
for _skript in sorted((BASE / "install").glob("*.sh")) + [BASE / "run.sh"]:
    _befunde = _heredoc_in_substitution(_skript.read_text(encoding="utf-8"))
    pruefe(not _befunde, f"{_skript.name}: keine Heredocs in Substitutionen ({_befunde})")
# bash -n zusaetzlich — es findet zwar diese Klasse nicht, aber andere.
for _skript in sorted((BASE / "install").glob("*.sh")) + [BASE / "run.sh"]:
    _lauf = _sp.run(["bash", "-n", str(_skript)], capture_output=True, text=True)
    pruefe(_lauf.returncode == 0, f"{_skript.name}: bash -n sauber ({_lauf.stderr[:80]})")
if _sh.which("shellcheck"):
    for _skript in sorted((BASE / "install").glob("*.sh")) + [BASE / "run.sh"]:
        _lauf = _sp.run(["shellcheck", "-S", "error", str(_skript)],
                        capture_output=True, text=True)
        pruefe(_lauf.returncode == 0, f"{_skript.name}: shellcheck ohne Fehler")
else:
    print("  ---  shellcheck nicht installiert — es faende SC1009/SC1073 dieser Klasse")

# Startskripte im Freigabenbetrieb: Wer von Hand startet und dabei eine
# Rechnung erzeugt, schreibt sie sonst in die Freigabe — wo das Aufraeumen sie
# spaeter entfernt. Es traefe ausgerechnet den, der gerade sucht.
for _skript, _muster in (("run.sh", "programm/freigaben"),
                         ("run.cmd", "programm\\freigaben")):
    _inhalt = (BASE / _skript).read_text(encoding="utf-8", errors="replace")
    pruefe(_muster in _inhalt,
           f"{_skript} erkennt, ob es in einer Freigabe liegt")
    pruefe(all(v in _inhalt for v in ("XRECHNUNG_BASIS", "XRECHNUNG_CONFIG_DIR",
                                      "XRECHNUNG_DATEN_DIR", "XRECHNUNG_LOG_DIR")),
           f"{_skript} setzt dann alle vier Variablen")

# beispiele/ gehoert zum Programm — sonst faellt die Beleg-Probe der Umstellung
# lautlos aus, weil die Datei in der Freigabe fehlt.
pruefe("beispiele" in updater.PROGRAMM,
       "beispiele/ wird bei einer Aktualisierung mitgeliefert")
pruefe("beispiele" in (BASE / "install" / "umstellen_freigaben.sh").read_text(encoding="utf-8"),
       "und die Umstellung verschiebt es mit")

# Ein falscher Zweigname darf nicht als Berechtigungsproblem erscheinen.
# Bestehende Installationen tragen teils noch "master" — der Updater soll den
# richtigen Namen nennen, statt den Anwender den Token pruefen zu lassen.
import urllib.error as _ue
_echt = updater._anfrage
# GitHub antwortet auf einen unbekannten Zweig mit 422, nicht mit 404:
# der commits-Endpunkt behandelt den Zweig als Referenz. 404 kommt nur, wenn
# das Repository selbst nicht sichtbar ist. Deshalb wird HIER der echte
# Auslöser geprueft und nicht die eigene Annahme.
for _code, _grund in ((422, "unbekannte Referenz"), (404, "Rueckfall, falls GitHub sich aendert")):
    def _antwort(url, token="", roh=False, _c=_code):
        if "/commits/" in url:
            raise _ue.HTTPError(url, _c, "Fehler", {}, None)
        return {"default_branch": "main"}
    updater._anfrage = _antwort
    try:
        z = updater.pruefen({"update": {"aktiv": True, "repo": "ahornhotels/XRechnungOPERA",
                                        "zweig": "master", "token": "x"}})
    finally:
        updater._anfrage = _echt
    pruefe(z.get("zweig_falsch") is True and z.get("standardzweig") == "main",
           f"HTTP {_code} ({_grund}): falscher Zweig wird erkannt")
    pruefe("'main'" in z["text"] and "master" in z["text"],
           f"HTTP {_code}: die Meldung nennt beide Zweignamen")
# Und wenn das Repository selbst nicht lesbar ist, bleibt es beim Token-Hinweis
def _antwort_zu(url, token="", roh=False):
    raise _ue.HTTPError(url, 404, "Not Found", {}, None)
updater._anfrage = _antwort_zu
try:
    z2 = updater.pruefen({"update": {"aktiv": True, "repo": "ahornhotels/GibtEsNicht",
                                     "zweig": "main", "token": "x"}})
finally:
    updater._anfrage = _echt
pruefe(not z2.get("zweig_falsch") and "Token" in z2["text"],
       "unsichtbares Repository bleibt ein Berechtigungshinweis")
# Beide Fehler zugleich: falscher Zweig UND kein Token. Ohne Token ist das
# Repository unsichtbar, dann kann die Rueckfrage den Standardzweig gar nicht
# kennen — es muss der Berechtigungshinweis kommen. Der Anwender wird so
# zweimal hintereinander richtig gefuehrt statt einmal falsch.
updater._anfrage = _antwort_zu
try:
    z3 = updater.pruefen({"update": {"aktiv": True, "repo": "ahornhotels/XRechnungOPERA",
                                     "zweig": "master", "token": ""}})
finally:
    updater._anfrage = _echt
pruefe(not z3.get("zweig_falsch") and "privat" in z3["text"],
       "falscher Zweig ohne Token: erst die Berechtigung, dann der Zweig")

print("6c) Passwortwechsel")
auth.anlegen("wechsler", "AltesPasswort1", "ansehen")
pruefe(auth.passwort_aendern("wechsler", "falsch", "NeuesPasswort1") is not None,
       "falsches altes Passwort wird abgelehnt")
pruefe(auth.passwort_aendern("wechsler", "AltesPasswort1", "kurz") is not None,
       "zu kurzes neues Passwort wird abgelehnt")
pruefe(auth.passwort_aendern("wechsler", "AltesPasswort1", "NeuesPasswort1") is None,
       "Passwortwechsel gelingt")
pruefe(auth.anmelden("wechsler", "NeuesPasswort1", "127.0.0.1") is not None,
       "Anmeldung mit neuem Passwort")

print("6d) Zweite Blindkopie fuer City Ledger")
# Der eingetragene Mailserver: Name UND Port. Die Namensaufloesung allein
# reicht nicht — der Fall, der das ausgeloest hat, loeste sauber auf: Der Name
# zeigte auf einen Webserver, auf Port 25 antwortete nichts. Eine Pruefung, die
# nur nachschlaegt, haette "in Ordnung" gemeldet.
import socket as _so
_horcher = _so.socket()
_horcher.bind(("127.0.0.1", 0))
_horcher.listen(1)
_offen = _horcher.getsockname()[1]
try:
    pruefe(mailer.host_pruefen({"mail": {"smtp_host": "127.0.0.1", "smtp_port": _offen}}) == "",
           "ein antwortender Server wird nicht beanstandet")
finally:
    _horcher.close()
_zu = mailer.host_pruefen({"mail": {"smtp_host": "127.0.0.1", "smtp_port": _offen}}, 1)
pruefe("antwortet kein Mailserver" in _zu,
       f"ein aufloesbarer Name ohne Mailserver faellt auf ({_zu[:60]})")
pruefe("Port" in _zu and "587" in _zu, "und die Meldung nennt die ueblichen Ports")
_weg = mailer.host_pruefen({"mail": {"smtp_host": "kein-mailserver.invalid", "smtp_port": 25}}, 1)
pruefe("nicht auflösen" in _weg, f"ein unbekannter Name ebenfalls ({_weg[:50]})")
pruefe("kein Mailserver eingetragen" in mailer.host_pruefen({"mail": {"smtp_host": ""}}),
       "und ein leeres Feld wird benannt")
pruefe(mailer.host_pruefen({"mail": {"smtp_host": "127.0.0.1", "smtp_port": _offen}}, 1)
       != mailer.host_pruefen({"mail": {"smtp_host": "kein-mailserver.invalid"}}, 1),
       "die beiden Faelle werden unterschiedlich benannt, nicht nur beide gemeldet")

cfg_bcc = json.loads(json.dumps(cfg))
cfg_bcc["mail"]["bcc"] = "buchhaltung@beispiel.de"
cfg_bcc["mail"]["bcc_city_ledger"] = "debitoren@beispiel.de"
cfg_bcc["mail"]["erlaubte_empfaenger"] = ["@beispiel.de"]
pruefe(mailer.blindkopien(cfg_bcc, False) == ["buchhaltung@beispiel.de"],
       "ohne City Ledger geht nur die allgemeine Blindkopie mit")
pruefe(mailer.blindkopien(cfg_bcc, True) == ["buchhaltung@beispiel.de", "debitoren@beispiel.de"],
       "mit City Ledger gehen beide Blindkopien mit")
# Dieselbe Adresse in beiden Feldern darf die Mail nicht doppelt zustellen
cfg_gleich = json.loads(json.dumps(cfg_bcc))
cfg_gleich["mail"]["bcc_city_ledger"] = "Buchhaltung@Beispiel.de"
pruefe(mailer.blindkopien(cfg_gleich, True) == ["buchhaltung@beispiel.de"],
       "dieselbe Adresse in beiden Feldern wird nur einmal zugestellt")
# Leeres Feld heisst: keine zusaetzliche Kopie
cfg_leer = json.loads(json.dumps(cfg_bcc))
cfg_leer["mail"]["bcc_city_ledger"] = ""
pruefe(mailer.blindkopien(cfg_leer, True) == ["buchhaltung@beispiel.de"],
       "leeres Feld schaltet die zusaetzliche Blindkopie ab")
# Auch die Blindkopie geht durch die Whitelist
cfg_fremd = json.loads(json.dumps(cfg_bcc))
cfg_fremd["mail"]["bcc_city_ledger"] = "jemand@fremde-firma.de"
cfg_fremd["mail"]["aktiv"] = True   # Voraussetzung des Tests, nicht der Umgebung
try:
    mailer.senden(cfg_fremd, an="kunde@beispiel.de", bill_no=1, issuedate="2026-01-01",
                  xml=b"<x/>", xml_name="x.xml", city_ledger=True)
    pruefe(False, "eine Blindkopie ausserhalb der Liste wird abgelehnt")
except mailer.MailFehler as e:
    pruefe("Blindkopie" in str(e), "eine Blindkopie ausserhalb der Liste wird abgelehnt")

print("7) Oberflaeche")
from app.main import app
# TestClient meldet sich sonst als Host "testclient" — der Netzfilter
# erwartet eine IP-Adresse, deshalb hier ausdruecklich 127.0.0.1.
with TestClient(app, client=("127.0.0.1", 50000)) as klient:
    pruefe(klient.get("/health").status_code == 200, "/health erreichbar")
    pruefe(klient.get("/", follow_redirects=False).status_code == 303, "ohne Anmeldung Umleitung")
    pruefe(klient.get("/login").status_code == 200, "Anmeldeseite laedt")
    antwort = klient.post("/login", data={"benutzer": "pruefer", "passwort": "Geheim!123"},
                          follow_redirects=False)
    pruefe(antwort.status_code == 303 and "sitzung" in antwort.cookies, "Anmeldung setzt Sitzung")
    for pfad in ("/", "/protokoll", "/konfiguration", "/benutzer", "/?status=neu",
                 "/hilfe", "/hilfe/installation"):
        seite = klient.get(pfad)
        pruefe(seite.status_code == 200, f"{pfad} laedt")
    # Die Konfigurationsseite muss die GESPEICHERTEN Werte auch anzeigen.
    # In Jinja trifft die Punktschreibweise zuerst Attribute — cfg.update ist
    # die dict-Methode update(), nicht der Abschnitt. Das rendert leer, und
    # weil das Formular den Leerstring zuruecksendet, loescht das naechste
    # Speichern die Angaben. Deshalb wird hier auf den Inhalt geprueft.
    seite = klient.get("/konfiguration")
    # Verglichen wird gegen die JETZT gueltige Konfiguration, nicht gegen die
    # beim Start eingelesene: Dazwischen liegen Pruefungen, die schreiben.
    # Vorher stand hier das cfg von ganz oben — die Pruefung verglich damit
    # einen veralteten Stand und wurde rot, sobald irgendwo anders ein Wert
    # geaendert wurde. Rot, ohne dass an der Seite etwas falsch war.
    _jetzt = config.laden()
    for wert, was in ((_jetzt["update"]["repo"], "Repository"),
                      (_jetzt["update"]["zweig"], "Zweig"),
                      (_jetzt["property"]["resort"], "Resort"),
                      (_jetzt["mail"]["betreff"][:20], "Mailbetreff")):
        pruefe(wert in seite.text, f"die Konfigurationsseite zeigt den {was} an")
    # Kein Geheimnis darf in einer ausgelieferten Seite stehen. Der Fall ist
    # real aufgetreten: Der Update-Token fehlte in GEHEIM und wurde, sobald die
    # Anzeige repariert war, vollstaendig im HTML ausgegeben — ein Fehler hatte
    # den anderen verdeckt.
    from app.config import GEHEIM as _geheim
    _roh = _json.loads((config.CONFIG_DIR / "app.json").read_text(encoding="utf-8"))
    marker = {"datenbank": "GEHEIMES-DB-PASSWORT", "mail": "GEHEIMES-SMTP-PASSWORT",
              "update": "GEHEIMER-TOKEN-1234567890"}
    for sektion, feld in _geheim:
        _roh.setdefault(sektion, {})[feld] = marker[sektion]
    (config.CONFIG_DIR / "app.json").write_text(_json.dumps(_roh, indent=2), encoding="utf-8")
    config.laden()          # verschluesselt die Klartextwerte einmalig
    for pfad in ("/konfiguration", "/", "/benutzer", "/protokoll"):
        seite = klient.get(pfad)
        for sektion, feld in _geheim:
            pruefe(marker[sektion] not in seite.text,
                   f"{pfad}: {sektion}.{feld} steht nicht im HTML")
    gespeichert = _json.loads((config.CONFIG_DIR / "app.json").read_text(encoding="utf-8"))
    for sektion, feld in _geheim:
        pruefe(gespeichert[sektion][feld].startswith("enc:"),
               f"{sektion}.{feld} liegt verschluesselt in der Datei")

    # Ein NEU eingetragener Token muss sofort verschluesselt in der Datei
    # landen — nicht erst beim naechsten Start. Sonst laege er bis zum
    # Neustart im Klartext, und genau das war der Fehler.
    klient.post("/konfiguration", data={"update.token": "github_pat_FRISCH_EINGETRAGEN"},
                follow_redirects=False)
    datei = (config.CONFIG_DIR / "app.json").read_text(encoding="utf-8")
    pruefe("github_pat_FRISCH_EINGETRAGEN" not in datei,
           "ein neu eingetragener Token steht nicht im Klartext in der Datei")
    pruefe(_json.loads(datei)["update"]["token"].startswith("enc:"),
           "ein neu eingetragener Token ist sofort verschluesselt, ohne Neustart")
    pruefe(config.laden()["update"]["token"] == "github_pat_FRISCH_EINGETRAGEN",
           "und er ist zur Laufzeit weiterhin brauchbar")

    # Und ein Speichern anderer Felder darf sie nicht loeschen.
    #
    # Verglichen wird gegen den Stand DIREKT VOR dem Speichern, nicht gegen
    # die Konfiguration von Testbeginn. Vorher stand hier cfg von ganz oben —
    # die Pruefung wurde damit rot, sobald irgendwo anders ein Wert geaendert
    # wurde, und zeigte auf die falsche Ursache. Derselbe Fehler steckte in
    # der Pruefung der Konfigurationsseite.
    _vorher_repo = config.laden()["update"]["repo"]
    klient.post("/konfiguration", data={"mail.bcc": "test@beispiel.de"},
                follow_redirects=False)
    danach = config.laden()
    pruefe(danach["update"]["repo"] == _vorher_repo,
           f"Speichern eines anderen Feldes loescht das Repository nicht "
           f"(vorher {_vorher_repo!r}, danach {danach['update']['repo']!r})")
    pruefe(danach["update"]["zweig"] == cfg["update"]["zweig"],
           "Speichern eines anderen Feldes loescht den Zweig nicht")
    # Versionsschalter auf der Konfigurationsseite: angeboten wird, was es
    # gibt; eine unbekannte Version wird nicht gespeichert.
    _kseite = klient.get("/konfiguration").text
    pruefe('name="xrechnung.version"' in _kseite and '<option value="3.0.2"' in _kseite,
           "die Konfigurationsseite bietet den Versionsschalter an")
    _a = klient.post("/konfiguration", data={"xrechnung.version": "4.0"}, follow_redirects=False)
    from urllib.parse import unquote as _unquote
    _ort = _unquote(_a.headers.get("location", ""))   # der Ort ist URL-kodiert
    pruefe("NICHT GESPEICHERT" in _ort and config.laden()["xrechnung"]["version"] == "3.0.2",
           f"eine nicht verfuegbare Version wird nicht gespeichert ({_ort[:70]}, "
           f"gespeichert: {config.laden()['xrechnung']['version']})")
    klient.post("/konfiguration", data={"xrechnung.version": "3.0.2"}, follow_redirects=False)
    pruefe(config.laden()["xrechnung"]["version"] == "3.0.2",
           "eine verfuegbare Version laesst sich speichern")
    # Der Versandknopf haengt an dem, was die SEITE rechnet. Stand der
    # BT-49-Rueckfall nur in der Erzeugung, meldete die Seite "BT-49 fehlt"
    # und sperrte den Knopf, waehrend die Erzeugung zufrieden war: eine
    # versandbereite Rechnung mit gueltigem Empfaenger, die sich nicht
    # versenden liess — und kein Weg, es doch zu tun. Geprueft wird deshalb
    # die Seite, nicht die Funktion.
    from app import ablauf as _ablauf
    _ohne_adresse = json.loads(json.dumps(rechnung))
    _ohne_adresse["header"]["customerendpointid"] = None
    _echt_r, _echt_e = opera.rechnung, opera.empfaenger
    opera.rechnung = lambda cfg, bill_no: json.loads(json.dumps(_ohne_adresse))
    opera.empfaenger = lambda bill_no: []
    # Die Detailseite fragt VOR den Rechnungsdaten Profil, Vorpruefung und
    # Buchungsfirma ab. Ohne Datenbank brach sie dort ab, rechnete gar nichts —
    # und die Pruefungen unten waren gruen, weil eine leere Seite weder BT-49
    # meldet noch den Knopf sperrt. Sie konnten nicht rot werden.
    _echt_pr, _echt_pf, _echt_bf = opera.profil, opera.pruefung, opera.buchungsfirma
    opera.profil = lambda cfg, bill_no: {}
    opera.pruefung = lambda cfg, bill_no: {}
    opera.buchungsfirma = lambda bill_no: {}
    store.rechnung_anlegen({"bill_no": 1400003, "resort": "IHRHAUS", "invoice_no": "1",
                            "issuedate": "2026-07-13", "total_net": 3450.44,
                            "total_gross": 3688.57, "kunde": "Beispiel GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    try:
        # Ohne gewaehlten Empfaenger: BT-49 fehlt, und das gehoert gemeldet.
        store.setzen(1400003, empfaenger="", status="neu")
        _d = _ablauf.rechnungsdaten(cfg, 1400003)
        pruefe(any("BT-49" in h for h in xml_build.pruefsummen(_d)),
               "ohne Empfaenger fehlt BT-49 — und das wird gesagt")
        # Nach dem Eintragen der Adresse muss der Befund weg sein, auf
        # demselben Weg, den auch die Erzeugung geht.
        store.setzen(1400003, empfaenger="rechnung@musterhotel.example", status="bereit")
        _d = _ablauf.rechnungsdaten(cfg, 1400003)
        pruefe(_d["header"]["customerendpointid"] == "rechnung@musterhotel.example",
               "die eingetragene Adresse wird zu BT-49")
        pruefe(not any("BT-49" in h for h in xml_build.pruefsummen(_d)),
               "und der Befund ist weg")
        seite = klient.get("/rechnung/1400003")
        pruefe("OPERA-Zugriff" not in seite.text and "Accommodation 7%" in seite.text,
               "die Detailseite hat die Rechnungsdaten wirklich gerechnet")
        pruefe("BT-49" not in seite.text,
               "die Detailseite meldet BT-49 nicht mehr als fehlend")
        _knopf = [z for z in seite.text.splitlines() if 'class="haupt"' in z and "button" in z]
        pruefe(bool(_knopf) and "disabled" not in _knopf[0],
               f"und der Versandknopf ist freigeschaltet ({(_knopf or ['kein Knopf'])[0].strip()[:70]})")
    finally:
        opera.rechnung, opera.empfaenger = _echt_r, _echt_e
        opera.profil, opera.pruefung, opera.buchungsfirma = _echt_pr, _echt_pf, _echt_bf
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no = 1400003")

    # Die Pflegeliste: 126 von 438 Belegen haben nirgends eine Adresse. Das
    # ist Handarbeit im Haus, und sie wird nach PROFIL erledigt, nicht nach
    # Rechnung — ein Profil traegt oft mehrere. Deshalb wird gebuendelt.
    store.rechnung_anlegen({"bill_no": 950001, "resort": "IHRHAUS", "invoice_no": "A",
                            "issuedate": "2026-09-02", "total_net": 100.0,
                            "total_gross": 119.0, "kunde": "Muster; GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    store.rechnung_anlegen({"bill_no": 950002, "resort": "IHRHAUS", "invoice_no": "B",
                            "issuedate": "2026-09-01", "total_net": 200.0,
                            "total_gross": 238.0, "kunde": "Muster; GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    store.rechnung_anlegen({"bill_no": 950003, "resort": "IHRHAUS", "invoice_no": "C",
                            "issuedate": "2026-09-03", "total_net": 50.0,
                            "total_gross": 59.5, "kunde": "Hat Adresse GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    # Zwei Belege desselben Profils, einer eines anderen — und ein vierter
    # ohne Kundennamen. Ueber den NAMEN gebuendelt landeten der und der andere
    # namenlose in einem Topf; ueber die Profilnummer nicht.
    store.rechnung_anlegen({"bill_no": 950004, "resort": "IHRHAUS", "invoice_no": "D",
                            "issuedate": "2026-09-04", "total_net": 10.0,
                            "total_gross": 11.9, "kunde": "",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    store.setzen(950001, name_id=4711)
    store.setzen(950002, name_id=4711)
    store.setzen(950003, name_id=4712)
    store.setzen(950004, name_id=4713)
    # Die Marke im Fehlerfeld darf KEINE Rolle spielen: Auf der Anlage war die
    # Liste leer, weil die Belege vor der Einfuehrung des Vermerks eingelesen
    # worden waren. Deshalb tragen die Testbelege hier auch keinen.
    _echt_e2 = opera.empfaenger
    opera.empfaenger = lambda bill_no: (
        [{"email": "da@beispiel.de"}] if bill_no == 950003 else [])
    _echt_pn = opera.profil_name
    opera.profil_name = lambda name_id: "Am Profil GmbH" if name_id == 4713 else ""
    try:
        _csv = klient.get("/pflegeliste.csv")
        pruefe(_csv.status_code == 200, "die Pflegeliste laesst sich abrufen")
        _zeilen = _csv.text.lstrip("\ufeff").strip().splitlines()
        pruefe(len(_zeilen) == 3,
               f"zwei Profile, zwei Zeilen — nicht je Rechnung ({_zeilen})")
        pruefe("950001 950002" in _zeilen[1],
               f"beide Rechnungen des Profils stehen zusammen ({_zeilen[1]})")
        pruefe(_zeilen[1].startswith("4711;"), "die Profilnummer steht dabei")
        pruefe(_zeilen[1].count(";") == 5,
               f"das Semikolon im Firmennamen verschiebt die Spalten nicht ({_zeilen[1]})")
        pruefe("357.00" in _zeilen[1], "die Summe der offenen Betraege stimmt")
        pruefe("2026-09-01" in _zeilen[1], "und das aelteste Datum zeigt, wie lange es liegt")
        pruefe("Hat Adresse GmbH" not in _csv.text,
               "wer eine Adresse hat, steht nicht drin — auch ohne Vermerk im Bestand")
        pruefe("950004" in _csv.text, "der Beleg ohne Kundennamen bleibt fuer sich")
        # Fehlt der Name auf dem Beleg, wird er am PROFIL nachgeschlagen —
        # sonst sucht der Empfang nach einer Nummer statt nach einem Kunden.
        pruefe("Am Profil GmbH" in _csv.text,
               f"der Name kommt dann vom Profil ({_zeilen})")
        pruefe(_csv.text.startswith("\ufeff"), "mit BOM, damit Excel die Umlaute anzeigt")
        # Eine Stoerung ist kein Pflegefall: Sie darf niemanden zu einem
        # Profil schicken, an dem nichts fehlt.
        opera.empfaenger = lambda bill_no: (_ for _ in ()).throw(
            RuntimeError("ORA-12170: TNS:Connect timeout"))
        _csv2 = klient.get("/pflegeliste.csv")
        pruefe("nicht geprüft" in _csv2.text and "4711" not in _csv2.text,
               f"bei gestoerter Datenbank meldet die Liste das, statt Profile zu nennen")
    finally:
        opera.empfaenger, opera.profil_name = _echt_e2, _echt_pn
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no >= 950001")
    _leer = klient.get("/")
    pruefe("ohne Adresse" not in _leer.text,
           "ist nichts zu pflegen, steht der Knopf auch nicht da")

    # Eine VERSENDETE Rechnung darf nicht beilaeufig neu erzeugt werden. Vorher
    # schrieb jeder Aufruf die Datei neu — auch das blosse ANSEHEN des XML,
    # denn die Anzeige geht durch dieselbe Funktion. Danach lag dort etwas
    # anderes als beim Kunden, und niemand konnte es sehen.
    _echt_rd2 = ablauf.rechnungsdaten
    ablauf.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(rechnung))
    store.rechnung_anlegen({"bill_no": 980001, "resort": "IHRHAUS", "invoice_no": "V",
                            "issuedate": "2026-09-05", "total_net": 100.0,
                            "total_gross": 119.0, "kunde": "Versendet GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    try:
        _cfg_v = json.loads(json.dumps(cfg))
        _cfg_v["validierung"]["aktiv"] = False
        _xml1, _pfad1, _ = ablauf.xml_erzeugen(_cfg_v, 980001)
        pruefe(store.rechnung(980001).get("xrechnung_version") == "3.0.2",
               "die Erzeugung haelt fest, in welcher XRechnung-Version die Datei steht")
        _cfg_x = json.loads(json.dumps(_cfg_v))
        _cfg_x["xrechnung"] = {"version": "4.0"}
        _vorher_bytes = _pfad1.read_bytes()
        try:
            ablauf.xml_erzeugen(_cfg_x, 980001)
            pruefe(False, "mit einer unbekannten Version entsteht keine Datei")
        except xml_build.XmlFehler:
            pruefe(_pfad1.read_bytes() == _vorher_bytes,
                   "mit einer unbekannten Version entsteht keine Datei, die alte bleibt")
        # Den Ordner von der Anwendung nennen lassen, nicht selbst ausrechnen:
        # Der Test rechnete ihn gegen das PROGRAMM aus und lag daneben, sobald
        # Programm und Bestand auseinanderfallen — genau der Fehler, den die
        # Trennung verhindern soll.
        _archiv = ablauf._ordner(_cfg_v, "archiv_ordner")
        (_archiv / "980001.xml").write_bytes(b"<Invoice>so ging sie raus</Invoice>")
        store.setzen(980001, status="gesendet", gesendet_am="2026-09-09T16:13:00")
        # Ansehen darf die Datei nicht ersetzen — und muss zeigen, was raus ging.
        _xml2, _pfad2, _ = ablauf.xml_erzeugen(_cfg_v, 980001)
        pruefe(_xml2 == b"<Invoice>so ging sie raus</Invoice>",
               "eine versendete Rechnung kommt aus dem Archiv, nicht neu gebaut")
        pruefe(_pfad1.read_bytes() == _xml1,
               "und die abgelegte Datei bleibt unveraendert")
        _antwort = klient.post("/rechnung/980001/xml", follow_redirects=False)
        # Der Ort ist URL-kodiert, die Leerzeichen also nicht als solche da.
        _ort = _antwort.headers.get("location", "")
        pruefe("versendet" in _ort and "Trotzdem" in _ort,
               f"der Knopf sagt es, statt stillschweigend zu ersetzen ({_ort[:80]})")
        pruefe(_pfad1.read_bytes() == _xml1, "auch nach dem Knopfdruck")
        # Wer es ausdruecklich will, kann es trotzdem.
        klient.post("/rechnung/980001/xml", data={"ersetzen": "1"}, follow_redirects=False)
        pruefe(_pfad1.exists(), "mit ausdruecklicher Bestaetigung wird neu erzeugt")
        _seite = klient.get("/rechnung/980001")
        pruefe("Trotzdem neu erzeugen" in _seite.text,
               "und die Detailseite bietet genau diesen Weg an")
    finally:
        ablauf.rechnungsdaten = _echt_rd2
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no = 980001")

    # Die Wahl der Darstellung auf der Detailseite: gespeichert, sichtbar, und
    # die Seite zeigt die Positionen, die auch hinausgehen.
    store.rechnung_anlegen({"bill_no": 970001, "resort": "IHRHAUS", "invoice_no": "P",
                            "issuedate": "2026-09-05", "total_net": 100.0,
                            "total_gross": 107.0, "kunde": "Gruppe GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    _echt_r3 = opera.rechnung
    _zwei_gaeste = json.loads(json.dumps(rechnung))
    _zwei_gaeste["header"]["gastname"] = "Musterfrau, Lena"
    _zwei_gaeste["lines"] = [
        {"trx_no": 1, "itemcode": "1000", "itemname": "Übernachtung", "invoicedquantity": 1,
         "lineextensionamountnet": 201.95, "lineextensionamount": 216.09,
         "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7,
         "bruttopreis": 216.09, "gast_resv_name_id": 501, "gast_zimmer": "214",
         "gast_name": "Musterfrau, Lena"},
        {"trx_no": 2, "itemcode": "1000", "itemname": "Übernachtung", "invoicedquantity": 1,
         "lineextensionamountnet": 201.95, "lineextensionamount": 216.09,
         "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7,
         "bruttopreis": 216.09, "gast_resv_name_id": 502, "gast_zimmer": "215",
         "gast_name": "Beispiel, Max"}]
    opera.rechnung = lambda cfg, bill_no: json.loads(json.dumps(_zwei_gaeste))
    _echt_e3 = opera.empfaenger
    opera.empfaenger = lambda bill_no: []
    _echt_pr3, _echt_pf3, _echt_bf3 = opera.profil, opera.pruefung, opera.buchungsfirma
    opera.profil = lambda cfg, bill_no: {}
    opera.pruefung = lambda cfg, bill_no: {}
    opera.buchungsfirma = lambda bill_no: {}
    try:
        _s = klient.get("/rechnung/970001")
        pruefe("OPERA-Zugriff" not in _s.text,
               "Detailseite: die Rechnungsdaten sind gerechnet, nicht abgebrochen")
        pruefe("Zi. 214 · Musterfrau, Lena" in _s.text and "automatisch: 2 Reservierungen" in _s.text,
               "Detailseite: zwei Gaeste — je Gast vorbelegt, mit Begruendung")
        _a = klient.post("/rechnung/970001/positionen", data={"art": "B"}, follow_redirects=False)
        pruefe(_a.status_code == 303 and store.rechnung(970001)["positionen"] == "B",
               "die Wahl wird gespeichert")
        _s = klient.get("/rechnung/970001")
        pruefe("Zi. 214" not in _s.text and "von Hand gewählt" in _s.text
               and "Vorbelegung wiederherstellen" in _s.text,
               "und die Seite zeigt danach die zusammengefasste Fassung")
        _ablauf.rechnungsdaten(cfg, 970001)  # derselbe Weg wie die Erzeugung
        pruefe(len(_ablauf.rechnungsdaten(cfg, 970001)["lines"]) == 1,
               "die Erzeugung sieht dieselbe Wahl: eine Position")
        klient.post("/rechnung/970001/positionen", data={"art": "Z"}, follow_redirects=False)
        pruefe(store.rechnung(970001)["positionen"] == "B",
               "ein unbekannter Wert wird abgelehnt, die Wahl bleibt")
        klient.post("/rechnung/970001/positionen", data={"art": ""}, follow_redirects=False)
        pruefe(not store.rechnung(970001)["positionen"],
               "leer stellt die Vorbelegung wieder her")
        # Nur wer versenden darf, bestimmt, wie die Rechnung aussieht — und
        # welche Kaeuferreferenz darauf steht. Vorher durfte das jedes Konto.
        auth.anlegen("leser", "Nur-Lesen!42", "ansehen")
        _leser = {"sitzung": auth.anmelden("leser", "Nur-Lesen!42", "127.0.0.1")}
        _a = klient.post("/rechnung/970001/positionen", data={"art": "A"},
                         cookies=_leser, follow_redirects=False)
        pruefe("Berechtigung" in _a.headers.get("location", "")
               and not store.rechnung(970001)["positionen"],
               "ein Konto mit Leserecht kann die Darstellung nicht umschalten")
        _a = klient.post("/rechnung/970001/buyerreference", data={"frei": "PO-LESER"},
                         cookies=_leser, follow_redirects=False)
        pruefe("Berechtigung" in _a.headers.get("location", "")
               and not store.rechnung(970001).get("buyerreference"),
               "und auch die Käuferreferenz nicht")
        _a = klient.post("/rechnung/970001/buyerreference", data={"frei": "PO-4711"},
                         follow_redirects=False)
        pruefe(store.rechnung(970001).get("buyerreference") == "PO-4711",
               "mit Verwaltungsrecht geht beides weiterhin")
        auth.loeschen("leser")
        # Eine Rechnung, die nicht in der Arbeitsliste steht: keine Erfolgsmeldung
        # fuer eine Wahl, die nirgends gespeichert wird.
        _vorher = len(store.protokoll_lesen(500, 970099))
        _a = klient.post("/rechnung/970099/positionen", data={"art": "C"}, follow_redirects=False)
        pruefe("Arbeitsliste" in _a.headers.get("location", "")
               and len(store.protokoll_lesen(500, 970099)) == _vorher,
               "ausserhalb der Arbeitsliste: Hinweis statt Erfolgsmeldung, kein Protokolleintrag")
        # Versendet: Die Seite sagt, dass die Tabelle neu gerechnet ist.
        store.setzen(970001, status="gesendet", gesendet_am="2026-09-10T16:13:00",
                     xrechnung_version="3.0.2")
        _s = klient.get("/rechnung/970001")
        pruefe("neu gerechnet" in _s.text and "XRechnung 3.0.2" in _s.text,
               "bei einer versendeten Rechnung verweist die Seite auf die abgelegte Fassung")
        pruefe(any(p["aktion"] == "positionen" for p in store.protokoll_lesen(20, 970001)),
               "die Wahl steht im Verlauf der Rechnung")
    finally:
        opera.rechnung, opera.empfaenger = _echt_r3, _echt_e3
        opera.profil, opera.pruefung, opera.buchungsfirma = _echt_pr3, _echt_pf3, _echt_bf3
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no = 970001")

    # --- Befunde aus dem Code-Review vom 14.09.2026: Oberflaeche --------------
    from urllib.parse import unquote as _uq
    from app import automatik as _automatik, db
    _echt_r12, _echt_e12 = opera.rechnung, opera.empfaenger
    _echt_pr12, _echt_pf12, _echt_bf12 = opera.profil, opera.pruefung, opera.buchungsfirma
    opera.rechnung = lambda cfg, bill_no: json.loads(json.dumps(rechnung))
    opera.empfaenger = lambda bill_no: [{"email": "a@firma.example", "quelle": "Profil", "rolle": "Zahler"},
                                        {"email": "b@firma.example", "quelle": "Profil", "rolle": "Zahler"}]
    opera.profil = lambda cfg, bill_no: {}
    opera.pruefung = lambda cfg, bill_no: {}
    opera.buchungsfirma = lambda bill_no: {}
    store.rechnung_anlegen({"bill_no": 970020, "resort": "IHRHAUS", "kunde": "Formular GmbH",
                            "total_gross": 3688.57}, 0)
    auth.anlegen("leser2", "Nur-Lesen!42", "ansehen")
    _l2 = {"sitzung": auth.anmelden("leser2", "Nur-Lesen!42", "127.0.0.1")}
    try:
        # Befund 3: Die Auswahl gewinnt gegen das (leere) Freitextfeld.
        store.setzen(970020, empfaenger="a@firma.example", status="neu")
        _s = klient.get("/rechnung/970020")
        pruefe('name="frei" value=""' in _s.text, "B3: das Freitextfeld ist nicht mit dem alten Empfaenger vorbelegt")
        klient.post("/rechnung/970020/empfaenger", data={"email": "b@firma.example", "frei": ""},
                    follow_redirects=False)
        pruefe(store.rechnung(970020)["empfaenger"] == "b@firma.example",
               "B3: eine andere Adresse anklicken speichert diese Adresse")
        klient.post("/rechnung/970020/empfaenger", data={"email": "", "frei": ""}, follow_redirects=False)
        pruefe(not store.rechnung(970020)["empfaenger"], "B3: der Empfaenger laesst sich entfernen")
        _a = klient.post("/rechnung/970020/empfaenger", data={"frei": "x@a.example; y@b.example"},
                         follow_redirects=False)
        pruefe(not store.rechnung(970020)["empfaenger"] and "gültige" in _uq(_a.headers.get("location", "")),
               "B19: zwei Adressen in einem Feld werden nicht gespeichert")
        klient.post("/rechnung/970020/buyerreference", data={"wert": "PO-1", "frei": ""}, follow_redirects=False)
        pruefe(store.rechnung(970020)["buyerreference"] == "PO-1", "B3: bei BT-10 gewinnt die Auswahl ebenso")
        klient.post("/rechnung/970020/buyerreference", data={"wert": "", "frei": ""}, follow_redirects=False)
        pruefe(not store.rechnung(970020)["buyerreference"], "B3: und 'automatisch' stellt BT-10 zurueck")
        # Befund 49: Ein Empfaenger gibt die Sichtpruefung nicht frei.
        store.setzen(970020, status="pruefung", fehler="Firma hängt an der Reservierung")
        klient.post("/rechnung/970020/empfaenger", data={"email": "a@firma.example"}, follow_redirects=False)
        _r = store.rechnung(970020)
        pruefe(_r["status"] == "pruefung" and _r["empfaenger"] == "a@firma.example",
               f"B49: ein Empfaenger holt den Beleg nicht aus der Pruefung ({_r['status']})")
        _a = klient.post("/rechnung/970020/freigeben", cookies=_l2, follow_redirects=False)
        pruefe(store.rechnung(970020)["status"] == "pruefung", "B49: Freigeben nur mit Verwaltungsrecht")
        klient.post("/rechnung/970020/freigeben", follow_redirects=False)
        pruefe(store.rechnung(970020)["status"] == "bereit" and any(
            p["aktion"] == "freigegeben" for p in store.protokoll_lesen(20, 970020)),
            "B49: 'Prüfung abgeschlossen' gibt frei und vermerkt es")
        store.setzen(970020, status="fehler", fehler=ablauf.VERSAND_OFFEN)
        klient.post("/rechnung/970020/freigeben", follow_redirects=False)
        pruefe(store.rechnung(970020)["status"] == "fehler",
               "B47: ein Versand mit offenem Ergebnis laesst sich nicht einfach freigeben")
        # Befund 9: Rechte je Aktion
        store.setzen(970020, status="bereit", fehler=None)
        for _pfad, _daten in (("/rechnung/970020/zuruecklegen", {}), ("/aufnehmen", {"bill_no": "970020"}),
                              ("/einlesen", {"tage": "365"}), ("/rechnung/970020/xml", {"ersetzen": "1"}),
                              ("/konfiguration/dbtest", {}), ("/update/pruefen", {})):
            _a = klient.post(_pfad, data=_daten, cookies=_l2, follow_redirects=False)
            pruefe("Berechtigung" in _uq(_a.headers.get("location", "")),
                   f"B9: {_pfad} braucht Verwaltungsrecht")
        pruefe(store.rechnung(970020)["status"] == "bereit", "B9: der Leser hat nichts zurueckgelegt")
        _s = klient.get("/", cookies=_l2)
        pruefe('action="/einlesen"' not in _s.text, "B9: der Leser sieht den Einlese-Knopf nicht")
        # Zuruecklegen und wieder aufnehmen
        store.setzen(970020, status="gesendet")
        klient.post("/rechnung/970020/zuruecklegen", follow_redirects=False)
        pruefe(store.rechnung(970020)["status"] == "gesendet", "B9: eine versendete Rechnung wird nicht zurueckgelegt")
        store.setzen(970020, status="bereit")
        klient.post("/rechnung/970020/zuruecklegen", follow_redirects=False)
        klient.post("/rechnung/970020/wieder_aufnehmen", follow_redirects=False)
        pruefe(store.rechnung(970020)["status"] == "pruefung", "eine zurueckgelegte Rechnung laesst sich wieder aufnehmen — in die Pruefung")
        # Befund 7: GET xml.xml schreibt nichts
        store.setzen(970020, fehler="Grund bleibt", pruefbefund=None, xml_pfad=None)
        klient.get("/rechnung/970020/xml.xml")
        _r = store.rechnung(970020)
        pruefe(_r["fehler"] == "Grund bleibt" and not _r["xml_pfad"], "B7: 'XML ansehen' veraendert nichts")
        # Befund 29: offene Weiterleitung
        from app.main import _zurueck
        pruefe(all(_zurueck(w) == "/" for w in ("/\\evil.example", "/\t/evil.example", "//evil", "/x:y")),
               "B29: keine Weiterleitung auf fremde Seiten")
        pruefe(_zurueck("/?status=pruefung&sortieren=kunde") == "/?status=pruefung&sortieren=kunde",
               "B29: eigene Listenadressen bleiben erlaubt")
        # Befund 39: Zugangsname im JavaScript
        _s = klient.get("/benutzer")
        pruefe("this.dataset.frage" in _s.text and "confirm('Zugang" not in _s.text,
               "B39: der Zugangsname steht nicht im JavaScript")
        # Befund 36: Konfigurationseingaben
        _vor = config.laden()
        _a = klient.post("/konfiguration", data={"automatik.wartezeit_minuten": "49,90x"}, follow_redirects=False)
        pruefe(_a.status_code == 303 and "keine Zahl" in _uq(_a.headers.get("location", "")),
               "B36: eine ungueltige Zahl gibt eine Meldung statt HTTP 500")
        klient.post("/konfiguration", data={"automatik.wartezeit_minuten": ""}, follow_redirects=False)
        pruefe(config.laden()["automatik"]["wartezeit_minuten"] == _vor["automatik"]["wartezeit_minuten"],
               "B36: eine geleerte Wartezeit wird nicht zu 0")
        _a = klient.post("/konfiguration", data={"server.erlaubte_netze": "10.0.0.0/33"}, follow_redirects=False)
        pruefe("kein gültiges Netz" in _uq(_a.headers.get("location", "")), "B36: ein ungueltiges Netz wird abgelehnt")
        _a = klient.post("/konfiguration", data={"server.erlaubte_netze": "10.0.0.0/8"}, follow_redirects=False)
        pruefe("ausgesperrt" in _uq(_a.headers.get("location", ""))
               and config.laden()["server"]["erlaubte_netze"] == _vor["server"]["erlaubte_netze"],
               "B36: wer sich selbst aussperren wuerde, speichert nicht")
        # Befund 16: Automatik folgt dem Schalter der Konfigurationsseite
        _automatik.stoppen()
        klient.post("/konfiguration", data={"_schalter": "automatik.aktiv", "automatik.aktiv": "1",
                                            "automatik.testlauf": "1"}, follow_redirects=False)
        pruefe(_automatik.zustand()["laeuft"], "B16: 'Automatik eingeschaltet' startet sie sofort")
        klient.post("/konfiguration", data={"_schalter": "automatik.aktiv"}, follow_redirects=False)
        pruefe(not _automatik.zustand()["laeuft"], "B16: und ausgeschaltet haelt sie an")
        # Ein laufender Automatiklauf: sichtbar, und die Knoepfe, die sonst
        # ins Leere liefen, sind gesperrt.
        _automatik._laeuft.set()
        try:
            _s = klient.get("/rechnung/970020")
            pruefe("Automatik arbeitet" in _s.text and "so lange gesperrt" in _s.text,
                   "ein laufender Automatiklauf steht in der Kopfzeile und im Hinweis")
            pruefe(_automatik.zustand()["arbeitet"], "und der Zustand sagt es ebenfalls")
            _a = klient.post("/einlesen", data={"tage": "30"}, follow_redirects=False)
            pruefe("Automatiklauf arbeitet gerade" in _uq(_a.headers.get("location", "")),
                   "Einlesen sagt, dass gerade ein Lauf arbeitet")
            _a = klient.post("/automatik/jetzt", follow_redirects=False)
            pruefe("Automatiklauf arbeitet gerade" in _uq(_a.headers.get("location", "")),
                   "ein zweiter Durchlauf wird nicht angestossen")
            store.setzen(970020, status="bereit", empfaenger="a@firma.example")
            _a = klient.post("/rechnung/970020/senden", follow_redirects=False)
            pruefe("Automatiklauf arbeitet gerade" in _uq(_a.headers.get("location", ""))
                   and store.rechnung(970020)["status"] == "bereit",
                   "und der Versand von Hand wartet nicht stumm, sondern sagt es")
        finally:
            _automatik._laeuft.clear()
        # Und ohne laufenden Lauf ist alles wieder frei.
        _s = klient.get("/rechnung/970020")
        pruefe("Automatik arbeitet" not in _s.text, "danach ist der Hinweis wieder weg")

        # N3: Ein Versand mit offenem Ergebnis laesst sich klaeren.
        store.setzen(970020, status="fehler", fehler=ablauf.VERSAND_OFFEN, empfaenger="a@firma.example")
        _s = klient.get("/rechnung/970020")
        pruefe("Ist die Mail hinausgegangen?" in _s.text, "N3: die Seite fragt nach dem Ergebnis")
        klient.post("/rechnung/970020/versand_klaeren", data={"ergebnis": "nicht_gesendet"},
                    follow_redirects=False)
        _r = store.rechnung(970020)
        pruefe(_r["status"] == "bereit" and ablauf.VERSAND_OFFEN not in (_r["fehler"] or ""),
               f"N3: 'nichts ging hinaus' gibt die Rechnung wieder frei ({_r['status']})")
        store.setzen(970020, status="fehler", fehler=ablauf.VERSAND_OFFEN)
        klient.post("/rechnung/970020/versand_klaeren", data={"ergebnis": "gesendet"},
                    follow_redirects=False)
        _r = store.rechnung(970020)
        pruefe(_r["status"] == "gesendet" and _r["gesendet_am"],
               "N3: 'die Mail ist raus' vermerkt sie als versendet, ohne sie erneut zu schicken")
        _a = klient.post("/rechnung/970020/versand_klaeren", data={"ergebnis": "gesendet"},
                         cookies=_l2, follow_redirects=False)
        pruefe("Berechtigung" in _uq(_a.headers.get("location", "")), "N3: nur mit Verwaltungsrecht")
        store.setzen(970020, status="neu", fehler=None, gesendet_am=None)
        # N9: Pflicht ohne Validierung ist eine Falle.
        _a = klient.post("/konfiguration", data={"_schalter": "validierung.aktiv,validierung.pflicht",
                                                 "validierung.pflicht": "1"}, follow_redirects=False)
        pruefe("NICHT GESPEICHERT" in _uq(_a.headers.get("location", ""))
               and config.laden()["validierung"]["aktiv"],
               "N9: 'Pflicht' ohne eingeschaltete Validierung wird nicht gespeichert")
        # N5: Kein Datenbanktest mitten im Automatiklauf.
        _automatik._laeuft.set()
        try:
            _a = klient.post("/konfiguration/dbtest", follow_redirects=False)
            pruefe("Automatiklauf arbeitet gerade" in _uq(_a.headers.get("location", "")),
                   "N5: der Datenbanktest wartet, statt dem Lauf die Verbindung wegzunehmen")
            _abbrueche = []
            _echt_stop = db.stop
            db.stop = lambda: _abbrueche.append(1)
            try:
                klient.post("/konfiguration", data={"mail.bcc": "kopie@haus.example"},
                            follow_redirects=False)
                pruefe(not _abbrueche, "N5: auch das Speichern trennt die Verbindung dann nicht")
            finally:
                db.stop = _echt_stop
        finally:
            _automatik._laeuft.clear()

        # Befund 40: Formeln in der Pflegeliste
        store.setzen(970020, status="neu", empfaenger=None, kunde="=HYPERLINK(\"http://x\")", name_id=5)
        opera.empfaenger = lambda bill_no: []
        _csv = klient.get("/pflegeliste.csv").text
        pruefe(";'=HYPERLINK" in _csv, "B40: ein Kundenname mit = wird in der Pflegeliste nicht als Formel ausgefuehrt")
    finally:
        opera.rechnung, opera.empfaenger = _echt_r12, _echt_e12
        opera.profil, opera.pruefung, opera.buchungsfirma = _echt_pr12, _echt_pf12, _echt_bf12
        auth.loeschen("leser2")
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no = 970020")

    # --- Suche: Arbeitsliste UND OPERA ------------------------------------
    # Wer eine Rechnungsnummer vom Kunden bekommt, sucht danach. Steht sie
    # nicht in der Arbeitsliste — zu alt fuers Zeitfenster, aussortiert oder nie
    # eingelesen —, waere sie in dieser Anwendung sonst unauffindbar.
    for _nr, _kunde, _empf in ((940001, "Suchbar GmbH", "a@suchbar.de"),
                               (940002, "Andere AG", "b@andere.de")):
        store.rechnung_anlegen({"bill_no": _nr, "resort": "IHRHAUS", "invoice_no": f"R-{_nr}",
                                "issuedate": "2026-09-07", "total_net": 100.0,
                                "total_gross": 119.0, "kunde": _kunde,
                                "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
        store.setzen(_nr, empfaenger=_empf)
    _echt_such = opera.suchen
    _stub_such = lambda cfg, begriff: (
        [{"bill_no": 940003, "invoice_no": "R-940003", "issuedate": "2026-05-02",
          "document_type": "INVOICE", "beleg_status": "OK", "total_net": 500.0,
          "total_gross": 595.0, "account_code": 4711, "name_id": 8888,
          "company_name": "Alt GmbH", "city_ledger": 0.0, "empfaenger_typ": "COMPANY",
          "empfaenger_land": "DE", "kunde": "Alt GmbH", "firmenbezug": "EMPFAENGER"},
         {"bill_no": 940001, "invoice_no": "R-940001", "issuedate": "2026-09-07",
          "document_type": "INVOICE", "beleg_status": "OK", "total_net": 100.0,
          "total_gross": 119.0, "account_code": None, "name_id": 7777,
          "company_name": "Suchbar GmbH", "city_ledger": 0.0, "empfaenger_typ": "COMPANY",
          "empfaenger_land": "DE", "kunde": "Suchbar GmbH", "firmenbezug": "EMPFAENGER"}]
        if "94000" in begriff else [])
    opera.suchen = _stub_such
    try:
        pruefe([r["bill_no"] for r in store.liste(suche="Suchbar")] == [940001],
               "die Suche findet den Kunden in der Arbeitsliste")
        pruefe([r["bill_no"] for r in store.liste(suche="940002")] == [940002],
               "und die Rechnungsnummer")
        pruefe([r["bill_no"] for r in store.liste(suche="b@andere")] == [940002],
               "und die Empfängeradresse")
        pruefe(store.liste(suche="gibtesnicht") == [], "ein Fehlgriff liefert nichts")
        _s = klient.get("/?suche=940001")
        pruefe("In OPERA gefunden" in _s.text, "die Seite zeigt auch die OPERA-Treffer")
        pruefe("steht schon in der Liste" in _s.text,
               "ein bereits bekannter Beleg wird als solcher gekennzeichnet")
        pruefe("940003" in _s.text and "In die Liste holen" in _s.text,
               "ein unbekannter bekommt einen Knopf")
        # Eine Suche ohne Ziffern fragt OPERA gar nicht erst — dort wird nach
        # Nummern gesucht, nicht nach Namen.
        _s2 = klient.get("/?suche=Suchbar")
        pruefe("In OPERA gefunden" not in _s2.text,
               "eine reine Namenssuche belastet OPERA nicht")
        # Und eine Stoerung in OPERA darf die Liste nicht mitreissen.
        opera.suchen = lambda cfg, begriff: (_ for _ in ()).throw(
            RuntimeError("ORA-12170: TNS:Connect timeout"))
        _s3 = klient.get("/?suche=940001")
        pruefe(_s3.status_code == 200 and "ORA-12170" in _s3.text,
               "faellt OPERA aus, bleibt die Arbeitsliste sichtbar und sagt es")
        # In die Liste holen: Anders als beim Einlesen wird NICHT gefiltert —
        # wer eine bestimmte Rechnung anfordert, soll sie bekommen. Wuerde sie
        # beim Einlesen durchfallen, kommt sie mit dem Grund in die
        # Sichtpruefung, statt stillschweigend zu verschwinden.
        opera.suchen = _stub_such
        opera.empfaenger = lambda bill_no: [{"email": "alt@altgmbh.de"}]
        _m = klient.post("/aufnehmen", data={"bill_no": "940003"}, follow_redirects=False)
        _neu = store.rechnung(940003)
        pruefe(_neu is not None, "die gefundene Rechnung landet in der Arbeitsliste")
        pruefe(_neu and _neu.get("empfaenger") == "alt@altgmbh.de",
               "samt gefundener Adresse")
        pruefe(_neu and _neu["status"] == "neu",
               f"eine unauffaellige Rechnung kommt normal an ({_neu and _neu['status']})")
        # Dieselbe Rechnung noch einmal: kein zweiter Datensatz.
        klient.post("/aufnehmen", data={"bill_no": "940003"}, follow_redirects=False)
        pruefe(len([r for r in store.liste() if r["bill_no"] == 940003]) == 1,
               "ein zweiter Versuch legt sie nicht doppelt an")
        # Und eine, die beim Einlesen durchgefallen waere: Ausland.
        opera.suchen = lambda cfg, begriff: [dict(_stub_such(cfg, begriff)[0],
                                                  bill_no=940004, empfaenger_land="US")]
        klient.post("/aufnehmen", data={"bill_no": "940004"}, follow_redirects=False)
        _aus = store.rechnung(940004)
        pruefe(_aus and _aus["status"] == "pruefung"
               and "Ausland" in (_aus.get("fehler") or ""),
               f"ein auslaendischer Beleg kommt in die Prüfung, nicht in den Versand "
               f"({_aus and _aus.get('fehler')})")
        pruefe(_aus and "Von Hand aufgenommen" in (_aus.get("fehler") or ""),
               "und es steht dabei, dass jemand ihn ausdruecklich geholt hat")
    finally:
        opera.suchen = _echt_such
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no >= 940001")

    # Filter: Beschriftung und Anzahl. Vorher stand dort der Datenbankwert.
    _f = klient.get("/")
    pruefe("Prüfung" in _f.text and ">pruefung<" not in _f.text,
           "der Filter ist richtig geschrieben")
    pruefe('class="anzahl"' in _f.text, "und nennt die Anzahl je Status")
    pruefe("Zurückgelegt" in _f.text, "auch 'ignoriert' heisst jetzt, was es bedeutet")

    # Sortierung: ueber Verweise, mit Positivliste. Der Spaltenname geht
    # unmaskiert in die Abfrage — alles andere waere eine Einschleusung.
    for _nr, _kunde, _datum in ((970001, "Zeta GmbH", "2026-09-01"),
                                (970002, "Alpha GmbH", "2026-09-03"),
                                (970003, "", "2026-09-02")):
        store.rechnung_anlegen({"bill_no": _nr, "resort": "IHRHAUS", "invoice_no": "S",
                                "issuedate": _datum, "total_net": 10.0,
                                "total_gross": 11.9, "kunde": _kunde,
                                "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    try:
        _auf = [r["bill_no"] for r in store.liste(sortieren="kunde", richtung="auf")]
        pruefe(_auf.index(970002) < _auf.index(970001),
               f"aufsteigend nach Kunde: Alpha vor Zeta ({_auf[:3]})")
        pruefe(_auf.index(970003) > _auf.index(970001),
               "und der leere Name steht hinten, nicht vorn")
        _ab = [r["bill_no"] for r in store.liste(sortieren="kunde", richtung="ab")]
        pruefe(_ab.index(970001) < _ab.index(970002), "absteigend andersherum")
        pruefe(_ab.index(970003) > _ab.index(970002),
               "der leere Name bleibt auch dann hinten")
        # Was nicht auf der Liste steht, wird ignoriert statt eingesetzt.
        _boese = store.liste(sortieren="kunde; DROP TABLE rechnungen--")
        pruefe(len(_boese) >= 3, "ein unbekannter Spaltenname sortiert nur nicht")
        pruefe(store.rechnung(970001) is not None,
               "und richtet keinen Schaden an")
        _seite = klient.get("/?sortieren=kunde&richtung=auf")
        pruefe("sortiert" in _seite.text and "▴" in _seite.text,
               "die Uebersicht zeigt, wonach gerade sortiert ist")
        pruefe(_seite.text.index("Alpha GmbH") < _seite.text.index("Zeta GmbH"),
               "und die Zeilen stehen wirklich in dieser Reihenfolge")
    finally:
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no >= 970001")

    # BT-10 von Hand: der einzige Weg fuer eine bereits abgerechnete Rechnung,
    # weil sich die Reservierung in OPERA nicht mehr aendern laesst.
    _echt_r2, _echt_e3 = opera.rechnung, opera.empfaenger
    _roh = json.loads(json.dumps(rechnung))
    _roh["header"].update(buyerreference="3000001", reservierungsnummer="3000001",
                          buyer_reference1=None, leitweg_id_vorhanden=None,
                          buyerreference_quelle="Ersatzwert: Reservierungsnummer")
    opera.rechnung = lambda cfg, bill_no: json.loads(json.dumps(_roh))
    opera.empfaenger = lambda bill_no: [{"email": "a@beispiel.de"}]
    store.rechnung_anlegen({"bill_no": 960001, "resort": "IHRHAUS", "invoice_no": "X",
                            "issuedate": "2026-09-05", "total_net": 100.0,
                            "total_gross": 119.0, "kunde": "Beispiel GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    try:
        _vorher = ablauf.rechnungsdaten(cfg, 960001)["header"]
        pruefe(_vorher["buyerreference"] == "3000001",
               "ohne Eintrag greift die Kette aus OPERA")
        klient.post("/rechnung/960001/buyerreference",
                    data={"frei": "PO-2026-4711"}, follow_redirects=False)
        _kopf = ablauf.rechnungsdaten(cfg, 960001)["header"]
        pruefe(_kopf["buyerreference"] == "PO-2026-4711",
               f"der eingetragene Wert gewinnt ({_kopf['buyerreference']})")
        pruefe(_kopf["buyerreference_quelle"] == "von Hand eingetragen",
               "und wird als solcher ausgewiesen")
        pruefe(not _kopf["buyerreference_quelle"].startswith("Ersatzwert"),
               "die Detailseite weist ihn damit NICHT als Platzhalter aus")
        # Er gewinnt auch gegen die Leitweg-ID: Wer bei einer Behoerdenrechnung
        # von Hand etwas anderes eintraegt, hat einen Grund — und sieht in der
        # Herkunft, was passiert ist. Umgekehrt traegt jemand etwas ein, es
        # wirkt nicht, und er sieht nicht warum.
        _roh["header"].update(buyerreference="991-33333TEST-33", leitweg_id_vorhanden=1)
        pruefe(ablauf.rechnungsdaten(cfg, 960001)["header"]["buyerreference"]
               == "PO-2026-4711", "auch gegen eine vorhandene Leitweg-ID")
        # Dieselbe Laengenregel wie am Reservierungsfeld — sonst gaelte sie
        # ausgerechnet fuer den Weg nicht, den ein Mensch benutzt.
        klient.post("/rechnung/960001/buyerreference",
                    data={"frei": "Bestellung des Kunden vom 3. September\n" * 4},
                    follow_redirects=False)
        _kopf = ablauf.rechnungsdaten(cfg, 960001)["header"]
        pruefe(len(_kopf["buyerreference"]) <= opera.BT10_LAENGE
               and "\n" not in _kopf["buyerreference"],
               f"auch von Hand wird gekuerzt ({len(_kopf['buyerreference'])} Zeichen)")
        pruefe(_kopf.get("buyerreference_gekuerzt"), "und die Kuerzung wird gemeldet")
        # Leeren stellt die Ermittlung wieder her
        klient.post("/rechnung/960001/buyerreference", data={"frei": ""},
                    follow_redirects=False)
        pruefe(ablauf.rechnungsdaten(cfg, 960001)["header"]["buyerreference"]
               == "991-33333TEST-33", "leeren gibt die automatische Ermittlung frei")
        _seite = klient.get("/rechnung/960001")
        pruefe("Käuferreferenz übernehmen" in _seite.text,
               "die Detailseite bietet das Feld an")
        pruefe("Buyer Reference1" in _seite.text and "vor dem Check-out" in _seite.text,
               "und sagt, wo es eigentlich gepflegt gehoert")
    finally:
        opera.rechnung, opera.empfaenger = _echt_r2, _echt_e3
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no = 960001")

    # Erscheinungsbild: Die Anwendung wird NEUTRAL ausgeliefert. Das eigene
    # Erscheinungsbild gehoert in den Bestand (branding/), nicht ins
    # Programm — dort ueberlebt es eine Aktualisierung.
    #
    # Was hier geprueft wird, ist nicht Geschmack, sondern zweierlei: dass
    # nichts von aussen nachgeladen wird, und dass die Ueberlagerung traegt.
    _css = klient.get("/static/stil.css")
    pruefe(_css.status_code == 200, "das Stylesheet wird ausgeliefert")
    import re as _re2
    # Nichts von aussen: Der Server hat nicht zwingend einen Weg ins Internet,
    # und ein Abruf bei Google verriete die IP jedes Arbeitsplatzes.
    pruefe(not _re2.search(r"(?i)@import|url\(\s*https?:", _css.text)
           and "fonts.googleapis" not in _css.text and "fonts.gstatic" not in _css.text,
           "das Stylesheet laedt nichts von aussen nach")
    # Geprueft wird die WIRKUNG, nicht der Text: Kommentare raus, dann muss
    # jede Variable noch da sein.
    #
    # Anlass: Ein Skript sollte den Variablenblock ersetzen, suchte ":root{"
    # und fand das BEISPIEL im Kopfkommentar. Es ersetzte die falsche Stelle,
    # verschluckte dabei das Kommentarende — und die ganze Palette lag stumm
    # im Kommentar. Die Oberflaeche verlor Kartenhintergrund und die Farben
    # fuer Fehler, Warnung und Erfolg. Aufgefallen ist es im Betrieb, nicht
    # hier: Die alte Pruefung suchte die Variablennamen im Rohtext, und dort
    # standen sie ja — nur eben auskommentiert.
    _ohne_kommentar = _re2.sub(r"/\*.*?\*/", "", _css.text, flags=_re2.S)
    pruefe(":root{" in _ohne_kommentar,
           "der Variablenblock steht ausserhalb jedes Kommentars")
    _fehlende = [_v for _v in ("--rand", "--grund", "--karte", "--text", "--gedaempft",
                               "--akzent", "--akzent-hell", "--kopf",
                               "--warn", "--fehler", "--ok",
                               "--schrift", "--schrift-titel")
                 if f"{_v}:" not in _ohne_kommentar]
    pruefe(not _fehlende,
           f"jede Vorgabevariable ist wirklich definiert ({_fehlende})")
    # Und was die Vorlagen benutzen, muss es auch geben.
    _benutzt = set(_re2.findall(r"var\((--[a-z-]+)\)", _css.text))
    _unbekannt = sorted(_v for _v in _benutzt if f"{_v}:" not in _ohne_kommentar)
    pruefe(not _unbekannt,
           f"keine Variable wird benutzt, die nirgends definiert ist ({_unbekannt})")
    # Nicht nur die Variablen: Beim Kommentarfehler lagen auch die
    # Grundregeln still — Kopfzeile ohne Hintergrund, Seite ohne Grundfarbe.
    # branding/ konnte das nicht auffangen, weil es nur Variablen setzt und
    # die Regeln sie nicht mehr verwendeten.
    _tote = [_s for _s in ("*{box-sizing", "body{", "header{", ".marke{", ".pille{",
                           ".karte{", "table{", ".knopf")
             if _s not in _ohne_kommentar]
    pruefe(not _tote, f"die Grundregeln stehen ausserhalb der Kommentare ({_tote})")
    # Ein grober Zaehler gegen genau diesen Fehlertyp: Ein verlorenes
    # Kommentarende verschluckt Dutzende Regeln auf einmal.
    _regeln = _ohne_kommentar.count("{")
    pruefe(_regeln >= 60, f"das Stylesheet hat noch seine Regeln ({_regeln})")
    pruefe("/static/schriften/" not in _css.text,
           "keine Schriften des Hauses im Programm — die liegen im Bestand")
    # Die Statusfarben sind Bedeutung, keine Gestaltung. Wer sie ans Branding
    # bindet, nimmt der Liste die Lesbarkeit.
    pruefe(all(f"--{n}:" in _css.text for n in ("ok", "fehler", "warn")),
           "die Statusfarben stehen getrennt von den Markenfarben")
    # LIZENZ: Die GPL verlangt, dass das Programm sie nennt. Bei einer
    # Weboberflaeche ist die Fusszeile der Ort dafuer.
    _start = klient.get("/").text
    pruefe("GPL v3" in _start and "gnu.org/licenses/gpl-3.0" in _start,
           "die Oberflaeche nennt ihre Lizenz")
    pruefe("AHORN Hotels" in _start, "und den Rechteinhaber")
    pruefe(updater.version() in _start,
           f"und den Stand ({updater.version()}) — sonst wird bei Rueckfragen geraten")
    _lizenz = (BASE / "LICENSE").read_text(encoding="utf-8")
    pruefe("GNU GENERAL PUBLIC LICENSE" in _lizenz and "Version 3" in _lizenz,
           "die Lizenzdatei liegt bei und ist die GPLv3")
    _readme = (BASE / "README.md").read_text(encoding="utf-8")
    pruefe("Copyright (C) 2026 AHORN Hotels" in _readme
           and "BITTE EINTRAGEN" not in _readme,
           "die README nennt den Rechteinhaber, ohne Platzhalter")
    # Die Ueberlagerung: nur eingebunden, wenn es sie gibt.
    _seite = klient.get("/").text
    _gibt_es = (pfade.BRANDING_DIR / "stil.css").is_file()
    pruefe(('/branding/stil.css' in _seite) == _gibt_es,
           f"eigenes Erscheinungsbild wird eingebunden, wenn es vorliegt (vorhanden={_gibt_es})")
    if _gibt_es:
        _b = klient.get("/branding/stil.css")
        pruefe(_b.status_code == 200 and ":root" in _b.text,
               "die eigene stil.css wird aus dem Bestand ausgeliefert")
        for _f in sorted((pfade.BRANDING_DIR / "schriften").glob("*.woff2"))[:4]:
            _a = klient.get(f"/branding/schriften/{_f.name}")
            pruefe(_a.status_code == 200 and _a.content[:4] == b"wOF2",
                   f"{_f.name} wird aus dem Bestand ausgeliefert")
    _kopf = klient.get("/").text
    pruefe('class="haus"' in _kopf, "die Kopfzeile nennt das Haus")

    # Ist die Quelle in der Unit festgenagelt, darf die Oberflaeche sie nicht
    # zum Bearbeiten anbieten — ein Feld, das keine Wirkung hat, ist schlimmer
    # als keines. Und ein untergeschobenes Formularfeld muss folgenlos bleiben.
    os.environ["XRECHNUNG_UPDATE_REPO"] = "aus/der-unit"
    os.environ["XRECHNUNG_UPDATE_ZWEIG"] = "aus-der-unit"
    try:
        _k = klient.get("/konfiguration")
        pruefe("aus/der-unit" in _k.text and 'name="update.repo"' not in _k.text,
               "die Oberflaeche zeigt die festgenagelte Quelle an, ohne Eingabefeld")
        _vorher_repo = config.laden()["update"]["repo"]
        klient.post("/konfiguration", data={"update.repo": "angreifer/boeses-repo"},
                    follow_redirects=False)
        pruefe(config.laden()["update"]["repo"] == _vorher_repo,
               "ein untergeschobenes Formularfeld aendert die Quelle nicht")
    finally:
        for _var in ("XRECHNUNG_UPDATE_REPO", "XRECHNUNG_UPDATE_ZWEIG"):
            os.environ.pop(_var, None)

    # Der Zurueck-Knopf, oben und unten. Sein Ziel kommt aus der Adresszeile
    # und landet in einem href — ohne Pruefung waere die Anwendung ein
    # Sprungbrett auf eine fremde Seite.
    _z = klient.get("/rechnung/1400003?zurueck=%2F%3Fstatus%3Dpruefung").text
    pruefe(_z.count('class="knopf zurueck"') == 2,
           f"der Zurueck-Knopf steht oben UND unten ({_z.count('knopf zurueck')})")
    pruefe('href="/?status=pruefung"' in _z,
           "und fuehrt in die Ansicht zurueck, aus der man kam")
    for _boese in ("//example.com", "https://example.com", "/x?a=b:c"):
        _b = klient.get(f"/rechnung/1400003?zurueck={_boese}").text
        pruefe("example.com" not in _b,
               f"'{_boese}' wird nicht als Ziel uebernommen")
    _ohne = klient.get("/rechnung/1400003").text
    pruefe('class="knopf zurueck" href="/"' in _ohne,
           "ohne Angabe fuehrt er auf die Liste")
    # Und die Liste gibt ihre Ansicht ueberhaupt mit — geprueft an einer
    # Ansicht, in der auch wirklich eine Zeile steht, sonst gibt es keinen
    # Verweis, an dem etwas haengen koennte.
    store.rechnung_anlegen({"bill_no": 930001, "resort": "IHRHAUS", "invoice_no": "Z",
                            "issuedate": "2026-09-06", "total_net": 10.0,
                            "total_gross": 11.9, "kunde": "Ansicht GmbH",
                            "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
    try:
        _l = klient.get("/?sortieren=kunde&richtung=auf").text
        pruefe("zurueck=" in _l and "sortieren%3Dkunde" in _l,
               "die Liste haengt ihre Ansicht an die Verweise")
    finally:
        with store.verbindung() as con:
            con.execute("DELETE FROM rechnungen WHERE bill_no = 930001")

    # Aufbau der Detailseite: Was man am haeufigsten braucht, soll oben stehen,
    # und was zusammengehoert, nebeneinander — statt alles untereinander.
    _d = klient.get("/rechnung/1400003").text
    if "aktionsleiste" in _d:
        pruefe(_d.index("aktionsleiste") < _d.index("<h2>Beleg</h2>"),
               "die Versandknoepfe stehen vor den Angaben zum Beleg")
        pruefe(_d.index("Wohin soll die Rechnung gehen?") < _d.index("Käuferreferenz"),
               "Empfaenger und Kaeuferreferenz stehen im selben Block")
        # Bis zum SCHLIESSENDEN div des Blocks zaehlen, nicht bis zum naechsten
        # Wort — "Positionen" kommt auch in einem Hinweistext vor.
        _ab = _d.index("vor-versand")
        _block = _d[_ab:_d.index("</div>", _d.index("</section>", _ab))]
        pruefe(_block.count("<section") == 2,
               f"und zwar als zwei Karten nebeneinander ({_block.count('<section')})")

    # Die Einrichtungsseite fuer die Leitweg-ID. Sie ist der Ersatz dafuer,
    # dass jedes Haus sonst im Data Dictionary nachsehen muesste — und genau
    # dabei ist der Fehler entstanden, der uns zwei Tage gekostet hat: das Feld
    # an der falschen Kartei.
    _e = klient.get("/einrichtung/leitweg")
    pruefe(_e.status_code == 200, "die Einrichtungsseite laedt")
    for _muss in ("Firmenkartei", "Screen Painter", "ACC_MAIN", "46 Zeichen",
                  "Mitgliedschaften"):
        pruefe(_muss in _e.text, f"die Anleitung nennt {_muss}")
    pruefe("Gastkartei" in _e.text,
           "und warnt vor der Verwechslung mit der Gastkartei")
    # Ohne Datenbank darf die Pruefung nicht die Seite mitreissen.
    _e2 = klient.get("/einrichtung/leitweg?pruefen=1")
    pruefe(_e2.status_code == 200 and "ging nicht" in _e2.text,
           "ohne Datenbank meldet die Feldpruefung das, statt abzustuerzen")
    # Speichern: nur gueltige Feldnamen.
    for _feld, _gilt in (("UDFC05", True), ("udfc07", True),
                         ("UDFC99", False), ("NAME", False), ("", True)):
        klient.post("/einrichtung/leitweg", data={"feld": _feld},
                    follow_redirects=False)
        _ist = config.laden()["property"].get("udf_leitweg", "")
        pruefe((_ist == _feld.upper()) is _gilt,
               f"'{_feld}' {'wird uebernommen' if _gilt else 'wird abgelehnt'} "
               f"(gespeichert: '{_ist}')")
    klient.post("/einrichtung/leitweg", data={"feld": ""}, follow_redirects=False)

    # Einrichtungsseite fuer die Anzahlungen. Sie ersetzt einen Knopf, der das
    # Ergebnis in eine Meldungszeile schrieb — eine Zeile ist der falsche Ort
    # fuer eine Auswahl: nicht lesbar, nicht vergleichbar, nichts uebernehmbar.
    _az = klient.get("/einrichtung/anzahlungen")
    pruefe(_az.status_code == 200, "die Einrichtungsseite fuer Anzahlungen laedt")
    for _muss in ("Belegstatus", "DEPOSIT", "Kopfbetrag", "Nullbeleg"):
        pruefe(_muss in _az.text, f"sie erklaert {_muss}")
    pruefe("Normalfall ist hier nichts einzustellen" in _az.text,
           "und sagt, dass im Normalfall nichts zu tun ist")
    # Ohne Datenbank darf die Abfrage die Seite nicht mitreissen.
    _az2 = klient.get("/einrichtung/anzahlungen?pruefen=1")
    pruefe(_az2.status_code == 200 and "ging nicht" in _az2.text,
           "ohne Datenbank meldet die Abfrage das, statt abzustuerzen")
    # Uebernehmen: Auswahl und Freitext, gross geschrieben, ohne Doppelte.
    klient.post("/einrichtung/anzahlungen",
                data={"code": ["8990", "8997"], "eigene": "dep1, 8997 dep2"},
                follow_redirects=False)
    _ist = config.laden()["auswahl"]["anzahlungscodes"]
    pruefe(_ist == ["8990", "8997", "DEP1", "DEP2"],
           f"Auswahl und Freitext werden zusammengefuehrt, ohne Doppelte ({_ist})")
    # Und die Codes wirken auch wirklich in der Abfrage.
    _mit = opera._mit_anzahlungscodes(opera._sql("invoice_guard.sql", config.laden()),
                                      config.laden())
    pruefe("'8990', '8997', 'DEP1', 'DEP2'" in _mit,
           "die uebernommenen Codes stehen danach in der Abfrage")
    # Leeres Formular heisst: nur der Belegstatus. Das muss sich zuruecknehmen
    # lassen, sonst ist die Seite eine Einbahnstrasse.
    klient.post("/einrichtung/anzahlungen", data={}, follow_redirects=False)
    pruefe(config.laden()["auswahl"]["anzahlungscodes"] == [],
           "und die Auswahl laesst sich wieder leeren")

    seite = klient.get("/rechnung/1400003")
    pruefe(seite.status_code == 200, "/rechnung/... laedt auch ohne Datenbank")
    pruefe("Datenbankverbindung" in seite.text or "Rechnung 1400003" in seite.text,
           "Detailseite meldet den fehlenden DB-Zugriff sauber")

# --- Rechnung MIT Anzahlung und Gutschriftsposition -------------------------
# Der Fall, an dem die drei Befunde vom 08.09. haengen. Er wird hier
# nachgestellt, weil ohne Anzahlung der BillingReference-Block leer bleibt und
# ohne negative Position kein Abschlag entsteht — beides Voraussetzung dafuer,
# dass die Fehler ueberhaupt auftreten koennen.
anzahlungsfall = {
    "bill_no": 1400019,
    "header": dict(rechnung["header"], billno=1400019,
                   prepaidamount=2250.40, payableamount=186.78),
    "lines": [
        {"itemname": "Accommodation 7%", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 2160.92, "lineextensionamount": 2312.18,
         "priceamount": 2160.92, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 7},
        {"itemname": "Parking 19%", "itemcode": "5200", "invoicedquantity": 1,
         "lineextensionamountnet": 150.00, "lineextensionamount": 178.50,
         "priceamount": 150.00, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 19},
        {"itemname": "Rabatt Firmenkunde", "itemcode": "9100", "invoicedquantity": 1,
         "lineextensionamountnet": -50.00, "lineextensionamount": -53.50,
         "priceamount": -50.00, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 7},
    ],
    "tax_breakdown": [
        {"taxcategorypercent": 7, "taxcategoryid": "S",
         "taxableamount": 2110.92, "taxamount": 147.76},
        {"taxcategorypercent": 19, "taxcategoryid": "S",
         "taxableamount": 150.00, "taxamount": 28.50},
    ],
    "totals": {"invoicenet": 2260.92, "invoicegross": 2437.18,
               "invoicetaxtotal": 176.26, "spay_cl": 0.0},
    "deposits": [{"billingreferenceid": 1400008,
                  "billingreferenceissuedate": "2026-06-30",
                  "total_net": 2103.18, "total_gross": 2250.40}],
    "kontrolle": {"kopf_netto": 157.74, "kopf_brutto": 186.78,
                  "anzahlung_netto": 2103.18, "anzahlung_brutto": 2250.40},
}

hinweise = xml_build.pruefsummen(anzahlungsfall)
pruefe(not hinweise, f"Anzahlungsfall: Vorpruefung sauber ({hinweise})")
xml_a = xml_build.bauen(anzahlungsfall).decode()

# Befund 10: UBL schreibt die Reihenfolge fest vor. Geprueft wird die
# Reihenfolge im erzeugten Dokument, nicht die im Template — sonst prueft man
# nur, dass man den Text so hingeschrieben hat, wie man ihn hinschreiben wollte.
pruefe("<cac:BillingReference>" in xml_a,
       "Anzahlungsfall: BillingReference wird ueberhaupt erzeugt")
pruefe("<cac:InvoicePeriod>" in xml_a,
       "Anzahlungsfall: InvoicePeriod wird ueberhaupt erzeugt")
pruefe(xml_a.index("<cac:InvoicePeriod>") < xml_a.index("<cac:BillingReference>"),
       "BT-10, BG-14, BG-3: InvoicePeriod steht vor BillingReference (UBL-Sequenz)")


def _betrag(text: str, tag: str):
    import re
    treffer = re.search(rf"<cbc:{tag}[^>]*>([-0-9.]+)</cbc:{tag}>", text)
    return float(treffer.group(1)) if treffer else None


line_ext = _betrag(xml_a, "LineExtensionAmount")
abzug = _betrag(xml_a, "AllowanceTotalAmount")
excl = _betrag(xml_a, "TaxExclusiveAmount")
incl = _betrag(xml_a, "TaxInclusiveAmount")
prepaid = _betrag(xml_a, "PrepaidAmount")
payable = _betrag(xml_a, "PayableAmount")

# Befund 11: BT-106 ist die Summe der PoSITIONEN. Steht dort weiter das
# Rechnungsnetto, enthaelt es den Abzug schon und BR-CO-13 geht nicht auf.
pruefe(line_ext == 2310.92,
       f"BR-CO-10: BT-106 ist die Summe der Positionen (2310.92, ist {line_ext})")
pruefe(abzug == 50.00,
       f"BR-CO-11: BT-107 wird ausgewiesen (50.00, ist {abzug})")
pruefe(excl == 2260.92,
       f"BR-CO-13: BT-109 = Positionen minus Abschlaege (2260.92, ist {excl})")
pruefe(incl is not None and round(incl - excl, 2) == 176.26,
       f"BR-CO-15: BT-112 - BT-109 ist die Steuersumme (ist {incl} / {excl})")
# Befund 9: prepaid und payable duerfen nicht aus verschiedenen Quellen kommen.
pruefe(prepaid == 2250.40, f"BT-113 ist der Anzahlungsbrutto (ist {prepaid})")
pruefe(payable is not None and round(incl - prepaid, 2) == payable,
       f"BR-CO-16: BT-115 = BT-112 - BT-113 (ist {payable})")

# Und derselbe Zusammenhang eine Ebene frueher, in der Datenaufbereitung:
# opera.rechnung() muss payableamount ableiten statt es getrennt zu bestimmen.
_quelle = (pathlib.Path(BASE / "app" / "opera.py")).read_text(encoding="utf-8")
pruefe('kopf["payableamount"] = round(totals["invoicegross"] - kopf["prepaidamount"], 2)'
       in _quelle,
       "opera.py leitet den Zahlbetrag aus Gesamtbetrag minus Anzahlung ab")

# --- Rundung und aufhebende Z-Positionen (Beleg 1400019) --------------------
# Nachgestellt nach den Zahlen der Beispiel Industrie-Rechnung: 20 krumme Positionen zu 7 %
# und ein Paar "Deposit Tax" in Kategorie Z, das sich aufhebt. Beides zusammen
# hat drei Schematron-Befunde erzeugt, und keiner davon war zu sehen, solange
# die Betraege glatt waren.
_rundungsfall = {
    "bill_no": 1400019,
    "header": dict(rechnung["header"], billno=1400019, prepaidamount=2419.18,
                   payableamount=0.0),
    "lines": (
        [{"itemname": f"Accommodation 7% Nacht {i+1}", "itemcode": "1000",
          "invoicedquantity": 1, "lineextensionamountnet": 113.0459,
          "lineextensionamount": 120.96, "priceamount": 113.0459,
          "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7}
         for i in range(20)]
        + [{"itemname": "Deposit Tax 7%", "itemcode": "8990", "invoicedquantity": 1,
            "lineextensionamountnet": 147.22, "lineextensionamount": 147.22,
            "priceamount": 147.22, "classifiedtaxcategoryid": "Z",
            "classifiedtaxcategorypercent": 7},
           {"itemname": "Deposit Tax 7%", "itemcode": "8990", "invoicedquantity": 1,
            "lineextensionamountnet": -147.22, "lineextensionamount": -147.22,
            "priceamount": -147.22, "classifiedtaxcategoryid": "Z",
            "classifiedtaxcategorypercent": 7}]),
    "tax_breakdown": [
        {"taxcategorypercent": 7, "taxcategoryid": "S",
         "taxableamount": 2260.92, "taxamount": 158.26},
    ],
    "totals": {"invoicenet": 2260.92, "invoicegross": 2419.18,
               "invoicetaxtotal": 158.26, "spay_cl": 0.0},
    "deposits": [{"billingreferenceid": 1400008,
                  "billingreferenceissuedate": "2026-06-30",
                  "total_net": 2103.18, "total_gross": 2250.40}],
    "kontrolle": {"kopf_netto": 157.74, "kopf_brutto": 168.78,
                  "anzahlung_netto": 2103.18, "anzahlung_brutto": 2250.40},
}
_hinweise = xml_build.pruefsummen(_rundungsfall)
pruefe(not _hinweise, f"Rundungsfall: Vorpruefung sauber ({_hinweise})")
_xml = xml_build.bauen(_rundungsfall).decode()

import re as _re
_positionen = [float(w) for w in _re.findall(
    r"<cac:InvoiceLine>.*?<cbc:LineExtensionAmount[^>]*>([-0-9.]+)<", _xml, _re.S)]
_bt106 = _betrag(_xml, "LineExtensionAmount")
# Der Kern des Befunds: BT-106 muss die Summe der GERUNDETEN Positionen sein,
# nicht der gerundete Wert der ungerundeten Summe. Frueher standen dort
# 2408.14, waehrend die 21 sichtbaren Positionen 2408.16 ergaben — zwei Cent,
# an denen BR-CO-10 haengenblieb.
pruefe(len(_positionen) == 21, f"Rundungsfall: 21 Positionen im XML ({len(_positionen)})")
pruefe(abs(sum(_positionen) - _bt106) < 0.005,
       f"BR-CO-10: BT-106 {_bt106} ist die Summe der sichtbaren Positionen {round(sum(_positionen), 2)}")

_basen = [float(w) for w in _re.findall(
    r"<cac:TaxSubtotal>\s*<cbc:TaxableAmount[^>]*>([-0-9.]+)<", _xml)]
_s_basis = _betrag(_xml.split("<cac:TaxSubtotal>")[1], "TaxableAmount")
pruefe(abs(round(sum(p for p in _positionen if p != 147.22), 2) - _s_basis) < 0.005,
       f"BR-S-08: Bemessungsgrundlage S {_s_basis} ist die Summe ihrer Positionen")

# BR-Z-01: Die Kategorie Z kommt in einer Position vor, also MUSS sie in der
# Steueraufteilung stehen — auch wenn sie sich zu null aufhebt.
pruefe(len(_basen) == 2, f"BR-Z-01: zwei Steuergruppen ausgewiesen ({len(_basen)})")
pruefe("<cbc:ID>Z</cbc:ID>" in _xml, "BR-Z-01: die Kategorie Z hat einen eigenen Block")
_z_teil = [teil for teil in _xml.split("<cac:TaxSubtotal>")[1:]
           if "<cbc:ID>Z</cbc:ID>" in teil.split("</cac:TaxSubtotal>")[0]]
pruefe(bool(_z_teil), "BR-Z-01: die Z-Gruppe ist eine eigene TaxSubtotal")
if _z_teil:
    pruefe(_betrag(_z_teil[0], "TaxableAmount") == 0.00
           and _betrag(_z_teil[0], "TaxAmount") == 0.00,
           f"BR-Z-08: die aufgehobene Z-Gruppe steht mit 0,00 / 0,00 "
           f"(ist {_betrag(_z_teil[0], 'TaxableAmount')} / {_betrag(_z_teil[0], 'TaxAmount')})")

# Und der Betrag darf sich durch das Runden nicht verschieben: Der Gast hat
# 2419.18 bezahlt, so viel muss die Rechnung ausweisen.
pruefe(_betrag(_xml, "TaxInclusiveAmount") == 2419.18,
       f"Gesamtbetrag bleibt der von OPERA ({_betrag(_xml, 'TaxInclusiveAmount')})")
pruefe(_betrag(_xml, "AllowanceTotalAmount") == 147.22, "BT-107: der Z-Abschlag steht drin")

# Die Grenze fuer den Rundungsausgleich: Sie muss den Rundungsrest fangen und
# eine echte Abweichung stehenlassen. Zwei Faelle, einer je Seite.
def _gruppe_mit_abweichung(abweichung):
    zeilen = [{"itemname": f"P{i}", "itemcode": "1000", "invoicedquantity": 1,
               "lineextensionamountnet": 10.00, "lineextensionamount": 11.90,
               "priceamount": 10.00, "classifiedtaxcategoryid": "S",
               "classifiedtaxcategorypercent": 19} for i in range(21)]
    basis = round(210.00 + abweichung, 2)
    return {"bill_no": 1, "header": dict(rechnung["header"], prepaidamount=0.0,
                                         payableamount=round(basis * 1.19, 2)),
            "lines": zeilen,
            "tax_breakdown": [{"taxcategorypercent": 19, "taxcategoryid": "S",
                               "taxableamount": basis,
                               "taxamount": round(basis * 0.19, 2)}],
            "totals": {"invoicenet": basis, "invoicegross": round(basis * 1.19, 2),
                       "invoicetaxtotal": round(basis * 0.19, 2), "spay_cl": 0.0},
            "deposits": [],
            "kontrolle": {"kopf_netto": basis, "kopf_brutto": round(basis * 1.19, 2),
                          "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}}


# Echte Fehlbuchung: 15 Cent bei 21 Positionen. Frueher lag die Grenze bei
# 0,22 — der Betrag wurde stillschweigend auf die groesste Position geschoben,
# und die Gegenprobe verglich danach zwei gleiche Zahlen.
_falsch = _gruppe_mit_abweichung(0.15)
_h = xml_build.pruefsummen(_falsch)
pruefe(_h != [], f"eine Abweichung von 0,15 bei 21 Positionen faellt auf ({_h})")
_gebaut = xml_build.bauen(_falsch).decode()
pruefe("10.15" not in _gebaut,
       "und kein Positionsbetrag wird dafuer erfunden")
# Echter Rundungsrest: hoechstens ein halber Cent je Position.
_knapp = _gruppe_mit_abweichung(0.05)
pruefe(xml_build.pruefsummen(_knapp) == [],
       f"ein echter Rundungsrest wird weiterhin ausgeglichen "
       f"({xml_build.pruefsummen(_knapp)})")

# --- Steuerrundung und BT-114 (Beleg 1400010) -------------------------------
# Der Fall, in dem die Positionen aufgehen und die Steuerbloecke nicht: OPERA
# fuehrt beide Steuergrundlagen ungerundet, die Summe der einzeln gerundeten
# Steuerbetraege ist ein Cent von der gerundeten Gesamtsumme entfernt.
# City-Ledger-Rechnung mit Anzahlung — der Zahlbetrag ist die offene Forderung.
_steuerfall = {
    "bill_no": 1400010,
    "header": dict(rechnung["header"], billno=1400010,
                   prepaidamount=4841.94, payableamount=10.63),
    "lines": [
        {"itemname": "Accommodation 7% A", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 1500.148598, "lineextensionamount": 1605.16,
         "priceamount": 1500.148598, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 7},
        {"itemname": "Accommodation 7% B", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 1499.65, "lineextensionamount": 1604.63,
         "priceamount": 1499.65, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 7},
        {"itemname": "Accommodation 7% C", "itemcode": "1000", "invoicedquantity": 1,
         "lineextensionamountnet": 1497.65, "lineextensionamount": 1602.49,
         "priceamount": 1497.65, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 7},
        {"itemname": "Parking 19%", "itemcode": "5200", "invoicedquantity": 1,
         "lineextensionamountnet": 33.865546, "lineextensionamount": 40.30,
         "priceamount": 33.865546, "classifiedtaxcategoryid": "S",
         "classifiedtaxcategorypercent": 19},
    ],
    "tax_breakdown": [
        {"taxcategorypercent": 7, "taxcategoryid": "S",
         "taxableamount": 4497.448598, "taxamount": 314.821402},
        {"taxcategorypercent": 19, "taxcategoryid": "S",
         "taxableamount": 33.865546, "taxamount": 6.434454},
    ],
    "totals": {"invoicenet": 4531.31, "invoicegross": 4852.57,
               "invoicetaxtotal": 321.26, "spay_cl": 10.63},
    "deposits": [{"billingreferenceid": 1400004,
                  "billingreferenceissuedate": "2026-07-17",
                  "total_net": 4069.70, "total_gross": 4841.94}],
    "kontrolle": {"kopf_netto": 461.61, "kopf_brutto": 10.63,
                  "anzahlung_netto": 4069.70, "anzahlung_brutto": 4841.94},
}
_hinweise = xml_build.pruefsummen(_steuerfall)
pruefe(not _hinweise, f"Steuerfall: Vorpruefung sauber ({_hinweise})")
_x = xml_build.bauen(_steuerfall).decode()

_steuerbetraege = [float(w) for w in _re.findall(
    r"<cac:TaxSubtotal>\s*<cbc:TaxableAmount[^>]*>[-0-9.]+</cbc:TaxableAmount>\s*"
    r"<cbc:TaxAmount[^>]*>([-0-9.]+)<", _x)]
_bt110 = float(_re.search(r"<cac:TaxTotal>\s*<cbc:TaxAmount[^>]*>([-0-9.]+)<", _x).group(1))
# BR-CO-14: BT-110 ist die Summe der ausgewiesenen Bloecke. Frueher kam der
# Wert aus OPERAs ungerundeter Gesamtsumme — 321.26 gegen 321.25.
pruefe(abs(sum(_steuerbetraege) - _bt110) < 0.005,
       f"BR-CO-14: BT-110 {_bt110} ist die Summe der Steuerbloecke {round(sum(_steuerbetraege), 2)}")

_bloecke = _x.split("<cac:TaxSubtotal>")[1:]
for _b in _bloecke:
    _basis = _betrag(_b, "TaxableAmount")
    _satz = float(_re.search(r"<cbc:Percent>([0-9.]+)<", _b).group(1))
    _soll = round(_basis * _satz / 100 + 1e-9, 2)
    pruefe(abs(_betrag(_b, "TaxAmount") - _soll) < 0.005,
           f"BR-S-09: {_satz} % auf {_basis} ergibt {_soll} (ist {_betrag(_b, 'TaxAmount')})")

# BT-114: der Cent, der sich nicht wegrechnen laesst. Entscheidend ist nicht,
# dass er dasteht, sondern dass der Zahlbetrag danach die Forderung des Hauses
# trifft — im City Ledger stehen 10,63 offen, nicht 10,64.
pruefe(_betrag(_x, "PayableRoundingAmount") == -0.01,
       f"BT-114: der Rundungsausgleich steht drin ({_betrag(_x, 'PayableRoundingAmount')})")
pruefe(_betrag(_x, "PayableAmount") == 10.63,
       f"BT-115 trifft die offene Forderung 10.63 (ist {_betrag(_x, 'PayableAmount')})")
pruefe(_betrag(_x, "PrepaidAmount") == 4841.94,
       "BT-113 ist die Anzahlung, nicht der City-Ledger-Betrag")
_incl = _betrag(_x, "TaxInclusiveAmount")
pruefe(abs(_incl - _betrag(_x, "TaxExclusiveAmount") - _bt110) < 0.005,
       f"BR-CO-15: BT-112 {_incl} = BT-109 + BT-110")

# Negative MENGE bei positivem Betrag: Der Einzelpreis wird als Betrag durch
# Menge gebildet und ist dann negativ — obwohl die Position dem Kunden
# berechnet wird. Frueher machte das eine Gutschrift daraus.
_negmenge = json.loads(json.dumps(rechnung))
_negmenge["lines"] = [
    {"itemname": "Normal", "itemcode": "1000", "invoicedquantity": 1,
     "lineextensionamountnet": 100.00, "lineextensionamount": 119.00,
     "priceamount": 100.00, "classifiedtaxcategoryid": "S",
     "classifiedtaxcategorypercent": 19},
    {"itemname": "Menge negativ", "itemcode": "1001", "invoicedquantity": -1,
     "lineextensionamountnet": 50.00, "lineextensionamount": 59.50,
     "priceamount": -50.00, "classifiedtaxcategoryid": "S",
     "classifiedtaxcategorypercent": 19}]
_negmenge["tax_breakdown"] = [{"taxcategorypercent": 19, "taxcategoryid": "S",
                               "taxableamount": 150.00, "taxamount": 28.50}]
_negmenge["totals"] = {"invoicenet": 150.00, "invoicegross": 178.50,
                       "invoicetaxtotal": 28.50, "spay_cl": 0.0}
_negmenge["kontrolle"] = {"kopf_netto": 150.00, "kopf_brutto": 178.50,
                          "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}
_negmenge["header"]["payableamount"] = 178.50
_nm = xml_build.bauen(_negmenge).decode()
pruefe(_betrag(_nm, "LineExtensionAmount") == 150.00,
       f"eine negative Menge macht aus der Position keine Gutschrift "
       f"({_betrag(_nm, 'LineExtensionAmount')})")
pruefe("<cac:AllowanceCharge>" not in _nm, "und es entsteht kein Abschlag")
pruefe(xml_build.pruefsummen(_negmenge) == [],
       f"die Vorpruefung ist zufrieden ({xml_build.pruefsummen(_negmenge)})")

# Menge 0 bei einem Betrag: R120 rechnet 0 x Preis = 0 und vergleicht mit dem
# Betrag. Frueher fiel die Menge im Preis stillschweigend auf 1 zurueck,
# waehrend im Dokument 0 stand — und die eigene Gegenprobe benutzte denselben
# Rueckfall und war deshalb blind.
_nullmenge = json.loads(json.dumps(rechnung))
_nullmenge["lines"] = [{"itemname": "Menge fehlt", "itemcode": "1000",
                        "invoicedquantity": 0, "lineextensionamountnet": 100.00,
                        "lineextensionamount": 119.00, "priceamount": 100.00,
                        "classifiedtaxcategoryid": "S",
                        "classifiedtaxcategorypercent": 19}]
_nullmenge["tax_breakdown"] = [{"taxcategorypercent": 19, "taxcategoryid": "S",
                                "taxableamount": 100.00, "taxamount": 19.00}]
_nullmenge["totals"] = {"invoicenet": 100.00, "invoicegross": 119.00,
                        "invoicetaxtotal": 19.00, "spay_cl": 0.0}
_nullmenge["kontrolle"] = {"kopf_netto": 100.00, "kopf_brutto": 119.00,
                           "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}
_nullmenge["header"]["payableamount"] = 119.00
_nu = xml_build.bauen(_nullmenge).decode()
pruefe("<cbc:InvoicedQuantity unitCode=\"C62\">0</cbc:InvoicedQuantity>" not in _nu,
       "eine Menge von 0 steht nicht mehr im Dokument")
_hn = xml_build.pruefsummen(_nullmenge)
pruefe(any("Menge 0" in h for h in _hn),
       f"und die Vorpruefung sagt, dass sie ersetzt wurde ({_hn})")

# --- Menge mal Einzelpreis (PEPPOL-EN16931-R120) ----------------------------
# Zwei Fruehstuecke zu 6.0748: auf zwei Stellen gerundet mal 2 ergibt 12.14,
# die Position lautet aber auf 12.15. An Beleg 1400010 auf 56 Positionen.
_preisfall = {
    "bill_no": 1400011,
    "header": dict(rechnung["header"], billno=1400011, prepaidamount=0.0,
                   payableamount=14.29),
    "lines": [
        {"itemname": "Wilsons breakfast food inclusive 7%", "itemcode": "2000",
         "invoicedquantity": 2, "lineextensionamountnet": 12.1496,
         "lineextensionamount": 13.00, "priceamount": 6.0748,
         "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7},
        {"itemname": "Wilsons breakfast beverages inclusive 19%", "itemcode": "2004",
         "invoicedquantity": 2, "lineextensionamountnet": 1.0952,
         "lineextensionamount": 1.30, "priceamount": 0.5476,
         "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19},
    ],
    "tax_breakdown": [
        {"taxcategorypercent": 7, "taxcategoryid": "S",
         "taxableamount": 12.1496, "taxamount": 0.850472},
        {"taxcategorypercent": 19, "taxcategoryid": "S",
         "taxableamount": 1.0952, "taxamount": 0.208088},
    ],
    "totals": {"invoicenet": 13.24, "invoicegross": 14.30,
               "invoicetaxtotal": 1.06, "spay_cl": 0.0},
    "deposits": [],
    "kontrolle": {"kopf_netto": 13.24, "kopf_brutto": 14.30,
                  "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0},
}
_p = xml_build.bauen(_preisfall).decode()
_zeilen = _re.findall(
    r"<cbc:InvoicedQuantity[^>]*>([0-9.]+)</cbc:InvoicedQuantity>.*?"
    r"<cbc:LineExtensionAmount[^>]*>([-0-9.]+)</cbc:LineExtensionAmount>.*?"
    r"<cbc:PriceAmount[^>]*>([-0-9.]+)</cbc:PriceAmount>", _p, _re.S)
pruefe(len(_zeilen) == 2, f"Preisfall: zwei Positionen im XML ({len(_zeilen)})")
for _menge, _betrag_z, _preis in _zeilen:
    # Genau so rechnet die Regel nach: beide Seiten auf zwei Stellen.
    pruefe(round(float(_menge) * float(_preis), 2) == round(float(_betrag_z), 2),
           f"R120: {_menge} x {_preis} = {round(float(_menge) * float(_preis), 2)} "
           f"= Positionsbetrag {_betrag_z}")
pruefe(any("." in p and len(p.split(".")[1]) > 2 for _, _, p in _zeilen),
       "BT-146 darf mehr als zwei Nachkommastellen tragen — und nutzt sie")

# Der Fall, in dem vier Stellen NICHT reichen. Bei Menge 3 reichen sie noch
# (9.9999 rundet auf 10.00); der Fehler je Stueck ist ein halber
# Zehntausendstel und faellt erst bei Mengen ueber rund hundert ins Gewicht.
# 10.01 auf 300 verteilt sind 0.0334, mal 300 ergibt 10.02.
_dreier = json.loads(json.dumps(_preisfall))
_dreier["lines"] = [{"itemname": "Tagungsgetraenk 7%", "itemcode": "1500",
                     "invoicedquantity": 300, "lineextensionamountnet": 10.01,
                     "lineextensionamount": 10.71, "priceamount": 0.0334,
                     "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 7}]
_dreier["tax_breakdown"] = [{"taxcategorypercent": 7, "taxcategoryid": "S",
                             "taxableamount": 10.01, "taxamount": 0.70}]
_dreier["totals"] = {"invoicenet": 10.01, "invoicegross": 10.71,
                     "invoicetaxtotal": 0.70, "spay_cl": 0.0}
_dreier["kontrolle"] = {"kopf_netto": 10.01, "kopf_brutto": 10.71,
                        "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}
_dreier["header"]["payableamount"] = 10.71
_hinweise = xml_build.pruefsummen(_dreier)
pruefe(not _hinweise, f"Grosse Menge: Vorpruefung sauber ({_hinweise})")
_d = xml_build.bauen(_dreier).decode()
pruefe("<cbc:BaseQuantity" in _d,
       "BT-149: reichen vier Stellen nicht, springt die Bezugsmenge ein")
_bq = float(_re.search(r"<cbc:BaseQuantity[^>]*>([0-9.]+)<", _d).group(1))
_pr = float(_re.search(r"<cbc:PriceAmount[^>]*>([0-9.]+)<", _d).group(1))
pruefe(round(300 * _pr / _bq, 2) == 10.01,
       f"R120 geht auch dann auf: 300 x {_pr} / {_bq} = {round(300 * _pr / _bq, 2)}")

# Und die Gegenprobe: bei Menge 3 wird die Bezugsmenge NICHT gebraucht.
_drei = json.loads(json.dumps(_dreier))
_drei["lines"][0].update(invoicedquantity=3, lineextensionamountnet=10.00,
                         lineextensionamount=10.70, priceamount=3.3333)
_drei["tax_breakdown"][0].update(taxableamount=10.00)
_drei["totals"].update(invoicenet=10.00, invoicegross=10.70)
_drei["kontrolle"].update(kopf_netto=10.00, kopf_brutto=10.70)
_drei["header"]["payableamount"] = 10.70
pruefe("<cbc:BaseQuantity" not in xml_build.bauen(_drei).decode(),
       "bei Menge 3 reichen vier Stellen — keine Bezugsmenge im Dokument")

# --- Darstellung der Positionen: A, B, C (Entscheidung vom 14.09.2026) ------
# Zwei Arten: Einzelrechnung zusammengefasst (B), Gruppe je Gast mit Zimmer und
# Name (C). Die Probe: DIESELBEN Buchungen in allen drei Darstellungen — die
# Vorpruefung muss jedes Mal sauber sein, und Gesamt- und Zahlbetrag duerfen
# sich um keinen Cent unterscheiden. Die Nettobetraege sind so ungerundet wie
# in OPERA (Brutto / 1,07), damit die Rundung wirklich etwas zu tun hat.
print("8) Darstellung der Positionen")


def _buchung(trx, code, name, brutto, satz, menge=1, gast=None, zimmer=None,
             gastname=None, von=None, bis=None, bemerkung=""):
    netto = brutto / (1 + satz / 100)
    return {"trx_no": trx, "itemcode": code, "itemname": name,
            "invoicedquantity": menge, "lineextensionamount": brutto,
            "lineextensionamountnet": netto,
            "priceamount": round(netto / menge, 2) if menge else None,
            "classifiedtaxcategoryid": "S" if satz else "Z",
            "classifiedtaxcategorypercent": satz,
            "bruttopreis": round(brutto / menge, 2) if menge else None,
            "gast_resv_name_id": gast, "gast_zimmer": zimmer, "gast_name": gastname,
            "gast_beginn": von, "gast_ende": bis, "bemerkung": bemerkung}


_riedel = dict(gast=501, zimmer="214", gastname="Musterfrau, Lena",
               von="2026-08-30", bis="2026-09-04")
# Bauer reist frueher an und spaeter ab als Musterfrau, dessen Aufenthalt am Kopf
# steht — der Fall, an dem PEPPOL-EN16931-R110/R111 haengen.
_bauer = dict(gast=502, zimmer="215", gastname="Beispiel, Max",
              von="2026-08-28", bis="2026-09-06")
_buchungen = []
_trx = 1000
# Bauer (Zimmer 215) ist ZUERST gebucht: Die Sortierung nach Zimmer muss etwas
# zu tun haben, sonst kann ihre Pruefung nicht rot werden.
for _preis in (189.00, 189.00, 216.09, 216.09, 216.09):   # Bauer: zwei Preise
    _buchungen.append(_buchung(_trx := _trx + 1, "1000", "Übernachtung", _preis, 7, **_bauer))
_buchungen.append(_buchung(_trx := _trx + 1, "5200", "Parken", 30.00, 19,
                           bemerkung="Tiefgarage", **_bauer))
# Inklusivleistung ohne Betrag: fuenfmal 0,00 soll EINE Position werden
for _i in range(5):
    _buchungen.append(_buchung(_trx := _trx + 1, "2010", "Frühstück inklusive", 0.00, 7, **_bauer))
for _i in range(5):                        # Musterfrau: 5 Naechte zu 216,09 und Fruehstueck
    _buchungen.append(_buchung(_trx := _trx + 1, "1000", "Übernachtung", 216.09, 7, **_riedel))
    _buchungen.append(_buchung(_trx := _trx + 1, "2000", "Frühstück", 25.00, 7, **_riedel))
# Eine Nacht gebucht und wieder storniert — hebt sich in der Gruppe auf
_buchungen.append(_buchung(_trx := _trx + 1, "1000", "Übernachtung", 216.09, 7, **_riedel))
_buchungen.append(_buchung(_trx := _trx + 1, "1000", "Übernachtung", -216.09, 7, menge=-1, **_riedel))
# Minibar gebucht und storniert — die Position faellt ganz weg
_buchungen.append(_buchung(_trx := _trx + 1, "3000", "Minibar", 4.50, 19, **_riedel))
_buchungen.append(_buchung(_trx := _trx + 1, "3000", "Minibar", -4.50, 19, menge=-1, **_riedel))


def _rechnung_aus(buchungen):
    """Kopf, Steuergruppen und Summen so, wie OPERA sie fuehrt: Grundlage je
    Satz aus den ungerundeten Nettobetraegen, Brutto auf den Cent."""
    gruppen = {}
    for b in buchungen:
        gruppen.setdefault(b["classifiedtaxcategorypercent"], []).append(b)
    steuer = [{"taxcategoryid": "S", "taxcategorypercent": s,
               "taxableamount": round(sum(b["lineextensionamountnet"] for b in bs), 2),
               "taxamount": round(sum(b["lineextensionamount"] - b["lineextensionamountnet"]
                                      for b in bs), 2)}
              for s, bs in gruppen.items()]
    netto = round(sum(b["lineextensionamountnet"] for b in buchungen), 2)
    brutto = round(sum(b["lineextensionamount"] for b in buchungen), 2)
    return {"bill_no": 1399001,
            "header": dict(rechnung["header"], id=1399001, prepaidamount=0.0,
                           payableamount=brutto, gastname="Musterfrau, Lena",
                           startdate="2026-08-30", enddate="2026-09-04"),
            "lines": json.loads(json.dumps(buchungen)),
            "tax_breakdown": steuer,
            "totals": {"invoicenet": netto, "invoicegross": brutto,
                       "invoicetaxtotal": round(brutto - netto, 2), "spay_cl": 0.0},
            "deposits": [],
            "kontrolle": {"kopf_netto": netto, "kopf_brutto": brutto,
                          "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}}


_gruppe = _rechnung_aus(_buchungen)
_dokumente = {}
# Ueber den ECHTEN Weg, den Detailseite und Erzeugung gehen — nicht ueber einen
# Nachbau der Aufrufe. Nur OPERA und die Adresssuche sind ersetzt.
_echt_r4, _echt_e4 = opera.rechnung, opera.empfaenger
opera.rechnung = lambda cfg, bill_no: json.loads(json.dumps(_gruppe))
opera.empfaenger = lambda bill_no: [{"email": "rechnung@beispiel.de"}]
store.rechnung_anlegen({"bill_no": 1399001, "resort": "IHRHAUS", "invoice_no": "G",
                        "issuedate": "2026-09-04", "kunde": "Gruppe GmbH",
                        "city_ledger": 0.0, "firmenbezug": "EMPFAENGER"}, 0)
try:
    for _art in ("A", "B", "C"):
        store.setzen(1399001, positionen=_art)
        _d = ablauf.rechnungsdaten(cfg, 1399001)
        _dokumente[_art] = (_d, xml_build.bauen(_d).decode())
finally:
    opera.rechnung, opera.empfaenger = _echt_r4, _echt_e4
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no = 1399001")
for _art, (_d, _x) in _dokumente.items():
    _h = xml_build.pruefsummen(_d)
    pruefe(_h == [], f"{_art}: Vorpruefung sauber ({_h})")
    pruefe(abs(sum(float(z["lineextensionamountnet"]) for z in _d["lines"])
               - sum(b["lineextensionamountnet"] for b in _buchungen)) < 1e-6,
           f"{_art}: die Summe der ungerundeten Nettobetraege bleibt dieselbe")
for _feld in ("TaxInclusiveAmount", "PayableAmount", "TaxExclusiveAmount"):
    _werte = {a: _betrag(x, _feld) for a, (_, x) in _dokumente.items()}
    pruefe(len(set(_werte.values())) == 1,
           f"{_feld} ist in allen drei Darstellungen gleich ({_werte})")
_steuer = {a: _re.findall(r"<cac:TaxSubtotal>\s*<cbc:TaxableAmount[^>]*>([-0-9.]+)<"
                          r".*?<cbc:TaxAmount[^>]*>([-0-9.]+)<", x, _re.S)
           for a, (_, x) in _dokumente.items()}
pruefe(_steuer["B"] == _steuer["C"],
       f"B und C weisen dieselben Steuergruppen aus ({_steuer['B']} / {_steuer['C']})")

_b_d, _b_x = _dokumente["B"]
_b_zeilen = [(z["itemname"], z["invoicedquantity"], z.get("bruttopreis")) for z in _b_d["lines"]]
pruefe(len(_b_d["lines"]) == 5,
       f"B: 25 Buchungen werden 5 Positionen ({_b_zeilen})")
pruefe(("Übernachtung", 8, 216.09) in _b_zeilen and ("Übernachtung", 2, 189.00) in _b_zeilen,
       "B: gleicher Preis wird zusammengefasst, zwei Preise bleiben zwei Positionen")
pruefe(("Frühstück inklusive", 5, 0.0) in _b_zeilen,
       "B: Inklusivleistungen ohne Betrag gehen ebenfalls zusammen")
pruefe(not any(z["itemname"] == "Minibar" for z in _b_d["lines"])
       and "<cac:AllowanceCharge>" not in _b_x,
       "B: Buchung und Storno heben sich auf — keine Position, kein Abschlag")
pruefe("Zi. " not in _b_x and _b_x.count("<cac:InvoicePeriod>") == 1,
       "B: kein Gast und kein Zeitraum an den Positionen, nur der Kopfzeitraum")
pruefe("<cbc:Note>Tiefgarage</cbc:Note>" in _b_x,
       "B: eine Bemerkung an der Buchung bleibt erhalten")
# Der Einzelpreis entsteht erst in der Normalisierung — gegen DEREN Ergebnis
# pruefen, nicht gegen die gebuendelte Zeile davor (dort ist er noch leer).
_uebern = [z for z in xml_build._normalisieren(_b_d)["lines"]
           if z["itemname"] == "Übernachtung" and z["invoicedquantity"] == 8][0]
pruefe(_uebern.get("priceamount") and not _uebern.get("pricebasequantity")
       and round(8 * float(_uebern["priceamount"]), 2) == round(float(_uebern["lineextensionamountnet"]), 2),
       f"B: R120 geht auf — 8 x {_uebern.get('priceamount')} = {_uebern['lineextensionamountnet']}")

_c_d, _c_x = _dokumente["C"]
_c_notes = [z.get("bemerkung") for z in _c_d["lines"]]
pruefe(len(_c_d["lines"]) == 6,
       f"C: je Gast gebuendelt — 2 fuer Musterfrau, 4 fuer Bauer ({_c_notes})")
pruefe(_c_notes[0].startswith("Zi. 214 · Musterfrau, Lena"),
       f"C: die erste Position nennt Zimmer und Gast ({_c_notes[0]})")
pruefe("Zi. 215 · Beispiel, Max · Tiefgarage" in _c_notes,
       "C: die Bemerkung der Buchung steht hinter Zimmer und Name")
pruefe([z["gast_zimmer"] for z in _c_d["lines"]] == ["214", "214", "215", "215", "215", "215"],
       "C: nach Zimmer geordnet, die Positionen eines Gastes stehen beieinander")
pruefe(_c_x.count("<cac:InvoicePeriod>") == 1 + len(_c_d["lines"]),
       "C: jede Position traegt den Aufenthalt (BT-134/135)")
_c_zeile = _c_x[_c_x.index("<cac:InvoiceLine>"):_c_x.index("</cac:InvoiceLine>")]
_reihe = ["<cbc:ID>", "<cbc:Note>", "<cbc:InvoicedQuantity", "<cbc:LineExtensionAmount",
          "<cac:InvoicePeriod>", "<cac:Item>", "<cac:Price>"]
pruefe(all(_t in _c_zeile for _t in _reihe)
       and [_c_zeile.index(_t) for _t in _reihe] == sorted(_c_zeile.index(_t) for _t in _reihe),
       "C: UBL-Reihenfolge in der Position — Note, Menge, Betrag, Zeitraum, Item, Preis")
pruefe("<cbc:StartDate>2026-08-30</cbc:StartDate>" in _c_zeile,
       "C: der Zeitraum ist der der Reservierung")
_kopfzeit = _c_x[_c_x.index("<cac:InvoicePeriod>"):_c_x.index("</cac:InvoicePeriod>")]
pruefe("<cbc:StartDate>2026-08-28</cbc:StartDate>" in _kopfzeit
       and "<cbc:EndDate>2026-09-06</cbc:EndDate>" in _kopfzeit,
       f"C: der Rechnungszeitraum umfasst alle Aufenthalte (R110/R111) ({_kopfzeit.split()[1:3]})")
_b_kopfzeit = _b_x[_b_x.index("<cac:InvoicePeriod>"):_b_x.index("</cac:InvoicePeriod>")]
pruefe("<cbc:StartDate>2026-08-30</cbc:StartDate>" in _b_kopfzeit,
       "B: ohne Positionszeitraum bleibt der Aufenthalt am Kopf, wie er ist")
# Und die Vorpruefung sieht einen Positionszeitraum ausserhalb selbst — der
# KoSIT-Validator laeuft nur auf dem Server.
_eng = json.loads(json.dumps(_c_d))
_eng["header"].update(startdate="2026-08-30", enddate="2026-09-04")
_he = xml_build.pruefsummen(_eng)
pruefe(any("R110" in h for h in _he) and any("R111" in h for h in _he),
       f"die Vorpruefung meldet R110 und R111, wenn der Kopf zu eng ist ({len(_he)} Befunde)")
from lxml import etree as _et3
_c_baum = _et3.fromstring(_c_x.encode())
_ns3 = {"cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"}
pruefe(len(_c_baum.findall("cac:InvoiceLine/cac:InvoicePeriod", _ns3)) == len(_c_d["lines"])
       and _c_baum.findtext("cac:InvoiceLine/cbc:Note", namespaces=_ns3) == "Zi. 214 · Musterfrau, Lena",
       "C: im geparsten Dokument hat jede Position Zeitraum und Gast")

_a_d, _ = _dokumente["A"]
pruefe(len(_a_d["lines"]) + len(_a_d.get("allowances") or []) == len(_buchungen),
       "A: jede Buchung bleibt einzeln — wie vor dem 14.09.")

# Sonderfaelle: Menge null wird nie zusammengefasst; ein unvollstaendiger
# oder verkehrter Zeitraum bleibt ganz weg (BR-30).
_null = [_buchung(1, "1000", "X", 10.00, 7, menge=0), _buchung(2, "1000", "X", 10.00, 7, menge=0)]
# Den Preis ausdruecklich setzen: Mit Preis None fiele die Buchung schon
# deswegen in den Zweig "einzeln", und die Pruefung der Menge waere blind.
for _z in _null:
    _z["bruttopreis"] = 10.00
pruefe(len(opera.positionen_buendeln(_null, "B")) == 2,
       "eine Buchung mit Menge 0 wird nicht mit anderen verrechnet")
# Menge summiert sich auf null, der Betrag nicht: 3 x 10,00 und -3 x -9,99
# tragen beide den Preis 3,33. Zusammengefasst ergaebe das "0 x ... = 0,01" —
# nicht nachrechenbar. Die Buchungen muessen einzeln stehen bleiben.
_schief = [_buchung(1, "1000", "X", 10.00, 7, menge=3), _buchung(2, "1000", "X", -9.99, 7, menge=-3)]
_s = opera.positionen_buendeln(_schief, "B")
pruefe(len(_s) == 2 and {z["invoicedquantity"] for z in _s} == {3, -3},
       f"Menge null bei einem Betrag: die Buchungen bleiben einzeln ({[(z['invoicedquantity'], z['lineextensionamount']) for z in _s]})")
# Zimmerwechsel: EINE Reservierung, Buchungen aus zwei Zimmern.
_umzug = [_buchung(1, "1000", "Übernachtung", 216.09, 7, gast=9, zimmer="101", gastname="Umzug, Uwe"),
          _buchung(2, "1000", "Übernachtung", 216.09, 7, gast=9, zimmer="202", gastname="Umzug, Uwe")]
_u = opera.positionen_buendeln(_umzug, "C")
pruefe(sorted(z["bemerkung"] for z in _u) == ["Zi. 101 · Umzug, Uwe", "Zi. 202 · Umzug, Uwe"],
       f"C: ein Zimmerwechsel ergibt je Zimmer eine Position ({[z['bemerkung'] for z in _u]})")
pruefe(len(opera.positionen_buendeln(_umzug, "B")) == 1,
       "B: dort bleibt es eine Position — das Zimmer steht nicht daran")
# Ein Rabatt fuer einen Gast wird zum Abschlag — und traegt den Gast mit.
_rabatt = [_buchung(1, "1000", "Übernachtung", 216.09, 7, **_riedel),
           _buchung(2, "9100", "Rabatt", -20.00, 7, **_riedel)]
_ra = xml_build._normalisieren({"lines": opera.positionen_buendeln(_rabatt, "C"),
                                "tax_breakdown": [], "totals": {}})
pruefe([a["reason"] for a in _ra["allowances"]] == ["Rabatt · Zi. 214 · Musterfrau, Lena"],
       f"C: der Abschlag nennt Zimmer und Gast ({[a['reason'] for a in _ra['allowances']]})")
_rb = xml_build._normalisieren({"lines": opera.positionen_buendeln(_rabatt, "B"),
                                "tax_breakdown": [], "totals": {}})
pruefe([a["reason"] for a in _rb["allowances"]] == ["Rabatt"],
       "B: dort bleibt der Abschlag ohne Gast, wie bisher")
# Der Kopf beginnt FRUEHER als jede Position: Er bleibt dann, wie er ist.
_frueh = {"startdate": "2026-08-01", "enddate": "2026-08-31"}
opera.rechnungszeitraum_erweitern(_frueh, [{"zeitraum_beginn": "2026-08-10", "zeitraum_ende": "2026-09-02"}])
pruefe(_frueh == {"startdate": "2026-08-01", "enddate": "2026-09-02"},
       f"der Rechnungszeitraum wird nur erweitert, nie verengt ({_frueh})")

# Rundungsrest mit Abschlaegen (Befund aus der Nachpruefung vom 14.09.2026):
# 8 Uebernachtungen, 6 verschiedene Rabatte. Einzeln 8 Positionen, gebuendelt
# 3 — die Grenze fuer den Rundungsausgleich zaehlte nur die Positionen und sank
# unter den echten Rest von 0,03. Die Rechnung wurde gesperrt.
_grenzfall = [_buchung(i + 1, "1000", "Übernachtung", p, 7, gast=1)
              for i, p in enumerate((189.00, 216.09, 149.50, 149.50, 216.09, 149.50, 149.50, 149.50))]
_grenzfall += [_buchung(20 + i, "9100", "Rabatt", r, 7, gast=1)
               for i, r in enumerate((-31.13, -15.39, -26.73, -38.31, -48.40, -31.76))]
_gf = _rechnung_aus(_grenzfall)
# Wie OPERA: Grundlage ungerundet summiert — _rechnung_aus rundet sie, das
# verschiebt genau den Rest, um den es geht.
_gf["tax_breakdown"][0]["taxableamount"] = sum(b["lineextensionamountnet"] for b in _grenzfall)
_gf["kontrolle"]["kopf_netto"] = sum(b["lineextensionamountnet"] for b in _grenzfall)
for _art in ("A", "B"):
    _d = json.loads(json.dumps(_gf))
    _d["lines"] = opera.positionen_buendeln(_d["lines"], _art)
    _h = xml_build.pruefsummen(_d)
    pruefe(_h == [], f"Rundungsrest mit sechs Abschlaegen, {_art}: Vorpruefung sauber ({_h})")
_verkehrt = [_buchung(1, "1000", "X", 10.00, 7, gast=1, zimmer="1", gastname="A",
                      von="2026-09-05", bis="2026-09-01")]
_v = opera.positionen_buendeln(_verkehrt, "C")[0]
pruefe("zeitraum_beginn" not in _v, "ein Zeitraum mit Ende vor Beginn wird nicht ausgegeben")
_ohne_gast = [_buchung(1, "1000", "X", 10.00, 7), _buchung(2, "1000", "X", 10.00, 7)]
_og = opera.positionen_buendeln(_ohne_gast, "C")
pruefe(len(_og) == 1 and not _og[0].get("bemerkung"),
       f"C ohne Gast an der Buchung: zusammengefasst, keine leere 'Zi.'-Bemerkung ({_og})")
pruefe(opera.positionen_buendeln(_buchungen, "A") is _buchungen,
       "A laesst die Buchungen unangetastet")

# Vorbelegung: mehrere Reservierungen -> C; ein Gast -> B; ein Gast an den
# Buchungen, aber keiner am Kopf -> C, sonst stuende der Name nirgends.
pruefe(opera.positionsart_vorschlag({"gastname": "Musterfrau"}, _buchungen)[0] == "C",
       "Vorbelegung: zwei Reservierungen ergeben C")
_einzel = [b for b in _buchungen if b["gast_resv_name_id"] == 501]
pruefe(opera.positionsart_vorschlag({"gastname": "Musterfrau, Lena"}, _einzel)[0] == "B",
       "Vorbelegung: ein Gast ergibt B")
pruefe(opera.positionsart_vorschlag({"gastname": None}, _einzel)[0] == "C",
       "Vorbelegung: Gast nur an den Buchungen ergibt C")
pruefe(opera.positionsart_vorschlag({"gastname": None}, _ohne_gast)[0] == "B",
       "Vorbelegung: gar kein Gast ergibt B")

# Reihenfolge der Entscheidung: Wahl von Hand, feste Vorgabe, Vorbelegung.
_cfg_p = json.loads(json.dumps(cfg))
_cfg_p["property"]["positionen"] = "automatisch"
pruefe(ablauf.positionsart(_cfg_p, {"positionen": "A"}, {"gastname": "R"}, _buchungen)
       == ("A", "von Hand gewählt"), "die Wahl auf der Detailseite gewinnt")
pruefe(ablauf.positionsart(_cfg_p, {}, {"gastname": "R"}, _buchungen)[0] == "C",
       "ohne Wahl gilt die Vorbelegung")
_cfg_p["property"]["positionen"] = "b"
pruefe(ablauf.positionsart(_cfg_p, {}, {"gastname": "R"}, _buchungen)
       == ("B", "feste Vorgabe der Konfiguration"), "eine feste Vorgabe gilt vor der Vorbelegung")
_cfg_p["property"]["positionen"] = "Gruppe"
pruefe(ablauf.positionsart(_cfg_p, {}, {"gastname": "R"}, _buchungen)[0] == "C",
       "ein unbekannter Wert faellt auf die Vorbelegung zurueck, nicht auf A")
_cfg_p["property"].pop("positionen")
pruefe(ablauf.positionsart(_cfg_p, {"positionen": "x"}, {"gastname": "R"}, _buchungen)[0] == "C",
       "ohne Eintrag und mit ungueltiger Wahl ebenso")
pruefe(_vorlage["property"]["positionen"] == "automatisch",
       "Vorlage: Vorbelegung ist 'automatisch'")

# Die Zuordnung zum Gast in der ABFRAGE: bei umgeleiteten Buchungen der
# Ursprung, nicht das Masterkonto. Ohne Kommentare gelesen.
_zeilen_sql = "\n".join(z.split("--")[0] for z in
                        (BASE / "sql" / "opera" / "invoice_lines.sql").read_text(encoding="utf-8").splitlines())
pruefe("NVL(ft.original_resv_name_id, ft.resv_name_id) AS gast_resv_name_id" in _zeilen_sql
       and "NVL(ft.original_room, ft.room)                 AS gast_zimmer" in _zeilen_sql,
       "die Abfrage ordnet die Buchung dem Ursprungszimmer zu")
pruefe("rn.resv_name_id = NVL(ft.original_resv_name_id, ft.resv_name_id)" in _zeilen_sql,
       "und holt Name und Aufenthalt von DIESER Reservierung")
pruefe("g.company" not in _zeilen_sql, "ohne Rueckfall auf den Firmennamen")

# --- Versionsschalter XRechnung ---------------------------------------------
# 4.0 gibt es am 14.09.2026 nicht. Der Schalter muss trotzdem wirken: Vorlage,
# CustomizationID und Regelwerk kommen aus EINER Angabe, und eine unbekannte
# Version erzeugt keine Datei, statt still auf 3.0.2 zu fallen.
print("8b) Kontakt des Hauses: Konfiguration vor OPERA")
# Entscheidung vom 14.09.2026. Geprueft ueber opera.rechnung() selbst, mit
# einer ersetzten Datenbank, die fuer das Resort eigene Werte liefert — nicht
# ueber einen Nachbau der Reihenfolge.
_echt_abfrage2 = opera.db.abfrage


def _db_mit_resortkontakt(sql, parameter=None):
    if "invoice_header.sql" in sql.splitlines()[0]:
        return [{"issuedate": "2026-09-10", "reservierungsnummer": "4711",
                 "suppliercontacttelephone": "+49 30 000000 (OPERA)",
                 "suppliercontactelectronicmail": "rezeption@opera.example"}]
    return []


opera.db.abfrage = _db_mit_resortkontakt
try:
    for _tel, _mail, _soll_tel, _soll_mail, _fall in (
            ("+49 30 111111", "buchhaltung@haus.example", "+49 30 111111",
             "buchhaltung@haus.example", "beides konfiguriert: die Konfiguration gilt"),
            ("", "", "+49 30 000000 (OPERA)", "rezeption@opera.example",
             "nichts konfiguriert: OPERA ist der Rueckfall"),
            ("+49 30 111111", "  ", "+49 30 111111", "rezeption@opera.example",
             "nur Telefon konfiguriert: E-Mail aus OPERA")):
        _cfg_k = json.loads(json.dumps(cfg))
        _cfg_k["property"].update(kontakt_telefon=_tel, kontakt_email=_mail, udf_leitweg="")
        _kk = opera.rechnung(_cfg_k, 1)["header"]
        pruefe((_kk["suppliercontacttelephone"], _kk["suppliercontactelectronicmail"])
               == (_soll_tel, _soll_mail),
               f"{_fall} ({_kk['suppliercontacttelephone']}, {_kk['suppliercontactelectronicmail']})")
finally:
    opera.db.abfrage = _echt_abfrage2
_kx = xml_build.bauen(dict(json.loads(json.dumps(rechnung)), header=dict(
    rechnung["header"], suppliercontactelectronicmail="buchhaltung@haus.example"))).decode()
_verk = _kx[_kx.index("<cac:AccountingSupplierParty>"):_kx.index("</cac:AccountingSupplierParty>")]
pruefe('<cbc:EndpointID schemeID="EM">buchhaltung@haus.example</cbc:EndpointID>' in _verk
       and "<cbc:ElectronicMail>buchhaltung@haus.example</cbc:ElectronicMail>" in _verk,
       "die E-Mail steht als elektronische Adresse (BT-34) und als Kontakt (BT-43) beim Verkaeufer")

print("9) Versionsschalter")
from app import validate as _val
pruefe(xml_build.version_aus({}) == "3.0.2", "ohne Angabe gilt 3.0.2")
pruefe(xml_build.version_aus({"xrechnung": {"version": "3.0"}}) == "3.0.2",
       "der fruehere Name '3.0' meint 3.0.2")
try:
    xml_build.version_aus({"xrechnung": {"version": "4.0"}})
    pruefe(False, "eine nicht verfuegbare Version wird abgelehnt")
except xml_build.XmlFehler as e:
    pruefe("4.0" in str(e), f"eine nicht verfuegbare Version wird abgelehnt ({e})")
try:
    xml_build.bauen(json.loads(json.dumps(rechnung)), "4.0")
    pruefe(False, "bauen() erzeugt nichts in einer unbekannten Version")
except xml_build.XmlFehler:
    pruefe(True, "bauen() erzeugt nichts in einer unbekannten Version")
# Die Kennung kommt aus der Versionsliste. Mit einem verfaelschten Eintrag muss
# sie sich im Dokument aendern — sonst stuende sie weiter fest in der Vorlage.
_kennung = xml_build.VERSIONEN["3.0.2"]["customizationid"]
try:
    xml_build.VERSIONEN["3.0.2"]["customizationid"] = "urn:probe:versionsschalter"
    _vx = xml_build.bauen(json.loads(json.dumps(rechnung)), "3.0.2").decode()
finally:
    xml_build.VERSIONEN["3.0.2"]["customizationid"] = _kennung
pruefe("<cbc:CustomizationID>urn:probe:versionsschalter</cbc:CustomizationID>" in _vx,
       "die CustomizationID kommt aus der Versionsliste, nicht fest aus der Vorlage")
pruefe(f"<cbc:CustomizationID>{_kennung}</cbc:CustomizationID>"
       in xml_build.bauen(json.loads(json.dumps(rechnung))).decode()
       and _kennung.endswith("urn:xeinkauf.de:kosit:xrechnung_3.0"),
       "und fuer 3.0.2 ist es die Kennung, die der Validator angenommen hat")
# Regelwerk zur Version
_cfg_v2 = json.loads(json.dumps(cfg))
_cfg_v2["xrechnung"] = {"version": "3.0.2"}
_cfg_v2["validierung"]["kosit_szenarien"] = "validation/xrechnung-{version}/scenarios.xml"
pruefe(_val.szenarien_zur_version(_cfg_v2) == ("validation/xrechnung-3.0.2/scenarios.xml", ""),
       "{version} im Pfad waehlt das Regelwerk mit")
_cfg_v2["validierung"]["kosit_szenarien"] = "validation/xrechnung-3.0.2/scenarios.xml"
pruefe(_val.szenarien_zur_version(_cfg_v2)[1] == "",
       "ein fester Pfad aelterer Anlagen bleibt gueltig, solange er zur Version passt")
_cfg_v2["validierung"]["kosit_szenarien"] = "validation/xrechnung-3.0.1/scenarios.xml"
_befund = _val.szenarien_zur_version(_cfg_v2)[1]
pruefe("passt nicht" in _befund and _befund in _val.zustand(_cfg_v2)["fehlt"],
       f"ein Regelwerk, das nicht zur Version passt, ist ein Befund ({_befund[:60]})")
pruefe(_vorlage["xrechnung"]["version"] == "3.0.2"
       and "{version}" in _vorlage["validierung"]["kosit_szenarien"],
       "Vorlage: Version 3.0.2, Regelwerk ueber {version}")

# =============================================================================
# 10) Befunde aus dem Code-Review vom 14.09.2026
# Jede Pruefung hier stellt den gemeldeten Fall nach und waere ohne die
# Korrektur rot. Die Nummern verweisen auf die Befundliste.
# =============================================================================
print("10) Befunde aus dem Code-Review")
import smtplib as _smtplib
import ssl as _ssl
import threading as _threading
from app import mailer as _mailer, db as _db, automatik as _automatik, config as _config

# --- Mailversand ------------------------------------------------------------
_smtp_protokoll = []


class _FalscherServer:
    """Ersetzt smtplib.SMTP/SMTP_SSL. Haelt fest, was aufgerufen wurde, und
    lehnt Empfaenger ab, wie es ein echter Server tut."""
    ablehnen: set = set()

    def __init__(self, host, port, timeout=None, context=None):
        _smtp_protokoll.append(("verbinden", host, port, context))

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        _smtp_protokoll.append(("starttls", context))

    def login(self, benutzer, passwort):
        _smtp_protokoll.append(("login", benutzer))

    def send_message(self, nachricht, from_addr=None, to_addrs=None):
        _smtp_protokoll.append(("senden", list(to_addrs)))
        return {a: (554, b"5.7.1 Relay access denied") for a in to_addrs if a in self.ablehnen}


_echt_smtp, _echt_smtp_ssl = _smtplib.SMTP, _smtplib.SMTP_SSL
_smtplib.SMTP = _smtplib.SMTP_SSL = _FalscherServer
_mcfg = json.loads(json.dumps(cfg))
_mcfg["mail"].update(aktiv=True, smtp_host="mail.example", smtp_port=587, verschluesselung="starttls",
                     benutzer="xrechnung", passwort="geheim", absender="rechnung@haus.example",
                     bcc="kopie@haus.example", bcc_city_ledger="", erlaubte_empfaenger=[],
                     betreff="Rechnung {bill_no}", text="Text {bill_no}")
try:
    # Befund 2: Der Kunde wird abgelehnt, die Blindkopie angenommen.
    _FalscherServer.ablehnen = {"kunde@firma.example"}
    try:
        _mailer.senden(_mcfg, an="kunde@firma.example", bill_no=1, issuedate="", xml=b"<x/>",
                       xml_name="x.xml")
        pruefe(False, "B2: ein abgelehnter Kunde bei angenommener Blindkopie ist ein Fehler")
    except _mailer.MailFehler as e:
        pruefe("abgelehnt" in str(e), f"B2: ein abgelehnter Kunde bei angenommener Blindkopie ist ein Fehler ({str(e)[:60]})")
    _FalscherServer.ablehnen = set()
    _smtp_protokoll.clear()
    _mailer.senden(_mcfg, an="kunde@firma.example", bill_no=1, issuedate="", xml=b"<x/>", xml_name="x.xml")
    # Befund 8: Das Zertifikat wird geprueft.
    _tls = [e for e in _smtp_protokoll if e[0] == "starttls"]
    pruefe(bool(_tls) and isinstance(_tls[0][1], _ssl.SSLContext)
           and _tls[0][1].verify_mode == _ssl.CERT_REQUIRED and _tls[0][1].check_hostname,
           "B8: STARTTLS mit Zertifikats- und Namenspruefung")
    _smtp_protokoll.clear()
    _mcfg["mail"]["verschluesselung"] = "ssl"
    _mailer.senden(_mcfg, an="kunde@firma.example", bill_no=1, issuedate="", xml=b"<x/>", xml_name="x.xml")
    _verb = [e for e in _smtp_protokoll if e[0] == "verbinden"]
    pruefe(bool(_verb) and isinstance(_verb[0][3], _ssl.SSLContext)
           and _verb[0][3].verify_mode == _ssl.CERT_REQUIRED, "B8: SSL ebenso")
    _mcfg["mail"]["verschluesselung"] = "keine"
    _smtp_protokoll.clear()
    try:
        _mailer.senden(_mcfg, an="kunde@firma.example", bill_no=1, issuedate="", xml=b"<x/>", xml_name="x.xml")
        pruefe(False, "B8: keine Anmeldung ohne Verschluesselung")
    except _mailer.MailFehler:
        pruefe(not any(e[0] == "login" for e in _smtp_protokoll), "B8: keine Anmeldung ohne Verschluesselung")
    _mcfg["mail"]["verschluesselung"] = "starttls"
    # Befund 19: mehrere Adressen in einem Feld.
    _mcfg["mail"]["erlaubte_empfaenger"] = ["@kunde.example"]
    pruefe(not _mailer.empfaenger_erlaubt(_mcfg, "a@kunde.example; b@fremd.example"),
           "B19: 'a@kunde; b@fremd' passiert die Positivliste nicht")
    pruefe(not _mailer.empfaenger_erlaubt({"mail": {"erlaubte_empfaenger": []}}, "a@x.example, b@y.example"),
           "B19: auch ohne Positivliste ist das keine erlaubte Adresse")
    pruefe(_mailer.empfaenger_erlaubt(_mcfg, "rechnung@kunde.example"), "B19: eine einzelne Adresse geht")
    _mcfg["mail"]["erlaubte_empfaenger"] = []
    # Befund 26: Formatangabe im Betreff laesst den Versand nicht scheitern.
    _mcfg["mail"]["betreff"] = "Rechnung {bill_no!z} {"
    try:
        _mailer.senden(_mcfg, an="kunde@firma.example", bill_no=1, issuedate="", xml=b"<x/>", xml_name="x.xml")
        pruefe(True, "B26: ein fehlerhafter Betreff laesst den Versand nicht scheitern")
    except Exception as e:
        pruefe(False, f"B26: ein fehlerhafter Betreff laesst den Versand nicht scheitern ({e})")
    _mcfg["mail"]["betreff"] = "Rechnung {bill_no}"
finally:
    _smtplib.SMTP, _smtplib.SMTP_SSL = _echt_smtp, _echt_smtp_ssl
# Befund 41: PDF-Ordner relativ zur Installation.
_pdfcfg = {"mail": {"pdf_ordner": "pdfablage", "pdf_muster": "{bill_no}.pdf"}}
(_config.CONFIG_DIR.parent / "pdfablage").mkdir(exist_ok=True)
(_config.CONFIG_DIR.parent / "pdfablage" / "4711.pdf").write_bytes(b"%PDF")
pruefe(_mailer.anhang_pdf(_pdfcfg, 4711) is not None,
       "B41: ein relativer PDF-Ordner gilt gegenueber der Installation")

# --- opera: Leitweg, Bemerkung, Vorlagen, Suche, Firmenprofile, Resort -------
_gerufen = []


def _db_befund(sql, parameter=None):
    kopfzeile = sql.splitlines()[0]
    _gerufen.append((kopfzeile, dict(parameter or {}), sql))
    if "invoice_header.sql" in kopfzeile:
        return [{"issuedate": "2026-09-10", "customer_name_id": 777, "reservierungsnummer": "4711",
                 "beleg_status": "OK", "document_type": "INVOICE"}]
    if "profil_udf" in kopfzeile or "@SPALTE@" in sql or "UDFC05" in sql:
        return [{"wert": "991-33333TEST-33"}]
    return []


_echt_abf2 = opera.db.abfrage
opera.db.abfrage = _db_befund
try:
    _bcfg = json.loads(json.dumps(cfg))
    _bcfg["property"].update(udf_leitweg="UDFC05", resort="MUSTER")
    _kk = opera.rechnung(_bcfg, 1)
    _udf = [g for g in _gerufen if "UDFC05" in g[2]]
    pruefe(bool(_udf) and _udf[0][1].get("name_id") == 777 and _kk["header"]["buyerreference"] == "991-33333TEST-33",
           f"B6: die Leitweg-ID wird ueber customer_name_id gelesen ({_kk['header'].get('buyerreference')})")
    # Befund 42: Resort in allen Abfragen je Beleg
    _je_beleg = [g for g in _gerufen if "bill_no" in g[1]]
    pruefe(all(g[1].get("resort") == "MUSTER" and ":resort" in g[2] for g in _je_beleg) and len(_je_beleg) >= 5,
           f"B42: jede Abfrage je Beleg filtert nach Resort ({[g[0][:28] for g in _je_beleg if g[1].get('resort') != 'MUSTER']})")
    _gerufen.clear()
    opera.empfaenger(1); opera.buchungsfirma(1)
    pruefe(all(":resort" in g[2] and g[1].get("resort") for g in _gerufen),
           "B42: auch Empfaenger und Buchungsfirma")
    # Befund 37/45: Suche und Firmenprofile
    _gerufen.clear()
    _scfg = json.loads(json.dumps(cfg))
    _scfg["auswahl"]["firmenprofile"] = ["COMPANY", "TRAVEL_AGENT"]
    opera.suchen(_scfg, "RE-1400003")
    pruefe(_gerufen[0][1]["invoice_no"] is None and _gerufen[0][1]["bill_no"] is None,
           "B37: ein Suchbegriff mit Buchstaben wird nicht als INVOICE_NO gebunden")
    pruefe("('COMPANY', 'TRAVEL_AGENT')" in _gerufen[0][2] and "/*FIRMENPROFILE*/" not in _gerufen[0][2],
           "B45: auswahl.firmenprofile wirkt in der Suche")
    _gerufen.clear()
    opera.suchen(_scfg, "1400003")
    pruefe(_gerufen[0][1]["invoice_no"] == 1400003, "B37: eine Nummer wird als Zahl gebunden")
    _gerufen.clear()
    _scfg["auswahl"]["firmenprofile"] = ["COMPANY'); DROP"]
    opera.kandidaten(_scfg, 30)
    pruefe("('COMPANY', 'TRAVEL_AGENT', 'G', 'S')" in _gerufen[0][2],
           "B45: ein unzulaessiger Eintrag geht nicht in die Abfrage")
finally:
    opera.db.abfrage = _echt_abf2
# Befund 12
_bz = [{"bem_remark": "Kulanz nach Rücksprache GM", "bem_reference": ""}]
opera.positionsbemerkung(_bz, {"positionsbemerkung": []})
pruefe(_bz[0]["bemerkung"] == "", "B12: eine leere Liste schaltet die Positionsbemerkung ab")
opera.positionsbemerkung(_bz, {"positionsbemerkung": ["remark"]})
pruefe(_bz[0]["bemerkung"] == "Kulanz nach Rücksprache GM", "B12: ein gewaehltes Feld wird ausgegeben")
# TZ1: REMARK ist das Feld, das OPERA in der Maske "Supplement" nennt —
# belegt an Beleg 1400001. Diese Pruefung stand kurzzeitig auf dem Gegenteil
# ("ohne Eintrag KEIN Feld"), weil eine 30-Tage-Stichprobe REMARK als interne
# Notiz erscheinen liess. Die Stichprobe traf fast nur Uebernachtungen.
opera.positionsbemerkung(_bz, {})
pruefe(_bz[0]["bemerkung"] == "Kulanz nach Rücksprache GM",
       "TZ1: ohne Eintrag gilt remark — das Supplement-Feld aus der Buchungsmaske")
_konf = [{"bem_remark": "Beamer Raum Lissabon / Muster Pharma GmbH",
          "bem_reference": "CHECK# 1000001 [1]"},
         {"bem_remark": "Tagungspauschale inklusive Abendessen", "bem_reference": ""},
         {"bem_remark": "DDR 13.03.2019", "bem_reference": ""}]
opera.positionsbemerkung(_konf, {})
pruefe([z["bemerkung"] for z in _konf] == ["Beamer Raum Lissabon / Muster Pharma GmbH",
                                           "Tagungspauschale inklusive Abendessen",
                                           "DDR 13.03.2019"],
       f"TZ1: der echte Supplement-Text kommt unveraendert durch ({[z['bemerkung'] for z in _konf]})")

# TZ2: Der Name eines FREMDEN Gastes darf nicht auf die Rechnung.
# OPERA schreibt bei umgeleiteten Buchungen "Routed From <Name> Of Room <Nr>"
# in REFERENCE — an echten Daten in 14,9 % der belegten Werte (TestZ,
# BERCC, 30 Tage, 16.09.2026), betroffen waere jede zwoelfte Firmenrechnung.
_tz = [{"bem_reference": "[NA P.Room] [Routed From Mustermann Erika Of Room 412]"},
       {"bem_reference": "[NA Pkgs.BFST] [Against Pkg.: BFST]"},
       {"bem_reference": "Routed From Mustermann Erika Of Room 412"},
       {"bem_reference": "CHECK# 0 [33] Routed From Mustermann Erika"}]
opera.positionsbemerkung(_tz, {"positionsbemerkung": ["reference"]})
pruefe(all("Mustermann" not in z["bemerkung"] and "Routed" not in z["bemerkung"] for z in _tz),
       f"TZ2: kein fremder Gastname in der Positionsbemerkung ({[z['bemerkung'] for z in _tz]})")
pruefe(_tz[0]["bemerkung"] == "[NA P.Room]", f"TZ2: der Rest bleibt stehen ({_tz[0]['bemerkung']})")
pruefe(_tz[1]["bemerkung"] == "[NA Pkgs.BFST] [Against Pkg.: BFST]",
       "TZ2: eine Bemerkung ohne Routing bleibt unveraendert")
pruefe(_tz[2]["bemerkung"] == "", "TZ2: besteht der Wert nur aus dem Routing-Hinweis, bleibt nichts")
pruefe(_tz[3]["bemerkung"] == "CHECK# 0 [33]",
       f"TZ2: auch ohne 'Of Room' faellt der Hinweis weg ({_tz[3]['bemerkung']})")
_tz_roh = [{"bem_remark": "Routed From irgendwo anders her"}]
opera.positionsbemerkung(_tz_roh, {"positionsbemerkung": ["remark"]})
pruefe(_tz_roh[0]["bemerkung"] == "",
       "TZ2: ein unbekanntes Routing-Muster laesst den ganzen Wert wegfallen, auch aus remark")

# TZ4: GEWAEHLTE RUFNUMMERN. Bei Telefonbuchungen ist das OPERA-"Supplement"
# genau das REFERENCE-Feld (View FT_HBCALLS_VIEW: ft.reference AS supplement),
# und in IFC_CALL_HIST tragen 49.967 von 50.000 Zeilen eine Ziffernfolge ab
# fuenf Stellen — die angerufene Nummer. Verkehrsdaten wiegen schwerer als
# ein Name (TestZ, 16.09.2026).
_tel = [{"bem_reference": "0301234567 12:44 03:21"},
        {"bem_reference": "CALL 00491701234567"},
        {"bem_reference": "[NA P.Room]"},
        {"bem_reference": "Zi. 412, 16.09.2026, 2 Nächte"},
        {"bem_reference": "CHECK# 0 [33]"}]
opera.positionsbemerkung(_tel, {"positionsbemerkung": ["reference"]})
pruefe(_tel[0]["bemerkung"] == "" and _tel[1]["bemerkung"] == "",
       f"TZ4: eine gewaehlte Rufnummer laesst die ganze Bemerkung wegfallen "
       f"({[z['bemerkung'] for z in _tel[:2]]})")
pruefe(_tel[2]["bemerkung"] == "[NA P.Room]" and _tel[4]["bemerkung"] == "CHECK# 0 [33]",
       "TZ4: kurze Zahlen bleiben — sonst kostet die Regel jede Bemerkung")
pruefe(_tel[3]["bemerkung"] == "Zi. 412, 16.09.2026, 2 Nächte",
       f"TZ4: Zimmernummer und Datum ueberstehen die Regel ({_tel[3]['bemerkung']})")
_tz_y = json.loads(json.dumps(rechnung))
_tz_y["lines"][0]["bemerkung"] = "Zi. 412 · Mustermann · 4111111111111111"
pruefe(any("Ziffernfolge" in f for f in xml_build.pruefsummen(xml_build.aufbereiten(_tz_y))),
       "TZ4: eine Karten- oder Auslandsrufnummer im Dokument haelt den Versand an")
_tz_z = json.loads(json.dumps(rechnung))
_tz_z["lines"][0]["bemerkung"] = "Zi. 4121 · Mustermann, Erika"
pruefe(not any("Ziffernfolge" in f for f in xml_build.pruefsummen(xml_build.aufbereiten(_tz_z))),
       "TZ4: eine vierstellige Zimmernummer haelt den Versand NICHT an")

# TZ5: Der Ziffernfilter haengt am FELD. Fuer REMARK ist er AUS — das Haus
# hat entschieden: ist das Supplement-Feld gefuellt, geht es vollstaendig auf
# die XRechnung (17.09.2026). Gekuerzt wird nichts. Fuer REFERENCE bleibt er
# scharf, dort stehen Rufnummern und Systemtext.
_v = [{"bem_remark": "Voucher 09000001"}, {"bem_remark": "Abr. CC'S 230626 HP"},
      {"bem_remark": "030552"}, {"bem_remark": "Karte 4111111111111111"}]
opera.positionsbemerkung(_v, {"positionsbemerkung": ["remark"]})
pruefe([z["bemerkung"] for z in _v] == ["Voucher 09000001", "Abr. CC'S 230626 HP",
                                        "030552", "Karte 4111111111111111"],
       f"TZ5: remark geht vollstaendig durch, auch mit Ziffern "
       f"({[z['bemerkung'] for z in _v]})")
_vr = [{"bem_reference": "Voucher 09000001"}]
opera.positionsbemerkung(_vr, {"positionsbemerkung": ["reference"]})
pruefe(_vr[0]["bemerkung"] == "",
       "TZ5: dieselbe Ziffernfolge faellt in reference weg — dort ist sie keine Kundenangabe")

# TZ6: Der Veranstaltername hinter dem Schraegstrich BLEIBT. Kurzzeitig fiel er
# weg, sobald ein Beleg mehrere verschiedene trug (1400001: Muster Pharma GmbH,
# Muster Technik AG, Reisedienst Nord, Beispiel Chemie GmbH). Das Haus hat dagegen entschieden: Der Text steht so
# auch auf der gedruckten Rechnung, und die XRechnung darf nichts anderes
# sagen als das Papier.
_sammel = [{"bem_remark": "Beamer Raum Lissabon / Muster Pharma GmbH"},
           {"bem_remark": "Beamer Raum Lissabon / Muster Technik AG"},
           {"bem_remark": "Raummiete / Reisedienst Nord"},
           {"bem_remark": "Tagungspauschale"}]
opera.positionsbemerkung(_sammel, {})
pruefe([z["bemerkung"] for z in _sammel] == ["Beamer Raum Lissabon / Muster Pharma GmbH",
                                             "Beamer Raum Lissabon / Muster Technik AG",
                                             "Raummiete / Reisedienst Nord", "Tagungspauschale"],
       f"TZ6: der Veranstaltername bleibt stehen, auch bei mehreren auf einem Beleg "
       f"({[z['bemerkung'] for z in _sammel]})")

# TZ7: Bei Gruppen steht vor dem Supplement-Text die Kennung des Gastes —
# BT-127 traegt beides, durch ' · ' getrennt. Der erfasste Text bleibt dabei
# unveraendert; er wird nur ergaenzt, nicht umgeschrieben.
_grp_b = opera.positionen_buendeln(
    [{"gast_resv_name_id": 7, "gast_zimmer": "412", "gast_name": "Mustermann, Erika",
      "itemcode": "2920", "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19,
      "bruttopreis": 230.0, "invoicedquantity": 1, "lineextensionamount": 230.0,
      "lineextensionamountnet": 193.28, "leistungsdatum": "2026-09-01",
      "bemerkung": "Beamer Raum Lissabon / Muster Pharma GmbH"}], "C")
pruefe(_grp_b[0]["bemerkung"] == "Zi. 412 · Mustermann, Erika · Beamer Raum Lissabon / Muster Pharma GmbH",
       f"TZ7: BT-127 traegt Gast, Zimmer UND den vollstaendigen Supplement-Text "
       f"({_grp_b[0]['bemerkung']})")
# TZ3: letzte Verteidigungslinie — kommt es doch bis ins Dokument, kein Versand.
_tz_x = json.loads(json.dumps(rechnung))
_tz_x["lines"][0]["bemerkung"] = "Routed From Mustermann Erika Of Room 412"
pruefe(any("fremden Gast" in f for f in xml_build.pruefsummen(xml_build.aufbereiten(_tz_x))),
       "TZ3: ein fremder Gastname im Dokument haelt den Versand an")
# Befund 13: halb gefuellte Vorlage
pruefe(opera._vorlage_fuellen("{kunde} / {debitor}", {"customername": "Firma GmbH"}, {}, 1) == "",
       "B13: eine halb gefuellte Vorlage wird nicht verwendet")
pruefe(opera._vorlage_fuellen("{kunde", {"customername": "Firma GmbH"}, {}, 1) == "",
       "B26: eine kaputte Vorlage wirft nicht")
# Absichtlich mit try: Wirft die Funktion doch, soll das hier als FEHL stehen
# und nicht den ganzen Selbsttest abbrechen — ein Abbruch sieht in der
# Gegenprobe wie "kein Fehler" aus.
try:
    _gz = opera.gastzeile({"gastname": "Mustermann"}, {"gastzeile": "Gast {gast!q}"})
    pruefe("note" not in _gz, "B26: eine kaputte Gastzeilen-Vorlage wirft nicht und faellt weg")
except Exception as _e:
    pruefe(False, f"B26: eine kaputte Gastzeilen-Vorlage wirft nicht und faellt weg ({_e})")
_kr = opera.kaeuferreferenz({"buyerreference": None, "reservierungsnummer": "3000001"},
                           {"haus": "Haus", "buyerreference_vorlage": "{haus} ReservNr.: {reservierungsnummer}"}, 1)
pruefe(_kr["buyerreference"] == "Haus ReservNr.: 3000001",
       "B13: ohne Referenz aus OPERA greift die Vorlage des Hauses")

# --- SQL-Texte (ohne Kommentare) --------------------------------------------
def _sql_ohne_kommentar(name):
    return "\n".join(z.split("--")[0] for z in
                     (BASE / "sql" / "opera" / name).read_text(encoding="utf-8").splitlines())


_empf_sql = _sql_ohne_kommentar("invoice_recipients.sql")
pruefe("b.payee_name_id IS NULL OR b.payee_name_id = b.name_id" in _empf_sql,
       "B4: das Folio-Profil (meist der Gast) nur, wenn es keinen anderen Zahler gibt")
pruefe("NVL(z.pct, 0)" in _sql_ohne_kommentar("invoice_tax.sql").split("GROUP BY")[1],
       "B18: Steuergruppen ohne Satz und mit 0 % werden zusammengefasst")
pruefe("beleg_status" in _sql_ohne_kommentar("invoice_header.sql"),
       "B7: der Belegstatus wird bei jedem Erzeugen gelesen")
pruefe("payee_name" in _sql_ohne_kommentar("invoice_list.sql"),
       "B38: die Einleseliste liefert den Zahlernamen")

# OE1: Das Datenbankschema ist konfigurierbar. Vorher stand "opera." in allen
# 15 Abfragen fest, waehrend die Konfiguration ein Feld "schema" anbot, das
# NIRGENDS gelesen wurde — eine Einstellung, die etwas verspricht und nichts
# tut. Ein Haus mit abweichendem Schemanamen konnte die Anwendung nicht
# betreiben.
_sql_dateien = sorted((BASE / "sql" / "opera").glob("*.sql"))
pruefe(all("@SCHEMA@" in d.read_text(encoding="utf-8") for d in _sql_dateien
           if "FROM " in d.read_text(encoding="utf-8").upper()),
       "OE1: jede Abfrage benutzt den Platzhalter fuer das Schema")
pruefe(not any(_re.search(r"(?i)\b(from|join)\s+opera\.", d.read_text(encoding="utf-8"))
               for d in _sql_dateien),
       "OE1: kein fest verdrahtetes Schema mehr in den Abfragen")
_cfg_schema = json.loads(json.dumps(cfg))
_cfg_schema["datenbank"]["schema"] = "PMS_PROD"
pruefe("FROM PMS_PROD.folio$_tax" in opera._sql("invoice_header.sql", _cfg_schema),
       "OE1: der konfigurierte Schemaname landet in der Abfrage")
pruefe("@SCHEMA@" not in opera._sql("invoice_header.sql", _cfg_schema),
       "OE1: es bleibt kein Platzhalter stehen")
_cfg_leer = json.loads(json.dumps(cfg))
_cfg_leer["datenbank"]["schema"] = ""
pruefe("FROM OPERA.folio$_tax" in opera._sql("invoice_header.sql", _cfg_leer),
       "OE1: ohne Eintrag gilt OPERA")
_cfg_boese = json.loads(json.dumps(cfg))
_cfg_boese["datenbank"]["schema"] = "x; DROP TABLE folios--"
pruefe("DROP TABLE" not in opera._sql("invoice_header.sql", _cfg_boese)
       and "FROM OPERA.folio$_tax" in opera._sql("invoice_header.sql", _cfg_boese),
       "OE1: ein unzulaessiger Schemaname kommt nicht in die Abfrage")

# OE2: Anzahlungen werden ueber die Folio-Klammer erkannt, nicht ueber eine
# Liste von Umsatzcodes. Die Liste war in jedem anderen Haus falsch — und in
# dem Haus, aus dem sie stammte, unvollstaendig: Die drei haeufigsten
# Anzahlungscodes fehlten (12.475 Vorkommen ueber ein Jahr). Eine nur darueber
# angezahlte Schlussrechnung galt damit als Nullbeleg.
for _n in ("invoice_guard.sql", "invoice_list.sql", "invoice_deposits.sql"):
    _q = _sql_ohne_kommentar(_n)
    pruefe(":anzahlung_status" in _q,
           f"OE2: {_n} erkennt Anzahlungen ueber den Belegstatus")
    pruefe(not _re.search(r"trx_code\s+IN\s*\(", _q),
           f"OE2: {_n} entscheidet nicht mehr ueber eine Umsatzcode-Liste")
pruefe("folios fo" in _sql_ohne_kommentar("invoice_guard.sql")
       and "folios fo" in _sql_ohne_kommentar("invoice_list.sql"),
       "OE2: beide gehen ueber FOLIOS auf das Folio — der Weg mit dem Index")
pruefe(opera.anzahlung_status({}) == "DEPOSIT", "OE2: ohne Eintrag gilt DEPOSIT")
pruefe(opera.anzahlung_status({"auswahl": {"anzahlung_status": "anzahlung"}}) == "ANZAHLUNG",
       "OE2: eine andere OPERA-Version laesst sich uebersteuern")
pruefe(json.loads((BASE / "config" / "app.example.json").read_text(encoding="utf-8"))
       ["auswahl"]["anzahlung_status"] == "DEPOSIT",
       "OE2: die Vorlage nennt den Wert, statt ihn zu verstecken")

# OE3: Die Codes sind nachpruefbar UND wirksam uebersteuerbar. Eine
# Einstellung, die nur dasteht, ist schlimmer als keine — siehe das tote
# Feld "schema" und "automatisch_pruefen".
_roh_g = opera._sql("invoice_guard.sql", cfg)
pruefe("/*ODER_CODES*/" in _roh_g and "/*ODER_CODES*/" in opera._sql("invoice_list.sql", cfg),
       "OE3: beide Abfragen haben den Einhaengepunkt fuer eigene Codes")
pruefe(opera._mit_anzahlungscodes(_roh_g, {}) == _roh_g,
       "OE3: ohne Eintrag bleibt die Abfrage unveraendert")
_mit_c = opera._mit_anzahlungscodes(_roh_g, {"auswahl": {"anzahlungscodes": ["8990", "dep1"]}})
pruefe("'8990', 'DEP1'" in _mit_c and "t.trx_code IN" in _mit_c
       and ":anzahlung_status" in _mit_c,
       f"OE3: eigene Codes kommen ZUSAETZLICH zur Statusregel hinzu")
_boese_c = opera._mit_anzahlungscodes(_roh_g, {"auswahl": {"anzahlungscodes": ["x'); DROP--"]}})
pruefe("DROP" not in _boese_c and _boese_c == _roh_g,
       "OE3: ein unzulaessiger Code aendert die Abfrage nicht")
pruefe((BASE / "sql" / "opera" / "anzahlungscodes.sql").exists()
       and ":anzahlung_status" in _sql_ohne_kommentar("anzahlungscodes.sql")
       and "zahlungsart" in _sql_ohne_kommentar("anzahlungscodes.sql"),
       "OE3: die Abfrage zum Nachsehen liegt bereit und trennt die Zahlungsarten ab")
pruefe("/einrichtung/anzahlungen" in
       (BASE / "app" / "templates" / "konfiguration.html").read_text(encoding="utf-8"),
       "OE3: die Konfiguration verweist auf die Einrichtungsseite")

# --- xml_build --------------------------------------------------------------
_neg = json.loads(json.dumps(rechnung))
_neg["lines"] = [{"itemname": "Menge negativ", "itemcode": "1", "invoicedquantity": -1,
                  "lineextensionamountnet": 50.00, "lineextensionamount": 59.50,
                  "classifiedtaxcategoryid": "S", "classifiedtaxcategorypercent": 19}]
_neg["tax_breakdown"] = [{"taxcategorypercent": 19, "taxcategoryid": "S", "taxableamount": 50.00, "taxamount": 9.50}]
_neg["totals"] = {"invoicenet": 50.00, "invoicegross": 59.50, "invoicetaxtotal": 9.50}
_neg["kontrolle"] = {"kopf_netto": 50.00, "kopf_brutto": 59.50, "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}
_neg["header"]["payableamount"] = 59.50
_nx = xml_build.bauen(_neg).decode()
pruefe(_betrag(_nx, "PriceAmount") == 50.00 and "<cbc:InvoicedQuantity unitCode=\"C62\">1<" in _nx,
       f"B14: negative Menge bei positivem Betrag ergibt Menge 1 zu 50,00 ({_betrag(_nx, 'PriceAmount')})")
_neg300 = json.loads(json.dumps(_neg))
_neg300["lines"][0].update(invoicedquantity=-300, lineextensionamountnet=10.01, lineextensionamount=11.91)
_neg300["tax_breakdown"][0].update(taxableamount=10.01, taxamount=1.90)
_neg300["totals"] = {"invoicenet": 10.01, "invoicegross": 11.91}
_neg300["kontrolle"].update(kopf_netto=10.01, kopf_brutto=11.91)
_n3 = xml_build.bauen(_neg300).decode()
pruefe("-" not in (_re.search(r"<cbc:BaseQuantity[^>]*>([^<]*)<", _n3) or [None, "x"])[1],
       "B14: auch die Bezugsmenge ist nie negativ")
_steuer = json.loads(json.dumps(rechnung))
_steuer["header"]["customername"] = "Meyer\x0c GmbH\x00"
pruefe(xml_build._leer_statt_none("Meyer\x0c GmbH\x00") == "Meyer GmbH",
       "B25: Steuerzeichen werden aus dem Wert entfernt")
try:
    _sx = xml_build.bauen(_steuer).decode()
    pruefe("\x0c" not in _sx and "\x00" not in _sx and "Meyer GmbH" in _sx,
           "B25: Steuerzeichen aus OPERA machen die Rechnung nicht unbaubar")
except Exception as _e:
    pruefe(False, f"B25: Steuerzeichen aus OPERA machen die Rechnung nicht unbaubar ({_e})")
_pre = json.loads(json.dumps(rechnung))
_pre["header"]["prepaidamount"] = -10.00
_px = xml_build.bauen(_pre).decode()
pruefe(_betrag(_px, "PrepaidAmount") == -10.00, "B24: eine negative Anzahlung wird ausgewiesen")
# BR-DE-6/BR-DE-7: Telefon und E-Mail des Hauses sind Pflicht. Ohne sie lehnt
# der KoSIT-Validator ab — gesehen an vier selbst gebauten Grenzfaellen, deren
# Vorpruefung "sauber" meldete.
for _feld, _regel in (("suppliercontacttelephone", "BR-DE-6"), ("suppliercontactelectronicmail", "BR-DE-7")):
    _ohne = json.loads(json.dumps(rechnung))
    _ohne["header"][_feld] = ""
    pruefe(any(_regel in h for h in xml_build.pruefsummen(_ohne)),
           f"{_regel}: fehlendes Pflichtfeld des Hauses faellt in der Vorpruefung auf ({_feld})")
_void = json.loads(json.dumps(rechnung))
_void["header"].update(beleg_status="VOID", document_type="INVOICE")
pruefe(any("storniert" in h for h in xml_build.pruefsummen(_void)), "B7: ein stornierter Beleg wird nicht versendet")
_adv = json.loads(json.dumps(rechnung))
_adv["header"].update(beleg_status="OK", document_type="ADVANCE INVOICE")
pruefe(any("keine Endrechnung" in h for h in xml_build.pruefsummen(_adv)),
       "B11: eine Anzahlungsrechnung wird nicht als Rechnung versendet")
_kb = json.loads(json.dumps(rechnung))
_kb["tax_kopf"] = [{"taxcategorypercent": 7, "taxableamount": 3094.04},
                   {"taxcategorypercent": 19, "taxableamount": 113.40},
                   {"taxcategorypercent": 0, "taxableamount": 243.00}]
pruefe(xml_build.pruefsummen(_kb) == [], f"B46: der Rechnungskopf bestaetigt die Steuergruppen ({xml_build.pruefsummen(_kb)})")
_kb["tax_kopf"] = [{"taxcategorypercent": 7, "taxableamount": 3000.00},
                   {"taxcategorypercent": 19, "taxableamount": 207.44},
                   {"taxcategorypercent": 0, "taxableamount": 243.00}]
pruefe(any("Rechnungskopf" in h for h in xml_build.pruefsummen(_kb)),
       "B46: weicht der Kopf bei einem Satz ab, faellt es auf")
# Fuehrte der Kopf die Saetze in einer anderen Einheit (0.19 statt 19), passte
# KEIN Satz zusammen — die Gegenprobe wuerde dann jede Rechnung sperren. In dem
# Fall bleibt sie aus; die uebrigen Pruefungen laufen weiter.
_kb2 = json.loads(json.dumps(rechnung))
_kb2["tax_kopf"] = [{"taxcategorypercent": 0.07, "taxableamount": 3094.04},
                    {"taxcategorypercent": 0.19, "taxableamount": 113.40},
                    {"taxcategorypercent": 0, "taxableamount": 243.00}]
pruefe(xml_build.pruefsummen(_kb2) == [],
       f"B46: eine andere Einheit im Kopf sperrt nicht jede Rechnung ({xml_build.pruefsummen(_kb2)})")
_kb3 = json.loads(json.dumps(_kb2))
_kb3["totals"]["invoicegross"] = 0.0
_kb3["lines"] = []
_kb3["tax_breakdown"] = []
_kb3["kontrolle"] = {"kopf_netto": 0.0, "kopf_brutto": 0.0, "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}
pruefe(any("Nullbeleg" in h for h in xml_build.pruefsummen(_kb3)),
       "und die Pruefungen danach laufen trotzdem")

# --- C: Zeitraum aus den Buchungstagen, Kopfgast bei Gruppen -----------------
_cz = [dict(_buchung(1, "1000", "Ü", 100.0, 7, gast=1, zimmer="1", gastname="A", von="2025-01-01", bis="2026-12-31"),
            leistungsdatum="2026-09-07"),
       dict(_buchung(2, "1000", "Ü", 100.0, 7, gast=1, zimmer="1", gastname="A", von="2025-01-01", bis="2026-12-31"),
            leistungsdatum="2026-09-08")]
_czb = opera.positionen_buendeln(_cz, "C")[0]
pruefe((_czb["zeitraum_beginn"], _czb["zeitraum_ende"]) == ("2026-09-07", "2026-09-08"),
       f"B33: der Positionszeitraum sind die berechneten Tage, nicht der Aufenthalt ({_czb.get('zeitraum_beginn')})")
_echt_r5, _echt_e5 = opera.rechnung, opera.empfaenger
_grp = json.loads(json.dumps(_gruppe))
_grp["header"].update(gastname="Musterfrau, Lena", note="Gast: Musterfrau", gastzeile_text="Gast: Musterfrau")
opera.rechnung = lambda cfg, bill_no: json.loads(json.dumps(_grp))
opera.empfaenger = lambda bill_no: []
store.rechnung_anlegen({"bill_no": 1399002, "resort": "IHRHAUS", "kunde": "G"}, 0)
try:
    store.setzen(1399002, positionen="C")
    _gd = ablauf.rechnungsdaten(cfg, 1399002)
    pruefe(not _gd["header"].get("gastname") and not _gd["header"].get("note"),
           "B33: eine Gruppenrechnung nennt am Kopf nicht nur den Gast der Kopfreservierung")
    store.setzen(1399002, positionen="B")
    pruefe(ablauf.rechnungsdaten(cfg, 1399002)["header"].get("gastname") == "Musterfrau, Lena",
           "B33: zusammengefasst bleibt der Gast am Kopf")
finally:
    opera.rechnung, opera.empfaenger = _echt_r5, _echt_e5
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no = 1399002")

# --- Einlesen: Gruende bleiben, Nullkopf mit Anzahlung ------------------------
_echt_k6, _echt_e6 = opera.kandidaten, opera.empfaenger
_kand = [
    {"bill_no": 960001, "issuedate": "2026-09-01", "total_gross": 300.0, "total_net": 260.0,
     "company_name": "Meyer AG", "payee_name": "Schulz", "empfaenger_typ": "D", "empfaenger_land": "DE",
     "firmenbezug": "RESERVIERUNG", "invoice_no": "1"},
    {"bill_no": 960002, "issuedate": "2026-09-01", "total_gross": 0.0, "total_net": 0.0,
     "company_name": "Vorkasse GmbH", "empfaenger_typ": "COMPANY", "empfaenger_land": "DE",
     "firmenbezug": "EMPFAENGER", "invoice_no": "2", "ohne_anzahlung": "N"},
]
_adr = {"960001": []}
opera.kandidaten = lambda cfg, tage=None: _kand
opera.empfaenger = lambda bill_no: [] if _adr.get(str(bill_no)) == [] else [{"email": "rechnung@firma.example"}]
_ecfg = json.loads(json.dumps(cfg))
_ecfg["automatik"]["empfaenger_automatisch"] = True
try:
    ablauf.einlesen(_ecfg)
    _r1 = store.rechnung(960001)
    pruefe("Reservierung" in (_r1["fehler"] or "") and "E-Mail-Adresse" in (_r1["fehler"] or ""),
           f"B1: beide Pruefgruende bleiben stehen ({_r1['fehler']})")
    _adr["960001"] = None                          # Adresse inzwischen gepflegt
    ablauf.einlesen(_ecfg)
    _r1 = store.rechnung(960001)
    pruefe(_r1["status"] == "pruefung" and "Reservierung" in (_r1["fehler"] or ""),
           f"B1: die gepflegte Adresse gibt den Beleg NICHT frei ({_r1['status']}: {_r1['fehler']})")
    _r2 = store.rechnung(960002)
    pruefe(_r2["status"] == "pruefung", f"B10: Kopf 0,00 mit Anzahlungen kommt in die Pruefung ({_r2['status']})")
    pruefe(_r1.get("kunde") == "Meyer AG", "B38: der Kunde steht in der Liste")
finally:
    opera.kandidaten, opera.empfaenger = _echt_k6, _echt_e6
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no IN (960001, 960002)")

# --- Aufnehmen: Dokumentart --------------------------------------------------
_echt_s7, _echt_e7 = opera.suchen, opera.empfaenger
opera.suchen = lambda cfg, begriff: [{"bill_no": 960003, "invoice_no": "3", "issuedate": "2026-09-01",
                                      "document_type": "ADVANCE INVOICE", "beleg_status": "OK",
                                      "total_net": 100.0, "total_gross": 119.0, "kunde": "Firma",
                                      "empfaenger_typ": "COMPANY", "empfaenger_land": "DE",
                                      "firmenbezug": "EMPFAENGER"}]
opera.empfaenger = lambda bill_no: [{"email": "rechnung@firma.example"}]
try:
    ablauf.aufnehmen(_ecfg, 960003)
    _r3 = store.rechnung(960003)
    pruefe(_r3["status"] == "pruefung" and "Dokumentart" in (_r3["fehler"] or ""),
           f"B11: eine Anzahlungsrechnung aus der Suche kommt in die Pruefung ({_r3['fehler']})")
finally:
    opera.suchen, opera.empfaenger = _echt_s7, _echt_e7
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no = 960003")
_echt_e8 = opera.empfaenger
opera.empfaenger = lambda bill_no: [{"email": "a@firma.example; b@firma.example"}, {"email": "ok@firma.example"}]
try:
    pruefe([a["email"] for a in ablauf.empfaenger_kandidaten(1)] == ["ok@firma.example"],
           "B19: mehrere Adressen in einem OPERA-Feld werden nicht vorbelegt")
finally:
    opera.empfaenger = _echt_e8

# --- Versenden: Status, Doppelklick, Testlauf, Ergebnis offen ----------------
_gesendet = []
_echt_senden, _echt_rd9 = _mailer.senden, ablauf.rechnungsdaten
ablauf.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(dict(rechnung, positionsart="B")))
_vcfg = json.loads(json.dumps(cfg))
_vcfg["validierung"].update(aktiv=False, pflicht=False)
_vcfg["automatik"]["testlauf"] = False
_vcfg["mail"]["erlaubte_empfaenger"] = []


def _senden_zaehlen(cfg, **k):
    import time as _t
    _t.sleep(0.2)
    _gesendet.append(k["bill_no"])
    return "<id@test>"


_mailer.senden = _senden_zaehlen
store.rechnung_anlegen({"bill_no": 960010, "resort": "IHRHAUS", "kunde": "V", "total_gross": 119.0}, 0)
store.setzen(960010, empfaenger="rechnung@firma.example", status="bereit")
try:
    _faeden = [_threading.Thread(target=lambda: _versuch()) for _ in range(3)]
    _ergebnisse = []

    def _versuch():
        try:
            _ergebnisse.append(ablauf.versenden(_vcfg, 960010, benutzer="k"))
        except Exception as e:
            _ergebnisse.append(type(e).__name__)

    for f in _faeden:
        f.start()
    for f in _faeden:
        f.join()
    pruefe(_gesendet.count(960010) == 1 and _ergebnisse.count("BereitsVersendet") == 2,
           f"B5: drei gleichzeitige Klicks verschicken die Rechnung genau einmal ({_ergebnisse})")
    store.setzen(960010, status="ignoriert")
    try:
        ablauf.versenden(_vcfg, 960010)
        pruefe(False, "B5: eine zurueckgelegte Rechnung wird nicht versendet")
    except ValueError:
        pruefe(_gesendet.count(960010) == 1, "B5: eine zurueckgelegte Rechnung wird nicht versendet")
    # Testlauf
    store.setzen(960010, status="bereit", gesendet_am=None, testlauf_am=None)
    _vcfg["automatik"]["testlauf"] = True
    pruefe(ablauf.versenden(_vcfg, 960010) == "testlauf"
           and store.rechnung(960010)["status"] == "bereit" and store.rechnung(960010)["testlauf_am"],
           "B23: der Testlauf vermerkt den Beleg und laesst den Status")
    pruefe(not [s for s in store.faellige(20, city_ledger=True, testlauf=True) if s["bill_no"] == 960010]
           and [s for s in store.faellige(20, city_ledger=True, testlauf=False) if s["bill_no"] == 960010],
           "B23: im Testlauf wird er nicht erneut genommen, danach schon")
    _vcfg["automatik"]["testlauf"] = False
    # Ergebnis offen: der Mailer bricht unerwartet ab
    _mailer.senden = lambda cfg, **k: (_ for _ in ()).throw(RuntimeError("Verbindung weg nach DATA"))
    try:
        ablauf.versenden(_vcfg, 960010)
    except RuntimeError:
        pass
    _r10 = store.rechnung(960010)
    pruefe(_r10["status"] == "fehler" and ablauf.VERSAND_OFFEN in (_r10["fehler"] or ""),
           f"B47: bricht der Versand unklar ab, steht der Beleg auf 'fehler' mit Vermerk ({_r10['status']})")
    pruefe(not [s for s in store.faellige(20, city_ledger=True) if s["bill_no"] == 960010],
           "B47: und die Automatik nimmt ihn nicht wieder")
    _mailer.senden = lambda cfg, **k: (_ for _ in ()).throw(_mailer.MailFehler("abgelehnt"))
    store.setzen(960010, status="bereit", fehler=None)
    try:
        ablauf.versenden(_vcfg, 960010)
    except _mailer.MailFehler:
        pass
    pruefe(store.rechnung(960010)["status"] == "fehler", "B2: ein abgelehnter Versand steht auf 'fehler'")
    # xml_erzeugen: Ansehen schreibt nichts, Befund getrennt von Gruenden
    store.setzen(960010, status="pruefung", fehler="Firma an der Reservierung", pruefbefund=None, xml_pfad=None)
    ablauf.xml_erzeugen(_vcfg, 960010, ablegen=False)
    _r11 = store.rechnung(960010)
    pruefe(_r11["fehler"] == "Firma an der Reservierung" and not _r11["xml_pfad"],
           "B7: XML ansehen schreibt nichts")
    ablauf.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(dict(ohne_leitweg, positionsart="B")))
    ablauf.xml_erzeugen(_vcfg, 960010)
    _r11 = store.rechnung(960010)
    pruefe(_r11["fehler"] == "Firma an der Reservierung" and "BR-DE-15" in (_r11["pruefbefund"] or ""),
           "B7: XML erzeugen legt den Befund ab, ohne den Pruefgrund zu ueberschreiben")
    # Befund 20: pflicht ohne aktiv
    ablauf.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(dict(rechnung, positionsart="B")))
    _vcfg["validierung"].update(aktiv=False, pflicht=True)
    _, _, _h20 = ablauf.xml_erzeugen(_vcfg, 960010)
    pruefe(any("Pflicht" in h for h in _h20), "B20: Pflicht wirkt auch bei abgeschalteter Validierung")
    _vcfg["validierung"].update(aktiv=False, pflicht=False)
    # Befund 33: Gruppenrechnung nicht automatisch vor der Datenprobe.
    # Der Schalter wird hier AUSDRUECKLICH gesetzt: Seit die Zuordnung an
    # Daten belegt ist, steht er in der Vorlage auf true — und die Pruefung
    # haette sonst geprueft, wie das Haus gerade eingestellt ist, statt ob
    # die Sperre funktioniert.
    ablauf.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(dict(rechnung, positionsart="C")))
    _mailer.senden = _senden_zaehlen
    _vcfg["property"]["gastzuordnung_bestaetigt"] = False
    store.setzen(960010, status="bereit", fehler=None)
    pruefe(ablauf.versenden(_vcfg, 960010, benutzer="automatik") == "pruefung"
           and store.rechnung(960010)["status"] == "pruefung" and _gesendet.count(960010) == 1,
           "B33: die Automatik schickt eine Rechnung je Gast nicht ohne bestaetigte Zuordnung")
finally:
    _mailer.senden, ablauf.rechnungsdaten = _echt_senden, _echt_rd9
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no = 960010")

# --- Anmeldung ----------------------------------------------------------------
auth.anlegen("wird_geloescht", "Loeschen!123", "verwalten")
_tok = auth.anmelden("wird_geloescht", "Loeschen!123", "127.0.0.1")
pruefe(auth.sitzung(_tok)["rolle"] == "verwalten", "B9: Ausgangslage — Sitzung mit Verwaltungsrecht")
_ud = json.loads(auth.USER_DATEI.read_text(encoding="utf-8"))
_ud["wird_geloescht"]["rolle"] = "ansehen"
_config._schreiben(auth.USER_DATEI, json.dumps(_ud))
pruefe(auth.sitzung(_tok)["rolle"] == "ansehen", "B9: eine Herabstufung wirkt sofort")
auth.loeschen("wird_geloescht")
pruefe(auth.sitzung(_tok) is None, "B9: ein geloeschter Zugang hat keine Sitzung mehr")
pruefe(auth.neu_anlegen("pruefer", "Irgendwas!123", "ansehen") is not None,
       "B35: ein vorhandener Zugang wird nicht still ueberschrieben")
_alle = json.loads(auth.USER_DATEI.read_text(encoding="utf-8"))
_verw = [n for n, d in _alle.items() if d.get("rolle") == "verwalten"]
for _n in _verw[1:]:
    auth.loeschen(_n)
pruefe(auth.loeschen(_verw[0]) is not None, "B35: der letzte Verwalter laesst sich nicht loeschen")
for _n in _verw[1:]:
    auth.anlegen(_n, "Geheim!123", "verwalten")

# --- Validator-Daemon, Datenbank, Konfiguration, Automatik -------------------
_popen_args = []


class _FalscherProzess:
    returncode = 1

    def __init__(self, befehl, **kw):
        _popen_args.append(kw)

    def poll(self):
        return 1


import subprocess as _sp
_echt_popen = _sp.Popen
_sp.Popen = _FalscherProzess
try:
    _val._daemon["gescheitert_bis"] = 0.0
    _z = {"java": "java", "jar": "x.jar", "szenarien": str(BASE / "x" / "scenarios.xml")}
    pruefe(_val._daemon_starten(_z, wartezeit=1) == 0, "B12: ein Daemon, der sofort endet, wird nicht benutzt")
    pruefe(_popen_args and _popen_args[0].get("stdout") == _sp.DEVNULL,
           "B12: die Ausgabe des Daemons geht nicht in eine ungelesene Pipe")
    _val._daemon_starten(_z, wartezeit=1)
    pruefe(len(_popen_args) == 1, "B12: nach einem Fehlstart wird nicht bei jeder Rechnung neu gestartet")
finally:
    _sp.Popen = _echt_popen
    _val._daemon["gescheitert_bis"] = 0.0


class _FalscheVerbindung:
    call_timeout = 0

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def cursor(self):
        class _C:
            description = None

            def execute(self, *a):
                pass
        return _C()


class _FalscherPool:
    def __init__(self):
        self.con = _FalscheVerbindung()

    def acquire(self):
        return self.con


_echt_pool = _db._pool
_db._pool = _FalscherPool()
try:
    _db.abfrage("SELECT 1 FROM dual")
    pruefe(_db._pool.con.call_timeout > 0, "B21: jede Oracle-Abfrage hat eine Zeitgrenze")
finally:
    _db._pool = _echt_pool

_c1 = _config.laden()
_c1["mail"]["bcc"] = "veraendert@nur.hier"
pruefe(_config.laden()["mail"]["bcc"] != "veraendert@nur.hier",
       "B51: der Konfigurations-Zwischenspeicher gibt Kopien heraus")

_echt_einl = ablauf.einlesen
_tage_gesehen = []
_waehrend = []


def _einlesen_stub(cfg, tage=None):
    _tage_gesehen.append(tage)
    # Waehrend des Laufs MUSS die Flagge stehen. Vorher prueften wir sie nur
    # danach — und das galt auch ohne jedes _laeuft.set().
    _waehrend.append(_automatik.laeuft_gerade())
    import time as _t
    _t.sleep(0.4)
    return {"gelesen": 0}


ablauf.einlesen = _einlesen_stub
_echt_fae = store.faellige
store.faellige = lambda *a, **k: []
try:
    _zweiter = []
    _f2 = _threading.Thread(target=lambda: _zweiter.append(_automatik._durchlauf_sync()))
    _f1 = _threading.Thread(target=_automatik._durchlauf_sync)
    _f1.start()
    import time as _zeit
    _zeit.sleep(0.15)
    _f2.start()
    _f1.join(); _f2.join()
    pruefe(_tage_gesehen == [None], "B34: die Automatik liest mit dem Zeitraum der Konfiguration ein")
    pruefe(_waehrend == [True], "waehrend des Laufs steht die Flagge — und ein zweiter Lauf startet nicht")
    pruefe(not _automatik.laeuft_gerade(), "danach ist sie wieder frei")
finally:
    ablauf.einlesen, store.faellige = _echt_einl, _echt_fae

# --- Folgefehler aus der Nachpruefung vom 16.09.2026 ------------------------
print("10b) Nachpruefung der Korrekturen")
_echt_einl2, _echt_fae2, _echt_send2 = ablauf.einlesen, store.faellige, ablauf.versenden
store.rechnung_anlegen({"bill_no": 960020, "resort": "IHRHAUS", "kunde": "Besetzt GmbH",
                        "total_gross": 119.0}, 0)
store.setzen(960020, status="bereit", empfaenger="rechnung@firma.example", fehler=None)
try:
    # N1: Ein besetzter Versand ist kein Fehler DES BELEGS.
    ablauf.einlesen = lambda cfg, tage=None: {"gelesen": 0}
    store.faellige = lambda *a, **k: [dict(store.rechnung(960020))]
    ablauf.versenden = lambda cfg, bill_no, benutzer="system": (_ for _ in ()).throw(
        ablauf.Beschaeftigt("Gerade wird eine andere Rechnung versendet"))
    _automatik._durchlauf_sync()
    _r = store.rechnung(960020)
    pruefe(_r["status"] == "bereit" and [s for s in store.faellige(20, city_ledger=True)],
           f"N1: ein besetzter Versand laesst den Beleg faellig, statt ihn auf 'fehler' zu legen ({_r['status']})")
    pruefe(any("uebersprungen" in (p["text"] or "") for p in store.protokoll_lesen(10, 960020)),
           "N1: und es steht im Verlauf")
finally:
    ablauf.einlesen, store.faellige, ablauf.versenden = _echt_einl2, _echt_fae2, _echt_send2
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no = 960020")

# N4: Eine freigegebene Gruppenrechnung nimmt die Automatik nicht zurueck.
_echt_rd4, _echt_send4 = ablauf.rechnungsdaten, _mailer.senden
_geschickt4 = []
ablauf.rechnungsdaten = lambda cfg, bill_no: json.loads(json.dumps(dict(rechnung, positionsart="C")))
_mailer.senden = lambda cfg, **k: _geschickt4.append(k["bill_no"]) or "<id@test>"
_ncfg = json.loads(json.dumps(cfg))
_ncfg["validierung"].update(aktiv=False, pflicht=False)
_ncfg["automatik"]["testlauf"] = False
_ncfg["mail"]["erlaubte_empfaenger"] = []
_ncfg["property"]["gastzuordnung_bestaetigt"] = False
store.rechnung_anlegen({"bill_no": 960021, "resort": "IHRHAUS", "kunde": "Gruppe GmbH",
                        "total_gross": 119.0}, 0)
store.setzen(960021, status="bereit", empfaenger="rechnung@firma.example")
try:
    pruefe(ablauf.versenden(_ncfg, 960021, benutzer="automatik") == "pruefung",
           "N4: ohne Freigabe legt die Automatik die Gruppenrechnung in die Pruefung")
    store.setzen(960021, status="bereit", fehler=None, freigabe_am=store.jetzt())
    pruefe(ablauf.versenden(_ncfg, 960021, benutzer="automatik") != "pruefung"
           and _geschickt4 == [960021],
           "N4: nach 'Prüfung abgeschlossen' nimmt sie die Freigabe nicht zurueck")
    # TZ8: Seit die Gastzuordnung an Daten belegt ist (ORIGINAL_RESV_NAME_ID
    # immer gefuellt, 17,9 % abweichend), steht der Schalter auf true — dann
    # braucht eine Gruppenrechnung keine Freigabe mehr.
    _geschickt4.clear()
    _ncfg["property"]["gastzuordnung_bestaetigt"] = True
    store.setzen(960021, status="bereit", fehler=None, freigabe_am=None)
    pruefe(ablauf.versenden(_ncfg, 960021, benutzer="automatik") != "pruefung"
           and _geschickt4 == [960021],
           "TZ8: mit bestaetigter Gastzuordnung geht die Gruppenrechnung ohne Freigabe")
finally:
    ablauf.rechnungsdaten, _mailer.senden = _echt_rd4, _echt_send4
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no = 960021")

# N6: Eine unbrauchbare Adresse ist etwas anderes als gar keine.
_echt_e13 = opera.empfaenger
opera.empfaenger = lambda bill_no: [{"email": "a@firma.example; b@firma.example"}]
try:
    pruefe(ablauf.adresshinweis(1) == ablauf.HINWEIS_ADRESSE_UNBRAUCHBAR,
           "N6: mehrere Adressen in einem Feld werden als solche benannt")
    opera.empfaenger = lambda bill_no: []
    pruefe(ablauf.adresshinweis(1) == ablauf.HINWEIS_OHNE_ADRESSE,
           "N6: gar keine Adresse bleibt der andere Grund")
finally:
    opera.empfaenger = _echt_e13

# N8: Ein Beleg mit zwei Gruenden zaehlt einmal.
_echt_k8, _echt_e8b = opera.kandidaten, opera.empfaenger
opera.kandidaten = lambda cfg, tage=None: [
    {"bill_no": 960022, "issuedate": "2026-09-01", "total_gross": 300.0, "total_net": 260.0,
     "company_name": "Meyer AG", "empfaenger_typ": "D", "empfaenger_land": None,
     "firmenbezug": "RESERVIERUNG", "invoice_no": "1"},
    # Zweiter Beleg: KEIN frueher Grund (Firma am Zahler, Land gepflegt),
    # nur der spaete Grund "keine Mailadresse". Er muss ebenfalls genau
    # einmal zaehlen — sonst zaehlt jeder eingelesene Beleg als Sichtpruefung.
    {"bill_no": 960023, "issuedate": "2026-09-01", "total_gross": 300.0, "total_net": 260.0,
     "company_name": "Mustermann GmbH", "empfaenger_typ": "D", "empfaenger_land": "DE",
     "firmenbezug": "ZAHLER", "invoice_no": "2"}]
opera.empfaenger = lambda bill_no: []
try:
    _z = ablauf.einlesen(json.loads(json.dumps(cfg)))
    pruefe(_z["pruefung"] == 2, f"N8: zwei Belege mit mehreren Gruenden zaehlen zweimal ({_z['pruefung']})")
    _r = store.rechnung(960022)
    pruefe(all(g in (_r["fehler"] or "") for g in ("Reservierung", "Land", "E-Mail")),
           f"N8: und alle Gruende stehen dran ({_r['fehler']})")
finally:
    opera.kandidaten, opera.empfaenger = _echt_k8, _echt_e8b
    with store.verbindung() as con:
        con.execute("DELETE FROM rechnungen WHERE bill_no IN (960022, 960023)")

# B51: Seiten, die auf OPERA, den Validator oder den Mailserver warten, duerfen
# nicht auf der Ereignisschleife laufen — sonst steht die ganze Oberflaeche.
# Geprueft werden ALLE diese Wege, nicht nur einer.
_main_quelle = (BASE / "app" / "main.py").read_text(encoding="utf-8")
_blockierend = ("uebersicht", "detail", "pflegeliste", "einlesen", "aufnehmen", "senden",
                "xml_bauen", "xml_anzeigen", "dbtest", "mailtest", "konfiguration",
                "update_pruefen", "update_anwenden", "einrichtung_leitweg")
_noch_async = [n for n in _blockierend if f"async def {n}(" in _main_quelle]
pruefe(not _noch_async and all(f"def {n}(" in _main_quelle for n in _blockierend),
       f"B51: Seiten mit Datenbank-, Validator- oder Mailzugriff laufen im Faden ({_noch_async})")
# Und die beiden, die eine laufende Ereignisschleife BRAUCHEN, bleiben async.
pruefe("async def automatik_jetzt(" in _main_quelle and "async def automatik_schalten(" in _main_quelle,
       "B51: die Automatik-Knoepfe bleiben asynchron — sie starten die Schleifenaufgabe")

# --- Betrieb: Aktualisierung, Installation, Freigaben ----------------------
# Eigene Datei, weil sie einen anderen Sandkasten braucht (Freigabebaeume,
# Dienstdateien). Sie laeuft hier mit, damit EIN Lauf alles prueft.
print("11) Betrieb (tools/smoketest_betrieb.py)")
import subprocess as _subp
_betrieb = _subp.run([sys.executable, str(BASE / "tools" / "smoketest_betrieb.py")],
                     capture_output=True, text=True)
for _zeile in _betrieb.stdout.splitlines():
    if _zeile.startswith("  FEHL"):
        fehler.append("Betrieb: " + _zeile[7:])
pruefe(_betrieb.returncode == 0,
       f"tools/smoketest_betrieb.py laeuft durch ({_betrieb.stdout.strip().splitlines()[-1] if _betrieb.stdout.strip() else _betrieb.stderr[:200]})")

import subprocess as _sp12
# Jede Einstellung muss beschrieben sein.
#
# Anlass: Beim Nachzaehlen waren neun Einstellungen in KEINER Dokumentation
# erklaert, darunter drei am selben Tag dazugekommene. Eine Einstellung, die
# niemand erklaert, wird entweder nie benutzt oder falsch — und bei einer
# Anwendung, die in fremden Haeusern laufen soll, ist das Zweite das
# Wahrscheinlichere.
#
# Die Uebersicht ist docs/15_EINSTELLUNGEN.md. Wer eine Einstellung ergaenzt,
# ergaenzt sie dort — sonst wird dieser Punkt rot.
_vorlage_cfg = json.loads((BASE / "config" / "app.example.json").read_text(encoding="utf-8"))
_uebersicht = (BASE / "docs" / "15_EINSTELLUNGEN.md").read_text(encoding="utf-8")
_unbeschrieben = []
for _abschnitt, _werte in _vorlage_cfg.items():
    if not isinstance(_werte, dict):
        continue
    for _k in _werte:
        if _k.startswith("_"):
            continue
        if f"`{_k}`" not in _uebersicht:
            _unbeschrieben.append(f"{_abschnitt}.{_k}")
pruefe(not _unbeschrieben,
       f"jede Einstellung steht in docs/15_EINSTELLUNGEN.md ({_unbeschrieben[:5]})")
# Und andersherum: keine Beschreibung fuer etwas, das es nicht mehr gibt.
_alle = {_k for _a, _w in _vorlage_cfg.items() if isinstance(_w, dict)
         for _k in _w if not _k.startswith("_")}
_erfunden = [_n for _n in _re.findall(r"^\| `([a-z_]+)`", _uebersicht, _re.M)
             if _n not in _alle]
pruefe(not _erfunden,
       f"die Uebersicht beschreibt nichts, was es nicht gibt ({_erfunden[:5]})")

print("12) Nichts Echtes im Repository")
# Diese Anwendung soll oeffentlich werden. Echte Daten Dritter — Kundennamen,
# Gastnamen, Belegnummern, Hausadressen, interne Hostnamen — haben im
# Quelltext nichts zu suchen, auch nicht als Testdaten und auch nicht in
# einem Kommentar, der erklaert, warum etwas so gebaut ist.
#
# 351 solcher Stellen waren es beim Aufraeumen. Ohne eine Pruefung kommen sie
# zurueck: Beim naechsten Fehler nimmt jemand wieder den Beleg zur Hand, an
# dem er ihn gesehen hat, und schreibt die Nummer dazu. Deshalb steht die
# Regel hier und nicht in einer Anweisung, die niemand liest.
# Die Muster enthalten die gesuchten Woerter NICHT im Klartext — eine
# Zeichenklasse um einen Buchstaben (alb[e]ck) trifft dasselbe, steht aber
# nicht als Zeichenkette in der Datei. Sonst faende die Pruefung sich selbst,
# und man muesste ausgerechnet die am staerksten belastete Datei von der
# Pruefung ausnehmen.
_VERBOTEN = [
    (r"(?i)\bcp-berli[n]\.com\b", "Domain des Hauses"),
    (r"(?i)\bahorn-hotel[s]\.de\b", "Domain der Gruppe"),
    (r"(?i)\bbsh[g]\.com\b", "Domain eines Kunden"),
    (r"(?i)\b(crown[e]\s*plaza|alb[e]ck|zehde[n])\b", "Name des Hauses oder Rechtstraegers"),
    (r"(?i)\b(sophi[a]\s+genetics|dertou[r]|pfize[r])\b", "Name eines Kunden"),
    (r"(?i)\brocky\.berc[c]|heberccsvrdb[0]", "interner Hostname"),
    (r"\b10\.49\.\d{1,3}\.\d{1,3}\b", "interne IP-Adresse"),
    (r"\bBEVODEB[B]\b", "BIC des Hauses"),
    (r"\bDE81\s?1009\s?00", "IBAN des Hauses"),
    (r"\b1(2[6-9]|3[01])\d{4}\b", "Belegnummer aus dem Produktivbestand"),
    (r"\b199[5-6]\d{4}\b", "Buchungsnummer aus dem Produktivbestand"),
]
# Binaerdateien werden uebersprungen — bis auf pptx und docx: Das sind
# ZIP-Archive mit XML darin, und ihr Text ist damit erreichbar. Sie wurden
# frueher uebersprungen, und genau darin ueberlebten die Namen von vier
# Tagungskunden eine Bereinigung, die alle Textdateien erwischt hatte.
_PRUEFE_NICHT = {".pdf", ".png", ".jpg", ".ico", ".woff2"}
_ALS_ZIP = {".pptx", ".docx", ".xlsx"}


def _text_von(pfad):
    """Den lesbaren Text einer Datei — auch aus einem Office-Archiv."""
    if pfad.suffix in _ALS_ZIP:
        import zipfile
        try:
            with zipfile.ZipFile(pfad) as z:
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
        return " ".join(_re.findall(r"<(?:a|w):t[^>]*>([^<]*)</(?:a|w):t>", roh))
    try:
        return pfad.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return ""

print()
if fehler:
    print(f"{len(fehler)} Punkt(e) offen:")
    for f in fehler:
        print("  -", f)
    sys.exit(1)
print("Alles in Ordnung. Beispiel-XML: data/beispiel.xml")
print("Die echte Konfiguration blieb unberuehrt; die Testkopien sind entfernt.")
