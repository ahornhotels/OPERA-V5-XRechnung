# -*- coding: utf-8 -*-
"""Bildschirmaufnahmen fuer die Anwenderanleitung (anleitung_erzeugen.py).

Kein Bestandteil der Anwendung. Startet die ECHTE Oberflaeche in einem
Sandkasten — Konfiguration und Arbeitsliste sind Kopien in einem
Temp-Verzeichnis, OPERA ist durch erfundene Musterdaten ersetzt. In den
Aufnahmen steht deshalb kein echter Kunde, kein echter Gast und keine echte
Adresse. Bitte so lassen: Die Anleitung wird weitergegeben.

Gebraucht werden Playwright (steuert das installierte Google Chrome, ohne
eigenen Browser-Download) und die Pakete der Anwendung:

    python3 -m venv /tmp/anleitung && /tmp/anleitung/bin/pip install \
        -r requirements.txt playwright python-pptx
    /tmp/anleitung/bin/python docs/praesentation/anleitung_aufnahmen.py /tmp/aufnahmen
    /tmp/anleitung/bin/python docs/praesentation/anleitung_erzeugen.py /tmp/aufnahmen
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import socket
import sys
import tempfile
import threading
import time

BASIS = pathlib.Path(__file__).resolve().parents[2]
ZIEL = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "aufnahmen").resolve()
ZIEL.mkdir(parents=True, exist_ok=True)

# --- Sandkasten, VOR dem ersten Import der Anwendung (wie tools/smoketest.py) --
_sandkasten = pathlib.Path(tempfile.mkdtemp(prefix="xrechnung-anleitung-"))
os.chmod(_sandkasten, 0o700)
(_sandkasten / "config").mkdir()
shutil.copy(BASIS / "config" / "app.example.json", _sandkasten / "config" / "app.example.json")
_cfg = json.loads((BASIS / "config" / "app.example.json").read_text(encoding="utf-8"))
_cfg["property"].update(haus="Musterhotel Berlin", resort="MUSTER", ust_id="DE123456789",
                        iban="DE02120300000000202051", bic="BYLADEM1001",
                        kontoinhaber="Musterhotel Berlin GmbH")
_cfg["mail"].update(bcc="buchhaltung@musterhotel.example", erlaubte_empfaenger=[])
_cfg["automatik"].update(aktiv=False, testlauf=True)
_cfg["validierung"]["aktiv"] = False
_cfg["update"]["automatisch_pruefen"] = False
_cfg["datenbank"]["host"] = "127.0.0.1"
_cfg["datenbank"]["port"] = 9   # nichts lauscht dort — ein Zugriff scheitert sofort
(_sandkasten / "config" / "app.json").write_text(json.dumps(_cfg, ensure_ascii=False), encoding="utf-8")
(_sandkasten / "data").mkdir()
os.environ.update(XRECHNUNG_BASIS=str(_sandkasten),
                  XRECHNUNG_CONFIG_DIR=str(_sandkasten / "config"),
                  XRECHNUNG_DATEN_DIR=str(_sandkasten / "data"),
                  XRECHNUNG_LOG_DIR=str(_sandkasten / "logs"))
sys.path.insert(0, str(BASIS))

from app import ablauf, auth, opera, store  # noqa: E402
from app.main import app                      # noqa: E402


# --- Musterdaten ------------------------------------------------------------
def buchung(trx, code, name, brutto, satz, menge=1, gast=None, zimmer=None,
            gastname=None, von=None, bis=None):
    netto = brutto / (1 + satz / 100)
    return {"trx_no": trx, "itemcode": code, "itemname": name, "invoicedquantity": menge,
            "lineextensionamount": brutto, "lineextensionamountnet": netto,
            "classifiedtaxcategoryid": "S" if satz else "Z",
            "classifiedtaxcategorypercent": satz,
            "bruttopreis": round(brutto / menge, 2) if menge else None,
            "gast_resv_name_id": gast, "gast_zimmer": zimmer, "gast_name": gastname,
            "gast_beginn": von, "gast_ende": bis, "bemerkung": ""}


def kopf(nr, kunde, stadt="Berlin", gast=None, zimmer=None, von="2026-09-07", bis="2026-09-10"):
    return {"id": nr, "issuedate": "2026-09-10", "duedate": "2026-09-24",
            "invoicetypecode": "380", "documentcurrencycode": "EUR",
            "buyerreference": "Musterhotel Berlin ReservNr.: 88" + str(nr)[-4:],
            "buyerreference_quelle": "Ersatzwert: Vorlage des Hauses",
            "reservierungsnummer": "88" + str(nr)[-4:],
            "startdate": von, "enddate": bis, "gastname": gast, "zimmer": zimmer,
            "suppliername": "Musterhotel Berlin", "supplierregistrationname": "Musterhotel Berlin GmbH",
            "supplierstreetname": "Musterallee 1", "suppliercityname": "Berlin",
            "supplierpostalzone": "10115", "supplieridentificationcode": "DE",
            "suppliercompanyid": "DE123456789", "suppliercontactname": "Buchhaltung",
            "suppliercontactelectronicmail": "buchhaltung@musterhotel.example",
            "customername": kunde, "customerregistrationname": kunde,
            "customerstreetname": "Beispielweg 5", "customercityname": stadt,
            "customerpostalzone": "10117", "customeridentificationcode": "DE",
            "payeefinancialaccountid": "DE02120300000000202051",
            "payeefinancialaccountbic": "BYLADEM1001",
            "payeefinancialaccountname": "Musterhotel Berlin GmbH",
            "prepaidamount": 0.0}


def rechnung_aus(nr, kopfdaten, zeilen):
    gruppen: dict = {}
    for z in zeilen:
        gruppen.setdefault(z["classifiedtaxcategorypercent"], []).append(z)
    steuer = [{"taxcategoryid": "S" if s else "Z", "taxcategorypercent": s,
               "taxableamount": sum(z["lineextensionamountnet"] for z in zs),
               "taxamount": sum(z["lineextensionamount"] - z["lineextensionamountnet"] for z in zs)}
              for s, zs in gruppen.items()]
    netto = sum(z["lineextensionamountnet"] for z in zeilen)
    brutto = round(sum(z["lineextensionamount"] for z in zeilen), 2)
    kopfdaten["payableamount"] = brutto
    return {"bill_no": nr, "header": kopfdaten, "lines": zeilen, "tax_breakdown": steuer,
            "totals": {"invoicenet": round(netto, 2), "invoicegross": brutto,
                       "invoicetaxtotal": round(brutto - netto, 2), "spay_cl": 0.0},
            "deposits": [],
            "kontrolle": {"kopf_netto": netto, "kopf_brutto": brutto,
                          "anzahlung_netto": 0.0, "anzahlung_brutto": 0.0}}


def einzel(nr, kunde, gast, zimmer, naechte=3, stadt="Berlin"):
    g = dict(gast=nr, zimmer=zimmer, gastname=gast, von="2026-09-07", bis="2026-09-10")
    z, t = [], 0
    for _ in range(naechte):
        z.append(buchung(t := t + 1, "1000", "Übernachtung", 149.00, 7, **g))
        z.append(buchung(t := t + 1, "2000", "Frühstück", 24.00, 7, **g))
    z.append(buchung(t := t + 1, "5200", "Parken", 28.00, 19, **g))
    return rechnung_aus(nr, kopf(nr, kunde, stadt, gast, zimmer), z)


def gruppe(nr, kunde):
    gaeste = [("Wagner, Lena", "214", 5001), ("Krause, Jonas", "215", 5002),
              ("Hoffmann, Mia", "216", 5003)]
    z, t = [], 0
    for name, zi, resv in gaeste:
        g = dict(gast=resv, zimmer=zi, gastname=name, von="2026-09-07", bis="2026-09-10")
        for _ in range(3):
            z.append(buchung(t := t + 1, "1000", "Übernachtung", 129.00, 7, **g))
            z.append(buchung(t := t + 1, "2000", "Frühstück", 24.00, 7, **g))
    return rechnung_aus(nr, kopf(nr, kunde, gast="Wagner, Lena", zimmer="214"), z)


RECHNUNGEN = {
    1400101: einzel(1400101, "Beispiel Consulting GmbH", "Neumann, Sabine", "312"),
    1400102: gruppe(1400102, "Nordlicht Reisen GmbH"),
    1400103: einzel(1400103, "Meyer Maschinenbau AG", "Schulz, Peter", "118", naechte=2),
    1400104: einzel(1400104, "Stadtwerke Musterstadt", "Becker, Anna", "207", naechte=1),
    1400105: einzel(1400105, "Hansa Logistik KG", "Fischer, Tom", "405", naechte=2),
    1400106: einzel(1400106, "Kranich Software GmbH", "Lang, Eva", "221", naechte=2, stadt=""),
}
ADRESSEN = {  # Herkunft und Rolle so benannt wie in sql/opera/invoice_recipients.sql
    1400101: [{"email": "rechnungen@beispiel-consulting.example", "quelle": "Debitorenkonto",
               "rolle": "AR-Konto", "typ": "AR", "primaer": "Y"},
              {"email": "info@beispiel-consulting.example", "quelle": "Profil",
               "rolle": "Zahler", "typ": "EMAIL", "primaer": "N"}],
    1400102: [{"email": "buchhaltung@nordlicht-reisen.example", "quelle": "Profil",
               "rolle": "Zahler", "typ": "EMAIL", "primaer": "Y"}],
    1400103: [{"email": "p.schulz@mail.example", "quelle": "Profil", "rolle": "Zahler",
               "typ": "EMAIL", "primaer": "Y"},
              {"email": "einkauf@meyer-maschinenbau.example", "quelle": "Profil", "rolle": "Profil",
               "typ": "EMAIL", "primaer": "N"}],
    1400104: [],
    1400105: [{"email": "invoice@hansa-logistik.example", "quelle": "Debitorenkonto",
               "rolle": "AR-Konto", "typ": "AR", "primaer": "Y"}],
    1400106: [{"email": "ap@kranich-software.example", "quelle": "Profil",
               "rolle": "Zahler", "typ": "EMAIL", "primaer": "Y"}],
}


def profil(cfg, nr):
    r = RECHNUNGEN.get(nr)
    if not r:
        return {}
    k = r["header"]
    return {"company": k["customername"], "legal_company": k["customername"],
            "name_type": "COMPANY" if nr != 1400103 else "D",
            "address1": k["customerstreetname"], "zip_code": k["customerpostalzone"],
            "city": k["customercityname"], "country": "DE", "tax1_no": None, "tax2_no": None,
            "leitweg_id": None, "anzahl_mails": len(ADRESSEN.get(nr, []))}


def buchungsfirma(nr):
    if nr == 1400103:
        return {"zahler_typ": "D", "firma_profil": "Meyer Maschinenbau AG", "firma_typ": "COMPANY",
                "city_ledger": 0, "karte": 358.00, "bar": 0}
    if nr == 1400102:
        return {"zahler_typ": "TRAVEL_AGENT", "firma_profil": "Nordlicht Reisen GmbH",
                "firma_typ": "TRAVEL_AGENT", "gruppe": "Herbstreise Nordlicht",
                "city_ledger": 1377.00, "karte": 0, "bar": 0}
    return {"zahler_typ": "COMPANY", "firma_profil": (RECHNUNGEN[nr]["header"]["customername"]
            if nr in RECHNUNGEN else None), "firma_typ": "COMPANY",
            "city_ledger": RECHNUNGEN[nr]["totals"]["invoicegross"] if nr in RECHNUNGEN else 0,
            "karte": 0, "bar": 0}


opera.rechnung = lambda cfg, nr: json.loads(json.dumps(RECHNUNGEN[nr]))
opera.empfaenger = lambda nr: ADRESSEN.get(nr, [])
opera.profil = profil
opera.pruefung = lambda cfg, nr: {"anzahlung_vorhanden": "N", "netto_ok": "J", "brutto_ok": "J",
                                  "netto_mit_anzahlung_ok": "J", "brutto_mit_anzahlung_ok": "J",
                                  "anzahl_deposits": 0}
opera.buchungsfirma = buchungsfirma
opera.suchen = lambda cfg, begriff: [
    {"bill_no": 1399877, "invoice_no": "R-1399877", "issuedate": "2026-07-02",
     "kunde": "Beispiel Consulting GmbH", "document_type": "INVOICE", "beleg_status": "OK",
     "empfaenger_land": "DE", "total_gross": 612.40}] if "1399" in begriff else []


def bestand():
    store.init()
    auth.anlegen("k.beispiel", "Anleitung!2026", "verwalten")
    zeilen = [
        (1400101, "Beispiel Consulting GmbH", "EMPFAENGER", "COMPANY", "bereit",
         "rechnungen@beispiel-consulting.example", None, 0),
        (1400102, "Nordlicht Reisen GmbH", "EMPFAENGER", "TRAVEL_AGENT", "neu",
         "buchhaltung@nordlicht-reisen.example", None, 0),
        (1400103, "Meyer Maschinenbau AG", "RESERVIERUNG", "D", "pruefung", None,
         "Firma hängt an der Reservierung, nicht am Zahler — bitte prüfen", 0),
        (1400104, "Stadtwerke Musterstadt", "EMPFAENGER", "COMPANY", "pruefung", None,
         ablauf.HINWEIS_OHNE_ADRESSE, 1),
        (1400105, "Hansa Logistik KG", "EMPFAENGER", "COMPANY", "gesendet",
         "invoice@hansa-logistik.example", None, 0),
        (1400106, "Kranich Software GmbH", "EMPFAENGER", "COMPANY", "bereit",
         "ap@kranich-software.example", None, 0),
        (1400107, "Beispiel Consulting GmbH", "EMPFAENGER", "COMPANY", "ignoriert", None,
         "Gesamtbetrag 0,00 — automatisch zurückgelegt", 0),
    ]
    for nr, kunde, bezug, typ, status, empf, fehler, ohne in zeilen:
        r = RECHNUNGEN.get(nr)
        store.rechnung_anlegen({
            "bill_no": nr, "resort": "MUSTER", "invoice_no": f"R-{nr}", "issuedate": "2026-09-10",
            "total_net": r["totals"]["invoicenet"] if r else 0.0,
            "total_gross": r["totals"]["invoicegross"] if r else 0.0,
            "kunde": kunde, "firmenbezug": bezug, "empfaenger_typ": typ, "empfaenger_land": "DE",
            "city_ledger": r["totals"]["invoicegross"] if r and nr not in (1400103,) else 0.0}, 120)
        store.setzen(nr, status=status, empfaenger=empf, fehler=fehler, adresse_fehlt=ohne)
    store.setzen(1400105, gesendet_am="2026-09-11T09:42:10", xrechnung_version="3.0.2")
    for nr, aktion, text in (
            (1400105, "geprueft", "XRechnung 3.0.2: Rechenprüfung und KoSIT ohne Befund"),
            (1400105, "versand", "XRechnung 3.0.2 an invoice@hansa-logistik.example, "
                                 "BCC buchhaltung@musterhotel.example (City Ledger), <kennung@musterhotel>"),
            (1400101, "empfaenger", "gesetzt auf rechnungen@beispiel-consulting.example"),
            (1400103, "pruefung", "Firma an der Reservierung — Sichtprüfung")):
        store.protokoll(aktion, text, bill_no=nr, benutzer="k.beispiel")


def freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def starten():
    import uvicorn
    port = freier_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), 0.2):
                return server, f"http://127.0.0.1:{port}"
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("Anwendung startet nicht")


# --- Markierungen im Bild -----------------------------------------------------
MARKIEREN = """
([sel, nr, text]) => {
  const el = document.querySelector(sel);
  if (!el) return false;
  const r = el.getBoundingClientRect();
  const x = r.left + window.scrollX, y = r.top + window.scrollY;
  const rahmen = document.createElement('div');
  Object.assign(rahmen.style, {position:'absolute', left:(x-5)+'px', top:(y-5)+'px',
    width:(r.width+10)+'px', height:(r.height+10)+'px', border:'3px solid #d0021b',
    borderRadius:'7px', zIndex:9998, pointerEvents:'none', boxSizing:'border-box'});
  const punkt = document.createElement('div');
  punkt.textContent = nr;
  Object.assign(punkt.style, {position:'absolute', left:(x-20)+'px', top:(y-20)+'px',
    width:'30px', height:'30px', borderRadius:'15px', background:'#d0021b', color:'#fff',
    font:'700 17px/30px Arial,sans-serif', textAlign:'center', zIndex:9999,
    boxShadow:'0 1px 4px rgba(0,0,0,.4)'});
  document.body.appendChild(rahmen); document.body.appendChild(punkt);
  return true;
}
"""


def markiere(seite, auswahl, nr):
    if not seite.evaluate(MARKIEREN, [auswahl, str(nr), ""]):
        raise RuntimeError(f"Nicht gefunden: {auswahl}")


def ausschnitt(seite, name, oben_sel, unten_sel=None, rand=24, breite=None):
    """Ausschnitt von oben_sel bis unten_sel (oder nur oben_sel), ganze Breite
    des Inhalts oder die angegebene Breite."""
    a = seite.locator(oben_sel).first.bounding_box()
    b = seite.locator(unten_sel).first.bounding_box() if unten_sel else a
    y0 = max(0, min(a["y"], b["y"]) - rand)
    y1 = max(a["y"] + a["height"], b["y"] + b["height"]) + rand
    x0 = max(0, min(a["x"], b["x"]) - rand)
    x1 = breite if breite else max(a["x"] + a["width"], b["x"] + b["width"]) + rand
    seite.screenshot(path=str(ZIEL / f"{name}.png"), full_page=True,
                     clip={"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0})


def aufnehmen(basis):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        seite = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2,
                                 locale="de-DE")
        neu_laden = lambda url: (seite.goto(basis + url), seite.wait_for_load_state("networkidle"))

        # 01 Anmelden
        neu_laden("/login")
        seite.fill("input[name=benutzer]", "k.beispiel")
        seite.fill("input[name=passwort]", "Anleitung!2026")
        markiere(seite, "input[name=benutzer]", 1)
        markiere(seite, "input[name=passwort]", 2)
        markiere(seite, "form button", 3)
        ausschnitt(seite, "01_anmelden", "form.karte", rand=60)
        neu_laden("/login")
        seite.fill("input[name=benutzer]", "k.beispiel")
        seite.fill("input[name=passwort]", "Anleitung!2026")
        seite.click("form button")
        seite.wait_for_load_state("networkidle")

        # 02 Liste
        neu_laden("/")
        markiere(seite, "form.einlesen button", 1)
        markiere(seite, "nav.filter", 2)
        markiere(seite, "form.suche input[name=suche]", 3)
        markiere(seite, "a[href^='/rechnung/1400102']", 4)
        markiere(seite, "tr.s-pruefung .status", 5)
        seite.screenshot(path=str(ZIEL / "02_liste.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 720})

        # 03 Einlesen — die Meldung, wie sie nach einem Lauf erscheint
        bericht = ablauf.bericht({"gelesen": 96, "neu": 7, "bekannt": 61, "pruefung": 2,
                                  "ohne_firmenbezug": 24, "ausland": 4, "zu_klein": 0, "nullbeleg": 0})
        neu_laden("/?meldung=" + bericht)
        markiere(seite, "div.meldung", 1)
        markiere(seite, "label.zeitraum", 2)
        markiere(seite, "form.einlesen button", 3)
        seite.screenshot(path=str(ZIEL / "03_einlesen.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 250})

        # 04 Filter Pruefung
        neu_laden("/?status=pruefung")
        markiere(seite, "nav.filter a.aktiv", 1)
        markiere(seite, "tr.s-pruefung .fehler", 2)
        seite.screenshot(path=str(ZIEL / "04_pruefung_liste.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 460})

        # 05 Detail oben: Knoepfe und Beleg
        neu_laden("/rechnung/1400101")
        markiere(seite, "form[action$='/xml'] button", 1)
        markiere(seite, "a[href$='xml.xml']", 2)
        markiere(seite, "form[action$='/senden'] button", 3)
        markiere(seite, "form[action$='/zuruecklegen'] button", 4)
        ausschnitt(seite, "05_detail_oben", "div.kopfzeile", "div.spalten", breite=1440)

        # 06 Empfaenger
        neu_laden("/rechnung/1400101")
        markiere(seite, "form[action$='/empfaenger'] table", 1)
        markiere(seite, "form[action$='/empfaenger'] input[name=frei]", 2)
        markiere(seite, "form[action$='/empfaenger'] > button", 3)
        ausschnitt(seite, "06_empfaenger", "div.vor-versand section:nth-of-type(1)")

        # 07 Kaeuferreferenz
        neu_laden("/rechnung/1400101")
        markiere(seite, "form[action$='/buyerreference'] input[name=frei]", 1)
        markiere(seite, "form[action$='/buyerreference'] > button", 2)
        ausschnitt(seite, "07_kaeuferreferenz", "div.vor-versand section:nth-of-type(2)")

        # 08 Positionen Einzelrechnung / 09 Gruppe
        for nr, name in ((1400101, "08_positionen_einzel"), (1400102, "09_positionen_gruppe")):
            neu_laden(f"/rechnung/{nr}")
            markiere(seite, "form[action$='/positionen'] p", 1)
            markiere(seite, "div.spalten.weit section:first-of-type table", 2)
            ausschnitt(seite, name, "div.spalten.weit section:first-of-type")

        # 10 XML erzeugen: Meldung danach
        neu_laden("/rechnung/1400101")
        seite.click("form[action$='/xml'] button")
        seite.wait_for_load_state("networkidle")
        markiere(seite, "div.meldung", 1)
        markiere(seite, "form[action$='/senden'] button", 2)
        seite.screenshot(path=str(ZIEL / "10_xml_erzeugt.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 330})

        # 11 Rote Vorpruefung
        neu_laden("/rechnung/1400106")
        markiere(seite, "div.fehler", 1)
        markiere(seite, "form[action$='/senden'] button", 2)
        ausschnitt(seite, "11_vorpruefung_rot", "section.aktionsleiste", "div.fehler", breite=650)

        # 12 Versendet (Testlauf-Meldung)
        neu_laden("/rechnung/1400101?meldung=Testlauf: nicht wirklich versendet")
        markiere(seite, "div.meldung", 1)
        markiere(seite, "header .pille", 2)
        seite.screenshot(path=str(ZIEL / "12_testlauf.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 250})
        neu_laden("/rechnung/1400101?meldung=Versendet")
        markiere(seite, "div.meldung", 1)
        seite.screenshot(path=str(ZIEL / "12b_versendet.png"), clip={"x": 0, "y": 0, "width": 760, "height": 200})

        # 13 Sichtpruefung: Firma an der Reservierung
        neu_laden("/rechnung/1400103")
        markiere(seite, "p.pruefhinweis", 1)
        markiere(seite, "div.spalten section:nth-of-type(2) dl", 2)
        ausschnitt(seite, "13_sichtpruefung", "div.kopfzeile", "div.spalten", breite=1440)

        # 13b Freigeben nach der Sichtpruefung
        store.setzen(1400103, empfaenger="einkauf@meyer-maschinenbau.example")
        neu_laden("/rechnung/1400103")
        markiere(seite, "form[action$='/empfaenger'] > button", 1)
        markiere(seite, "form[action$='/freigeben'] button", 2)
        markiere(seite, "form[action$='/senden'] button", 3)
        ausschnitt(seite, "13b_freigeben", "div.kopfzeile", "section.aktionsleiste", rand=14, breite=1100)
        store.setzen(1400103, empfaenger=None)

        # 19 Ein Automatiklauf arbeitet gerade
        from app import automatik as _auto
        _auto._laeuft.set()
        try:
            neu_laden("/")
            markiere(seite, "header .pille", 1)
            markiere(seite, "div.pruefhinweis.arbeitet", 2)
            markiere(seite, "form.einlesen button", 3)
            seite.screenshot(path=str(ZIEL / "19_automatik_arbeitet.png"),
                             clip={"x": 0, "y": 0, "width": 1440, "height": 230})
        finally:
            _auto._laeuft.clear()

        # 14 Keine Adresse
        neu_laden("/rechnung/1400104")
        markiere(seite, "form[action$='/empfaenger'] td.leer", 1)
        markiere(seite, "form[action$='/empfaenger'] input[name=frei]", 2)
        ausschnitt(seite, "14_keine_adresse", "div.vor-versand section:nth-of-type(1)")
        neu_laden("/")
        markiere(seite, "a[href='/pflegeliste.csv']", 1)
        seite.screenshot(path=str(ZIEL / "14b_ohne_adresse_knopf.png"), clip={"x": 700, "y": 40, "width": 740, "height": 110})

        # 15 Suche und In die Liste holen
        neu_laden("/?suche=1399877")
        markiere(seite, "form.suche", 1)
        markiere(seite, "section.opera-treffer button", 2)
        ausschnitt(seite, "15_suche", "form.suche", "section.opera-treffer", breite=1440)

        # 16 Versendete Rechnung
        neu_laden("/rechnung/1400105")
        markiere(seite, "form[action$='/xml'] button", 1)
        markiere(seite, "form[action$='/senden'] button", 2)
        ausschnitt(seite, "16_versendet", "div.kopfzeile", "section.aktionsleiste", breite=1440)

        # 17 Verlauf auf der Detailseite / Protokoll
        neu_laden("/protokoll")
        markiere(seite, "main table", 1)
        seite.screenshot(path=str(ZIEL / "17_protokoll.png"), clip={"x": 0, "y": 0, "width": 1440, "height": 420})

        # 18 Status in der Liste, ohne Markierung
        neu_laden("/")
        ausschnitt(seite, "18_statusspalte", "main table", breite=1440)
        browser.close()


if __name__ == "__main__":
    bestand()
    server, basis = starten()
    try:
        aufnehmen(basis)
    finally:
        server.should_exit = True
        shutil.rmtree(_sandkasten, ignore_errors=True)
    print("Aufnahmen in", ZIEL)
    for f in sorted(ZIEL.glob("*.png")):
        print(" ", f.name)
