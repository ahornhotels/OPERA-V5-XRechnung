"""Oracle-Zugriff. Standard ist der Thin-Modus — dafuer wird KEIN Oracle-Client
gebraucht, weder unter Windows noch unter Linux. Das erspart auf beiden Systemen
die aufwendigste Einzelheit der Installation.

Thick-Modus ist zuschaltbar, falls die Datenbank aeltere Passwort-Verifier nutzt
(Fehler DPY-3015); dann wird ein Oracle-Client gebraucht."""
from __future__ import annotations
import logging
import oracledb

log = logging.getLogger(__name__)
_pool: oracledb.ConnectionPool | None = None
ABFRAGE_GRENZE_MS = 120_000
_thick = False


def start(cfg: dict) -> None:
    global _pool, _thick
    d = cfg["datenbank"]
    if d.get("thick_mode") and not _thick:
        oracledb.init_oracle_client(lib_dir=d.get("oracle_client_pfad") or None)
        _thick = True
    dsn = oracledb.makedsn(d["host"], int(d["port"]), service_name=d["service_name"])
    _pool = oracledb.create_pool(user=d["benutzer"], password=d["passwort"], dsn=dsn,
                                 min=1, max=4, increment=1, tcp_connect_timeout=15)
    log.info("Oracle-Pool aufgebaut (%s, %s-Modus)", dsn, "thick" if _thick else "thin")


def stop() -> None:
    global _pool
    if _pool:
        _pool.close(force=True)
        _pool = None


def pruefen(cfg: dict) -> str:
    """Verbindungstest. Gibt die Bannerzeile zurueck oder wirft."""
    if _pool is None:
        start(cfg)
    with _pool.acquire() as con:
        con.call_timeout = ABFRAGE_GRENZE_MS
        cur = con.cursor()
        cur.execute("SELECT banner FROM v$version WHERE ROWNUM = 1")
        return cur.fetchone()[0]


def bereit() -> bool:
    return _pool is not None


def sicherstellen() -> None:
    """Baut die Verbindung auf, falls sie noch nicht steht. Beim Start ist die
    Konfiguration oft noch leer; danach soll die Anwendung von selbst verbinden
    und nicht darauf warten, dass jemand 'Datenbank testen' drueckt."""
    if _pool is not None:
        return
    from . import config
    try:
        start(config.laden())
    except Exception as e:
        raise RuntimeError(
            f"Keine Datenbankverbindung: {e}. Zugangsdaten unter Konfiguration "
            "pruefen und dort 'Datenbank testen' druecken.") from e


def abfrage(sql: str, params: dict | None = None) -> list[dict]:
    """Fuehrt ein SELECT aus und liefert Dicts mit kleingeschriebenen Schluesseln.
    Es werden ausschliesslich SELECTs abgesetzt — die App schreibt nie in OPERA."""
    sicherstellen()
    with _pool.acquire() as con:
        # Ohne Grenze haengt eine Abfrage, die in OPERA nicht zurueckkommt
        # (Sperre, Netz weg ohne Abbruch), den aufrufenden Thread auf
        # unbestimmte Zeit auf — und damit einen Automatiklauf oder eine Seite.
        con.call_timeout = ABFRAGE_GRENZE_MS
        cur = con.cursor()
        cur.execute(sql, params or {})
        if cur.description is None:
            return []
        spalten = [c[0].lower() for c in cur.description]
        zeilen = []
        for row in cur.fetchall():
            eintrag = {}
            for name, wert in zip(spalten, row):
                if hasattr(wert, "read"):
                    wert = wert.read()
                eintrag[name] = wert
            zeilen.append(eintrag)
        return zeilen
