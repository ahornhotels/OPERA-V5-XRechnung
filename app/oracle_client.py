"""Oracle-Client fuer den Thick-Modus finden oder laden (Fehler DPY-3015).

DPY-3015 heisst: Das Passwort des Datenbankbenutzers liegt in OPERA noch im
alten 10g-Verfahren. Der Thin-Modus (ohne Client) kennt es nicht; mit einem
Oracle-Client geht es. Vorher musste das Haus den Client selbst besorgen,
entpacken, den Pfad eintragen und neu starten — und lag dabei oft daneben:
Der Client, der fuer OPERA auf dem Rechner liegt, ist meist 32 Bit, und ohne
Visual-C++-Laufzeit startet auch ein 64-Bit-Client nicht.

Ablauf von einrichten():
  1. Vorhandene Clients suchen, nur 64 Bit (am Dateikopf der DLL erkannt).
  2. Unter Windows die Visual-C++-Laufzeit pruefen, bei Bedarf installieren
     (Microsoft, Signatur geprueft).
  3. Jeden Kandidaten mit einer echten Anmeldung probieren — in einem
     eigenen Prozess: init_oracle_client geht je Prozess nur einmal und laesst
     sich nicht zuruecknehmen. Ein falscher Versuch im Dienst selbst haette ihn
     bis zum Neustart festgelegt.
  4. Hilft keiner: unter Windows den Instant Client "Basic Light" (64 Bit) von
     oracle.com nach BASIS/oracle laden (Signatur geprueft) und probieren.
     Unter Linux wird nichts geladen, dort sagt die Meldung, was zu tun ist.

Gespeichert wird hier nichts. Das tut die aufrufende Route erst, wenn die
Probe geklappt hat — eine Konfiguration mit Thick-Modus und falschem Pfad
liesse den Dienst ohne Datenbank starten."""
from __future__ import annotations
import glob
import json
import logging
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from . import pfade

log = logging.getLogger(__name__)

WINDOWS = os.name == "nt"
# Feste Adressen der jeweils neuesten Fassung. Basic Light reicht: Es kennt
# die Zeichensaetze, die OPERA nutzt (AL32UTF8, WE8MSWIN1252, WE8ISO8859P1).
CLIENT_URL = ("https://download.oracle.com/otn_software/nt/instantclient/"
              "instantclient-basiclite-windows.zip")
VC_URL = "https://aka.ms/vs/17/release/vc_redist.x64.exe"
# Unter BASIS, nicht unter PROGRAMM: Das Programmverzeichnis wechselt bei
# jeder Aktualisierung, der Client muss sie ueberstehen.
ZIEL = pfade.BASIS / "oracle"
BIBLIOTHEK = "oci.dll" if WINDOWS else "libclntsh.so"
PROBE_SEKUNDEN = 60

ANSAGE = ("Sucht einen Oracle-Client (64 Bit) auf diesem Rechner und probiert ihn mit "
          "einer Anmeldung an der Datenbank. Findet sich keiner, wird unter Windows der "
          "Oracle Instant Client von oracle.com geladen (etwa 60 MB, nach "
          f"{ZIEL}) und bei Bedarf die Visual-C++-Laufzeit von Microsoft installiert. "
          "Klappt die Anmeldung, wird der Thick-Modus eingetragen und der Dienst startet neu.")


def unterzeichner_ok(subjekt: str) -> bool:
    return bool(re.search(r'(^|,\s*)O="?Oracle America, Inc\.("|,|$)', subjekt))


def ist_dpy3015(text: str) -> bool:
    return "DPY-3015" in (text or "")


# ------------------------------------------------------------ 64 Bit?
def ist_64bit(datei: Path) -> bool:
    """Am Dateikopf: PE (Windows) mit Maschine x64, ELF (Linux) mit Klasse
    64 Bit. Ein 32-Bit-Client laesst sich in ein 64-Bit-Python nicht laden."""
    try:
        with open(datei, "rb") as f:
            kopf = f.read(4096)
    except OSError:
        return False
    if kopf[:2] == b"MZ" and len(kopf) >= 0x40:
        pe = struct.unpack_from("<I", kopf, 0x3C)[0]
        if pe + 6 <= len(kopf) and kopf[pe:pe + 4] == b"PE\0\0":
            return struct.unpack_from("<H", kopf, pe + 4)[0] in (0x8664, 0xAA64)
        return False
    if kopf[:4] == b"\x7fELF":
        return kopf[4] == 2
    return False


# ------------------------------------------------------------ Suchen
def _ordner_mit_bibliothek(ordner: Path) -> Path | None:
    if (ordner / BIBLIOTHEK).is_file():
        return ordner
    if not WINDOWS:
        # libclntsh.so ist oft nur als libclntsh.so.23.1 da
        if any(ordner.glob("libclntsh.so*")):
            return ordner
    return None


def _bibliothek(ordner: Path) -> Path | None:
    p = ordner / BIBLIOTHEK
    if p.is_file():
        return p
    treffer = sorted(ordner.glob("libclntsh.so*")) if not WINDOWS else []
    return treffer[0] if treffer else None


def kandidaten() -> list[Path]:
    """Ordner, in denen ein Oracle-Client liegt — der eigene zuerst."""
    muster: list[str] = [str(ZIEL / "*")]
    einzeln: list[str] = []
    if os.environ.get("ORACLE_HOME"):
        einzeln += [os.environ["ORACLE_HOME"], os.path.join(os.environ["ORACLE_HOME"], "bin"),
                    os.path.join(os.environ["ORACLE_HOME"], "lib")]
    pfadvar = "PATH" if WINDOWS else "LD_LIBRARY_PATH"
    einzeln += [p for p in os.environ.get(pfadvar, "").split(os.pathsep) if p]
    if WINDOWS:
        for lw in ("C:", "D:"):
            muster += [lw + r"\oracle\*", lw + r"\oracle\*\*", lw + r"\oracle\*\*\*",
                       lw + r"\app\*\product\*\*\bin", lw + r"\app\product\*\*\bin",
                       lw + r"\instantclient*", lw + r"\Program Files\Oracle\*"]
    else:
        muster += ["/opt/oracle/instantclient*", "/usr/lib/oracle/*/client64/lib",
                   "/usr/lib64/oracle/*/client64/lib"]
    gesehen: set[str] = set()
    aus: list[Path] = []
    for ordner in einzeln + [t for m in muster for t in sorted(glob.glob(m))]:
        try:
            p = Path(ordner).resolve()
        except OSError:
            continue
        schluessel = str(p).lower() if WINDOWS else str(p)
        if schluessel in gesehen or not p.is_dir():
            continue
        gesehen.add(schluessel)
        if _ordner_mit_bibliothek(p):
            aus.append(p)
    return aus


def suchen() -> list[tuple[Path, bool]]:
    """Alle gefundenen Clients mit der Angabe, ob sie 64 Bit sind."""
    return [(p, ist_64bit(_bibliothek(p) or p / BIBLIOTHEK)) for p in kandidaten()]


# ------------------------------------------------------------ Probe
_PROBE = r"""
import os, sys, oracledb
oracledb.init_oracle_client(lib_dir=os.environ["XR_LIB"])
d = __import__("json").loads(os.environ["XR_DB"])
dsn = oracledb.makedsn(d["host"], int(d["port"]), service_name=d["service_name"])
con = oracledb.connect(user=d["benutzer"], password=d["passwort"], dsn=dsn,
                       tcp_connect_timeout=15)
print("OK Oracle " + con.version)
"""


def probieren(cfg: dict, ordner: Path) -> str:
    """Meldet sich mit diesem Client an der Datenbank an, in einem eigenen
    Prozess. Gibt die Version zurueck oder wirft RuntimeError mit dem Grund.
    Das Passwort geht ueber die Umgebung, nicht ueber die Befehlszeile — die
    sieht jeder im Taskmanager."""
    d = cfg.get("datenbank") or {}
    umgebung = dict(os.environ)
    umgebung["XR_LIB"] = str(ordner)
    umgebung["XR_DB"] = json.dumps({k: d.get(k, "") for k in
                                    ("host", "port", "service_name", "benutzer", "passwort")})
    if WINDOWS:
        # Abhaengige DLLs liegen neben oci.dll
        umgebung["PATH"] = str(ordner) + os.pathsep + umgebung.get("PATH", "")
    else:
        umgebung["LD_LIBRARY_PATH"] = str(ordner) + os.pathsep + umgebung.get("LD_LIBRARY_PATH", "")
    try:
        lauf = subprocess.run([sys.executable, "-I", "-c", _PROBE], env=umgebung,
                              capture_output=True, text=True, timeout=PROBE_SEKUNDEN)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"keine Antwort nach {PROBE_SEKUNDEN} s")
    if lauf.returncode == 0 and lauf.stdout.strip().startswith("OK "):
        return lauf.stdout.strip()[3:]
    zeilen = [z.strip() for z in (lauf.stderr or lauf.stdout or "").splitlines() if z.strip()]
    # oracledb haengt eine "Help: https://..."-Zeile an; der Grund steht in der
    # Zeile mit der Fehlernummer (DPI-1047, DPY-3015, ORA-01017 ...).
    mit_nummer = [z for z in zeilen if re.search(r"\b(DPI|DPY|ORA)-\d{4,5}\b", z)]
    raise RuntimeError((mit_nummer or zeilen or [f"Rueckgabewert {lauf.returncode}"])[-1])


# ------------------------------------------------------------ Laden (Windows)
def _laden(url: str, ziel: Path) -> None:
    bitte = urllib.request.Request(url, headers={"User-Agent": "OPERA-XRechnung"})
    with urllib.request.urlopen(bitte, timeout=120) as antwort, open(ziel, "wb") as f:
        shutil.copyfileobj(antwort, f, 1024 * 1024)


def _signatur(datei: Path, firma: str) -> None:
    """Authenticode-Signatur ueber PowerShell pruefen; wirft, wenn sie nicht
    gueltig ist oder nicht von dieser Firma stammt."""
    befehl = ("$s = Get-AuthenticodeSignature -LiteralPath $env:XR_DATEI; "
              "\"$($s.Status)|$($s.SignerCertificate.Subject)\"")
    lauf = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", befehl],
                          env={**os.environ, "XR_DATEI": str(datei)},
                          capture_output=True, text=True, timeout=60)
    status, _, wer = (lauf.stdout or "").strip().partition("|")
    if status != "Valid" or firma.lower() not in wer.lower():
        raise RuntimeError(f"Signatur von {datei.name} nicht in Ordnung ({status or 'unbekannt'}, "
                           f"{wer or 'ohne Zertifikat'}) - nicht verwendet")


def _manifest_lesen(text: str) -> dict[str, dict[str, str]]:
    """JAR-Manifest: Abschnitte durch Leerzeilen getrennt, lange Zeilen mit
    fuehrendem Leerzeichen fortgesetzt. Ergebnis: Name -> Attribute; der
    Kopfabschnitt steht unter ''."""
    abschnitte: dict[str, dict[str, str]] = {}
    for block in re.split(r"\r?\n\r?\n", text.replace("\r\n", "\n")):
        zeilen: list[str] = []
        for z in block.split("\n"):
            if z.startswith(" ") and zeilen:
                zeilen[-1] += z[1:]
            elif z:
                zeilen.append(z)
        werte = dict(z.split(": ", 1) for z in zeilen if ": " in z)
        if werte:
            abschnitte.setdefault(werte.get("Name", ""), {}).update(werte)
    return abschnitte


def _zip_pruefen(zip_datei: Path, cms_pruefen=None) -> None:
    """Prueft die JAR-Signatur, mit der Oracle das Zip ausliefert.

    Die DLLs darin tragen KEINE Authenticode-Signatur (nachgesehen an
    oci.dll aus instantclient_23_0) — signiert ist das Zip: META-INF/
    MANIFEST.MF fuehrt die SHA-256 jeder Datei, ORACLE_C.SF die des Manifests,
    ORACLE_C.RSA signiert die .SF mit dem Zertifikat von Oracle America.
    Geprueft wird die ganze Kette: jede Datei gegen das Manifest (keine
    fehlt, keine ist dazugekommen), das Manifest gegen die .SF, die .SF gegen
    die Signatur."""
    import base64
    import hashlib
    with zipfile.ZipFile(zip_datei) as z:
        namen = z.namelist()
        sf_name = next((n for n in namen if re.fullmatch(r"META-INF/[^/]+\.SF", n)), "")
        p7_name = next((n for n in namen if re.fullmatch(r"META-INF/[^/]+\.(RSA|EC|DSA)", n)), "")
        if "META-INF/MANIFEST.MF" not in namen or not sf_name or not p7_name:
            raise RuntimeError("Das Zip ist nicht signiert (META-INF fehlt)")
        manifest_roh = z.read("META-INF/MANIFEST.MF")
        sf_roh = z.read(sf_name)
        sf = _manifest_lesen(sf_roh.decode("utf-8"))
        soll = (sf.get("") or {}).get("SHA-256-Digest-Manifest", "")
        ist = base64.b64encode(hashlib.sha256(manifest_roh).digest()).decode()
        if not soll or soll != ist:
            raise RuntimeError("Das Manifest des Zips passt nicht zur Signaturdatei")
        manifest = _manifest_lesen(manifest_roh.decode("utf-8"))
        dateien = [n for n in namen if not n.endswith("/") and not n.startswith("META-INF/")]
        if not dateien:
            raise RuntimeError("Das Zip enthaelt keine Dateien")
        for n in dateien:
            soll = (manifest.get(n) or {}).get("SHA-256-Digest", "")
            ist = base64.b64encode(hashlib.sha256(z.read(n)).digest()).decode()
            if not soll:
                raise RuntimeError(f"{n} steht nicht im signierten Manifest")
            if soll != ist:
                raise RuntimeError(f"{n} ist veraendert (Pruefsumme stimmt nicht)")
        (cms_pruefen or _cms_pruefen)(sf_roh, z.read(p7_name))


_CMS_PS = r"""
Add-Type -AssemblyName System.Security
try {
  $sf = [IO.File]::ReadAllBytes($env:XR_SF); $p7 = [IO.File]::ReadAllBytes($env:XR_P7)
  $ci = New-Object System.Security.Cryptography.Pkcs.ContentInfo -ArgumentList (,$sf)
  $cms = New-Object System.Security.Cryptography.Pkcs.SignedCms -ArgumentList $ci, $true
  $cms.Decode($p7)
  $cms.CheckSignature($true)
  $cert = $cms.SignerInfos[0].Certificate
  $kette = New-Object System.Security.Cryptography.X509Certificates.X509Chain
  $kette.ChainPolicy.RevocationMode = 'NoCheck'
  $kette.ChainPolicy.VerificationFlags = 'IgnoreNotTimeValid'
  $kette.ChainPolicy.ExtraStore.AddRange($cms.Certificates)
  if (-not $kette.Build($cert)) { throw ("Zertifikatskette ungueltig: " + (($kette.ChainStatus | ForEach-Object { $_.StatusInformation.Trim() }) -join '; ')) }
  "OK|" + $cert.Subject
} catch { "FEHLER|" + $_.Exception.Message }
"""


def _cms_pruefen(sf: bytes, p7: bytes) -> None:
    """Signatur ueber die .SF mit Windows-Bordmitteln (.NET SignedCms) und
    Kette bis zu einer im Windows-Zertifikatspeicher vertrauten Wurzel. Die
    Laufzeit des Zertifikats zaehlt nicht: Oracle signiert mit Zeitstempel,
    ein inzwischen abgelaufenes Zertifikat macht den Client nicht falsch."""
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "a.sf").write_bytes(sf)
        (Path(tmp) / "a.p7").write_bytes(p7)
        lauf = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _CMS_PS],
                              env={**os.environ, "XR_SF": str(Path(tmp) / "a.sf"),
                                   "XR_P7": str(Path(tmp) / "a.p7")},
                              capture_output=True, text=True, timeout=60)
    status, _, rest = (lauf.stdout or "").strip().partition("|")
    if status != "OK":
        raise RuntimeError(f"Signatur des Zips nicht gueltig: {rest or lauf.stderr.strip()[-200:]}")
    # .NET setzt Werte mit Komma in Anfuehrungszeichen: O="Oracle America, Inc."
    if not unterzeichner_ok(rest):
        raise RuntimeError(f"Das Zip ist nicht von Oracle signiert ({rest})")


def vc_laufzeit_da() -> bool:
    """Instant Client 23 braucht die Visual-C++-Laufzeit 2017 oder neuer."""
    if not WINDOWS:
        return True
    sys32 = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"
    return all((sys32 / n).is_file() for n in ("vcruntime140.dll", "vcruntime140_1.dll",
                                               "msvcp140.dll"))


def vc_installieren() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        exe = Path(tmp) / "vc_redist.x64.exe"
        _laden(VC_URL, exe)
        _signatur(exe, "Microsoft Corporation")
        lauf = subprocess.run([str(exe), "/install", "/quiet", "/norestart"],
                              capture_output=True, timeout=600)
        # 3010: Neustart empfohlen, 1638: neuere Fassung schon da
        if lauf.returncode not in (0, 3010, 1638):
            raise RuntimeError(f"Visual-C++-Installer meldet Rueckgabewert {lauf.returncode}")


def client_laden() -> Path:
    """Laedt den Instant Client nach ZIEL und gibt seinen Ordner zurueck.
    Entpackt wird erst daneben; ein schon vorhandener gleichnamiger Ordner
    wird erst ersetzt, wenn der neue vollstaendig und signiert ist."""
    ZIEL.mkdir(parents=True, exist_ok=True)
    zip_datei = ZIEL / "_instantclient.zip"
    neu = ZIEL / "_neu"
    try:
        _laden(CLIENT_URL, zip_datei)
        _zip_pruefen(zip_datei)
        shutil.rmtree(neu, ignore_errors=True)
        with zipfile.ZipFile(zip_datei) as z:
            for name in z.namelist():
                # Kein Eintrag darf aus dem Zielordner herausfuehren
                if name.startswith(("/", "\\")) or ".." in Path(name).parts:
                    raise RuntimeError(f"unerwarteter Eintrag im Zip: {name}")
            z.extractall(neu)
        # Neben instantclient_23_0/ liegt META-INF/ (Signaturdaten des Zips)
        innen = [p for p in neu.iterdir() if p.is_dir() and (p / "oci.dll").is_file()]
        if len(innen) != 1:
            raise RuntimeError("Im Zip liegt kein (eindeutiger) Ordner mit oci.dll")
        if not ist_64bit(innen[0] / "oci.dll"):
            raise RuntimeError("Die geladene oci.dll ist nicht 64 Bit")
        ziel = ZIEL / innen[0].name
        if ziel.exists():
            shutil.rmtree(ziel)
        innen[0].rename(ziel)
        return ziel
    finally:
        shutil.rmtree(neu, ignore_errors=True)
        try:
            zip_datei.unlink()
        except OSError:
            pass


# ------------------------------------------------------------ Gesamtablauf
def einrichten(cfg: dict) -> tuple[Path | None, list[str]]:
    """Gibt (Ordner, Schritte) zurueck. Ordner ist None, wenn nichts klappte;
    die Schritte sagen dann, woran es lag."""
    schritte: list[str] = []
    gefunden = suchen()
    for p, b64 in gefunden:
        if not b64:
            schritte.append(f"{p}: 32 Bit, nicht verwendbar")
    brauchbar = [p for p, b64 in gefunden if b64]

    if WINDOWS and not vc_laufzeit_da():
        try:
            vc_installieren()
            schritte.append("Visual-C++-Laufzeit installiert")
        except Exception as e:  # noqa: BLE001 — Grund wird gemeldet
            schritte.append(f"Visual-C++-Laufzeit nicht installiert: {e}")

    for p in brauchbar:
        try:
            version = probieren(cfg, p)
            schritte.append(f"{p}: Anmeldung gelungen ({version})")
            return p, schritte
        except Exception as e:  # noqa: BLE001
            schritte.append(f"{p}: {e}")

    if not WINDOWS:
        schritte.append("Kein passender Oracle-Client gefunden. Unter Linux als root: "
                        "dnf install oracle-instantclient-release-el9 && "
                        "dnf install oracle-instantclient-basic - danach erneut versuchen.")
        return None, schritte

    try:
        p = client_laden()
        schritte.append(f"Oracle Instant Client geladen nach {p}")
    except Exception as e:  # noqa: BLE001
        schritte.append(f"Laden von oracle.com nicht gelungen: {e}")
        return None, schritte
    try:
        version = probieren(cfg, p)
        schritte.append(f"Anmeldung gelungen ({version})")
        return p, schritte
    except Exception as e:  # noqa: BLE001
        schritte.append(f"{p}: {e}")
        return None, schritte
