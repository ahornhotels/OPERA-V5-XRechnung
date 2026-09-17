"""KoSIT-Validierung. Läuft ausschliesslich LOKAL als Java-Werkzeug auf dem
eigenen Server — eine fertige XRechnung enthaelt Kaeufername, Anschrift und
Betraege und gehoert in keine gehostete Pruefseite.

Die Aufruf-Eigenheiten stammen aus der Suite8-Vorlage
(reference/XRechnung_Slim/modules/kosit_validator.py, GPLv3) und sind dort im
Feld erarbeitet — insbesondere die leere stdin-Pipe, ohne die der Validator
unter Windows mit "Unzulaessige Funktion" abbricht."""
from __future__ import annotations
import atexit
import logging
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from lxml import etree

from . import pfade, xml_build

log = logging.getLogger(__name__)
BASE = pfade.PROGRAMM

NS = {"rep": "http://www.xoev.de/de/validator/varl/1",
      "svrl": "http://purl.oclc.org/dsdl/svrl"}


class ValidierungsFehler(Exception):
    def __init__(self, meldungen: list[str]):
        self.meldungen = meldungen
        super().__init__("KoSIT-Validierung fehlgeschlagen:\n" + "\n".join(meldungen))


class NichtEingerichtet(Exception):
    """Validator ist nicht installiert oder nicht konfiguriert."""


def _pfad(wert: str) -> Path | None:
    """Pfad zum Validator. Relative Angaben gelten gegenueber der INSTALLATION.

    validation/ ist 16 MB gross, liegt bewusst nicht im Repository und wird bei
    einer Aktualisierung nicht mitgeliefert. Gegen das Programmverzeichnis
    aufgeloest zeigte der Pfad in einer frischen Freigabe ins Leere — und weil
    validierung.pflicht gesetzt ist, scheiterte ab dem Umschalten JEDE
    Rechnung."""
    if not (wert or "").strip():
        return None
    return pfade.im_bestand(wert)


def java_pfad(cfg: dict) -> str | None:
    """Sucht Java: erst der konfigurierte Pfad, dann eine mitgelieferte JRE,
    dann java im Systempfad."""
    gesetzt = (cfg["validierung"].get("java") or "").strip()
    if gesetzt and gesetzt.lower() not in ("java", "java.exe"):
        # Ein relativer Pfad gilt gegenueber der INSTALLATION — das
        # Arbeitsverzeichnis ist im Freigabebetrieb die jeweilige Freigabe.
        pfad = pfade.im_bestand(gesetzt) if ("/" in gesetzt or "\\" in gesetzt) else None
        if pfad is not None:
            return str(pfad) if pfad.exists() else None
        return shutil.which(gesetzt)
    name = "java.exe" if os.name == "nt" else "java"
    mitgeliefert = pfade.BASIS / "validation" / "jre" / "bin" / name
    if mitgeliefert.exists():
        return str(mitgeliefert)
    return shutil.which("java")


_java_versionen: dict[str, str | None] = {}


def java_laeuft(java: str) -> str | None:
    """Wie _java_laeuft, aber je Pfad nur einmal je Prozess. Vorher startete
    jede einzelne Pruefung dafuer eine zusaetzliche JVM."""
    if java not in _java_versionen or _java_versionen[java] is None:
        _java_versionen[java] = _java_laeuft(java)
    return _java_versionen[java]


def _java_laeuft(java: str) -> str | None:
    """Prueft, ob das gefundene Java wirklich startet. Gibt die Versionszeile
    zurueck oder None.

    Noetig, weil ein vorhandener Pfad nichts beweist: macOS liefert unter
    /usr/bin/java einen Platzhalter, der nur auf die Java-Webseite verweist,
    und auch unter Linux kann ein Verweis ins Leere zeigen. Ohne diese Probe
    meldete sich die Validierung als einsatzbereit und scheiterte erst an der
    ersten echten Rechnung."""
    try:
        lauf = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return None
    if lauf.returncode != 0:
        return None
    ausgabe = (lauf.stderr or lauf.stdout or "").strip().splitlines()
    return ausgabe[0] if ausgabe else "Java"


_REGELWERK_IM_PFAD = re.compile(r"xrechnung-(\d+\.\d+(?:\.\d+)?)")


def szenarien_zur_version(cfg: dict) -> tuple[str, str]:
    """(Pfad zur scenarios.xml, Befund) fuer die eingestellte XRechnung-Version.

    Der Pfad darf {version} enthalten — dann waehlt der Versionsschalter das
    Regelwerk mit. Aeltere Anlagen tragen einen festen Pfad
    (validation/xrechnung-3.0.2/...). Der bleibt gueltig, solange er zur
    Version passt; passt er nicht, ist das ein Befund und keine stille
    Pruefung gegen das falsche Regelwerk. Eine 4.0-Rechnung gegen 3.0.2
    geprueft meldete nur "kein Szenario gefunden", ohne zu sagen warum."""
    try:
        version = xml_build.version_aus(cfg)
    except xml_build.XmlFehler as e:
        return "", str(e)
    wert = (cfg["validierung"].get("kosit_szenarien") or "").strip()
    if "{version}" in wert:
        return wert.replace("{version}", version), ""
    im_pfad = _REGELWERK_IM_PFAD.search(wert)
    regelwerk = xml_build.VERSIONEN[version]["regelwerk"]
    if im_pfad and f"xrechnung-{im_pfad.group(1)}" != regelwerk:
        return wert, (f"Regelwerk {im_pfad.group(0)} passt nicht zur eingestellten "
                      f"XRechnung-Version {version} — Pfad auf {regelwerk} ändern "
                      "oder {version} einsetzen")
    return wert, ""


def zustand(cfg: dict) -> dict:
    """Was fehlt zur Einrichtung? Wird in der Oberflaeche angezeigt."""
    v = cfg["validierung"]
    jar = _pfad(v.get("kosit_jar") or "")
    pfad_szenarien, versionsbefund = szenarien_zur_version(cfg)
    szenarien = _pfad(pfad_szenarien)
    java = java_pfad(cfg)
    version = java_laeuft(java) if java else None
    fehlt = []
    if versionsbefund:
        fehlt.append(versionsbefund)
    if not java:
        fehlt.append("Java (JRE 11 oder neuer) — nicht gefunden")
    elif not version:
        fehlt.append(f"Java gefunden ({java}), startet aber nicht — "
                     "vermutlich nur ein Platzhalter oder eine kaputte Verknuepfung")
    if not jar:
        fehlt.append("Validator-JAR — Pfad nicht konfiguriert")
    elif not jar.exists():
        fehlt.append(f"Validator-JAR nicht gefunden: {jar}")
    if not szenarien:
        fehlt.append("scenarios.xml — Pfad nicht konfiguriert")
    elif not szenarien.exists():
        fehlt.append(f"scenarios.xml nicht gefunden: {szenarien}")
    return {"bereit": not fehlt, "fehlt": fehlt,
            "java": java or "—", "java_version": version or "—",
            "jar": str(jar) if jar else "—",
            "szenarien": str(szenarien) if szenarien else "—",
            "xrechnung_version": _version_oder_strich(cfg)}


def _version_oder_strich(cfg: dict) -> str:
    try:
        return xml_build.version_aus(cfg)
    except xml_build.XmlFehler:
        return "—"


# --- Daemon-Betrieb -------------------------------------------------------
# Der Validator braucht zum Start rund zwoelf Sekunden, davon 44 Millisekunden
# fuer die JVM und den ganzen Rest fuer das Einlesen und Uebersetzen der
# Schematron-Regelwerke. Die eigentliche Pruefung dauert danach 674 ms. Bei
# einem Aufruf je Rechnung wird dieser Aufwand fuer JEDE Rechnung neu
# getrieben: Ein voller Durchlauf waere so von Minuten auf Stunden gewachsen.
#
# Der Validator bringt dafuer einen Daemon-Modus mit. Er laeuft einmal, haelt
# die Regeln geladen und nimmt die Rechnungen per HTTP entgegen. Er lauscht
# ausschliesslich auf 127.0.0.1 und ohne Oberflaeche (-G): Eine fertige
# XRechnung traegt Namen, Anschrift und Betraege und gehoert in kein Netz.
#
# Der Einzelaufruf bleibt vollstaendig erhalten. Antwortet der Daemon nicht,
# wird er benutzt — lieber langsam als gar nicht, und das Urteil ist
# dasselbe, weil beide Wege denselben Bericht auswerten.
_daemon: dict = {"prozess": None, "port": 0, "jar": "", "szenarien": "",
                 "gescheitert_bis": 0.0}
# Die Oberflaeche und die Automatik pruefen in verschiedenen Threads. Ohne
# Sperre starteten zwei gleichzeitige Pruefungen zwei Daemons.
_daemon_sperre = threading.Lock()
# Nach einem gescheiterten Start so lange nicht erneut versuchen. Vorher
# wartete JEDE Rechnung bis zu 90 Sekunden auf einen Daemon, der nicht kam.
DAEMON_PAUSE_NACH_FEHLSTART = 600


def _freier_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _lauscht(port: int, sekunden: float = 0.5) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), sekunden):
            return True
    except OSError:
        return False


def daemon_zustand() -> dict:
    """Laeuft der Daemon? Fuer die Oberflaeche und den Selbsttest."""
    p = _daemon["prozess"]
    laeuft = bool(p and p.poll() is None and _lauscht(_daemon["port"]))
    return {"laeuft": laeuft, "port": _daemon["port"] if laeuft else 0}


def daemon_stoppen() -> None:
    p = _daemon["prozess"]
    _daemon["prozess"] = None
    if not p or p.poll() is not None:
        return
    p.terminate()
    try:
        p.wait(timeout=10)
    except subprocess.TimeoutExpired:
        p.kill()
    log.info("KoSIT-Daemon beendet")


def _daemon_starten(z: dict, wartezeit: int = 90) -> int:
    """Startet den Daemon und wartet, bis er antwortet. 0 heisst: nicht
    verfuegbar — dann laeuft der Einzelaufruf."""
    with _daemon_sperre:
        return _daemon_starten_gesperrt(z, wartezeit)


def _daemon_starten_gesperrt(z: dict, wartezeit: int) -> int:
    vorhanden = _daemon["prozess"]
    if vorhanden and vorhanden.poll() is None:
        # Aenderte sich die Einrichtung, muss der alte Daemon weichen: Er
        # haelt die ALTEN Regeln geladen und wuerde weiter danach urteilen.
        if (_daemon["jar"], _daemon["szenarien"]) == (z["jar"], z["szenarien"]):
            if _lauscht(_daemon["port"]):
                return _daemon["port"]
        daemon_stoppen()

    if time.monotonic() < _daemon["gescheitert_bis"]:
        return 0
    port = _freier_port()
    szenarien = Path(z["szenarien"])
    befehl = [z["java"], "-jar", z["jar"], "-s", z["szenarien"],
              "-D", "-H", "127.0.0.1", "-P", str(port), "-T", "1", "-G"]
    try:
        prozess = subprocess.Popen(
            befehl, cwd=str(szenarien.parent),
            # NICHT in eine Pipe: Die las niemand. War ihr Puffer voll (unter
            # Linux 64 KiB, unter Windows wenige KiB), blieb der Daemon im
            # Schreiben haengen, lauschte aber weiter — und jede Pruefung
            # wartete 120 Sekunden auf eine Antwort, die nie kam.
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError) as e:
        log.warning("KoSIT-Daemon liess sich nicht starten (%s) — Einzelaufruf", e)
        _daemon["gescheitert_bis"] = time.monotonic() + DAEMON_PAUSE_NACH_FEHLSTART
        return 0

    ende = time.monotonic() + wartezeit
    while time.monotonic() < ende:
        if prozess.poll() is not None:
            log.warning("KoSIT-Daemon hat sich sofort beendet (Rueckgabewert %s) — "
                        "Einzelaufruf", prozess.returncode)
            _daemon["gescheitert_bis"] = time.monotonic() + DAEMON_PAUSE_NACH_FEHLSTART
            return 0
        if _lauscht(port):
            _daemon.update(prozess=prozess, port=port,
                           jar=z["jar"], szenarien=z["szenarien"])
            atexit.register(daemon_stoppen)
            log.info("KoSIT-Daemon läuft auf 127.0.0.1:%s", port)
            return port
        time.sleep(0.5)

    log.warning("KoSIT-Daemon antwortet nach %s Sekunden nicht — Einzelaufruf", wartezeit)
    prozess.terminate()
    _daemon["gescheitert_bis"] = time.monotonic() + DAEMON_PAUSE_NACH_FEHLSTART
    return 0


def anfrage_an_daemon(port: int, xml: bytes) -> bytes | None:
    """Eine Rechnung an den laufenden Daemon schicken. Gibt den Pruefbericht
    zurueck, oder None, wenn dieser Weg nicht geht.

    Der Daemon nimmt die Rechnung als POST auf / entgegen, Content-Type
    application/xml (GET beantwortet er mit 'Method not supported'). Das
    Urteil steckt im HTTP-Status: 200 fuer angenommen, 406 fuer abgelehnt —
    der Bericht liegt in BEIDEN Faellen im Koerper. Wer nur 200 gelten laesst,
    schickt jede abgelehnte Rechnung in den langsamen Einzelaufruf.

    Eigene Funktion, damit sich der Weg ohne Java pruefen laesst."""
    anfrage = urllib.request.Request(
        f"http://127.0.0.1:{port}/", data=xml, method="POST",
        headers={"Content-Type": "application/xml"})
    try:
        with urllib.request.urlopen(anfrage, timeout=120) as antwort:
            return antwort.read()
    except urllib.error.HTTPError as e:
        roh = e.read()
        if roh and b"<" in roh[:200]:
            return roh
        log.warning("KoSIT-Daemon antwortet mit HTTP %s — Einzelaufruf", e.code)
    except (urllib.error.URLError, OSError) as e:
        log.warning("KoSIT-Daemon nicht erreichbar (%s) — Einzelaufruf", e)
    return None


def _ueber_daemon(z: dict, xml: bytes) -> bytes | None:
    """Startet den Daemon bei Bedarf und schickt die Rechnung hin.
    None heisst: der Aufrufer soll den Einzelaufruf nehmen."""
    port = _daemon_starten(z)
    if not port:
        return None
    return anfrage_an_daemon(port, xml)


def pruefen(cfg: dict, xml: bytes) -> list[str]:
    """Validiert das XML. Leere Liste heisst: angenommen.
    Wirft NichtEingerichtet, wenn der Validator fehlt.

    Nur was den Versand verhindert. Die Warnungen liefert
    pruefen_ausfuehrlich()."""
    return pruefen_ausfuehrlich(cfg, xml)[0]


def pruefen_ausfuehrlich(cfg: dict, xml: bytes) -> tuple[list[str], list[str]]:
    """Wie pruefen(), gibt aber (Fehler, Warnungen) zurueck.

    Warnungen blockieren nichts — eine angenommene Rechnung kann trotzdem
    welche tragen, und sie verschwanden bisher unbemerkt. Die Empfangssysteme
    grosser Konzerne pruefen strenger als der KoSIT-Validator; was er nur
    anmerkt, kann dort eine Rueckfrage ausloesen."""
    z = zustand(cfg)
    if not z["bereit"]:
        raise NichtEingerichtet("; ".join(z["fehlt"]))

    if cfg["validierung"].get("daemon", True):
        roh = _ueber_daemon(z, xml)
        if roh is not None:
            try:
                # etree.fromstring() liefert ein Element, etree.parse() einen
                # Baum — nur der hat getroot(). Ohne die Klammer hier stuerzte
                # der Daemon-Weg bei JEDER Rechnung ab, auch bei einer
                # fehlerfreien, und der AttributeError lief am except vorbei.
                return _bericht_auswerten(etree.ElementTree(etree.fromstring(roh)))
            except etree.XMLSyntaxError as e:
                log.warning("Antwort des Daemons nicht lesbar (%s) — Einzelaufruf", e)

    java = z["java"]
    jar = Path(z["jar"])
    szenarien = Path(z["szenarien"])

    with tempfile.TemporaryDirectory() as ordner:
        tmp = Path(ordner)
        eingabe = tmp / "rechnung.xml"
        eingabe.write_bytes(xml)
        try:
            lauf = subprocess.run(
                [java, "-jar", str(jar), "-s", str(szenarien), "-o", str(tmp), str(eingabe)],
                capture_output=True, text=True, timeout=120,
                cwd=str(szenarien.parent),
                # Ohne leere stdin bricht der Validator unter Windows ab
                # ("Unzulaessige Funktion"). Unter Linux schadet es nicht.
                input="",
            )
        except subprocess.TimeoutExpired:
            raise ValidierungsFehler(["Der Validator hat nach 120 Sekunden nicht geantwortet"])

        bericht = tmp / "rechnung-report.xml"
        if not bericht.exists():
            raise ValidierungsFehler([
                f"Kein Prüfbericht erzeugt (Rückgabewert {lauf.returncode}). "
                f"Meldung: {(lauf.stderr or '')[:400]}"])

        try:
            baum = etree.parse(str(bericht))
        except etree.XMLSyntaxError as e:
            raise ValidierungsFehler([f"Prüfbericht nicht lesbar: {e}"])
        return _bericht_auswerten(baum)


def _bericht_auswerten(baum) -> tuple[list[str], list[str]]:
    """Aus dem Pruefbericht (Fehler, Warnungen) machen — fuer beide Wege
    derselbe Code, damit Daemon und Einzelaufruf nie verschieden urteilen."""
    warnungen = [
        "Warnung " + (e.get("code") or "") + ": " + (e.text or "").strip()[:400]
        for e in baum.xpath("//rep:message[@level='warning']", namespaces=NS)]
    # Ein Sicherheitsnetz muss im Zweifel SPERREN, nicht durchlassen. Vorher
    # stand hier "true" als Vorgabe: Ein Bericht ohne das Merkmal galt als
    # angenommen — und ueber den Daemon kommt jeder Antwortkoerper hier an, der
    # mit einem '<' beginnt. Eine unvalidierte Rechnung waere als
    # "KoSIT ohne Befund" protokolliert und versendet worden.
    urteil = baum.getroot().get("valid")
    if urteil is None:
        return (["Der Prüfbericht nennt kein Ergebnis (Merkmal 'valid' fehlt). "
                 "Die Rechnung gilt damit als NICHT geprüft — kein Versand."],
                warnungen)
    if urteil.lower() == "true":
        return [], warnungen

    meldungen: list[str] = []
    for e in baum.xpath("//rep:schemaValidationError/rep:errorMessage", namespaces=NS):
        meldungen.append(f"Schema: {(e.text or '').strip()[:400]}")
    for e in baum.xpath("//svrl:failed-assert", namespaces=NS):
        meldungen.append("Regel: " + " ".join(t.strip() for t in e.itertext() if t.strip())[:400])
    for e in baum.xpath("//rep:message[@level='error']", namespaces=NS):
        meldungen.append(f"Annahme {e.get('code','')}: {(e.text or '').strip()[:400]}")
    if baum.xpath("//rep:noScenarioMatched", namespaces=NS):
        meldungen.append("Kein Szenario gefunden — CustomizationID oder Namensraum prüfen")
    if not meldungen:
        meldungen.append("Der Validator lehnt die Rechnung ab, nennt aber keinen Grund")
    return meldungen, warnungen
