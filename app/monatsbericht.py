"""Monatlicher Statusbericht per Mail: wie viele XRechnungen im Vormonat
erstellt und wie viele versendet wurden, mit dem Namen des Hauses.

Gedacht fuer die Abrechnung des Betriebs: Ein fester Tag im Monat, an dem
eine kurze Aufstellung an eine oder mehrere Adressen geht. Berichtet wird
IMMER der vorhergehende Kalendermonat — am 3. Dezember also der November.

Gezaehlt wird aus der eigenen Arbeitsliste (data/status.sqlite), nicht aus
OPERA: Der Bericht soll auch dann stimmen, wenn die Datenbank gerade nicht
erreichbar ist, und er zaehlt, was DIESE Anwendung getan hat.

Der Bericht laeuft unabhaengig von der Automatik in einem eigenen Takt.
Ein Haus, das von Hand versendet, rechnet genauso ab.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import date, datetime, timedelta

from . import config, mailer, store

log = logging.getLogger(__name__)

AKTION = "monatsbericht"
# Wie oft nachgesehen wird, ob der Bericht faellig ist. Der Versand selbst
# geschieht einmal im Monat; der Takt bestimmt nur, wie bald nach dem
# Versandzeitpunkt (oder nach einem Neustart) er hinausgeht.
TAKT_SEKUNDEN = 30 * 60
# Hoechster waehlbarer Versandtag. Ab dem 29. gaebe es Monate ohne diesen Tag.
LETZTER_TAG = 28

_task: asyncio.Task | None = None


# ------------------------------------------------------------------ Zeitraum
def vormonat(heute: date | None = None) -> tuple[date, date]:
    """Erster und letzter Tag des Monats vor 'heute'."""
    heute = heute or date.today()
    erster_dieser = heute.replace(day=1)
    letzter = erster_dieser - timedelta(days=1)
    return letzter.replace(day=1), letzter


def monat_schluessel(erster: date) -> str:
    return erster.strftime("%Y-%m")


MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember")


def monat_text(erster: date) -> str:
    return f"{MONATE[erster.month - 1]} {erster.year}"


# ------------------------------------------------------------- Einstellungen
def einstellungen(cfg: dict) -> dict:
    b = dict(cfg.get("bericht") or {})
    try:
        tag = int(b.get("tag") or 1)
    except (TypeError, ValueError):
        tag = 1
    try:
        stunde = int(b.get("stunde") if b.get("stunde") not in (None, "") else 6)
    except (TypeError, ValueError):
        stunde = 6
    empfaenger = b.get("empfaenger") or []
    if isinstance(empfaenger, str):
        empfaenger = [t for t in empfaenger.replace(";", ",").split(",")]
    return {
        "aktiv": bool(b.get("aktiv")),
        "empfaenger": [str(a).strip() for a in empfaenger if str(a).strip()],
        "tag": min(max(tag, 1), LETZTER_TAG),
        "stunde": min(max(stunde, 0), 23),
        "betriebsname": str(b.get("betriebsname") or "").strip(),
    }


def pruefen(cfg: dict) -> list[str]:
    """Was an den Einstellungen nicht stimmt — fuer das Speichern der
    Konfiguration. Leer: in Ordnung."""
    b = cfg.get("bericht") or {}
    fehler: list[str] = []
    try:
        tag = int(b.get("tag") or 1)
        if not 1 <= tag <= LETZTER_TAG:
            fehler.append(f"Versandtag des Monatsberichts: 1 bis {LETZTER_TAG} — "
                          "ab dem 29. gäbe es Monate ohne diesen Tag")
    except (TypeError, ValueError):
        fehler.append("Versandtag des Monatsberichts ist keine Zahl")
    try:
        stunde = int(b.get("stunde") if b.get("stunde") not in (None, "") else 6)
        if not 0 <= stunde <= 23:
            fehler.append("Uhrzeit des Monatsberichts: volle Stunde von 0 bis 23")
    except (TypeError, ValueError):
        fehler.append("Uhrzeit des Monatsberichts ist keine Zahl")
    e = einstellungen(cfg)
    for adresse in e["empfaenger"]:
        if not mailer.adresse_gueltig(adresse):
            fehler.append(f"Empfänger des Monatsberichts: „{adresse}“ ist keine gültige Adresse")
    if e["aktiv"] and not e["empfaenger"]:
        fehler.append("Monatsbericht eingeschaltet, aber kein Empfänger eingetragen")
    return fehler


def betriebsname(cfg: dict) -> str:
    """Der Name im Bericht: eigens eingetragen, sonst der Name des Hauses aus
    der Konfiguration, sonst aus OPERA, sonst das Resortkuerzel."""
    eigen = einstellungen(cfg)["betriebsname"]
    if eigen:
        return eigen
    from . import opera
    p = cfg.get("property") or {}
    aus_opera = ""
    if not opera.eigener_hausname(p):
        try:
            from . import zahlungsanforderung
            aus_opera = str(zahlungsanforderung.haus(cfg).get("suppliername") or "").strip()
        except Exception as e:      # Datenbank nicht erreichbar: kein Grund, nicht zu berichten
            log.info("Hotelname aus OPERA fuer den Monatsbericht nicht lesbar: %s", e)
    return opera.hausname(p, aus_opera) or str(p.get("resort") or "")


# ------------------------------------------------------------------- Zahlen
def zahlen(von: date, bis: date) -> dict:
    """Die Zahlen fuer den Zeitraum von..bis (beide einschliesslich).

    erstellt   Rechnungen, zu denen im Zeitraum eine XRechnung abgelegt wurde
               (Protokoll 'xml_erzeugt', aeltere Staende 'geprueft') oder die
               im Zeitraum versendet wurden — jede Rechnung einmal, auch wenn
               ihr XML mehrmals erzeugt wurde.
    versendet  Rechnungen mit Versanddatum im Zeitraum.
    storno     Stornorechnungen, die im Zeitraum versendet wurden.
    """
    a, b = von.isoformat(), (bis + timedelta(days=1)).isoformat()
    with store.verbindung() as con:
        versendet = con.execute(
            "SELECT COUNT(*) FROM rechnungen WHERE status = 'gesendet' "
            "AND gesendet_am >= ? AND gesendet_am < ?", (a, b)).fetchone()[0]
        automatisch = con.execute(
            "SELECT COUNT(DISTINCT bill_no) FROM protokoll WHERE aktion = 'versand' "
            "AND erfolg = 1 AND benutzer IN ('automatik', 'system') AND text LIKE 'XRechnung%' "
            "AND zeit >= ? AND zeit < ? AND bill_no IN (SELECT bill_no FROM rechnungen "
            "WHERE status = 'gesendet' AND gesendet_am >= ? AND gesendet_am < ?)",
            (a, b, a, b)).fetchone()[0]
        erstellt = con.execute(
            "SELECT COUNT(*) FROM ("
            " SELECT bill_no FROM protokoll WHERE aktion IN ('xml_erzeugt', 'geprueft')"
            "   AND bill_no IS NOT NULL AND zeit >= ? AND zeit < ?"
            " UNION"
            " SELECT bill_no FROM rechnungen WHERE status = 'gesendet'"
            "   AND gesendet_am >= ? AND gesendet_am < ?)", (a, b, a, b)).fetchone()[0]
        eingelesen = con.execute(
            "SELECT COUNT(*) FROM rechnungen WHERE zuerst_gesehen >= ? AND zuerst_gesehen < ?",
            (a, b)).fetchone()[0]
        try:
            storno = con.execute(
                "SELECT COUNT(*) FROM rechnungen WHERE storno_versand = 'gesendet' "
                "AND storno_am >= ? AND storno_am < ?", (a, b)).fetchone()[0]
        except Exception:           # Spalte fehlt in sehr alten Bestaenden
            storno = 0
        # Rechnungen MIT Rechnungsdatum im Monat, die heute noch nicht beim
        # Kunden sind — ohne zurueckgelegte. Damit "erstellt" und "versendet"
        # nicht fuer vollstaendig gehalten werden, wenn noch etwas haengt.
        offen = con.execute(
            "SELECT COUNT(*) FROM rechnungen WHERE substr(issuedate, 1, 10) >= ? "
            "AND substr(issuedate, 1, 10) < ? AND status NOT IN ('gesendet', 'ignoriert')",
            (a, b)).fetchone()[0]
    return {"erstellt": erstellt, "versendet": versendet, "automatisch": automatisch,
            "von_hand": max(versendet - automatisch, 0), "storno": storno,
            "eingelesen": eingelesen, "offen": offen}


def _de(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def text(cfg: dict, von: date, bis: date, z: dict | None = None) -> tuple[str, str]:
    """(Betreff, Text) des Berichts."""
    z = z if z is not None else zahlen(von, bis)
    name = betriebsname(cfg)
    monat = monat_text(von)
    betreff = f"XRechnung Statusbericht {monat} – {name}"
    a = cfg.get("automatik") or {}
    zeilen = [
        "Statusbericht OPERA XRechnung",
        "",
        f"Betrieb:   {name}",
        f"Resort:    {(cfg.get('property') or {}).get('resort') or '-'}",
        f"Zeitraum:  {_de(von)} bis {_de(bis)} ({monat})",
        "",
        f"XRechnungen erstellt:           {z['erstellt']:>6}",
        f"XRechnungen versendet:          {z['versendet']:>6}",
        f"  davon automatisch:            {z['automatisch']:>6}",
        f"  davon von Hand:               {z['von_hand']:>6}",
        f"Stornorechnungen versendet:     {z['storno']:>6}",
        "",
        f"In die Arbeitsliste eingelesen: {z['eingelesen']:>6}",
        f"Aus dem Monat noch offen:       {z['offen']:>6}",
        "",
        "Erläuterung:",
        "- erstellt: Rechnungen, zu denen im Monat eine XRechnung erzeugt und",
        "  abgelegt wurde; jede Rechnung zählt einmal.",
        "- versendet: Rechnungen, deren XRechnung im Monat an den Kunden ging.",
        "- noch offen: Rechnungen mit Rechnungsdatum im Monat, die noch nicht",
        "  versendet sind (Prüfung, Fehler, bereit); zurückgelegte zählen nicht.",
    ]
    if a.get("testlauf"):
        zeilen += ["", "HINWEIS: Der Testlauf ist eingeschaltet — die Automatik prüft nur "
                   "und versendet nichts."]
    zeilen += ["", f"Erstellt am {datetime.now().strftime('%d.%m.%Y %H:%M')} von OPERA XRechnung."]
    return betreff, "\n".join(zeilen) + "\n"


# ------------------------------------------------------------------- Versand
def schon_gesendet(schluessel: str) -> bool:
    """Ging der Bericht fuer diesen Monat schon erfolgreich hinaus?"""
    with store.verbindung() as con:
        z = con.execute("SELECT 1 FROM protokoll WHERE aktion = ? AND erfolg = 1 "
                        "AND text LIKE ? LIMIT 1", (AKTION, f"{schluessel}:%")).fetchone()
    return bool(z)


def faellig(cfg: dict, jetzt: datetime | None = None) -> tuple[date, date] | None:
    """Der Zeitraum, fuer den jetzt ein Bericht hinausgehen soll, sonst None.

    Faellig ab dem eingestellten Tag und der Stunde, und dann bis zum
    Monatsende: Lief der Dienst am Versandtag nicht, geht der Bericht beim
    naechsten Takt hinterher, statt einen Monat auszufallen."""
    e = einstellungen(cfg)
    if not e["aktiv"] or not e["empfaenger"]:
        return None
    jetzt = jetzt or datetime.now()
    if (jetzt.day, jetzt.hour) < (e["tag"], e["stunde"]):
        return None
    von, bis = vormonat(jetzt.date())
    if schon_gesendet(monat_schluessel(von)):
        return None
    # Ging der letzte Versuch schief (Mailserver weg), nicht bei jedem Takt
    # erneut — sonst stuende das Protokoll voll. Einmal alle paar Stunden.
    if _zuletzt_gescheitert(monat_schluessel(von)):
        return None
    return von, bis


WIEDERHOLEN_STUNDEN = 6


def _zuletzt_gescheitert(schluessel: str) -> bool:
    # Gegen die echte Uhr: Das Protokoll traegt die echte Zeit.
    grenze = (datetime.now() - timedelta(hours=WIEDERHOLEN_STUNDEN)).isoformat(timespec="seconds")
    with store.verbindung() as con:
        z = con.execute("SELECT 1 FROM protokoll WHERE aktion = ? AND erfolg = 0 "
                        "AND text LIKE ? AND zeit >= ? LIMIT 1",
                        (AKTION, f"{schluessel}:%", grenze)).fetchone()
    return bool(z)


def senden(cfg: dict, von: date, bis: date, benutzer: str = "system",
           an: list[str] | None = None) -> list[str]:
    """Verschickt den Bericht an alle Empfaenger (oder an 'an'). Gibt die
    Adressen zurueck, an die er ging. Wirft mailer.MailFehler, wenn er an
    keine ging."""
    ziele = an if an is not None else einstellungen(cfg)["empfaenger"]
    if not ziele:
        raise mailer.MailFehler("Für den Monatsbericht ist kein Empfänger eingetragen.")
    z = zahlen(von, bis)
    betreff, inhalt = text(cfg, von, bis, z)
    schluessel = monat_schluessel(von)
    gegangen: list[str] = []
    fehler: list[str] = []
    for adresse in ziele:
        try:
            mailer.senden(cfg, an=adresse, bill_no=0, issuedate="", xml=None, xml_name="",
                          vorlage=(betreff, inhalt), ohne_bcc=True)
            gegangen.append(adresse)
        except mailer.MailFehler as e:
            fehler.append(f"{adresse}: {e}")
    zusammenfassung = (f"erstellt {z['erstellt']}, versendet {z['versendet']}, "
                       f"Storno {z['storno']}, offen {z['offen']}")
    # Erledigt ist der Monat, sobald der Bericht an MINDESTENS eine Adresse
    # ging. Sonst bekaemen die erreichten Adressen ihn bei jedem Takt erneut,
    # nur weil eine andere falsch ist; der Fehler steht im Protokoll. Der Text
    # beginnt mit dem Monat, daran erkennt schon_gesendet() ihn wieder. Ein
    # Probeversand von Hand an eine einzelne Adresse zaehlt nicht.
    erledigt = bool(gegangen) and an is None
    if gegangen:
        store.protokoll(AKTION if erledigt else "monatsbericht_probe",
                        f"{schluessel}: an {', '.join(gegangen)} ({zusammenfassung})",
                        benutzer=benutzer)
    if fehler:
        store.protokoll(AKTION, f"{schluessel}: fehlgeschlagen — {'; '.join(fehler)}",
                        benutzer=benutzer, erfolg=False)
        if not gegangen:
            raise mailer.MailFehler("; ".join(fehler))
    return gegangen


def pruefen_und_senden(cfg: dict | None = None, jetzt: datetime | None = None) -> bool:
    """Ein Takt: senden, falls faellig. True, wenn gesendet wurde."""
    cfg = cfg or config.laden()
    zeitraum = faellig(cfg, jetzt)
    if not zeitraum:
        return False
    try:
        senden(cfg, *zeitraum)
        return True
    except mailer.MailFehler as e:
        log.warning("Monatsbericht nicht versendet: %s", e)
        return False


async def _schleife() -> None:
    while True:
        try:
            await asyncio.to_thread(pruefen_und_senden)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Monatsbericht: Takt fehlgeschlagen")
        await asyncio.sleep(TAKT_SEKUNDEN)


def starten() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_schleife())


def stoppen() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
