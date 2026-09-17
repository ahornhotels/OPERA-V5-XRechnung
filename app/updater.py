"""Aktualisierung über GitHub. Holt den aktuellen Stand des Repositories,
tauscht ausschliesslich Programmdateien aus und laesst Konfiguration, Daten,
Protokoll und die Validierungsartefakte unberuehrt.

Bewusst einfach gehalten: kein Abgleich mit dem Vorhandenen, sondern ein
sauberer Stand aus dem Archiv. Vor dem Austausch wird gesichert, damit ein
Rueckweg bleibt."""
from __future__ import annotations
import asyncio
import getpass
import importlib.util
import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from . import config, pfade, store

log = logging.getLogger(__name__)
BASE = pfade.PROGRAMM
STAND_DATEI = pfade.DATEN_DIR / "update_stand.json"

# Was ausgetauscht wird. Alles andere — vor allem die eigene Konfiguration,
# data/, logs/ und validation/ — bleibt unangetastet.
# Was zum PROGRAMM gehoert und bei einer Aktualisierung mitkommt.
# beispiele/ steht hier, weil es im Repository liegt: Was dort liegt, wird
# auch ausgeliefert. Vorher war es weder Programm noch Bestand, sondern
# unbeantwortet — mit der Folge, dass die Beleg-Probe der Umstellung
# lautlos nie stattfand.
PROGRAMM = ["app", "sql", "tools", "docs", "install", "beispiele",
            "requirements.txt", "requirements-dev.txt",
            "run.cmd", "run.sh", "VERSION", "README.md", "PROTOTYP.md",
            "HANDBUCH.md", "INSTALLATION.md"]

# Wird beim Austausch von install/ ausgespart: das Werkzeug laedt der
# Installer selbst nach, und es gehoert nicht ins Repository. Vor allem aber
# LAEUFT es: NSSM ist der Prozess, der diesen Dienst traegt. Windows verweigert
# das Loeschen eines laufenden Programms — frueher scheiterte rmtree(install/)
# genau daran, mitten im Austausch, und liess eine halb ersetzte Installation
# zurueck. Eine Ausnahme wird deshalb weder geloescht noch ersetzt noch
# verschoben, nicht einmal angefasst.
AUSNAHMEN = {"nssm.exe"}

# Einzelne Dateien aus config/, die mitkommen duerfen. Die VORLAGE wird
# erneuert, damit neue Einstellungen bekannt werden — die eigene app.json,
# users.json und der Schluessel werden NIE angefasst. Fehlende Einstellungen
# ergaenzt config.laden() beim naechsten Start aus der Vorlage.
KONFIG_VORLAGEN = ["config/app.example.json"]


def version() -> str:
    datei = BASE / "VERSION"
    return datei.read_text(encoding="utf-8").strip() if datei.exists() else "unbekannt"


# Jede Freigabe traegt bei sich, WAS sie ist. Das ist der Unterschied zu einer
# Datei daneben, die den Stand hueten muss: Beim Zuruecksetzen wandert die
# Wahrheit mit dem Symlink mit, ohne dass jemand sie nachfuehren muesste.
#
# Vorher schrieb nur anwenden() den Stand. Nach einem Zuruecksetzen stand dort
# weiterhin die neuere Freigabe — pruefen() verglich die Spitze des Zweiges
# dagegen, fand sie gleich und meldete "Bereits aktuell". Wer zurueckgegangen
# war, kam ueber die Oberflaeche nicht wieder nach vorn.
FREIGABE_STAND = ".freigabe.json"


def stand() -> dict:
    """Welcher Stand laeuft gerade?

    Zuerst die laufende Freigabe selbst, dann die Datei daneben. Traegt eine
    Freigabe nichts bei sich (die erste aus der Umstellung, oder eine aus der
    Zeit vor dieser Aenderung), liefert der Verzeichnisname wenigstens die
    verkuerzte Kennung — pruefen() vergleicht entsprechend."""
    if AKTUELL.is_symlink():
        eigen = AKTUELL / FREIGABE_STAND
        try:
            if eigen.exists():
                daten = json.loads(eigen.read_text(encoding="utf-8"))
                daten["freigabe"] = AKTUELL.resolve().name
                return daten
        except (json.JSONDecodeError, OSError):
            pass
        # Kein eigener Vermerk: Der Verzeichnisname endet auf den Kurz-Sha.
        name = AKTUELL.resolve().name
        teil = name.rsplit("-", 1)[-1]
        if len(teil) >= 7 and all(c in "0123456789abcdef" for c in teil.lower()):
            return {"sha": teil, "freigabe": name, "verkuerzt": True}
    if STAND_DATEI.exists():
        try:
            return json.loads(STAND_DATEI.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def _anfrage(url: str, token: str = "", roh: bool = False):
    """Alle Aufrufe laufen ueber die GitHub-API — auch der Archiv-Download.
    Das ist Absicht: Bei einem PRIVATEN Repository funktioniert nur dieser Weg,
    weil er den Token mitschickt. Ein anonymer Zugriff bekaeme dort 404."""
    kopf = {"User-Agent": "OPERA-XRechnung", "Accept": "application/vnd.github+json"}
    if token:
        kopf["Authorization"] = f"Bearer {token}"
    bitte = urllib.request.Request(url, headers=kopf)
    with urllib.request.urlopen(bitte, timeout=60) as antwort:
        return antwort.read() if roh else json.loads(antwort.read())


def _fehlertext(fehler: Exception, repo: str, token: str) -> str:
    """Uebersetzt die GitHub-Antwort in etwas, das weiterhilft.
    Wichtigster Fall: 404 bedeutet bei einem privaten Repository fast immer
    einen fehlenden oder unzureichenden Token, nicht ein fehlendes Repository —
    GitHub antwortet dort aus Sicherheitsgruenden mit 404 statt 403."""
    code = getattr(fehler, "code", None)
    if code == 404:
        if not token:
            return (f"'{repo}' nicht gefunden. Ist das Repository privat? Dann wird ein "
                    "Token gebraucht (Konfiguration → Aktualisierung, Berechtigung "
                    "'Contents: Read').")
        return (f"'{repo}' nicht gefunden — Name pruefen, oder der Token hat keinen "
                "Zugriff auf genau dieses Repository.")
    if code == 422:
        return (f"In '{repo}' gibt es die angegebene Referenz nicht — vermutlich ein "
                "falscher Zweigname. In der Konfiguration unter Aktualisierung pruefen.")
    if code in (401, 403):
        return (f"Zugriff auf '{repo}' verweigert (HTTP {code}). Der Token ist abgelaufen "
                "oder hat keine Leseberechtigung fuer den Inhalt.")
    return f"GitHub nicht erreichbar: {fehler}"


def quelle(cfg: dict) -> tuple[str, str, bool]:
    """Repository, Zweig — und ob sie festgenagelt sind.

    Steht in der Umgebung ein Wert (aus der root-eigenen systemd-Unit), gewinnt
    er gegen config/app.json. Der Grund: app.json gehoert dem Dienstkonto. Ein
    uebernommener Dienst koennte den Zeiger sonst auf ein fremdes Repository
    richten, eine Aktualisierung ausloesen und sich dauerhaft einnisten —
    neustartfest, weil systemd ihn wieder hochfaehrt. Der Token nuetzt dabei
    niemandem; der ZEIGER ist das Problem, nicht der Schluessel."""
    u = cfg.get("update") or {}
    repo = (os.environ.get("XRECHNUNG_UPDATE_REPO") or "").strip()
    zweig = (os.environ.get("XRECHNUNG_UPDATE_ZWEIG") or "").strip()
    festgenagelt = bool(repo)
    return (repo or (u.get("repo") or "").strip(),
            zweig or (u.get("zweig") or "main").strip(),
            festgenagelt)


def pruefen(cfg: dict) -> dict:
    """Sieht nach, ob es einen neueren Stand gibt."""
    u = cfg.get("update") or {}
    if not u.get("aktiv"):
        return {"moeglich": False, "text": "Aktualisierung ist abgeschaltet."}
    repo, zweig, _ = quelle(cfg)
    if "/" not in repo:
        return {"moeglich": False, "text": "Kein Repository konfiguriert."}
    token = u.get("token") or ""
    try:
        daten = _anfrage(f"https://api.github.com/repos/{repo}/commits/{zweig}", token)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        # Zwei Faelle, die GitHub sauber trennt — aber anders, als man vermutet:
        #   404  Repository nicht sichtbar        -> Token oder Berechtigung
        #   422  Repository sichtbar, Referenz unbekannt -> Zweigname
        # Der commits-Endpunkt behandelt den Zweig als Referenz; eine unbekannte
        # Referenz ist fuer GitHub keine fehlende Ressource, sondern eine
        # unverarbeitbare Angabe. Beide Codes werden geprueft: 422 ist der
        # tatsaechliche Fall, 404 bleibt drin, falls GitHub das je aendert.
        if getattr(e, "code", None) in (404, 422):
            try:
                info = _anfrage(f"https://api.github.com/repos/{repo}", token)
                standard = info.get("default_branch")
                if standard and standard != zweig:
                    return {"moeglich": False, "zweig_falsch": True, "standardzweig": standard,
                            "text": (f"Den Zweig '{zweig}' gibt es in {repo} nicht. "
                                     f"Der Standardzweig heisst '{standard}' — bitte in der "
                                     "Konfiguration unter Aktualisierung eintragen.")}
            except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
                pass
        return {"moeglich": False, "text": _fehlertext(e, repo, token)}
    neu = daten.get("sha", "")
    datum = (daten.get("commit", {}).get("author", {}) or {}).get("date", "")
    betreff = (daten.get("commit", {}) or {}).get("message", "").splitlines()[0][:120]
    alt = stand().get("sha", "")
    # Eine Freigabe ohne eigenen Vermerk kennt nur die verkuerzte Kennung.
    # Verglichen wird dann auf der kuerzeren der beiden Laengen — sonst gaelte
    # ein Stand als verschieden, nur weil er kuerzer aufgeschrieben ist.
    gleich = bool(alt) and (neu == alt or (len(alt) < len(neu) and neu.startswith(alt)))
    moeglich = bool(neu) and not gleich
    # Anzeige und Entscheidung kommen aus DERSELBEN Rechnung. Vorher stand hier
    # 'neu != alt' — ein exakter Vergleich, waehrend moeglich praefixbewusst
    # rechnete. Bei einer Freigabe ohne eigenen Vermerk (die erste nach einer
    # Umstellung traegt keinen) fielen die beiden auseinander: Die Oberflaeche
    # meldete "Neuer Stand verfuegbar" und weigerte sich zugleich, ihn
    # einzuspielen. Der Knopf tat nichts, und die Meldung daneben sagte, es
    # gaebe etwas zu tun.
    return {"moeglich": moeglich, "sha": neu, "kurz": neu[:8],
            "datum": datum, "betreff": betreff, "aktuell": alt[:8] or "unbekannt",
            "text": ("Neuer Stand verfügbar" if moeglich else "Bereits aktuell")}


def schreibrechte_pruefen() -> list[str]:
    """Kann der laufende Benutzer ueberhaupt alles ersetzen, was ersetzt werden
    soll? Gibt die Verzeichnisse zurueck, an denen es scheitern wuerde.

    Das muss VOR dem ersten Anfassen geschehen. Der Austausch rollt einen
    Fehler zwar zurueck (siehe _austausch_an_ort), aber eine Aktualisierung,
    die an Rechten scheitern MUSS, soll gar nicht erst anfangen — jeder
    Rueckweg ist ein Weg mehr, auf dem etwas schiefgehen kann.

    Auf Rocky Linux ist genau das passiert: Der Installer uebergibt nur
    config/, data/ und logs/ dem Dienstkonto, die Programmverzeichnisse
    bleiben root:root. Der Dienst laeuft als xrechnung und darf in
    /opt/xrechnung nicht schreiben. Dass dabei nichts kaputtging, war Glueck —
    rmtree scheiterte gleich am ersten Eintrag.

    Geprueft wird das ELTERNVERZEICHNIS: Ein Verzeichnis zu ersetzen heisst,
    im Elternverzeichnis zu loeschen und anzulegen. Ob die Datei selbst
    beschreibbar ist, sagt darueber nichts."""
    fehlend: list[str] = []
    for name in PROGRAMM + KONFIG_VORLAGEN:
        ziel = BASE / name
        eltern = ziel.parent
        if not eltern.exists():
            continue
        if not os.access(eltern, os.W_OK | os.X_OK):
            eintrag = str(eltern)
            if eintrag not in fehlend:
                fehlend.append(eintrag)
    return fehlend


def _requirements_lesen() -> set[str]:
    datei = BASE / "requirements.txt"
    if not datei.exists():
        return set()
    return {z.split("#")[0].strip().lower()
            for z in datei.read_text(encoding="utf-8").splitlines()
            if z.split("#")[0].strip()}


def _neue_abhaengigkeiten(vorher: set[str]) -> list[str]:
    return sorted(_requirements_lesen() - vorher)


# --- Freigabeverzeichnisse ------------------------------------------------
# Der Weg unter Linux: Jeder Stand bekommt ein eigenes Verzeichnis, und
# 'aktuell' zeigt darauf. Umgeschaltet wird mit os.replace() auf den Symlink —
# ein Schritt, der ganz oder gar nicht passiert. Scheitert das Auspacken,
# laeuft die alte Fassung unveraendert weiter; es gibt keinen Zustand
# "halb ersetzt" mehr.
#
# Unter Windows bleibt es beim Austausch an Ort und Stelle: Symbolische
# Verknuepfungen brauchen dort besondere Rechte, Junctions lassen sich nicht in
# einem Schritt umhaengen — der Vorteil des Verfahrens waere gerade weg, und
# das Rechteproblem, das ihn noetig macht, gibt es dort nicht.
PROGRAMM_DIR = pfade.BASIS / "programm"
FREIGABEN = PROGRAMM_DIR / "freigaben"
AKTUELL = PROGRAMM_DIR / "aktuell"
FREIGABEN_BEHALTEN = 3


def freigabenbetrieb() -> bool:
    """Laeuft diese Installation schon mit Freigaben?"""
    return AKTUELL.is_symlink() or (FREIGABEN.exists() and FREIGABEN.is_dir())


def freigaben() -> list[Path]:
    """Vorhandene Freigaben, neueste zuerst."""
    if not FREIGABEN.is_dir():
        return []
    return sorted((p for p in FREIGABEN.iterdir() if p.is_dir()
                   and not p.name.endswith(".neu")),
                  key=lambda p: p.name, reverse=True)


def umschalten(ziel: Path) -> None:
    """'aktuell' auf eine Freigabe zeigen lassen — in einem Schritt.

    Erst einen Symlink unter Hilfsnamen anlegen, dann os.replace(). Ein
    Symlink, der auf os.replace() trifft, wird ersetzt, nicht verfolgt; ein
    Zwischenzustand ohne 'aktuell' entsteht nicht."""
    # Guertel neben dem Hosentraeger: Das Ziel MUSS unterhalb der Freigaben
    # liegen. Geprueft wird auf den aufgeloesten Pfaden, nicht auf dem Text.
    if not ziel.resolve().is_relative_to(FREIGABEN.resolve()):
        raise ValueError(f"'{ziel}' liegt nicht unterhalb von {FREIGABEN}")
    hilfsname = AKTUELL.with_name("aktuell.neu")
    if hilfsname.is_symlink() or hilfsname.exists():
        hilfsname.unlink()
    hilfsname.symlink_to(ziel.relative_to(PROGRAMM_DIR), target_is_directory=True)
    os.replace(hilfsname, AKTUELL)
    vorlage_uebernehmen(ziel)


def vorlage_uebernehmen(programm: Path) -> bool:
    """Die Konfigurationsvorlage eines Programmstands in den Bestand legen.

    config.laden() ergaenzt fehlende Einstellungen aus CONFIG_DIR/app.example.json
    — also aus dem BESTAND, nicht aus der Freigabe. Im Freigabenbetrieb kam die
    neue Vorlage aber nur in die Freigabe; die im Bestand blieb fuer immer die
    aus der Umstellung. Eine Einstellung, die eine neue Version mitbringt,
    erreichte app.json deshalb nie, und der Code lief mit dem eingebauten
    Rueckfallwert, ohne dass es jemand sah.

    Auch beim Zuruecksetzen: Die Vorlage beschreibt den Code, der laufen wird.
    Eine aeltere Vorlage nimmt app.json nichts weg — laden() ergaenzt nur.

    Geschrieben wird unter Hilfsnamen und dann mit os.replace(): Wer die Datei
    gleichzeitig liest, bekommt die alte oder die neue, nie eine halbe. Die
    Vorlage bleibt fuer alle lesbar (0644) — sie enthaelt bewusst keine
    Geheimnisse, und config.ordner_absichern() nimmt sie genau deshalb aus.

    Ein Fehler hier bricht nichts ab: Die Aktualisierung selbst ist dann
    gelungen, nur die neuen Vorgabewerte fehlen. Das steht im Protokoll."""
    quelle_datei = programm / "config" / "app.example.json"
    if not quelle_datei.is_file():
        return False
    ziel = pfade.CONFIG_DIR / "app.example.json"
    hilfsdatei = None
    try:
        inhalt = quelle_datei.read_bytes()
        if ziel.is_file() and ziel.read_bytes() == inhalt:
            return False
        pfade.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, hilfsdatei = tempfile.mkstemp(dir=pfade.CONFIG_DIR, prefix=".app.example.",
                                          suffix=".neu")
        with os.fdopen(fd, "wb") as datei:
            datei.write(inhalt)
        os.chmod(hilfsdatei, 0o644)
        os.replace(hilfsdatei, ziel)
        hilfsdatei = None
    except OSError as e:
        log.warning("Konfigurationsvorlage nicht übernommen (%s): %s", ziel, e)
        return False
    finally:
        if hilfsdatei:
            try:
                os.unlink(hilfsdatei)
            except OSError:
                pass
    log.info("Konfigurationsvorlage aus %s übernommen", programm.name)
    return True


def _laufende_freigabe() -> Path | None:
    """Die Freigabe, aus der DIESER Prozess seinen Code geladen hat.

    Das ist nicht dasselbe wie das Ziel von 'aktuell'. Der Symlink wandert beim
    Einspielen und beim Zuruecksetzen sofort, der Prozess erst beim Neustart.
    BASE kommt aus pfade.PROGRAMM, also aus __file__ mit resolve() — dort steht
    der Pfad, von dem tatsaechlich importiert wurde."""
    try:
        laeuft = Path(BASE).resolve()
        if laeuft.is_relative_to(FREIGABEN.resolve()):
            return laeuft
    except OSError:
        pass
    return None


def aufraeumen(behalten: int = FREIGABEN_BEHALTEN) -> list[str]:
    """Alte Freigaben entfernen. Nie die, auf die 'aktuell' zeigt, und nie die,
    aus der der Dienst gerade laeuft.

    Der Zeitstempel ist kein Beweis: Nach einem Zuruecksetzen zeigt 'aktuell'
    auf eine aeltere Freigabe, und die zu loeschen hiesse, dem laufenden Dienst
    den Boden wegzuziehen.

    'aktuell' allein genuegt aber nicht. Vorher war nur das Ziel des Symlinks
    geschuetzt — und das ist nach einer Aktualisierung schon die NEUE Freigabe,
    waehrend der Prozess noch aus der alten laeuft. Drei Aktualisierungen ohne
    Neustart, oder ein Zuruecksetzen auf eine alte Freigabe mit anschliessendem
    Update, und der laufende Dienst verlor seine Vorlagen und SQL-Dateien unter
    sich. Die Seiten brachen erst beim naechsten Aufruf, nicht beim Loeschen."""
    entfernt: list[str] = []
    geschuetzt: set[Path] = set()
    if AKTUELL.is_symlink():
        geschuetzt.add(AKTUELL.resolve())
    laufend = _laufende_freigabe()
    if laufend:
        geschuetzt.add(laufend)
    if not os.access(FREIGABEN, os.W_OK | os.X_OK):
        return entfernt
    for alt in freigaben()[behalten:]:
        if alt.resolve() in geschuetzt:
            continue
        shutil.rmtree(alt, ignore_errors=True)
        entfernt.append(alt.name)
    return entfernt


def _freigabe_einspielen(quelle_verzeichnis: Path, sha: str,
                         datum: str = "") -> tuple[Path, list[str]]:
    """Eine neue Freigabe anlegen und einschalten. Gibt (Freigabe, entfernte)."""
    FREIGABEN.mkdir(parents=True, exist_ok=True)
    zeitstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"{zeitstempel}-{sha[:8]}"
    roh = FREIGABEN / (name + ".neu")
    if roh.exists():
        shutil.rmtree(roh)
    # Nur das Programm. validation/ und beilaeufig Angesammeltes bleiben, wo
    # sie sind — sie gehoeren zum Bestand.
    shutil.copytree(quelle_verzeichnis, roh,
                    ignore=shutil.ignore_patterns(*AUSNAHMEN))
    fertig = FREIGABEN / name
    if fertig.exists():
        shutil.rmtree(fertig)
    # Der Vermerk gehoert IN die Freigabe, bevor umgeschaltet wird: Danach ist
    # sie die Quelle der Wahrheit darueber, was laeuft.
    (roh / FREIGABE_STAND).write_text(json.dumps(
        {"sha": sha, "datum": datum, "eingespielt": store.jetzt()}, indent=2),
        encoding="utf-8")
    roh.rename(fertig)
    umschalten(fertig)
    return fertig, aufraeumen()


def _abhaengigkeiten_nachziehen(quelle_ordner: Path, sekunden: int = 600) -> str:
    """Neue Abhaengigkeiten in die venv holen. Leerer String heisst: in Ordnung.

    Laeuft VOR dem Umschalten. Scheitert es, wird NICHT umgeschaltet — der
    schlimmste Fall ist dann 'Aktualisierung abgebrochen, alte Fassung laeuft
    weiter', und genau dafuer gibt es das Verfahren."""
    neue = quelle_ordner / "requirements.txt"
    if not neue.exists():
        return ""
    vorher = _requirements_lesen()
    nachher = {z.split("#")[0].strip().lower()
               for z in neue.read_text(encoding="utf-8").splitlines()
               if z.split("#")[0].strip()}
    if not (nachher - vorher):
        return ""
    # pip als Modul DES LAUFENDEN Interpreters, nicht als Skript daneben.
    # sys.executable ist die venv, aus der der Dienst gestartet wurde (die Unit
    # ruft .venv/bin/python auf) — genau dorthin muessen die Pakete. Das
    # pip-Skript dagegen traegt in seiner ersten Zeile einen festen Pfad zum
    # Interpreter; wurde die venv je verschoben, installierte es woanders hin
    # oder gar nicht, ohne dass der Dienst davon etwas merkte.
    if importlib.util.find_spec("pip") is None:
        return (f"requirements.txt hat neue Einträge ({', '.join(sorted(nachher - vorher))}), "
                f"aber in der Umgebung {sys.executable} gibt es kein pip. Nicht umgeschaltet.")
    log.info("Neue Abhängigkeiten: %s — pip läuft in %s",
             ", ".join(sorted(nachher - vorher)), sys.executable)
    try:
        lauf = subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(neue)],
                              capture_output=True, text=True, timeout=sekunden)
    except (OSError, subprocess.SubprocessError) as e:
        return f"Abhängigkeiten liessen sich nicht nachziehen ({e}). Nicht umgeschaltet."
    if lauf.returncode != 0:
        letzte = (lauf.stderr or lauf.stdout or "").strip().splitlines()[-3:]
        return ("Abhängigkeiten liessen sich nicht nachziehen. Nicht umgeschaltet, "
                "die laufende Fassung bleibt. Meldung: " + " | ".join(letzte)[:400])
    log.info("Abhängigkeiten nachgezogen")
    return ""


def _ausgenommen(teile: tuple[str, ...]) -> bool:
    """Bleibt dieser Pfad beim Austausch unberuehrt?

    Gross- und Kleinschreibung zaehlt nicht: Unter Windows ist NSSM.EXE
    dieselbe laufende Datei wie nssm.exe. __pycache__ baut Python selbst neu
    auf; eine uebrig gebliebene .pyc ohne Quelldatei daneben laedt es nicht."""
    ausnahmen = {a.lower() for a in AUSNAHMEN}
    return any(t.lower() in ausnahmen or t == "__pycache__" for t in teile)


def _dateien(wurzel: Path, name: str) -> list[str]:
    """Alle Dateien eines Programmbereichs, relativ zu wurzel, ohne Ausnahmen."""
    pfad = wurzel / name
    if pfad.is_file() or pfad.is_symlink() and not pfad.is_dir():
        return [] if _ausgenommen(Path(name).parts) else [name]
    gefunden: list[str] = []
    for ordner, unterordner, dateien in os.walk(pfad):
        unterordner[:] = [u for u in unterordner if not _ausgenommen((u,))]
        for datei in dateien:
            rel = Path(ordner, datei).relative_to(wurzel)
            if not _ausgenommen(rel.parts):
                gefunden.append(rel.as_posix())
    return gefunden


def _austausch_an_ort(quelle_ordner: Path) -> tuple[list[str], str]:
    """Programmdateien an Ort und Stelle ersetzen — ganz oder gar nicht.
    Gibt (ersetzte Bereiche, Fehlermeldung) zurueck; leere Meldung heisst gelungen.

    Der Weg unter Windows, wo es keine Freigaben gibt. Vorher lief er Bereich
    fuer Bereich: rmtree, neu kopieren, naechster. Unter Windows scheiterte
    rmtree(install/) an der laufenden nssm.exe — nach app/, docs/ und sql/,
    vor beispiele/ und VERSION. Die Ausnahme ging als 500 an die Oberflaeche,
    der Stand war nicht vermerkt, und der naechste Versuch lief in dieselbe
    Wand. Zurueck blieb Code aus zwei Staenden.

    Jetzt in drei Schritten, von denen nur der mittlere etwas veraendert:
      1. Den neuen Stand VOLLSTAENDIG in ein Bereitstellungsverzeichnis neben
         dem Programm schreiben. Scheitert das, ist nichts angefasst.
      2. Datei fuer Datei: die alte beiseite schieben, die neue hineinschieben,
         jeden Schritt vermerken. Beide Verzeichnisse liegen unter BASE, also
         auf demselben Laufwerk — os.replace() ist dort ein Umbenennen, kein
         Kopieren, und kann nicht halb gelingen.
      3. Scheitert ein Schritt, laeuft der Vermerk rueckwaerts: neue Dateien
         weg, alte zurueck. Erst wenn alles durch ist, wird das Beiseite-
         geschobene geloescht.
    Ausnahmen (nssm.exe) kommen in keiner der Listen vor, werden also weder
    geloescht noch ersetzt noch verschoben."""
    bereit = BASE / ".aktualisierung.neu"
    beiseite = BASE / ".aktualisierung.alt"
    # Liegt hier noch Beiseitegeschobenes, ist ein frueherer Austausch hart
    # abgebrochen (Stromausfall, Prozess getoetet) oder sein Rueckweg
    # gescheitert. Darin koennen die einzigen Exemplare alter Dateien liegen.
    # Das ueberschreibt keine Automatik — das sieht sich ein Mensch an.
    if beiseite.exists():
        return [], (f"Keine Aktualisierung: {beiseite} liegt noch von einem abgebrochenen "
                    "Austausch da. Bitte pruefen, ob dort Programmdateien fehlen, und das "
                    "Verzeichnis danach loeschen. Es wurde NICHTS geaendert.")
    shutil.rmtree(bereit, ignore_errors=True)

    bereiche = [n for n in PROGRAMM + KONFIG_VORLAGEN if (quelle_ordner / n).exists()]
    neue: list[str] = []
    try:
        for name in bereiche:
            for rel in _dateien(quelle_ordner, name):
                ziel = bereit / rel
                ziel.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(quelle_ordner / rel, ziel)
                neue.append(rel)
    except OSError as e:
        shutil.rmtree(bereit, ignore_errors=True)
        return [], (f"Keine Aktualisierung: Der neue Stand liess sich nicht bereitstellen ({e}). "
                    "Es wurde NICHTS am Programm geaendert.")

    # Was im alten Stand liegt und im neuen nicht mehr, geht mit weg — sonst
    # bliebe ein entferntes Modul importierbar. Nur fuer Bereiche, die der
    # neue Stand mitbringt; aus config/ ausschliesslich die Vorlage.
    # normcase: Unter Windows ist 'Foo.py' im neuen Stand dieselbe Datei wie
    # 'foo.py' im alten; sie als "entfallen" zu fuehren, schoebe die gerade
    # eingesetzte neue Datei wieder beiseite.
    neu_schluessel = {os.path.normcase(r) for r in neue}
    entfallen = [rel for name in bereiche if name in PROGRAMM
                 for rel in _dateien(BASE, name)
                 if os.path.normcase(rel) not in neu_schluessel]

    vermerk: list[tuple[str, Path, Path | None]] = []
    angelegt: list[Path] = []

    def _ordner_fuer(pfad: Path) -> None:
        fehlend = []
        p = pfad.parent
        while not p.exists():
            fehlend.append(p)
            p = p.parent
        for ordner in reversed(fehlend):
            ordner.mkdir()
            angelegt.append(ordner)

    try:
        for rel, einsetzen in [(r, True) for r in neue] + [(r, False) for r in entfallen]:
            ziel = BASE / rel
            if ziel.exists() or ziel.is_symlink():
                weg = beiseite / rel
                weg.parent.mkdir(parents=True, exist_ok=True)
                os.replace(ziel, weg)
                vermerk.append(("beiseite", ziel, weg))
            if einsetzen:
                _ordner_fuer(ziel)
                os.replace(bereit / rel, ziel)
                vermerk.append(("neu", ziel, None))
    except OSError as e:
        rest: list[str] = []
        for art, ziel, weg in reversed(vermerk):
            try:
                if art == "neu":
                    ziel.unlink()
                else:
                    os.replace(weg, ziel)
            except OSError as e2:
                rest.append(f"{ziel} ({e2})")
        for ordner in reversed(angelegt):
            try:
                ordner.rmdir()
            except OSError:
                pass
        shutil.rmtree(bereit, ignore_errors=True)
        if rest:
            # Der Rueckweg selbst ist gescheitert. beiseite/ bleibt dann
            # stehen — dort liegen die alten Dateien, die nicht zurueckkamen.
            return [], (f"Aktualisierung abgebrochen ({e}), und der Rueckweg ist nur teilweise "
                        f"gelungen. Nicht zurueckgelegt: {'; '.join(rest)[:600]}. Die alten "
                        f"Dateien liegen unter {beiseite}. Den Dienst NICHT neu starten, bevor "
                        "das von Hand bereinigt ist.")
        shutil.rmtree(beiseite, ignore_errors=True)
        return [], (f"Aktualisierung abgebrochen ({e}). Alles wurde zurueckgerollt, die "
                    "laufende Fassung ist unveraendert.")

    shutil.rmtree(beiseite, ignore_errors=True)
    shutil.rmtree(bereit, ignore_errors=True)
    # Leere Verzeichnisse, die der neue Stand nicht mehr kennt. Nicht leere
    # bleiben — darin liegt dann etwas, das nicht vom Programm stammt.
    for name in bereiche:
        if not (BASE / name).is_dir():
            continue
        for ordner, _, _ in sorted(os.walk(BASE / name), key=lambda x: -len(x[0])):
            if not (quelle_ordner / Path(ordner).relative_to(BASE)).exists():
                try:
                    os.rmdir(ordner)
                except OSError:
                    pass
    return bereiche, ""


def anwenden(cfg: dict, benutzer: str = "system") -> str:
    """Spielt den aktuellen Stand ein. Gibt eine Meldung zurueck."""
    u = cfg.get("update") or {}
    pruefung = pruefen(cfg)
    if not pruefung.get("moeglich"):
        return pruefung.get("text", "Keine Aktualisierung möglich.")

    # Erst fragen, dann anfassen. Im Freigabenbetrieb wird nichts ersetzt,
    # sondern danebengelegt — dort muss nur das Freigabenverzeichnis
    # beschreibbar sein.
    fehlend = [] if freigabenbetrieb() else schreibrechte_pruefen()
    if freigabenbetrieb():
        eltern = FREIGABEN if FREIGABEN.exists() else PROGRAMM_DIR
        if not os.access(eltern, os.W_OK | os.X_OK):
            fehlend = [str(eltern)]
    if fehlend:
        wer = getpass.getuser()
        meldung = (f"Keine Aktualisierung: Der Dienst laeuft als '{wer}' und darf in "
                   + ", ".join(fehlend) + " nicht schreiben. Es wurde NICHTS geaendert. "
                   "Abhilfe auf dem Server: chown -R " + wer + " " + str(BASE)
                   + " (siehe docs/12_AKTUALISIERUNG.md).")
        store.protokoll("update", meldung, benutzer=benutzer, erfolg=False)
        log.error(meldung)
        return meldung

    repo, _, _ = quelle(cfg)
    sha, token = pruefung["sha"], (u.get("token") or "")
    vorher_requirements = _requirements_lesen()
    archiv_url = f"https://api.github.com/repos/{repo}/tarball/{sha}"
    zeitstempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    sicherung = pfade.DATEN_DIR / f"sicherung-{zeitstempel}"

    try:
        rohdaten = _anfrage(archiv_url, token, roh=True)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return "Herunterladen fehlgeschlagen: " + _fehlertext(e, repo, token)

    with tempfile.TemporaryDirectory() as ordner:
        tmp = Path(ordner)
        archiv = tmp / "stand.tar.gz"
        archiv.write_bytes(rohdaten)
        with tarfile.open(archiv, "r:gz") as t:
            # 'filter' gibt es erst ab Python 3.12 (und in neueren 3.11er-Ausgaben).
            # Ohne ihn bleibt das Auspacken ungefiltert — deshalb nur aus dem
            # eigenen Repository laden.
            try:
                t.extractall(tmp / "aus", filter="data")
            except TypeError:
                t.extractall(tmp / "aus")
        wurzeln = [p for p in (tmp / "aus").iterdir() if p.is_dir()]
        if not wurzeln:
            return "Das Archiv ist leer."
        quelle_ordner = wurzeln[0]

        if freigabenbetrieb():
            # Abhaengigkeiten VOR dem Umschalten. Im Freigabenbetrieb kostet
            # das keine Verfuegbarkeit — die alte Fassung laeuft weiter, bis
            # umgeschaltet wird. Und ein blosser Hinweis wird ueberlesen:
            # Dann schaltet die Aktualisierung auf eine Freigabe um, deren
            # Abhaengigkeiten fehlen, und der Dienst geht nach dem Umschalten
            # in die Neustartschleife. Genau davor soll das Verfahren schuetzen.
            fehlt = _abhaengigkeiten_nachziehen(quelle_ordner)
            if fehlt:
                store.protokoll("update", fehlt, benutzer=benutzer, erfolg=False)
                log.error(fehlt)
                return fehlt
            fertig, entfernt = _freigabe_einspielen(quelle_ordner, sha,
                                                    pruefung.get("datum", ""))
            nachzuziehen = _neue_abhaengigkeiten(vorher_requirements)
            STAND_DATEI.parent.mkdir(parents=True, exist_ok=True)
            STAND_DATEI.write_text(json.dumps(
                {"sha": sha, "datum": pruefung.get("datum"), "eingespielt": store.jetzt(),
                 "version": version(), "freigabe": fertig.name}, indent=2), encoding="utf-8")
            meldung = (f"Stand {pruefung['kurz']} eingespielt als Freigabe {fertig.name}. "
                       "Der Dienst muss neu starten; die vorige Freigabe bleibt stehen.")
            if entfernt:
                meldung += f" Aufgeräumt: {', '.join(entfernt)}."
            if nachzuziehen:
                meldung += (" ACHTUNG: requirements.txt hat sich geändert (" +
                            ", ".join(nachzuziehen) + "). Vor dem Neustart auf dem "
                            "Server '.venv/bin/pip install -r requirements.txt' "
                            "ausführen, sonst startet der Dienst nicht mehr.")
            store.protokoll("update", meldung, benutzer=benutzer)
            log.info(meldung)
            return meldung

        # Sichern ist Lesen: Scheitert es, ist noch nichts angefasst.
        try:
            sicherung.mkdir(parents=True, exist_ok=True)
            # Eigene Konfiguration vor dem Austausch sichern — sie wird zwar
            # nicht angefasst, aber eine Kopie kostet nichts.
            from . import config as _config
            kopie = _config.sichern()
            if kopie:
                shutil.copy2(kopie, sicherung / kopie.name)
            for name in PROGRAMM + KONFIG_VORLAGEN:
                alt_pfad = BASE / name
                if not (quelle_ordner / name).exists() or not alt_pfad.exists():
                    continue
                if alt_pfad.is_dir():
                    shutil.copytree(alt_pfad, sicherung / name, dirs_exist_ok=True)
                else:
                    (sicherung / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(alt_pfad, sicherung / name)
        except OSError as e:
            meldung = (f"Keine Aktualisierung: Die Sicherung nach {sicherung} ist gescheitert "
                       f"({e}). Es wurde NICHTS am Programm geaendert.")
            store.protokoll("update", meldung, benutzer=benutzer, erfolg=False)
            log.error(meldung)
            return meldung

        ersetzt, fehler = _austausch_an_ort(quelle_ordner)
        if fehler:
            store.protokoll("update", fehler, benutzer=benutzer, erfolg=False)
            log.error(fehler)
            return fehler
        # Weicht CONFIG_DIR vom Programmverzeichnis ab, braucht die Vorlage
        # den zweiten Weg; sonst ist sie dieselbe Datei und hier nichts zu tun.
        vorlage_uebernehmen(BASE)

    # requirements.txt wird mit ersetzt, aber pip laeuft nicht nach. Kommt eine
    # Abhaengigkeit dazu, fehlt sie nach dem Neustart — und der Dienst bleibt
    # mit einem ImportError stehen, ohne dass jemand den Zusammenhang sieht.
    # Nachinstalliert wird hier NICHT: Das braucht Rechte auf die venv und kann
    # minutenlang dauern. Gesagt wird es aber.
    nachzuziehen = _neue_abhaengigkeiten(vorher_requirements)

    STAND_DATEI.parent.mkdir(parents=True, exist_ok=True)
    STAND_DATEI.write_text(json.dumps(
        {"sha": sha, "datum": pruefung.get("datum"), "eingespielt": store.jetzt(),
         "version": version(), "sicherung": str(sicherung)}, indent=2), encoding="utf-8")
    meldung = (f"Stand {pruefung['kurz']} eingespielt ({len(ersetzt)} Bereiche). "
               f"Sicherung unter {sicherung.name}. Der Dienst muss neu starten.")
    if nachzuziehen:
        meldung += (" ACHTUNG: requirements.txt hat sich geändert (" +
                    ", ".join(nachzuziehen) + "). Vor dem Neustart auf dem Server "
                    "'.venv/bin/pip install -r requirements.txt' ausführen, sonst "
                    "startet der Dienst mit einem ImportError nicht mehr.")
    store.protokoll("update", meldung, benutzer=benutzer)
    log.info(meldung)
    return meldung


def zuruecksetzen(name: str = "", benutzer: str = "system") -> str:
    """Auf eine frühere Freigabe zurückgehen. Ohne Namen: auf die, die
    unmittelbar VOR der steht, auf die 'aktuell' zeigt.

    Das ist der eigentliche Gewinn des Verfahrens. Sicherungen unter
    data/sicherung-* gab es schon vorher — aber kein Verfahren, sie
    zurückzuspielen."""
    if not freigabenbetrieb():
        return ("Diese Installation läuft ohne Freigabeverzeichnisse. "
                "Zurückgesetzt wird von Hand aus data/sicherung-*.")
    vorhanden = freigaben()
    if len(vorhanden) < 2 and not name:
        return "Es gibt keine frühere Freigabe, auf die zurückzugehen wäre."
    verlinkt = AKTUELL.resolve() if AKTUELL.is_symlink() else None
    if name:
        # Gegen die LISTE pruefen, nicht gegen das Dateisystem. Ein
        # Verzeichnisname kommt aus einem Formular; 'ist ein Verzeichnis'
        # genuegt als Bedingung nicht, weil '../../data/boese' das auch
        # erfuellt — und data/ kann der Dienst selbst befuellen. Path.
        # relative_to() haette den Ausbruch nicht bemerkt: Es vergleicht
        # zeichenweise und liefert 'freigaben/../../data/boese' zurueck,
        # statt zu werfen. 'aktuell' haette dann auf selbst geschriebenen
        # Code gezeigt, neustartfest — genau das, was das Festnageln der
        # Quelle in der Unit verhindern soll.
        passend = [f for f in vorhanden if f.name == name]
        if not passend:
            return (f"Freigabe '{name}' gibt es nicht. Vorhanden: "
                    + ", ".join(f.name for f in vorhanden))
        ziel = passend[0]
    else:
        # "Zurueck" heisst: die naechstaeltere. Vorher war es "die neueste,
        # die nicht verlinkt ist" — stand 'aktuell' schon auf einer aelteren,
        # sprang der Knopf VORWAERTS, zurueck auf den Stand, von dem man
        # gerade weggegangen war. Die Liste ist nach Namen absteigend sortiert,
        # und der Name beginnt mit dem Zeitstempel.
        stelle = next((i for i, f in enumerate(vorhanden)
                       if verlinkt and f.resolve() == verlinkt), None)
        if stelle is None:
            return ("'aktuell' zeigt auf keine der vorhandenen Freigaben — bitte die "
                    "Freigabe namentlich auswählen. Vorhanden: "
                    + ", ".join(f.name for f in vorhanden))
        if stelle + 1 >= len(vorhanden):
            return (f"Es gibt keine frühere Freigabe als {vorhanden[stelle].name}, "
                    "auf die zurückzugehen wäre.")
        ziel = vorhanden[stelle + 1]
    umschalten(ziel)
    meldung = (f"Zurückgesetzt auf Freigabe {ziel.name}. "
               "Der Dienst muss neu starten.")
    store.protokoll("update", meldung, benutzer=benutzer)
    log.warning(meldung)
    return meldung


NEUSTART_FRIST = 120      # Sekunden, die ein laufender Automatiklauf bekommt
_NEUSTART_TAKT = 1.0      # wie oft nachgesehen wird


def _automatik_laeuft() -> bool:
    """Arbeitet gerade ein Automatiklauf? Im Zweifel: nein.

    Lokal importiert und ueber getattr: automatik.laeuft_gerade() kam spaeter
    dazu als dieser Aufruf. Fehlt die Funktion oder wirft sie, darf das den
    Neustart nicht verhindern — ein Dienst, der nach einer Aktualisierung
    nicht neu startet, ist der schlimmere Fehler."""
    try:
        from . import automatik
        pruefung = getattr(automatik, "laeuft_gerade", None)
        return bool(pruefung()) if callable(pruefung) else False
    except Exception:  # noqa: BLE001 — siehe oben
        return False


def neustart(frist: float | None = None) -> None:
    """Beendet den Prozess. Als Dienst startet ihn das System wieder — unter
    Windows NSSM, unter Linux systemd (Restart=always). Im Vordergrundbetrieb
    muss run.cmd bzw. run.sh erneut aufgerufen werden.

    os._exit fragt niemanden. Lief gerade ein Automatiklauf, riss es ihn mitten
    im Versand ab: Rechnung erzeugt, Mail vielleicht draussen, Vermerk nicht
    geschrieben — beim naechsten Lauf ginge sie ein zweites Mal hinaus. Deshalb
    wird erst gewartet, bis der Durchlauf fertig ist, hoechstens aber
    NEUSTART_FRIST Sekunden. Ein Lauf, der laenger haengt, haengt vermutlich
    wirklich; dann geht der Neustart vor, und das steht im Protokoll."""
    frist = NEUSTART_FRIST if frist is None else frist
    # Erst ansagen, dann warten: Sonst koennte waehrend der Wartezeit der
    # naechste Durchlauf beginnen und doch mitten im Versand abbrechen.
    try:
        from . import automatik
        ansage = getattr(automatik, "neustart_ankuendigen", None)
        if callable(ansage):
            ansage()
    except Exception:  # noqa: BLE001 — ein Neustart darf daran nicht scheitern
        log.exception("Neustart konnte der Automatik nicht angekuendigt werden")
    if _automatik_laeuft():
        log.warning("Neustart wartet: ein Automatiklauf arbeitet noch (höchstens %d s)", frist)
        store.protokoll("update", f"Neustart wartet auf laufenden Automatiklauf "
                                  f"(höchstens {frist:.0f} s)")
        ende = time.monotonic() + frist
        while _automatik_laeuft() and time.monotonic() < ende:
            time.sleep(_NEUSTART_TAKT)
        if _automatik_laeuft():
            log.error("Automatiklauf nach %d s nicht fertig — Neustart trotzdem", frist)
            store.protokoll("update", f"Automatiklauf nach {frist:.0f} s nicht fertig — "
                                      "Neustart trotzdem ausgelöst", erfolg=False)
        else:
            log.info("Automatiklauf beendet, Neustart folgt")
    store.protokoll("update", "Neustart ausgelöst")
    logging.shutdown()
    os._exit(0)


# --------------------------------------------------- Automatisch nachsehen
#
# update.automatisch_pruefen stand in der Konfiguration und wurde NIRGENDS
# gelesen. Wer es sah, nahm an, der Dienst melde sich, wenn etwas Neues
# bereitliegt — er tat es nicht. Genau dieser Fall trat ein: Vier Tage
# Arbeit lagen im Repository, und im Haus wusste es niemand.
#
# Eingespielt wird weiterhin NUR auf Knopfdruck. Hier wird ausschliesslich
# nachgesehen und das Ergebnis gemerkt; die Oberflaeche liest es aus dem
# Speicher, ohne selbst ins Netz zu gehen. Ein Seitenaufbau darf nicht an
# einer fremden Verbindung haengen.
_hinweis: dict = {}
_hinweis_zeit: float = 0.0
PRUEFABSTAND_STUNDEN = 6


def hinweis() -> dict:
    """Was beim letzten Nachsehen herauskam. Ohne Netzzugriff."""
    return dict(_hinweis)


def _nachsehen(cfg: dict) -> None:
    global _hinweis, _hinweis_zeit
    try:
        ergebnis = pruefen(cfg)
    except Exception as e:
        # Ein Netzfehler darf den Dienst nicht beruehren. Gemerkt wird er
        # trotzdem, sonst sucht jemand die Ursache im Falschen.
        log.warning("Automatische Update-Pruefung fehlgeschlagen: %s", e)
        _hinweis = {}
        _hinweis_zeit = time.time()
        return
    _hinweis = ergebnis if ergebnis.get("neuer") else {}
    _hinweis_zeit = time.time()
    if _hinweis:
        log.info("Neuer Stand verfuegbar: %s", ergebnis.get("text", ""))
        store.protokoll("update", "Neuer Stand verfügbar: " + ergebnis.get("text", ""))


async def wache() -> None:
    """Sieht in Abstaenden nach, ob ein neuerer Stand bereitliegt.

    Laeuft neben der Automatik und unabhaengig von ihr — ein Haus, das die
    Automatik ausgeschaltet hat, soll trotzdem erfahren, dass es eine neue
    Fassung gibt. Das Nachsehen selbst geht in einen Faden, weil es eine
    Netzverbindung aufbaut und die Schleife sonst blockierte."""
    while True:
        try:
            cfg = config.laden()
            u = cfg.get("update") or {}
            if u.get("aktiv") and u.get("automatisch_pruefen"):
                await asyncio.to_thread(_nachsehen, cfg)
            else:
                globals()["_hinweis"] = {}
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Update-Wache: unerwarteter Fehler")
        await asyncio.sleep(PRUEFABSTAND_STUNDEN * 3600)
