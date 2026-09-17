"""Konfiguration laden/speichern. Geheimnisse werden Fernet-verschluesselt."""
from __future__ import annotations
import json
import logging
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

from . import pfade

# Der Ordner laesst sich umlenken (siehe app/pfade.py). Das ist kein Komfort,
# sondern zweierlei Schutz: Der Selbsttest schrieb sonst in die echte
# Konfiguration des Rechners, und mit Freigabeverzeichnissen laege sie im
# Programmverzeichnis und waere bei der naechsten Aktualisierung weg.
BASE = pfade.PROGRAMM
CONFIG_DIR = pfade.CONFIG_DIR
CONFIG_FILE = CONFIG_DIR / "app.json"
KEY_FILE = CONFIG_DIR / "secret.key"

# Felder, die verschluesselt in der Datei stehen sollen
# Felder, die verschluesselt in der Datei stehen und in der Oberflaeche nie
# im Klartext erscheinen. Wer hier ein Feld vergisst, merkt es nicht: Der Wert
# funktioniert, er steht nur offen da.
GEHEIM = [("datenbank", "passwort"), ("mail", "passwort"), ("update", "token")]
PREFIX = "enc:"


def ordner_absichern() -> list[str]:
    """Alles in config/ auf 0600 ziehen. Gibt zurueck, was angefasst wurde.

    Nicht nur die drei bekannten Namen: Wer von Hand eine Sicherung daneben
    legt — app.json.vor_netzfreigabe und dergleichen —, erzeugt sie mit der
    Standardmaske. Die naechste koennte Zugangsdaten enthalten, und dann liegt
    der Schluessel zwar geschuetzt, die Kopie daneben aber offen.

    Die Vorlage bleibt ausgenommen: Sie enthaelt bewusst keine Geheimnisse und
    wird beim Einrichten gelesen."""
    angefasst: list[str] = []
    if not CONFIG_DIR.is_dir():
        return angefasst
    for datei in sorted(CONFIG_DIR.iterdir()):
        if not datei.is_file() or datei.name == "app.example.json":
            continue
        try:
            if os.stat(datei).st_mode & 0o077:
                os.chmod(datei, 0o600)
                angefasst.append(datei.name)
        except OSError:
            continue
    return angefasst


def _nur_eigner(datei: Path) -> None:
    """Rechte auf 0600 setzen, wo das Betriebssystem es kennt.

    Wird auch beim Laden aufgerufen: Eine Datei, die frueher offen angelegt
    wurde, bleibt sonst offen. Unter Windows tut chmod hier nichts — dort
    haengt der Schutz an den Ordnerrechten."""
    try:
        os.chmod(datei, 0o600)
    except OSError:
        pass


class KonfigFehler(Exception):
    """Die Konfiguration liess sich nicht schreiben. Traegt eine Meldung, die
    dem Anwender sagt, was zu tun ist — nicht nur, dass etwas schiefging."""


def schreibbar() -> tuple[bool, str]:
    """Kann die Anwendung ihre Konfiguration ueberhaupt speichern?
    Wird auf der Konfigurationsseite angezeigt, BEVOR jemand ein langes
    Formular ausfuellt und die Eingaben verliert.

    Massgeblich ist das VERZEICHNIS, nicht die Datei: Geschrieben wird ueber
    eine temporaere Datei, die anschliessend umbenannt wird — und Umbenennen
    haengt an den Rechten des Verzeichnisses. Eine schreibgeschuetzte
    app.json in einem beschreibbaren Verzeichnis laesst sich damit sehr wohl
    ersetzen."""
    if os.access(CONFIG_DIR, os.W_OK):
        return True, ""
    ziel = CONFIG_DIR
    try:
        eigner = ziel.owner()
    except (KeyError, OSError, NotImplementedError):
        eigner = "unbekannt"
    laeuft_als = "unbekannt"
    try:
        import pwd
        laeuft_als = pwd.getpwuid(os.geteuid()).pw_name
    except (ImportError, KeyError):
        pass
    return False, (f"{ziel} gehört '{eigner}', die Anwendung laeuft als "
                   f"'{laeuft_als}' und darf nicht schreiben. Unter Linux behebt das: "
                   f"sudo chown -R {laeuft_als}:{laeuft_als} {CONFIG_DIR}")


def _schreiben(pfad: Path, inhalt: str) -> None:
    """Schreibt ueber eine temporaere Datei und benennt um. Ein Absturz
    mitten im Schreiben laesst so keine halbe Konfiguration zurueck —
    die Anwendung startet sonst nicht mehr."""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(pfad.parent),
                                         prefix=pfad.name + ".", suffix=".neu",
                                         delete=False) as f:
            f.write(inhalt)
            f.flush()
            os.fsync(f.fileno())
            temp = Path(f.name)
        os.replace(temp, pfad)
    except OSError as e:
        moeglich, grund = schreibbar()
        if not moeglich:
            raise KonfigFehler(grund) from e
        raise KonfigFehler(f"{pfad} liess sich nicht schreiben: {e}") from e


def _key() -> bytes:
    if not KEY_FILE.exists():
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(Fernet.generate_key())
        # Der Schluessel entschluesselt die Zugangsdaten zu OPERA und zum
        # Mailserver. Er lag mit der Standardmaske auf der Platte, also
        # weltweit lesbar — geschuetzt nur durch 'chmod 700' auf den Ordner,
        # das genau ein Zweig genau eines Installationsskripts setzt.
    # Auch bei einer vorhandenen Datei: Wer frueher installiert hat, hat sie
    # mit der Standardmaske angelegt.
    _nur_eigner(KEY_FILE)
    return KEY_FILE.read_bytes()


def _entschluesseln(wert: str) -> str:
    if not isinstance(wert, str) or not wert.startswith(PREFIX):
        return wert
    try:
        return Fernet(_key()).decrypt(wert[len(PREFIX):].encode()).decode()
    except (InvalidToken, ValueError):
        return ""


def _verschluesseln(wert: str) -> str:
    if not wert or wert.startswith(PREFIX):
        return wert
    return PREFIX + Fernet(_key()).encrypt(wert.encode()).decode()


def _ergaenzen(vorgabe: dict, eigen: dict) -> tuple[dict, list[str]]:
    """Fuegt fehlende Schluessel aus der Vorlage hinzu. Eigene Werte gewinnen
    IMMER — auch wenn sie leer sind oder anders lauten als die Vorgabe.

    Das ist der Kern der Update-Sicherheit: Eine Aktualisierung bringt neue
    Einstellungen mit, ohne eine einzige bestehende zu ueberschreiben."""
    aus = dict(eigen)
    neu: list[str] = []
    for schluessel, wert in vorgabe.items():
        if schluessel not in aus:
            aus[schluessel] = wert
            neu.append(schluessel)
        elif isinstance(wert, dict) and isinstance(aus[schluessel], dict):
            aus[schluessel], tiefer = _ergaenzen(wert, aus[schluessel])
            neu += [f"{schluessel}.{k}" for k in tiefer]
    return aus, neu


_zwischenspeicher: dict = {"schluessel": None, "cfg": None}


def _stand() -> tuple:
    """Woran sich erkennen laesst, dass sich eine der beiden Dateien geaendert
    hat. Auch die Groesse, weil zwei Schreibvorgaenge in derselben Sekunde auf
    manchen Dateisystemen dieselbe Zeit tragen."""
    aus = []
    for datei in (CONFIG_FILE, CONFIG_DIR / "app.example.json"):
        try:
            s = datei.stat()
            aus.append((str(datei), s.st_mtime_ns, s.st_size))
        except OSError:
            aus.append((str(datei), None, None))
    return tuple(aus)


def laden() -> dict:
    """Liest die Konfiguration — aus dem Zwischenspeicher, solange sich die
    Dateien nicht geaendert haben. Jede Anfrage las und entschluesselte sie
    vorher neu, die Kopfzeile allein zweimal.

    Zurueck kommt immer eine eigene Kopie: Aufrufer veraendern das Ergebnis
    (etwa beim Speichern), und das darf nicht in den Zwischenspeicher
    durchschlagen."""
    schluessel = _stand()
    if schluessel == _zwischenspeicher["schluessel"] and _zwischenspeicher["cfg"] is not None:
        return json.loads(json.dumps(_zwischenspeicher["cfg"]))
    cfg = _laden_von_platte()
    _zwischenspeicher.update(schluessel=_stand(), cfg=json.loads(json.dumps(cfg)))
    return cfg


def _laden_von_platte() -> dict:
    """Liest die Konfiguration. Fehlende Schluessel werden aus der Vorlage
    ergaenzt, Klartext-Passwoerter einmalig verschluesselt zurueckgeschrieben.

    Die eigene Konfiguration wird bei einer Aktualisierung NIE ersetzt — nur
    um neu hinzugekommene Einstellungen erweitert."""
    vorlage_datei = CONFIG_DIR / "app.example.json"
    if not CONFIG_FILE.exists():
        CONFIG_FILE.write_text(vorlage_datei.read_text(encoding="utf-8"), encoding="utf-8")
    roh = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    muss_speichern = False

    if vorlage_datei.exists():
        try:
            vorgabe = json.loads(vorlage_datei.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            vorgabe = {}
        roh, dazugekommen = _ergaenzen(vorgabe, roh)
        if dazugekommen:
            muss_speichern = True
            logging.getLogger(__name__).info(
                "Neue Einstellungen aus der Vorlage ergänzt: %s", ", ".join(dazugekommen))
    for sektion, feld in GEHEIM:
        wert = (roh.get(sektion) or {}).get(feld) or ""
        if wert and not wert.startswith(PREFIX):
            roh[sektion][feld] = _verschluesseln(wert)
            muss_speichern = True
    if muss_speichern:
        try:
            _schreiben(CONFIG_FILE, json.dumps(roh, indent=2, ensure_ascii=False))
        except KonfigFehler as e:
            # Beim Laden ist das kein Grund abzubrechen — die ergaenzten
            # Vorgaben gelten fuer diesen Lauf, sie sind nur nicht dauerhaft.
            logging.getLogger(__name__).warning("Konfiguration nicht schreibbar: %s", e)
    # Fuer die Laufzeit entschluesseln
    cfg = json.loads(json.dumps(roh))
    for sektion, feld in GEHEIM:
        if sektion in cfg and feld in cfg[sektion]:
            cfg[sektion][feld] = _entschluesseln(cfg[sektion][feld])
    return cfg


def sichern() -> Path | None:
    """Legt eine datierte Kopie der Konfiguration an. Wird vor jeder
    Aktualisierung aufgerufen — der Guertel zum Hosentraeger."""
    if not CONFIG_FILE.exists():
        return None
    ziel = CONFIG_DIR / f"app.json.{datetime.now():%Y%m%d-%H%M%S}.sicherung"
    shutil.copy2(CONFIG_FILE, ziel)
    return ziel


def speichern(neu: dict) -> None:
    """Schreibt die Konfiguration zurueck; Passwoerter werden verschluesselt.
    Ein leeres Passwortfeld laesst den bisherigen Wert stehen."""
    alt = json.loads(CONFIG_FILE.read_text(encoding="utf-8")) if CONFIG_FILE.exists() else {}
    for sektion, feld in GEHEIM:
        wert = (neu.get(sektion) or {}).get(feld)
        if not wert:
            neu.setdefault(sektion, {})[feld] = (alt.get(sektion) or {}).get(feld, "")
        else:
            neu[sektion][feld] = _verschluesseln(wert)
    _schreiben(CONFIG_FILE, json.dumps(neu, indent=2, ensure_ascii=False))
    _zwischenspeicher.update(schluessel=None, cfg=None)


def oeffentlich(cfg: dict) -> dict:
    """Kopie ohne Geheimnisse — fuer die Anzeige in der Oberflaeche.
    Passwoerter erscheinen nur als 'gesetzt' oder 'nicht gesetzt'."""
    aus = json.loads(json.dumps(cfg))
    for sektion, feld in GEHEIM:
        if sektion in aus and feld in aus[sektion]:
            aus[sektion][feld] = "gesetzt" if aus[sektion][feld] else ""
    return aus
