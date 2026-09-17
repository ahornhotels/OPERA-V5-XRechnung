"""Automatikbetrieb: liest in festem Takt neue Rechnungen ein und verschickt
sie, sobald die eingestellte Wartezeit abgelaufen ist. Die Wartezeit ist das
Sicherheitsnetz — bis dahin kann jede Rechnung in der Oberflaeche geprueft,
umgeleitet oder zurueckgestellt werden."""
from __future__ import annotations
import asyncio
import logging
import threading

from . import ablauf, config, store

log = logging.getLogger(__name__)
_task: asyncio.Task | None = None
_letzter_lauf: str | None = None
# Gesetzt, solange ein Durchlauf arbeitet. Der Neustart nach einer
# Aktualisierung wartet darauf (app/updater.py) — sonst beendet er den Prozess
# mitten in einem Versand.
_laeuft = threading.Event()
# Nur ein Durchlauf zur Zeit. "Durchlauf starten" und der Takt liefen sonst
# nebeneinander: Zwei Laeufe lasen gleichzeitig ein, und der zuerst fertige
# loeschte die Flagge, waehrend der andere noch versendete — der Neustart nach
# einer Aktualisierung haette ihn dann mitten im Versand abgeschnitten.
_lauf_sperre = threading.Lock()
# Gesetzt, sobald ein Neustart ansteht. Der Updater wartet, bis ein laufender
# Durchlauf fertig ist — ohne diese Bremse koennte in genau dieser Wartezeit
# der naechste beginnen und dann doch mitten im Versand abgeschnitten werden.
_neustart_steht = threading.Event()


def laeuft_gerade() -> bool:
    return _laeuft.is_set()


def neustart_ankuendigen() -> None:
    """Ab jetzt keinen neuen Durchlauf mehr beginnen."""
    _neustart_steht.set()


def zustand() -> dict:
    cfg = config.laden()
    return {
        "aktiv": bool(cfg["automatik"].get("aktiv")),
        "laeuft": _task is not None and not _task.done(),
        "letzter_lauf": _letzter_lauf,
        "poll_minuten": cfg["automatik"].get("poll_minuten"),
        "wartezeit_minuten": cfg["automatik"].get("wartezeit_minuten"),
        "testlauf": bool(cfg["automatik"].get("testlauf")),
        # Arbeitet gerade ein Durchlauf? Die Oberflaeche zeigt es an und sperrt
        # so lange, was sonst mitten hineinliefe.
        "arbeitet": laeuft_gerade(),
        "neustart_steht": _neustart_steht.is_set(),
    }


def _durchlauf_sync() -> None:
    """Der eigentliche Durchlauf. Laeuft in einem eigenen Thread: Er spricht
    mit OPERA, dem Validator und dem Mailserver, und jede dieser Wartezeiten
    hielt vorher die einzige Ereignisschleife an — die Oberflaeche antwortete
    nicht, bis der Lauf durch war."""
    global _letzter_lauf
    if _neustart_steht.is_set():
        log.info("Durchlauf uebersprungen: ein Neustart steht an")
        return
    if not _lauf_sperre.acquire(blocking=False):
        log.info("Durchlauf uebersprungen: es laeuft bereits einer")
        return
    _laeuft.set()
    try:
        cfg = config.laden()
        a = cfg["automatik"]
        _letzter_lauf = store.jetzt()
        try:
            # Der Zeitraum aus der Konfiguration, nicht fest 30 Tage.
            ablauf.einlesen(cfg)
        except Exception as e:
            log.exception("Einlesen fehlgeschlagen")
            store.protokoll("automatik", f"Einlesen fehlgeschlagen: {e}", erfolg=False)
            return

        for satz in store.faellige(int(a.get("max_pro_lauf", 20)),
                                   city_ledger=bool(a.get("city_ledger_versenden")),
                                   testlauf=bool(a.get("testlauf"))):
            bill_no = satz["bill_no"]
            try:
                ergebnis = ablauf.versenden(cfg, bill_no, benutzer="automatik")
                log.info("Rechnung %s automatisch verarbeitet (%s)", bill_no, ergebnis)
            except ablauf.BereitsVersendet:
                continue
            except ablauf.Beschaeftigt as e:
                # Jemand versendet gerade von Hand. Das ist kein Fehler DES
                # BELEGS — er bleibt faellig und kommt im naechsten Takt dran.
                # Vorher setzte ihn der Sammelzweig auf 'fehler', und dorthin
                # sieht die Automatik nie wieder.
                log.info("Rechnung %s uebersprungen: %s", bill_no, e)
                store.protokoll("automatik", f"uebersprungen: {e}", bill_no=bill_no,
                                benutzer="automatik")
                break
            except Exception as e:
                # Den Status setzt ablauf.versenden selbst, mit den Gruenden, die
                # schon am Beleg stehen. Hier nur, falls es gar nicht so weit kam.
                aktuell = store.rechnung(bill_no) or {}
                if aktuell.get("status") not in ("fehler", "gesendet", "pruefung"):
                    store.setzen(bill_no, status="fehler", fehler=ablauf.hinweis_dazu(
                        aktuell.get("fehler"), str(e)[:500]))
                store.protokoll("automatik", f"Versand fehlgeschlagen: {e}",
                                bill_no=bill_no, benutzer="automatik", erfolg=False)
    finally:
        _laeuft.clear()
        _lauf_sperre.release()


async def _durchlauf() -> None:
    await asyncio.to_thread(_durchlauf_sync)


async def _schleife() -> None:
    log.info("Automatik gestartet")
    store.protokoll("automatik", "gestartet")
    try:
        while True:
            cfg = config.laden()
            try:
                if cfg["automatik"].get("aktiv"):
                    await _durchlauf()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Vorher beendete jeder unerwartete Fehler die Schleife still —
                # die Kopfzeile zeigte weiter "Automatik an", und nichts lief.
                log.exception("Automatiklauf fehlgeschlagen")
                store.protokoll("automatik", f"Durchlauf fehlgeschlagen: {e}", erfolg=False)
            try:
                takt = max(int(cfg["automatik"].get("poll_minuten", 15)), 1) * 60
            except (TypeError, ValueError):
                takt = 15 * 60
            await asyncio.sleep(takt)
    except asyncio.CancelledError:
        log.info("Automatik beendet")
        store.protokoll("automatik", "beendet")
        raise


def starten() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_schleife())


def stoppen() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None


async def einmal_jetzt() -> None:
    """Einen Durchlauf sofort anstossen — der Knopf 'Durchlauf starten'."""
    await _durchlauf()
