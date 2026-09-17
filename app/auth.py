"""Anmeldung und Sitzungen. Bewusst klein gehalten und ohne Fremdbibliothek:
Passwoerter als scrypt-Hash (Standardbibliothek), Sitzungen serverseitig,
Bremse gegen Rateversuche."""
from __future__ import annotations
import hashlib
import ipaddress
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import config, store

# Benutzerdatei im selben Ordner wie die Konfiguration — damit ein umgelenkter
# Ordner (Selbsttest, zweite Instanz) auch die Anmeldedaten mitnimmt und nicht
# die echten Konten des Betriebs beschreibt.
USER_DATEI = config.CONFIG_DIR / "users.json"
SITZUNG_STUNDEN = 8
MAX_FEHLVERSUCHE = 5

_fehlversuche: dict[str, list[float]] = {}


def _hash(passwort: str, salz: bytes) -> str:
    roh = hashlib.scrypt(passwort.encode(), salt=salz, n=2**14, r=8, p=1, dklen=32)
    return salz.hex() + ":" + roh.hex()


def _pruefen(passwort: str, gespeichert: str) -> bool:
    try:
        salz_hex, _ = gespeichert.split(":", 1)
    except ValueError:
        return False
    return secrets.compare_digest(_hash(passwort, bytes.fromhex(salz_hex)), gespeichert)


def benutzer_laden() -> dict:
    if not USER_DATEI.exists():
        # Erststart: Standardbenutzer anlegen und Passwort in die Datei schreiben
        start_passwort = secrets.token_urlsafe(12)
        anlegen("admin", start_passwort, "verwalten")
        erst = config.CONFIG_DIR / "ERSTES_PASSWORT.txt"
        erst.write_text(
            f"Benutzer: admin\nPasswort: {start_passwort}\n"
            f"Bitte nach der ersten Anmeldung aendern und diese Datei loeschen.\n",
            encoding="utf-8")
        # Sie traegt ein gueltiges Passwort im Klartext.
        try:
            os.chmod(erst, 0o600)
        except OSError:
            pass
    # Auch bei einer vorhandenen Datei: Wer frueher installiert hat, hat sie
    # mit der Standardmaske angelegt — und dann liegen die Passwort-Hashes
    # offen.
    try:
        os.chmod(USER_DATEI, 0o600)
    except OSError:
        pass
    return json.loads(USER_DATEI.read_text(encoding="utf-8"))


def anlegen(benutzer: str, passwort: str, rolle: str = "ansehen") -> None:
    """Zugang anlegen oder ersetzen. Laufende Sitzungen des Namens enden:
    Sie tragen die ALTE Rolle und gehoerten womoeglich jemand anderem."""
    daten = {}
    if USER_DATEI.exists():
        daten = json.loads(USER_DATEI.read_text(encoding="utf-8"))
    daten[benutzer] = {"hash": _hash(passwort, os.urandom(16)), "rolle": rolle}
    USER_DATEI.parent.mkdir(parents=True, exist_ok=True)
    _speichern(daten)
    sitzungen_beenden(benutzer)


def neu_anlegen(benutzer: str, passwort: str, rolle: str) -> str | None:
    """Fuer die Oberflaeche: legt nur NEUE Zugaenge an. Gibt eine
    Fehlermeldung zurueck oder None. Vorher ersetzte "Zugang anlegen" mit einem
    vorhandenen Namen kommentarlos Passwort und Rolle."""
    benutzer = (benutzer or "").strip()
    if not benutzer:
        return "Bitte einen Benutzernamen angeben."
    if USER_DATEI.exists() and benutzer in json.loads(USER_DATEI.read_text(encoding="utf-8")):
        return f"Den Zugang „{benutzer}“ gibt es schon. Erst löschen, dann neu anlegen."
    anlegen(benutzer, passwort, rolle)
    return None


def sitzungen_beenden(benutzer: str) -> None:
    with store.verbindung() as con:
        con.execute("DELETE FROM sitzungen WHERE benutzer = ?", (benutzer,))


def _speichern(daten: dict) -> None:
    """Zugaenge schreiben. Scheitert das an den Rechten, sagt die Meldung,
    woran es liegt — ein stiller Fehlschlag waere hier besonders unangenehm,
    weil der Anwender sein neues Passwort fuer gesetzt haelt."""
    from . import config
    try:
        # Ueber eine temporaere Datei und Umbenennen: Ein Abbruch mitten im
        # Schreiben liess sonst eine halbe Benutzerdatei zurueck — und niemand
        # koennte sich mehr anmelden.
        config._schreiben(USER_DATEI, json.dumps(daten, indent=2))
        # Die Datei traegt die Passwort-Hashes aller Zugaenge. Sie lag mit der
        # Standardmaske auf der Platte und war damit fuer jeden lesbar, der auf
        # den Rechner kommt.
        try:
            os.chmod(USER_DATEI, 0o600)
        except OSError:
            pass
    except config.KonfigFehler:
        raise
    except OSError as e:
        moeglich, grund = config.schreibbar()
        raise config.KonfigFehler(grund if not moeglich
                                  else f"{USER_DATEI} liess sich nicht schreiben: {e}") from e


def loeschen(benutzer: str) -> str | None:
    """Zugang loeschen. Gibt eine Fehlermeldung zurueck oder None.

    Die Sitzungen enden sofort. Vorher behielt ein geloeschter Verwalter bis zu
    acht Stunden alle Rechte — auch ueber einen Neustart hinweg — und konnte
    sich ueber "Zugang anlegen" selbst wieder anlegen."""
    daten = json.loads(USER_DATEI.read_text(encoding="utf-8"))
    if benutzer not in daten:
        return None
    verwalter = [n for n, d in daten.items() if d.get("rolle") == "verwalten"]
    if daten[benutzer].get("rolle") == "verwalten" and len(verwalter) <= 1:
        return "Das ist der letzte Zugang mit Verwaltungsrecht — ohne ihn ließe sich nichts mehr einstellen."
    daten.pop(benutzer, None)
    _speichern(daten)
    sitzungen_beenden(benutzer)
    return None


def passwort_aendern(benutzer: str, alt: str, neu: str) -> str | None:
    """Aendert das eigene Passwort. Gibt eine Fehlermeldung zurueck oder None."""
    daten = json.loads(USER_DATEI.read_text(encoding="utf-8"))
    eintrag = daten.get(benutzer)
    if not eintrag or not _pruefen(alt, eintrag["hash"]):
        return "Das bisherige Passwort stimmt nicht."
    if len(neu) < 10:
        return "Das neue Passwort muss mindestens 10 Zeichen haben."
    eintrag["hash"] = _hash(neu, os.urandom(16))
    from . import config
    try:
        _speichern(daten)
    except config.KonfigFehler as e:
        return str(e)
    # Nach der Aenderung alle Sitzungen dieses Benutzers beenden
    with store.verbindung() as con:
        con.execute("DELETE FROM sitzungen WHERE benutzer = ?", (benutzer,))
    store.protokoll("passwort", "geaendert", benutzer=benutzer)
    erst = config.CONFIG_DIR / "ERSTES_PASSWORT.txt"
    if erst.exists():
        erst.unlink()   # Startpasswort ist jetzt wertlos — Datei weg
    return None


def gesperrt(schluessel: str) -> int:
    """Verbleibende Sperrzeit in Sekunden."""
    versuche = [t for t in _fehlversuche.get(schluessel, []) if time.time() - t < 900]
    _fehlversuche[schluessel] = versuche
    if len(versuche) < MAX_FEHLVERSUCHE:
        return 0
    wartezeit = min(60 * 2 ** (len(versuche) - MAX_FEHLVERSUCHE), 900)
    rest = int(versuche[-1] + wartezeit - time.time())
    return max(rest, 0)


def anmelden(benutzer: str, passwort: str, ip: str) -> str | None:
    schluessel = f"{benutzer}|{ip}"
    if gesperrt(schluessel):
        return None
    daten = benutzer_laden().get(benutzer)
    if not daten or not _pruefen(passwort, daten["hash"]):
        _fehlversuche.setdefault(schluessel, []).append(time.time())
        store.protokoll("anmeldung", f"fehlgeschlagen für '{benutzer}' von {ip}",
                        benutzer=benutzer, erfolg=False)
        return None
    _fehlversuche.pop(schluessel, None)
    token = secrets.token_urlsafe(32)
    ablauf = (datetime.now() + timedelta(hours=SITZUNG_STUNDEN)).isoformat(timespec="seconds")
    with store.verbindung() as con:
        con.execute("INSERT INTO sitzungen (token, benutzer, rolle, laeuft_ab) VALUES (?,?,?,?)",
                    (token, benutzer, daten.get("rolle", "ansehen"), ablauf))
    store.protokoll("anmeldung", f"'{benutzer}' von {ip}", benutzer=benutzer)
    return token


def sitzung(token: str | None) -> dict | None:
    if not token:
        return None
    with store.verbindung() as con:
        r = con.execute("SELECT * FROM sitzungen WHERE token = ?", (token,)).fetchone()
    if not r:
        return None
    if r["laeuft_ab"] < store.jetzt():
        abmelden(token)
        return None
    # Rolle und Existenz kommen aus der BENUTZERDATEI, nicht aus der Sitzung.
    # Die Sitzungszeile haelt den Stand der Anmeldung fest; wer inzwischen
    # geloescht oder herabgestuft wurde, hatte bis zum Ablauf die alten Rechte.
    try:
        eintrag = json.loads(USER_DATEI.read_text(encoding="utf-8")).get(r["benutzer"])
    except (OSError, ValueError):
        eintrag = None
    if not eintrag:
        abmelden(token)
        return None
    sitzung = dict(r)
    sitzung["rolle"] = eintrag.get("rolle", "ansehen")
    return sitzung


def abmelden(token: str) -> None:
    with store.verbindung() as con:
        con.execute("DELETE FROM sitzungen WHERE token = ?", (token,))


def netz_erlaubt(ip: str, netze: list[str]) -> bool:
    if not netze:
        return True
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for netz in netze:
        try:
            if adresse in ipaddress.ip_network(netz, strict=False):
                return True
        except ValueError:
            continue
    return False
