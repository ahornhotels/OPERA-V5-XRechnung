"""OPERA XRechnung — Weboberflaeche und Dienst.

Erreichbar im lokalen Netz, geschuetzt durch Anmeldung. Die App liest
ausschliesslich aus OPERA; geschrieben wird nur in die eigene SQLite-Datei
und in die Ablageordner.

Copyright (C) 2026 AHORN Hotels
Freie Software unter der GNU General Public License v3 — siehe LICENSE.
Ohne jede Gewaehrleistung, auch nicht fuer die Richtigkeit der erzeugten
Rechnungen; dafuer ist der Betreiber verantwortlich."""
from __future__ import annotations
import logging
import asyncio
import ipaddress
import re
from urllib.parse import urlencode
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import ablauf, auth, automatik, config, db, mailer, markdown, opera, store, updater, validate, xml_build

from . import pfade
# Programm: Handbuch und Vorlagen wechseln mit jeder Aktualisierung.
BASE = pfade.PROGRAMM
# Das Verzeichnis muss VOR der Protokollierung stehen — sie wird beim Import
# eingerichtet, nicht beim Start. Bei einer frischen Installation oder einem
# umgelenkten Bestand gibt es es sonst noch nicht, und der Dienst kommt mit
# einem FileNotFoundError gar nicht erst hoch.
pfade.LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    handlers=[logging.FileHandler(pfade.LOG_DIR / "app.log", encoding="utf-8"),
              logging.StreamHandler()],
)
log = logging.getLogger("xrechnung")
seiten = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

OEFFENTLICH = {"/login", "/health", "/static"}


@asynccontextmanager
async def lebenszyklus(app: FastAPI):
    # Beim Start alles in config/ zuziehen — auch Sicherungen, die jemand von
    # Hand daneben gelegt hat.
    angefasst = config.ordner_absichern()
    if angefasst:
        log.warning("Dateirechte in config/ nachgezogen: %s", ", ".join(angefasst))
    store.init()
    auth.benutzer_laden()
    cfg = config.laden()
    try:
        db.start(cfg)
    except Exception as e:
        log.error("Datenbankverbindung beim Start nicht möglich: %s", e)
    if cfg["automatik"].get("aktiv"):
        automatik.starten()
    # Nachsehen, ob ein neuerer Stand bereitliegt — unabhaengig von der
    # Automatik, weil auch ein Haus ohne Automatik davon erfahren soll.
    # Eingespielt wird weiterhin nur auf Knopfdruck.
    wache = asyncio.create_task(updater.wache())
    yield
    wache.cancel()
    automatik.stoppen()
    # Der Validator-Daemon ist ein Kindprozess. Ohne dieses Beenden bliebe er
    # nach einem Neustart des Dienstes stehen und haelt seinen Port besetzt.
    validate.daemon_stoppen()
    db.stop()


app = FastAPI(title="OPERA XRechnung", lifespan=lebenszyklus)
app.mount("/static", StaticFiles(directory=str(Path(__file__).resolve().parent / "static")), name="static")

# Das Erscheinungsbild des Hauses liegt im BESTAND, nicht im Programm — es
# gehoert dem Haus und soll eine Aktualisierung ueberstehen. Das Verzeichnis
# wird angelegt, damit die Einbindung immer traegt; ist es leer, sieht die
# Anwendung so aus, wie sie ausgeliefert wird.
pfade.BRANDING_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/branding", StaticFiles(directory=str(pfade.BRANDING_DIR)), name="branding")


def eigenes_branding() -> bool:
    """Liegt im Bestand eine eigene stil.css? Nur dann wird sie eingebunden —
    ein Verweis auf eine fehlende Datei kostet bei jedem Seitenaufbau einen
    vergeblichen Abruf."""
    return (pfade.BRANDING_DIR / "stil.css").is_file()


@app.middleware("http")
async def zugang(request: Request, call_next):
    cfg = config.laden()
    ip = request.client.host if request.client else ""
    if not auth.netz_erlaubt(ip, cfg["server"].get("erlaubte_netze") or []):
        return HTMLResponse("Zugriff aus diesem Netz ist nicht erlaubt.", status_code=403)
    pfad = request.url.path
    if any(pfad.startswith(p) for p in OEFFENTLICH):
        return await call_next(request)
    sitzung = auth.sitzung(request.cookies.get("sitzung"))
    if not sitzung:
        return RedirectResponse("/login", status_code=303)
    request.state.benutzer = sitzung["benutzer"]
    request.state.rolle = sitzung["rolle"]
    return await call_next(request)


BESCHAEFTIGT = ("Ein Automatiklauf arbeitet gerade — Einlesen, Versenden und ein "
                "zweiter Durchlauf sind so lange gesperrt. Bitte kurz warten.")


def _darf_verwalten(request: Request) -> bool:
    return getattr(request.state, "rolle", "") == "verwalten"


def _ansicht(status: str, suche: str, sortieren: str, richtung: str) -> str:
    """Die aktuelle Ansicht der Liste als Adresse — Filter, Suche, Sortierung."""
    teile = [(name, wert) for name, wert in
             (("status", status), ("suche", suche),
              ("sortieren", sortieren), ("richtung", richtung)) if wert]
    return "/" + ("?" + urlencode(teile) if teile else "")


def _zurueck(wert: str) -> str:
    """Das Ziel des Zurueck-Knopfes. Nur eigene Adressen.

    Der Wert kommt aus der Adresszeile und landet in einem href. Ohne diese
    Pruefung liesse sich die Anwendung als Sprungbrett auf eine fremde Seite
    benutzen — '//example.com' ist fuer den Browser eine vollstaendige
    Adresse, obwohl es mit einem Schraegstrich beginnt."""
    ziel = (wert or "").strip()
    # Positivliste statt Ausschluss: Browser machen aus "/\\host" und
    # "/<Tab>/host" ebenfalls "//host". Erlaubt sind nur Zeichen, die in den
    # eigenen Listenadressen vorkommen.
    if (not ziel.startswith("/") or ziel.startswith("//")
            or not _EIGENE_ADRESSE.match(ziel)):
        return "/"
    return ziel


_EIGENE_ADRESSE = re.compile(r"^/[A-Za-z0-9/?=&%._\-+~]*$")


def _hausname() -> str:
    """Der Name des Hauses fuer die Kopfzeile. Faellt auf das Resortkuerzel
    zurueck — ein Kuerzel ist immer da, ein Name nicht."""
    try:
        p = config.laden().get("property") or {}
    except Exception:
        return ""
    return (p.get("haus") or "").strip() or (p.get("resort") or "").strip()


def _kontext(request: Request, **extra) -> dict:
    return {"request": request,
            "version": updater.version(),
            "eigenes_branding": eigenes_branding(),
            "update_hinweis": updater.hinweis(),
            "benutzer": getattr(request.state, "benutzer", ""),
            "rolle": getattr(request.state, "rolle", ""),
            "verwalten": _darf_verwalten(request),
            "automatik": automatik.zustand(),
            "haus": _hausname(),
            **extra}


# ---------------------------------------------------------------- Anmeldung
@app.get("/login", response_class=HTMLResponse)
def login_seite(request: Request, fehler: str = ""):
    return seiten.TemplateResponse(request, "login.html", {"fehler": fehler})


@app.post("/login")
def login(request: Request, benutzer: str = Form(...), passwort: str = Form(...)):
    ip = request.client.host if request.client else ""
    rest = auth.gesperrt(f"{benutzer}|{ip}")
    if rest:
        return RedirectResponse(f"/login?fehler=Gesperrt, bitte {rest} Sekunden warten", status_code=303)
    token = auth.anmelden(benutzer, passwort, ip)
    if not token:
        return RedirectResponse("/login?fehler=Benutzer oder Passwort falsch", status_code=303)
    antwort = RedirectResponse("/", status_code=303)
    antwort.set_cookie("sitzung", token, httponly=True, samesite="strict", max_age=8 * 3600)
    return antwort


@app.get("/logout")
def logout(request: Request):
    token = request.cookies.get("sitzung")
    if token:
        auth.abmelden(token)
    antwort = RedirectResponse("/login", status_code=303)
    antwort.delete_cookie("sitzung")
    return antwort


@app.get("/health")
def health():
    return {"status": "ok", "automatik": automatik.zustand()}


# ------------------------------------------------------------------ Uebersicht
@app.get("/", response_class=HTMLResponse)
def uebersicht(request: Request, status: str = "", meldung: str = "",
                     sortieren: str = "", richtung: str = "", suche: str = ""):
    cfg = config.laden()
    suche = (suche or "").strip()
    alle = store.liste(status or None, sortieren=sortieren, richtung=richtung, suche=suche)

    # Die Suche geht ueber die Arbeitsliste UND ueber OPERA. Sonst waere eine
    # Rechnung, die nie eingelesen wurde, in dieser Anwendung unauffindbar —
    # und genau nach so einer sucht jemand, der eine Nummer vom Kunden bekommen
    # hat. Gefragt wird nur bei einem Begriff, der eine Nummer sein kann.
    in_opera: list[dict] = []
    opera_fehler = ""
    bestand = store.liste(limit=5000)
    bekannt = {int(r["bill_no"]) for r in bestand}
    # Anzahl je Status fuer die Reiter. Ohne sie muss man jeden einzeln
    # anklicken, um zu sehen, ob dort etwas liegt.
    zaehler = {"": len(bestand)}
    for r in bestand:
        zaehler[r.get("status") or ""] = zaehler.get(r.get("status") or "", 0) + 1
    if suche and any(z.isdigit() for z in suche):
        try:
            in_opera = [dict(r, bekannt=int(r["bill_no"]) in bekannt)
                        for r in opera.suchen(cfg, suche)]
        except Exception as e:
            log.exception("Suche in OPERA fehlgeschlagen (%s)", suche)
            opera_fehler = str(e)
    # Gezaehlt wird die Spalte, nicht der Hinweistext: Ein Beleg kann aus
    # mehreren Gruenden in der Sichtpruefung stehen, und dann stand die
    # Adressfrage nicht mehr im Text.
    ohne_adresse = sum(1 for r in store.liste(limit=5000)
                       if r.get("adresse_fehlt")
                       and not (r.get("empfaenger") or "").strip()
                       and r.get("status") not in ("gesendet", "ignoriert"))
    return seiten.TemplateResponse(request, "liste.html", _kontext(
        request, rechnungen=alle, status=status, meldung=meldung,
        suche=suche, in_opera=in_opera, opera_fehler=opera_fehler, zaehler=zaehler,
        zurueck_ziel=_ansicht(status, suche, sortieren, richtung),
        status_namen=store.STATUS_NAMEN, status_reihe=store.STATUS_REIHE,
        sortieren=sortieren if sortieren in store.SORTIERBAR else "",
        richtung=("auf" if (richtung or "").lower() == "auf" else "ab"),
        ohne_adresse=ohne_adresse,
        zeitraum=(cfg.get("auswahl") or {}).get("zeitraum_tage", 30)))


@app.post("/aufnehmen")
def aufnehmen(request: Request, bill_no: int = Form(...), suche: str = Form("")):
    """Eine in OPERA gefundene Rechnung in die Arbeitsliste holen."""
    if not _darf_verwalten(request):
        return RedirectResponse("/?meldung=Keine Berechtigung", status_code=303)
    cfg = config.laden()
    try:
        meldung = ablauf.aufnehmen(cfg, bill_no)
        store.protokoll("aufgenommen", meldung, benutzer=request.state.benutzer)
    except Exception as e:
        meldung = f"Fehler: {e}"
    ziel = f"/?meldung={meldung}"
    if suche:
        ziel += f"&suche={suche}"
    return RedirectResponse(ziel, status_code=303)


@app.get("/pflegeliste.csv")
def pflegeliste(request: Request):
    """Die Rechnungen, deren Empfaengerprofil keine E-Mail-Adresse traegt.

    An knapp einem Drittel der Firmenprofile ist nirgends eine Adresse
    hinterlegt — weder am Profil noch an der Rechnungsanschrift noch am
    Debitorenkonto. Das laesst sich nicht programmieren, das muss jemand im
    Haus pflegen. Damit das nicht Rechnung fuer Rechnung geschieht, hier die
    Liste zum Abarbeiten, nach PROFIL gebuendelt. Das lohnt sich: Die Belege
    entfallen auf deutlich weniger Profile als Rechnungen, und eine Handvoll
    grosser Profile erledigt einen erheblichen Teil davon.

    Gefragt wird dabei LIVE, nicht der Vermerk im Bestand. Der stammt vom Tag
    des Einlesens und sagt nichts darueber, ob inzwischen jemand die Adresse
    gepflegt hat — bei der Einfuehrung war die Liste leer, waehrend die
    Rechnungen dalagen: Sie waren eingelesen worden, bevor es den Vermerk
    ueberhaupt gab.
    """
    betroffen: dict[object, list[dict]] = {}
    ungeklaert = 0
    for r in store.liste(limit=5000):
        if (r.get("empfaenger") or "").strip() or r.get("status") in ("gesendet", "ignoriert"):
            continue
        adressen = ablauf.empfaenger_kandidaten(r["bill_no"])
        if adressen is None:
            ungeklaert += 1        # Stoerung, kein Pflegefall
            continue
        if adressen:
            continue
        # Gebuendelt wird ueber die Profilnummer, nicht ueber den Namen:
        # Belege ohne Kundennamen kaemen sonst alle in einen Topf — auf der
        # Anlage 28 Stueck von verschiedenen Kunden, und die Liste schickte
        # jemanden zu einem Profil, das es nicht gibt.
        schluessel = r.get("name_id") or f"beleg:{r['bill_no']}"
        betroffen.setdefault(schluessel, []).append(r)

    zeilen = ["Profil;Kunde;Rechnungen;Nummern;ältestes Datum;Summe brutto"]
    for schluessel in sorted(betroffen, key=lambda k: (-len(betroffen[k]), str(k))):
        gruppe = betroffen[schluessel]
        namen = {(r.get("kunde") or "").strip() for r in gruppe} - {""}
        kunde = sorted(namen)[0] if namen else ""
        if not kunde and isinstance(schluessel, int):
            # Auf dem Beleg fehlt der Firmenname haeufig, am Profil steht er
            # trotzdem. Ohne dieses Nachschlagen suchte der Empfang nach einer
            # Nummer statt nach einem Kunden.
            kunde = opera.profil_name(schluessel)
        kunde = kunde or "(kein Name am Beleg)"
        nummern = " ".join(str(r["bill_no"]) for r in sorted(
            gruppe, key=lambda r: r["bill_no"])[:20])
        if len(gruppe) > 20:
            nummern += f" (+{len(gruppe) - 20} weitere)"
        summe = sum(float(r.get("total_gross") or 0) for r in gruppe)
        aeltestes = min((str(r.get("issuedate") or "") for r in gruppe), default="")
        profil = schluessel if isinstance(schluessel, int) else ""
        # Semikolon im Firmennamen wuerde die Spalten verschieben
        zeilen.append(f"{profil};{_csv_zelle(kunde.replace(';', ','))};{len(gruppe)};{nummern};"
                      f"{aeltestes};{summe:.2f}")
    if ungeklaert:
        zeilen.append(f";{ungeklaert} Belege nicht geprüft (Datenbank nicht erreichbar);;;;")
    inhalt = "\r\n".join(zeilen) + "\r\n"
    store.protokoll("pflegeliste", f"{len(betroffen)} Profile ohne Adresse abgerufen",
                    benutzer=request.state.benutzer)
    return Response(
        # BOM, damit Excel die Umlaute richtig anzeigt — ohne das steht dort
        # "GmbH & Co. KG" mit zerlegten Umlauten, und die Liste wird von Hand
        # in Excel abgearbeitet.
        content="\ufeff" + inhalt,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="profile-ohne-adresse.csv"'})


def _csv_zelle(text: str) -> str:
    """Eine Zelle, die Excel nicht als Formel ausfuehrt. Der Kundenname kommt
    aus OPERA; beginnt er mit = + - @ oder einem Steuerzeichen, rechnete Excel
    ihn beim Oeffnen der Liste — genau so wird sie benutzt."""
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@app.post("/einlesen")
def einlesen(request: Request, tage: str = Form("")):
    if automatik.laeuft_gerade():
        return RedirectResponse("/?meldung=" + BESCHAEFTIGT, status_code=303)
    # Einlesen nimmt Rechnungen in den Lauf — mit einem grossen Zeitraum auch
    # alte, die nach der Wartezeit automatisch hinausgehen. Das ist eine
    # Entscheidung fuer Verwalter, kein Lesevorgang.
    if not _darf_verwalten(request):
        return RedirectResponse("/?meldung=Keine Berechtigung", status_code=303)
    cfg = config.laden()
    try:
        zeitraum = int(tage) if str(tage).strip().isdigit() else None
        zahlen = ablauf.einlesen(cfg, tage=zeitraum)
        meldung = ablauf.bericht(zahlen)
        grenze = zahlen.get("grenze_erreicht")
        if grenze:
            warnung = (f"ACHTUNG: Obergrenze von {grenze} erreicht — es wurden nur die "
                       "neuesten Rechnungen gelesen, ältere fehlen. Zeitraum verkleinern "
                       "oder unter Konfiguration → Auswahl die Obergrenze erhöhen. "
                       "Anlagen, die vor September 2026 eingerichtet wurden, tragen dort "
                       "oft noch 500 aus einer Zeit, in der die Grenze etwas anderes "
                       "bedeutete.")
            meldung += " — " + warnung
    except Exception as e:
        meldung = f"Fehler: {e}"
    return RedirectResponse(f"/?meldung={meldung}", status_code=303)


@app.post("/automatik")
async def automatik_schalten(request: Request, an: str = Form("")):
    if not _darf_verwalten(request):
        return RedirectResponse("/?meldung=Keine Berechtigung", status_code=303)
    cfg = config.laden()
    cfg["automatik"]["aktiv"] = (an == "1")
    config.speichern(cfg)
    if cfg["automatik"]["aktiv"]:
        automatik.starten()
        meldung = "Automatik eingeschaltet"
    else:
        automatik.stoppen()
        meldung = "Automatik ausgeschaltet"
    store.protokoll("automatik", meldung, benutzer=request.state.benutzer)
    return RedirectResponse(f"/?meldung={meldung}", status_code=303)


@app.post("/automatik/jetzt")
async def automatik_jetzt(request: Request):
    """Ein Durchlauf von Hand. Verschickt echte Rechnungen — deshalb nur fuer
    Verwalter. Vorher konnte jedes angemeldete Konto ihn ausloesen, und der
    Schalter 'Automatik aus' half nicht: Er wird nur in der Schleife geprueft,
    nicht beim Knopf."""
    if not _darf_verwalten(request):
        return RedirectResponse("/?meldung=Keine Berechtigung", status_code=303)
    if automatik.laeuft_gerade():
        return RedirectResponse("/?meldung=" + BESCHAEFTIGT, status_code=303)
    cfg = config.laden()
    store.protokoll("automatik", "Durchlauf von Hand ausgelöst"
                    + (" (Automatik ist abgeschaltet)"
                       if not cfg["automatik"].get("aktiv") else ""),
                    benutzer=request.state.benutzer)
    await automatik.einmal_jetzt()
    return RedirectResponse("/?meldung=Durchlauf ausgeführt", status_code=303)


# -------------------------------------------------------------------- Detail
@app.get("/rechnung/{bill_no}", response_class=HTMLResponse)
def detail(request: Request, bill_no: int, meldung: str = "",
                 zurueck: str = ""):
    cfg = config.laden()
    satz = store.rechnung(bill_no) or {"bill_no": bill_no}
    fehler = None
    profil = pruefung = {}
    adressen: list = []
    daten: dict = {}
    buchung: dict = {}
    try:
        profil = opera.profil(cfg, bill_no)
        adressen = opera.empfaenger(bill_no)
        pruefung = opera.pruefung(cfg, bill_no)
        # ueber ablauf, damit die Seite genau das sieht, was auch erzeugt
        # wird — sonst sperrt sie den Versand wegen eines Befunds, den die
        # Erzeugung gar nicht hat.
        daten = ablauf.rechnungsdaten(cfg, bill_no)
        buchung = opera.buchungsfirma(bill_no)
    except Exception as e:
        fehler = str(e)
    hinweise = xml_build.pruefsummen(daten) if daten else []
    # Die Positionen so, wie sie im XML stehen — gerundet, Abschlaege getrennt.
    aufbereitet = xml_build.aufbereiten(daten) if daten else {}
    erlaubt = mailer.empfaenger_erlaubt(cfg, satz.get("empfaenger") or "")
    return seiten.TemplateResponse(request, "detail.html", _kontext(
        request, satz=satz, profil=profil, adressen=adressen, pruefung=pruefung,
        daten=daten, hinweise=hinweise, fehler=fehler, meldung=meldung,
        zurueck=_zurueck(zurueck),
        referenzen=ablauf.buyerreference_vorschlaege(daten.get("header") or {}) if daten else [],
        empfaenger_erlaubt=erlaubt, buchung=buchung,
        positionsarten=opera.POSITIONSARTEN,
        versand_offen=ablauf.VERSAND_OFFEN in (satz.get("fehler") or ""),
        aufbereitet=aufbereitet,
        blindkopien=mailer.blindkopien(cfg, float(satz.get("city_ledger") or 0) > 0),
        protokoll=store.protokoll_lesen(30, bill_no)))


@app.post("/rechnung/{bill_no}/buyerreference")
def buyerreference_setzen(request: Request, bill_no: int,
                                wert: str = Form(""), frei: str = Form("")):
    """BT-10 von Hand setzen. Eine abgerechnete Reservierung laesst sich in
    OPERA nicht mehr aendern — ohne diesen Weg waere die Kaeuferreferenz fuer
    jede bereits erstellte Rechnung endgueltig, und gerade die Bestellnummer
    meldet der Kunde meist erst, wenn er die Rechnung in der Hand hat."""
    # BT-10 geht an den Kunden — nur wer versenden darf, darf ihn setzen.
    # Vorher ging das mit jedem angemeldeten Konto.
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung",
                                status_code=303)
    if not store.rechnung(bill_no):
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Die Rechnung steht nicht in der Arbeitsliste — "
            "erst aufnehmen, dann lässt sich die Käuferreferenz setzen", status_code=303)
    # Das Freitextfeld ist nicht mehr vorbelegt; es gewinnt nur, wenn jemand
    # etwas hineinschreibt. Vorher trug es den bisherigen Wert und schlug damit
    # jede andere Auswahl — die gewaehlte Referenz wurde verworfen.
    eingabe = (frei.strip() or wert).strip()
    gekuerzt = opera.kuerzen(eingabe)[1] if eingabe else 0
    store.setzen(bill_no, buyerreference=eingabe or None)
    store.protokoll("kaeuferreferenz", f"gesetzt auf {eingabe or '-'}", bill_no=bill_no,
                    benutzer=request.state.benutzer)
    # Der Status bleibt, wie er ist: Eine geaenderte Kaeuferreferenz sagt
    # nichts darueber, ob die Rechnung versandfertig ist.
    meldung = "Käuferreferenz gespeichert"
    if gekuerzt:
        meldung += f" — von {gekuerzt} auf {opera.BT10_LAENGE} Zeichen gekürzt"
    return RedirectResponse(f"/rechnung/{bill_no}?meldung={meldung}", status_code=303)


@app.post("/rechnung/{bill_no}/positionen")
def positionen_setzen(request: Request, bill_no: int, art: str = Form("")):
    """Die Darstellung der Positionen fuer diese eine Rechnung waehlen. Leer
    stellt die Vorbelegung wieder her.

    Eine versendete Rechnung aendert sich dadurch nicht: Angezeigt und
    zurueckgegeben wird die archivierte Fassung (ablauf.xml_erzeugen)."""
    # Wie die Rechnung aussieht, die hinausgeht, ist eine Entscheidung vor dem
    # Versand — dieselbe Berechtigung wie beim Empfaenger.
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung",
                                status_code=303)
    if not store.rechnung(bill_no):
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Die Rechnung steht nicht in der Arbeitsliste — "
            "erst aufnehmen, dann lässt sich die Darstellung wählen", status_code=303)
    art = (art or "").strip().upper()
    if art and art not in opera.POSITIONSARTEN:
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Unbekannte Darstellung „{art}“",
                                status_code=303)
    store.setzen(bill_no, positionen=art or None)
    text = opera.POSITIONSARTEN[art] if art else "Vorbelegung"
    store.protokoll("positionen", f"Darstellung: {text}", bill_no=bill_no,
                    benutzer=request.state.benutzer)
    meldung = f"Darstellung der Positionen: {text}"
    if (store.rechnung(bill_no) or {}).get("status") == "gesendet":
        meldung += (" — die Rechnung ist bereits versendet; die abgelegte Fassung "
                    "bleibt, wie sie ist")
    return RedirectResponse(f"/rechnung/{bill_no}?meldung={meldung}", status_code=303)


@app.post("/rechnung/{bill_no}/empfaenger")
def empfaenger_setzen(request: Request, bill_no: int, email: str = Form(""),
                            frei: str = Form("")):
    # Wer den Empfaenger setzen darf, bestimmt, wohin eine Rechnung geht. Ohne
    # diese Pruefung konnte ein Konto mit Leserecht jede Rechnung auf eine frei
    # eingetippte Adresse umleiten.
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung",
                                status_code=303)
    # Siehe Kaeuferreferenz: Das Freitextfeld ist leer vorbelegt und gewinnt
    # nur, wenn es gefuellt ist. Vorher trug es den bisherigen Empfaenger und
    # ueberstimmte die Auswahl — eine andere Adresse anzuklicken speicherte die
    # alte, und die Rechnung stand auf 'bereit'.
    ziel = (frei.strip() or email).strip()
    satz = store.rechnung(bill_no) or {}
    if not satz:
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Die Rechnung steht nicht in der Arbeitsliste", status_code=303)
    if ziel and not mailer.adresse_gueltig(ziel):
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=„{ziel}“ ist keine einzelne gültige E-Mail-Adresse",
            status_code=303)
    # Eine versendete oder zurueckgelegte Rechnung wird durch eine geaenderte
    # Adresse NICHT wieder versandbereit. Sonst holt der naechste
    # Automatiklauf sie aus store.faellige() heraus und schickt sie ein
    # zweites Mal — und die abgelegte Fassung wird dabei ueberschrieben.
    if satz.get("status") in ("gesendet", "ignoriert"):
        store.setzen(bill_no, empfaenger=ziel)
        store.protokoll("empfaenger", f"gesetzt auf {ziel or '-'} (Status bleibt "
                        f"{store.status_name(satz.get('status'))})",
                        bill_no=bill_no, benutzer=request.state.benutzer)
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Empfänger gespeichert. Der Status "
            f"„{store.status_name(satz.get('status'))}“ bleibt — die Rechnung wird "
            "dadurch nicht erneut versendet.", status_code=303)
    if satz.get("status") in ("pruefung", "fehler"):
        # Ein Empfaenger ist keine Freigabe. Vorher holte das Speichern einer
        # Adresse JEDEN Beleg aus der Sichtpruefung auf 'bereit' — egal, aus
        # welchem Grund er dort stand —, und die Automatik schickte ihn.
        store.setzen(bill_no, empfaenger=ziel)
        store.protokoll("empfaenger", f"gesetzt auf {ziel or '-'} (Status bleibt "
                        f"{store.status_name(satz.get('status'))})",
                        bill_no=bill_no, benutzer=request.state.benutzer)
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Empfänger gespeichert. Die Rechnung bleibt in "
            f"„{store.status_name(satz.get('status'))}“ — nach dem Prüfen „Prüfung abgeschlossen“ "
            "drücken oder von Hand versenden.", status_code=303)
    store.setzen(bill_no, empfaenger=ziel, status="bereit" if ziel else "neu")
    store.protokoll("empfaenger", f"gesetzt auf {ziel or '-'}", bill_no=bill_no,
                    benutzer=request.state.benutzer)
    return RedirectResponse(f"/rechnung/{bill_no}?meldung=Empfänger gespeichert", status_code=303)


@app.post("/rechnung/{bill_no}/freigeben")
def freigeben(request: Request, bill_no: int):
    """Die Sichtpruefung ausdruecklich abschliessen. Danach darf die
    Automatik die Rechnung versenden — vorausgesetzt, ein Empfaenger steht fest.
    Die Gruende bleiben im Verlauf nachlesbar."""
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung", status_code=303)
    satz = store.rechnung(bill_no) or {}
    if satz.get("status") not in ("pruefung", "fehler"):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Die Rechnung steht nicht in der Prüfung",
                                status_code=303)
    if not (satz.get("empfaenger") or "").strip():
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Erst einen Empfänger wählen",
                                status_code=303)
    if ablauf.VERSAND_OFFEN in (satz.get("fehler") or ""):
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Hier ist ein Versand begonnen worden, dessen Ergebnis "
            "offen ist. Erst im Postfach der Blindkopie nachsehen, ob die Mail hinausging — "
            "freigeben würde sie womöglich ein zweites Mal schicken.", status_code=303)
    store.setzen(bill_no, status="bereit", fehler=None, freigabe_am=store.jetzt())
    store.protokoll("freigegeben", f"Sichtprüfung abgeschlossen (Gründe waren: {satz.get('fehler') or '-'})",
                    bill_no=bill_no, benutzer=request.state.benutzer)
    return RedirectResponse(f"/rechnung/{bill_no}?meldung=Prüfung abgeschlossen — die Rechnung ist bereit",
                            status_code=303)


@app.post("/rechnung/{bill_no}/versand_klaeren")
def versand_klaeren(request: Request, bill_no: int, ergebnis: str = Form("")):
    """Einen Versand mit offenem Ergebnis abschliessen.

    Bricht ein Versand unklar ab, steht der Beleg auf 'fehler' mit dem Vermerk.
    Wer im Postfach der Blindkopie nachgesehen hat, weiss es — und braucht
    dafuer einen Knopf. Ohne ihn war der einzige Ausweg ein zweiter Versand,
    also genau das, wovor der Vermerk warnt."""
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung", status_code=303)
    satz = store.rechnung(bill_no) or {}
    if ablauf.VERSAND_OFFEN not in (satz.get("fehler") or ""):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Für diese Rechnung ist kein Versand offen",
                                status_code=303)
    rest = ablauf.hinweis_weg(satz.get("fehler"), ablauf.VERSAND_OFFEN)
    if ergebnis == "gesendet":
        store.setzen(bill_no, status="gesendet", gesendet_am=satz.get("gesendet_am") or store.jetzt(),
                     fehler=rest)
        store.protokoll("versand", "von Hand als versendet vermerkt (Ergebnis war offen)",
                        bill_no=bill_no, benutzer=request.state.benutzer)
        meldung = "Als versendet vermerkt — die Rechnung geht nicht noch einmal hinaus."
    elif ergebnis == "nicht_gesendet":
        store.setzen(bill_no, status="pruefung" if rest else "bereit", fehler=rest)
        store.protokoll("versand", "von Hand als NICHT versendet vermerkt — erneuter Versand möglich",
                        bill_no=bill_no, benutzer=request.state.benutzer)
        meldung = "Vermerkt: nichts ist hinausgegangen. Die Rechnung lässt sich wieder versenden."
    else:
        meldung = "Bitte angeben, ob die Mail hinausgegangen ist."
    return RedirectResponse(f"/rechnung/{bill_no}?meldung={meldung}", status_code=303)


@app.post("/rechnung/{bill_no}/xml")
def xml_bauen(request: Request, bill_no: int, ersetzen: str = Form("")):
    cfg = config.laden()
    satz = store.rechnung(bill_no) or {}
    if ersetzen and not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung", status_code=303)
    if not ersetzen and ablauf.versendete_fassung(cfg, bill_no):
        # Nicht stillschweigend ersetzen: Danach laege dort etwas anderes als
        # beim Kunden, und niemand saehe es.
        gesendet = (satz.get("gesendet_am") or "")[:10]
        return RedirectResponse(
            f"/rechnung/{bill_no}?meldung=Diese Rechnung ist am {gesendet} versendet worden. "
            "Die versendete Fassung bleibt liegen — zum Ersetzen den Knopf "
            "'Trotzdem neu erzeugen' verwenden.", status_code=303)
    try:
        _, pfad, hinweise = ablauf.xml_erzeugen(cfg, bill_no, ersetzen=bool(ersetzen))
        meldung = f"XML erzeugt: {pfad.name}" + (f" — Hinweise: {'; '.join(hinweise)}" if hinweise else "")
    except Exception as e:
        meldung = f"Fehler: {e}"
    return RedirectResponse(f"/rechnung/{bill_no}?meldung={meldung}", status_code=303)


@app.get("/rechnung/{bill_no}/xml.xml")
def xml_anzeigen(request: Request, bill_no: int):
    cfg = config.laden()
    try:
        # Ansehen schreibt nichts: keine Datei, kein Befund, kein Protokoll.
        xml, _, _ = ablauf.xml_erzeugen(cfg, bill_no, ablegen=False)
    except Exception as e:
        from xml.sax.saxutils import escape
        return Response(f"<fehler>{escape(str(e))}</fehler>", media_type="application/xml",
                        status_code=500)
    return Response(xml, media_type="application/xml")


@app.post("/rechnung/{bill_no}/senden")
def senden(request: Request, bill_no: int):
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung", status_code=303)
    if automatik.laeuft_gerade():
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=" + BESCHAEFTIGT, status_code=303)
    cfg = config.laden()
    try:
        ergebnis = ablauf.versenden(cfg, bill_no, benutzer=request.state.benutzer)
        meldung = ("Testlauf: nicht wirklich versendet" if ergebnis == "testlauf"
                   else "Versendet")
    except Exception as e:
        meldung = f"Fehler: {e}"
    return RedirectResponse(f"/rechnung/{bill_no}?meldung={meldung}", status_code=303)


@app.post("/rechnung/{bill_no}/zuruecklegen")
def zuruecklegen(request: Request, bill_no: int):
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung", status_code=303)
    satz = store.rechnung(bill_no) or {}
    if not satz:
        return RedirectResponse("/?meldung=Die Rechnung steht nicht in der Arbeitsliste", status_code=303)
    if satz.get("status") == "gesendet":
        # Eine versendete Rechnung zurueckzulegen, wuerde verschleiern, dass
        # sie beim Kunden liegt.
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Die Rechnung ist bereits versendet",
                                status_code=303)
    store.setzen(bill_no, status="ignoriert")
    store.protokoll("zurueckgelegt", f"vorher {store.status_name(satz.get('status'))}",
                    bill_no=bill_no, benutzer=request.state.benutzer)
    return RedirectResponse("/?meldung=Rechnung zurückgelegt", status_code=303)


@app.post("/rechnung/{bill_no}/wieder_aufnehmen")
def wieder_aufnehmen(request: Request, bill_no: int):
    """Eine zurueckgelegte Rechnung zurueck in die Pruefung holen. Bewusst in
    die PRUEFUNG, nicht auf 'bereit': Wer zuruecklegt, hatte einen Grund."""
    if not _darf_verwalten(request):
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Keine Berechtigung", status_code=303)
    satz = store.rechnung(bill_no) or {}
    if satz.get("status") != "ignoriert":
        return RedirectResponse(f"/rechnung/{bill_no}?meldung=Die Rechnung ist nicht zurückgelegt",
                                status_code=303)
    ablauf.zur_pruefung(bill_no, "Wieder aufgenommen — bitte prüfen")
    store.protokoll("wieder aufgenommen", "", bill_no=bill_no, benutzer=request.state.benutzer)
    return RedirectResponse(f"/rechnung/{bill_no}?meldung=Wieder aufgenommen, liegt in der Prüfung",
                            status_code=303)


# ------------------------------------------------------------- Konfiguration
@app.get("/konfiguration", response_class=HTMLResponse)
def konfiguration(request: Request, meldung: str = ""):
    cfg = config.laden()
    _quelle = updater.quelle(cfg)
    schreibbar, schreibgrund = config.schreibbar()
    return seiten.TemplateResponse(request, "konfiguration.html", _kontext(
        request, cfg=config.oeffentlich(cfg), meldung=meldung,
        schalter=[f"{s}.{f}" for s, f in SCHALTER],
        schreibbar=schreibbar, schreibgrund=schreibgrund,
        validator=validate.zustand(cfg), version=updater.version(),
        xrechnung_versionen=list(xml_build.VERSIONEN),
        quelle_repo=_quelle[0], quelle_zweig=_quelle[1], quelle_festgenagelt=_quelle[2],
        freigaben=[f.name for f in updater.freigaben()],
        freigabe_aktiv=(updater.AKTUELL.resolve().name
                        if updater.AKTUELL.is_symlink() else ""),
        update_stand=updater.stand().get("eingespielt", "noch nie aktualisiert")))


# ------------------------------------------------------------ Aktualisierung
@app.post("/update/pruefen")
def update_pruefen(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    p = updater.pruefen(config.laden())
    if p.get("moeglich"):
        meldung = (f"Neuer Stand {p['kurz']} vom {p.get('datum','')[:10]}: "
                   f"{p.get('betreff','')} (aktuell: {p.get('aktuell')})")
    else:
        meldung = p.get("text", "Keine Aussage möglich")
    return RedirectResponse(f"/konfiguration?meldung={meldung}", status_code=303)


@app.post("/update/anwenden")
def update_anwenden(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    meldung = updater.anwenden(config.laden(), benutzer=request.state.benutzer)
    return RedirectResponse(f"/konfiguration?meldung={meldung}", status_code=303)


@app.post("/neustart")
def neustart(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    store.protokoll("neustart", "von Hand ausgelöst", benutzer=request.state.benutzer)
    from threading import Timer
    Timer(1.0, updater.neustart).start()
    return RedirectResponse("/konfiguration?meldung=Dienst startet neu — Seite in einigen Sekunden neu laden",
                            status_code=303)


# ------------------------------------------------------------------ Benutzer
@app.get("/benutzer", response_class=HTMLResponse)
def benutzer(request: Request, meldung: str = ""):
    return seiten.TemplateResponse(request, "benutzer.html", _kontext(
        request, meldung=meldung, benutzerliste=auth.benutzer_laden()))


@app.post("/benutzer/passwort")
def passwort(request: Request, alt: str = Form(...), neu: str = Form(...),
                   wiederholung: str = Form(...)):
    if neu != wiederholung:
        return RedirectResponse("/benutzer?meldung=Die beiden neuen Passwörter stimmen nicht überein",
                                status_code=303)
    fehler = auth.passwort_aendern(request.state.benutzer, alt, neu)
    if fehler:
        return RedirectResponse(f"/benutzer?meldung={fehler}", status_code=303)
    antwort = RedirectResponse("/login?fehler=Passwort geändert, bitte neu anmelden", status_code=303)
    antwort.delete_cookie("sitzung")
    return antwort


@app.post("/benutzer/anlegen")
def benutzer_anlegen(request: Request, name: str = Form(...),
                           passwort: str = Form(...), rolle: str = Form("ansehen")):
    if not _darf_verwalten(request):
        return RedirectResponse("/benutzer?meldung=Keine Berechtigung", status_code=303)
    if len(passwort) < 10:
        return RedirectResponse("/benutzer?meldung=Das Passwort muss mindestens 10 Zeichen haben",
                                status_code=303)
    fehler = auth.neu_anlegen(name.strip(), passwort,
                              rolle if rolle in ("ansehen", "verwalten") else "ansehen")
    if fehler:
        return RedirectResponse(f"/benutzer?meldung={fehler}", status_code=303)
    store.protokoll("benutzer", f"'{name}' angelegt ({rolle})", benutzer=request.state.benutzer)
    return RedirectResponse(f"/benutzer?meldung=Benutzer {name} angelegt", status_code=303)


@app.post("/benutzer/loeschen")
def benutzer_loeschen(request: Request, name: str = Form(...)):
    if not _darf_verwalten(request):
        return RedirectResponse("/benutzer?meldung=Keine Berechtigung", status_code=303)
    if name == request.state.benutzer:
        return RedirectResponse("/benutzer?meldung=Der eigene Zugang lässt sich nicht löschen",
                                status_code=303)
    fehler = auth.loeschen(name)
    if fehler:
        return RedirectResponse(f"/benutzer?meldung={fehler}", status_code=303)
    store.protokoll("benutzer", f"'{name}' gelöscht", benutzer=request.state.benutzer)
    return RedirectResponse(f"/benutzer?meldung=Benutzer {name} gelöscht", status_code=303)


# Alle Ja/Nein-Schalter der Konfigurationsseite, in der Reihenfolge der Seite.
# Die Vorlage bekommt dieselbe Liste, damit beide nicht auseinanderlaufen.
SCHALTER = (("datenbank", "thick_mode"), ("mail", "aktiv"),
            ("auswahl", "reservierungsfirma_aufnehmen"),
            ("auswahl", "reservierungsfirma_pruefen"),
            ("auswahl", "nur_inland"),
            ("automatik", "aktiv"), ("automatik", "testlauf"),
            ("automatik", "nur_mit_firmenbezug"),
            ("automatik", "city_ledger_versenden"),
            ("automatik", "empfaenger_automatisch"),
            ("validierung", "aktiv"), ("validierung", "pflicht"),
            ("update", "aktiv"))


@app.post("/konfiguration")
async def konfiguration_speichern(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    formular = await request.form()
    cfg = config.laden()
    vorher_mail = ((cfg.get("mail") or {}).get("smtp_host"),
                   (cfg.get("mail") or {}).get("smtp_port"))
    vorher_update = dict(cfg.get("update") or {})
    vorher_automatik = bool(cfg["automatik"].get("aktiv"))
    ungueltig: list[str] = []
    # Felder, die ohne Inhalt wertlos sind: Ein leeres Feld laesst den
    # bisherigen Wert stehen, statt ihn zu loeschen. Guertel neben dem
    # Hosentraeger — ein Anzeigefehler in der Vorlage soll nicht die
    # Konfiguration kosten.
    NICHT_LEEREN = {("update", "repo"), ("update", "zweig"),
                    ("property", "resort"), ("ablage", "xml_ordner"),
                    ("ablage", "archiv_ordner")}
    for schluessel, wert in formular.items():
        if "." not in schluessel:
            continue
        sektion, feld = schluessel.split(".", 1)
        if sektion not in cfg:
            continue
        alt = cfg[sektion].get(feld)
        if (sektion, feld) in NICHT_LEEREN and not str(wert).strip():
            continue
        if isinstance(alt, bool):
            cfg[sektion][feld] = (wert == "1")
        elif isinstance(alt, (int, float)) and not isinstance(alt, bool):
            # Vorher int(wert or 0): "49,90" ergab HTTP 500 und eine geleerte
            # Wartezeit wurde 0 — die Automatik verschickte dann sofort.
            roh = str(wert).strip().replace(",", ".")
            if not roh:
                continue
            try:
                zahl = float(roh)
            except ValueError:
                ungueltig.append(f"{sektion}.{feld}: „{wert}“ ist keine Zahl")
                continue
            if zahl < 0:
                ungueltig.append(f"{sektion}.{feld}: darf nicht negativ sein")
                continue
            cfg[sektion][feld] = int(zahl) if isinstance(alt, int) and zahl == int(zahl) else zahl
        elif isinstance(alt, list):
            cfg[sektion][feld] = [t.strip() for t in wert.split(",") if t.strip()]
        else:
            cfg[sektion][feld] = wert
    # Ein nicht angehakter Schalter wird vom Browser nicht mitgeschickt — sein
    # Fehlen bedeutet "aus". Zurueckgesetzt werden aber nur die Schalter, die
    # das abgeschickte Formular auch enthielt (verstecktes Feld _schalter).
    # Ohne diese Einschraenkung schaltete ein Formular mit Teilinhalt alles ab,
    # was es nicht kannte: Auslandsfilter, Pruefweg, Validierungspflicht — und
    # zwar ohne Meldung. Genau das ist im Selbsttest passiert.
    # Ist die Quelle in der Unit festgenagelt, kommen repo und zweig gar nicht
    # erst aus dem Formular — das Feld ist dort nur zur Anzeige.
    if updater.quelle(cfg)[2]:
        for feld in ("repo", "zweig"):
            cfg["update"][feld] = vorher_update.get(feld, cfg["update"].get(feld))

    if ungueltig:
        return RedirectResponse("/konfiguration?meldung=NICHT GESPEICHERT — " + "; ".join(ungueltig),
                                status_code=303)
    # Erlaubte Netze: jeder Eintrag muss ein Netz sein, und das Netz, aus dem
    # gerade gespeichert wird, muss darin liegen. Ein Tippfehler sperrte sonst
    # alle aus — auch den, der ihn gemacht hat.
    netze = cfg["server"].get("erlaubte_netze") or []
    for netz in netze:
        try:
            ipaddress.ip_network(netz, strict=False)
        except ValueError:
            return RedirectResponse(f"/konfiguration?meldung=NICHT GESPEICHERT — „{netz}“ ist "
                                    "kein gültiges Netz (z. B. 10.0.0.0/8)", status_code=303)
    ip = request.client.host if request.client else ""
    if netze and not auth.netz_erlaubt(ip, netze):
        return RedirectResponse(f"/konfiguration?meldung=NICHT GESPEICHERT — Ihre Adresse {ip} "
                                "läge außerhalb der erlaubten Netze; Sie hätten sich ausgesperrt",
                                status_code=303)

    # Eine unbekannte XRechnung-Version wird nicht gespeichert: Ab dem naechsten
    # Lauf liesse sich sonst keine einzige Rechnung mehr erzeugen.
    try:
        xml_build.version_aus(cfg)
    except xml_build.XmlFehler as e:
        return RedirectResponse(f"/konfiguration?meldung=NICHT GESPEICHERT — {e}",
                                status_code=303)

    gezeigt = {s.strip() for s in (formular.get("_schalter") or "").split(",") if s.strip()}
    for sektion, feld in SCHALTER:
        name = f"{sektion}.{feld}"
        if name in gezeigt and name not in formular:
            cfg[sektion][feld] = False

    # ERST NACH dem Auswerten der Schalter: Ein nicht angehakter Schalter kommt
    # gar nicht im Formular an; davor stand hier noch der alte Wert, und die
    # Pruefung lief ins Leere.
    # Pflicht ohne eingeschaltete Validierung sperrt jede Rechnung — und zwar
    # dauerhaft und ohne dass die Seite es sagt.
    if cfg["validierung"].get("pflicht") and not cfg["validierung"].get("aktiv"):
        return RedirectResponse("/konfiguration?meldung=NICHT GESPEICHERT — „Pflicht“ ohne "
                                "eingeschaltete Validierung würde jeden Versand sperren. Entweder "
                                "die Validierung einschalten oder die Pflicht abwählen.",
                                status_code=303)

    try:
        config.speichern(cfg)
    except config.KonfigFehler as e:
        store.protokoll("konfiguration", f"nicht gespeichert: {e}",
                        benutzer=request.state.benutzer, erfolg=False)
        return RedirectResponse(f"/konfiguration?meldung=NICHT GESPEICHERT — {e}",
                                status_code=303)
    store.protokoll("konfiguration", "geaendert", benutzer=request.state.benutzer)
    # Die Automatik folgt dem Schalter sofort. Vorher zeigte die Kopfzeile nach
    # dem Speichern "Automatik an", waehrend bis zum Neustart nichts lief.
    if bool(cfg["automatik"].get("aktiv")) != vorher_automatik:
        if cfg["automatik"].get("aktiv"):
            automatik.starten()
        else:
            automatik.stoppen()
    # Verbindung verwerfen: Beim naechsten Zugriff wird sie mit den neuen
    # Zugangsdaten neu aufgebaut. VOR der Mailprobe — deren Warnung kehrte
    # vorher frueh zurueck, und die alte Verbindung blieb stehen.
    #
    # Nicht mitten in einen Automatiklauf hinein: Dort haengt eine Abfrage
    # daran. Der Lauf benutzt dann noch die alte Verbindung; die naechste
    # Anfrage baut sie ohnehin neu auf.
    if not automatik.laeuft_gerade():
        db.stop()
    else:
        store.protokoll("konfiguration", "Datenbankverbindung bleibt vorerst stehen — "
                        "ein Automatiklauf arbeitet gerade", benutzer=request.state.benutzer)
    # Geprueft wird, wenn der Versand eingeschaltet ist ODER der Servername
    # gerade geaendert wurde — sonst bekaeme niemand eine Warnung, der den
    # Server einrichtet, waehrend der Versand noch aus ist. Und wer an anderen
    # Feldern arbeitet, wartet nicht jedes Mal auf den Zeitablauf: Bei einem
    # gefilterten Namen dauert die Probe die vollen drei Sekunden, weil kein
    # "Connection refused" zurueckkommt, sondern gar nichts.
    geaendert = (cfg["mail"].get("smtp_host"), cfg["mail"].get("smtp_port")) != vorher_mail
    warnung = (await asyncio.to_thread(mailer.host_pruefen, cfg)
               if (cfg["mail"].get("aktiv") or geaendert) else "")
    if warnung:
        store.protokoll("konfiguration", warnung,
                        benutzer=request.state.benutzer, erfolg=False)
        return RedirectResponse(f"/konfiguration?meldung=Gespeichert — ACHTUNG: {warnung}",
                                status_code=303)
    return RedirectResponse("/konfiguration?meldung=Gespeichert", status_code=303)


@app.post("/update/zuruecksetzen")
def update_zuruecksetzen(request: Request, freigabe: str = Form("")):
    """Auf eine frühere Freigabe zurückgehen — ein Umhängen, kein Rückspielen."""
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    meldung = updater.zuruecksetzen(freigabe.strip(), benutzer=request.state.benutzer)
    return RedirectResponse(f"/konfiguration?meldung={meldung}", status_code=303)


@app.get("/einrichtung/leitweg", response_class=HTMLResponse)
def einrichtung_leitweg(request: Request, pruefen: str = "", meldung: str = ""):
    """Einrichtungsseite fuer das Leitweg-ID-Feld.

    Sie beantwortet die drei Fragen, die bei jeder neuen Installation
    dieselben sind: Welches Feld ist frei? Welches nehmen wir? Und wie bekommt
    man es in OPERA sichtbar? Ohne diese Seite muss jedes Haus im Data
    Dictionary nachsehen — und dabei ist genau der Fehler entstanden, der uns
    zwei Tage gekostet hat: das Feld an der falschen Kartei."""
    cfg = config.laden()
    felder: list = []
    fehler = ""
    if pruefen:
        try:
            felder = opera.udf_uebersicht()
        except Exception as e:
            log.exception("UDF-Uebersicht nicht lesbar")
            fehler = str(e)
    return seiten.TemplateResponse(request, "einrichtung_leitweg.html", _kontext(
        request, cfg=config.oeffentlich(cfg), felder=felder, fehler=fehler,
        meldung=meldung, geprueft=bool(pruefen)))


@app.post("/einrichtung/leitweg")
def einrichtung_leitweg_speichern(request: Request, feld: str = Form(""),
                                        bedeutung: str = Form("")):
    if not _darf_verwalten(request):
        return RedirectResponse("/einrichtung/leitweg?meldung=Keine Berechtigung",
                                status_code=303)
    cfg = config.laden()
    feld = (feld or "").strip().upper()
    if feld and feld not in opera.UDF_SPALTEN:
        return RedirectResponse(
            f"/einrichtung/leitweg?meldung=„{feld}“ ist kein gültiges Feld. "
            "Erlaubt sind UDFC01 bis UDFC40.", status_code=303)
    cfg["property"]["udf_leitweg"] = feld
    if bedeutung in ("erlaubt", "schliesst_aus"):
        cfg["property"]["udf_erechnung_bedeutung"] = bedeutung
    try:
        config.speichern(cfg)
    except config.KonfigFehler as e:
        return RedirectResponse(f"/einrichtung/leitweg?meldung=NICHT GESPEICHERT — {e}",
                                status_code=303)
    store.protokoll("einrichtung", f"Leitweg-Feld gesetzt auf {feld or '(keines)'}",
                    benutzer=request.state.benutzer)
    return RedirectResponse(
        "/einrichtung/leitweg?meldung=" + (
            f"Gespeichert. Die Anwendung liest die Leitweg-ID ab jetzt aus {feld}."
            if feld else "Gespeichert. Es wird kein Feld ausgelesen."),
        status_code=303)


@app.post("/konfiguration/dbtest")
def dbtest(request: Request):
    # Baut die Datenbankverbindung ab und neu. Waehrend ein Automatiklauf sie
    # benutzt, risse das ihm die Verbindung mitten in einer Abfrage weg.
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    if automatik.laeuft_gerade():
        return RedirectResponse("/konfiguration?meldung=" + BESCHAEFTIGT, status_code=303)
    try:
        db.stop()
        banner = db.pruefen(config.laden())
        meldung = f"Verbindung steht: {banner}"
    except Exception as e:
        meldung = f"Fehler: {e}"
    return RedirectResponse(f"/konfiguration?meldung={meldung}", status_code=303)


@app.get("/einrichtung/anzahlungen", response_class=HTMLResponse)
def einrichtung_anzahlungen(request: Request, pruefen: str = "", meldung: str = ""):
    """Einrichtungsseite fuer die Anzahlungserkennung.

    Sie beantwortet die Frage, die sich in jedem Haus anders beantwortet:
    Fuehrt dieses Haus Anzahlungen als eigene Belege — dann erkennt die
    Anwendung sie am Belegstatus und braucht keine Codes — oder bucht es sie
    innerhalb desselben Belegs um? Im zweiten Fall greift die Statusregel
    nicht, und dann muessen die Umsatzcodes hier hinein.

    Fruher stand dahinter ein Knopf, der das Ergebnis in eine Meldungszeile
    schrieb. Eine Zeile ist der falsche Ort fuer eine Auswahl: Man kann sie
    nicht lesen, nicht vergleichen und nichts daraus uebernehmen."""
    cfg = config.laden()
    zeilen: list = []
    fehler = ""
    if pruefen:
        try:
            zeilen = opera.anzahlungscodes_ermitteln(cfg)
        except Exception as e:
            log.exception("Anzahlungscodes nicht ermittelbar")
            fehler = str(e)
    gewaehlt = [str(c).upper() for c in ((cfg.get("auswahl") or {}).get("anzahlungscodes") or [])]
    # Zahlungsarten getrennt: Sie stehen zwar auf dem Anzahlungsbeleg, sind
    # aber das MITTEL, mit dem gezahlt wurde — Karte, Ueberweisung, PayPal.
    # Genau diese Vermischung liess die frueher fest verdrahtete Codeliste
    # unbrauchbar werden.
    echte = [z for z in zeilen if str(z.get("zahlungsart") or "N").upper() != "J"]
    zahlarten = [z for z in zeilen if str(z.get("zahlungsart") or "N").upper() == "J"]
    return seiten.TemplateResponse(request, "einrichtung_anzahlungen.html", _kontext(
        request, echte=echte, zahlarten=zahlarten, fehler=fehler,
        geprueft=bool(pruefen), gewaehlt=gewaehlt, meldung=meldung,
        status=opera.anzahlung_status(cfg)))


@app.post("/einrichtung/anzahlungen")
async def einrichtung_anzahlungen_speichern(request: Request):
    if not _darf_verwalten(request):
        return RedirectResponse("/einrichtung/anzahlungen?meldung=Keine Berechtigung",
                                status_code=303)
    form = await request.form()
    codes = [w.strip().upper() for w in form.getlist("code") if w.strip()]
    # Von Hand ergaenzte Codes: Ein Haus kann einen benutzen, der im
    # gemessenen Zeitraum nicht vorkam.
    for w in re.split(r"[\s,;]+", form.get("eigene", "") or ""):
        if w.strip() and w.strip().upper() not in codes:
            codes.append(w.strip().upper())
    cfg = config.laden()
    cfg.setdefault("auswahl", {})["anzahlungscodes"] = codes
    try:
        config.speichern(cfg)
    except config.KonfigFehler as e:
        return RedirectResponse(f"/einrichtung/anzahlungen?meldung=Fehler: {e}", status_code=303)
    store.protokoll("konfiguration", "Anzahlungscodes gesetzt: "
                    + (", ".join(codes) if codes else "keine (nur Belegstatus)"),
                    benutzer=request.state.benutzer)
    hinweis = (f"{len(codes)} Umsatzcode(s) uebernommen: " + ", ".join(codes)) if codes else \
              "Keine Codes — es gilt allein der Belegstatus. Das ist der Normalfall."
    return RedirectResponse(f"/einrichtung/anzahlungen?meldung={hinweis}", status_code=303)


@app.post("/konfiguration/mailtest")
def mailtest(request: Request, an: str = Form(...)):
    if not _darf_verwalten(request):
        return RedirectResponse("/konfiguration?meldung=Keine Berechtigung", status_code=303)
    try:
        mailer.test(config.laden(), an)
        meldung = f"Testmail an {an} verschickt (BCC inbegriffen)"
    except Exception as e:
        meldung = f"Fehler: {e}"
    return RedirectResponse(f"/konfiguration?meldung={meldung}", status_code=303)


# --------------------------------------------------------------------- Hilfe
HILFE = {"handbuch": ("HANDBUCH.md", "Handbuch"),
         "installation": ("INSTALLATION.md", "Installation")}


def _hilfe(request: Request, seite: str):
    datei, titel = HILFE[seite]
    pfad = BASE / datei
    if not pfad.exists():
        text, verzeichnis = f"<p>Die Datei {datei} liegt nicht im Programmordner.</p>", []
    else:
        text, verzeichnis = markdown.rendern(pfad.read_text(encoding="utf-8"))
    return seiten.TemplateResponse(request, "hilfe.html", _kontext(
        request, text=text, verzeichnis=verzeichnis, seite=seite, titel=titel))


@app.get("/hilfe", response_class=HTMLResponse)
def hilfe(request: Request):
    return _hilfe(request, "handbuch")


@app.get("/hilfe/installation", response_class=HTMLResponse)
def hilfe_installation(request: Request):
    return _hilfe(request, "installation")


@app.get("/protokoll", response_class=HTMLResponse)
def protokoll(request: Request):
    return seiten.TemplateResponse(request, "protokoll.html", _kontext(
        request, eintraege=store.protokoll_lesen(300)))
