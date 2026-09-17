"""Selbsttest fuer Betrieb und Aktualisierung: Updater, Startskripte, Dienst.

Eigenstaendig, ohne Datenbank und ohne Netz:
    python tools/smoketest_betrieb.py

Was hier steht, laesst sich im Haupttest schlecht pruefen, weil es an Dingen
haengt, die dort nicht vorkommen: an einer laufenden nssm.exe, an einem Prozess,
der aus einer anderen Freigabe laeuft als 'aktuell', an einem Symlink im
Startpfad, an Windows PowerShell 5.1. Jede dieser Stellen ist in Betrieb
schiefgegangen oder waere es. Nachgestellt wird das Verhalten, das den Fehler
ausloeste — nicht bloss, dass eine Zeile im Code steht.

Geschrieben wird ausschliesslich in einen Sandkasten unter dem Temp-Verzeichnis.
"""
import io
import json
import logging
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import types

WURZEL = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

# Umlenken VOR dem ersten Import von app — pfade.py liest die Umgebung beim
# Import. Danach zeigt nichts mehr auf echte Konfiguration oder Daten.
_sandkasten = pathlib.Path(tempfile.mkdtemp(prefix="xrechnung-betrieb-")).resolve()
import atexit
atexit.register(lambda: shutil.rmtree(_sandkasten, ignore_errors=True))
os.environ["XRECHNUNG_BASIS"] = str(_sandkasten)
os.environ["XRECHNUNG_CONFIG_DIR"] = str(_sandkasten / "config")
os.environ["XRECHNUNG_DATEN_DIR"] = str(_sandkasten / "data")
os.environ["XRECHNUNG_LOG_DIR"] = str(_sandkasten / "logs")
for _ordner in ("config", "data", "logs"):
    (_sandkasten / _ordner).mkdir()
for _var in ("XRECHNUNG_UPDATE_REPO", "XRECHNUNG_UPDATE_ZWEIG"):
    os.environ.pop(_var, None)

import app  # noqa: E402
from app import pfade, store, updater  # noqa: E402

store.init()   # der Updater protokolliert — in die Sandkasten-Datenbank
logging.disable(logging.CRITICAL)
fehler: list[str] = []


def pruefe(bedingung, text):
    print(("  ok   " if bedingung else "  FEHL ") + text)
    if not bedingung:
        fehler.append(text)


def uebersprungen(text):
    print("  ---  " + text)


assert pfade.CONFIG_DIR == _sandkasten / "config", pfade.CONFIG_DIR
_echt = {n: getattr(updater, n) for n in
         ("BASE", "PROGRAMM_DIR", "FREIGABEN", "AKTUELL", "pruefen", "_anfrage")}


def _zuruecksetzen_modul():
    for n, w in _echt.items():
        setattr(updater, n, w)


def _tarball(dateien: dict[str, str], wurzel="ahorn-XRechnungOPERA-abc1234") -> bytes:
    puffer = io.BytesIO()
    with tarfile.open(fileobj=puffer, mode="w:gz") as t:
        for name, inhalt in dateien.items():
            b = inhalt.encode()
            info = tarfile.TarInfo(f"{wurzel}/{name}")
            info.size, info.mtime = len(b), time.time()
            t.addfile(info, io.BytesIO(b))
    return puffer.getvalue()


def _schnappschuss(wurzel: pathlib.Path) -> dict[str, bytes]:
    return {p.relative_to(wurzel).as_posix(): p.read_bytes()
            for p in sorted(wurzel.rglob("*"))
            if p.is_file() and "__pycache__" not in p.parts}


CFG = {"update": {"aktiv": True, "repo": "a/b", "zweig": "main"}}

# =========================================================================
print("1) Aktualisierung an Ort und Stelle (Windows) mit laufender nssm.exe")
# Unter Windows laesst sich ein laufendes Programm weder loeschen noch
# umbenennen. Nachgestellt ueber os.unlink/os.remove/os.replace/os.rename:
# Jeder Zugriff auf nssm.exe wirft, wie WinError 5. Vorher lief rmtree(install/)
# genau hinein — nach app/, sql/, docs/, vor beispiele/ und VERSION.
ALT = {"app/__init__.py": "", "app/alt_modul.py": "ALT", "app/kern.py": "ALT",
       "sql/a.sql": "ALT", "tools/t.py": "ALT", "docs/d.md": "ALT",
       "install/installieren.ps1": "ALT", "beispiele/b.xml": "ALT",
       "requirements.txt": "ALT\n", "run.cmd": "ALT", "run.sh": "ALT",
       "VERSION": "ALT", "config/app.example.json": '{"alt": 1}'}
NEU = {"app/__init__.py": "", "app/kern.py": "NEU", "app/neu_modul.py": "NEU",
       "sql/a.sql": "NEU", "tools/t.py": "NEU", "docs/d.md": "NEU",
       "install/installieren.ps1": "NEU", "install/unit_erzeugen.sh": "NEU",
       "beispiele/b.xml": "NEU", "requirements.txt": "ALT\n", "run.cmd": "NEU",
       "run.sh": "NEU", "VERSION": "NEU", "config/app.example.json": '{"alt": 1, "neu": 2}'}


def _flach_anlegen(name: str) -> pathlib.Path:
    basis = _sandkasten / name
    for rel, inhalt in ALT.items():
        (basis / rel).parent.mkdir(parents=True, exist_ok=True)
        (basis / rel).write_text(inhalt)
    (basis / "install" / "nssm.exe").write_bytes(b"MZ-laufendes-nssm")
    return basis


def _gesperrt(pfad) -> bool:
    return os.path.basename(os.fspath(pfad)).lower() == "nssm.exe"


_os_echt = {n: getattr(os, n) for n in ("unlink", "remove", "replace", "rename")}


def _windows_sperre(zusatz=lambda quelle, ziel: False):
    def unlink(p, *a, **k):
        if _gesperrt(p):
            raise PermissionError(13, "[nachgestellt WinError 5] Zugriff verweigert", os.fspath(p))
        return _os_echt["unlink"](p, *a, **k)

    def replace(q, z, *a, **k):
        if _gesperrt(q) or _gesperrt(z):
            raise PermissionError(13, "[nachgestellt WinError 5] Zugriff verweigert", os.fspath(q))
        if zusatz(q, z):
            raise PermissionError(13, "[nachgestellt] Datei in Benutzung", os.fspath(z))
        return _os_echt["replace"](q, z, *a, **k)
    os.unlink = os.remove = unlink
    os.replace = os.rename = replace


def _sperre_aufheben():
    for n, f in _os_echt.items():
        setattr(os, n, f)


def _anwenden_flach(basis: pathlib.Path, zusatz=lambda q, z: False):
    updater.BASE = basis
    # Kein Freigabenbetrieb: die Pfade zeigen ins Leere.
    updater.PROGRAMM_DIR = _sandkasten / "keine-freigaben"
    updater.FREIGABEN = updater.PROGRAMM_DIR / "freigaben"
    updater.AKTUELL = updater.PROGRAMM_DIR / "aktuell"
    updater.pruefen = lambda cfg: {"moeglich": True, "sha": "abc1234" + "0" * 33,
                                   "kurz": "abc12340", "datum": ""}
    daten = _tarball(NEU)
    updater._anfrage = lambda url, token="", roh=False: daten
    _windows_sperre(zusatz)
    try:
        return updater.anwenden(CFG, benutzer="test"), None
    except Exception as e:  # noqa: BLE001 — genau das soll nicht passieren
        return None, e
    finally:
        _sperre_aufheben()
        _zuruecksetzen_modul()


try:
    basis = _flach_anlegen("flach1")
    nssm_vorher = (basis / "install" / "nssm.exe").stat()
    meldung, ausnahme = _anwenden_flach(basis)
    pruefe(ausnahme is None, f"keine Ausnahme bis zur Oberflaeche (vorher HTTP 500) ({ausnahme!r})")
    pruefe(meldung is not None and "eingespielt" in meldung, f"die Aktualisierung gelingt ({meldung})")
    stand = _schnappschuss(basis)
    erwartet = {k: v.encode() for k, v in NEU.items()}
    erwartet["install/nssm.exe"] = b"MZ-laufendes-nssm"
    pruefe(stand == erwartet,
           "danach steht genau der neue Stand da — nichts halb, nichts doppelt "
           f"(abweichend: {sorted(set(stand.items()) ^ set(erwartet.items()))[:4]})")
    nssm_nachher = (basis / "install" / "nssm.exe").stat()
    pruefe((nssm_vorher.st_ino, nssm_vorher.st_mtime_ns) == (nssm_nachher.st_ino, nssm_nachher.st_mtime_ns),
           "die laufende nssm.exe ist dieselbe Datei wie vorher, nicht angefasst")
    pruefe(not (basis / "app" / "alt_modul.py").exists(),
           "ein im neuen Stand entfallenes Modul ist weg")
    pruefe(not any(p.name.startswith(".aktualisierung") for p in basis.iterdir()),
           "keine Bereitstellungs- oder Rueckwegreste")
    pruefe((_sandkasten / "config" / "app.example.json").is_file() and
           json.loads((_sandkasten / "config" / "app.example.json").read_text()).get("neu") == 2,
           "die Vorlage erreicht auch ein abweichendes CONFIG_DIR")

    # Scheitert ein Schritt MITTEN im Austausch (eine Datei in Benutzung),
    # muss alles zurueck. VERSION kommt spaet — davor ist schon viel ersetzt.
    basis = _flach_anlegen("flach2")
    vorher = _schnappschuss(basis)
    meldung, ausnahme = _anwenden_flach(
        basis, zusatz=lambda q, z: os.path.basename(os.fspath(z)) == "VERSION"
        and ".aktualisierung.neu" in os.fspath(q))
    pruefe(ausnahme is None, f"ein Fehler mitten im Austausch wird nicht zur Ausnahme ({ausnahme!r})")
    pruefe(meldung is not None and "zurueckgerollt" in meldung,
           f"die Meldung sagt, dass zurueckgerollt wurde ({(meldung or '')[:80]})")
    pruefe(_schnappschuss(basis) == vorher,
           "und die Installation ist Byte fuer Byte die alte")
    pruefe(not any(p.name.startswith(".aktualisierung") for p in basis.iterdir()),
           "ohne Reste des abgebrochenen Versuchs")
    pruefe(not (basis / "app" / "neu_modul.py").exists(),
           "auch neu hinzugekommene Dateien sind wieder weg")
finally:
    _sperre_aufheben()
    _zuruecksetzen_modul()

# =========================================================================
print("2) Freigaben: die LAUFENDE schuetzen, zurueck heisst zurueck")


def _freigaben_anlegen(unter: str, namen) -> dict[str, pathlib.Path]:
    updater.PROGRAMM_DIR = _sandkasten / unter / "programm"
    updater.FREIGABEN = updater.PROGRAMM_DIR / "freigaben"
    updater.AKTUELL = updater.PROGRAMM_DIR / "aktuell"
    ergebnis = {}
    for name, vorlage in namen:
        d = updater.FREIGABEN / name
        (d / "app").mkdir(parents=True)
        (d / "requirements.txt").write_text("")
        if vorlage is not None:
            (d / "config").mkdir()
            (d / "config" / "app.example.json").write_text(vorlage)
        ergebnis[name[-1]] = d
    return ergebnis


A, B, C, D, E = ("20260901-100000-aaaaaaaa", "20260902-100000-bbbbbbbb",
                 "20260903-100000-cccccccc", "20260904-100000-dddddddd",
                 "20260905-100000-eeeeeeee")
try:
    # Zurueckgesetzt auf A, neu gestartet (der Prozess laeuft jetzt aus A),
    # danach zwei Aktualisierungen: 'aktuell' zeigt auf E, A ist die aelteste.
    f = _freigaben_anlegen("fr1", [(n, None) for n in (A, B, C, D, E)])
    updater.umschalten(f["e"])
    updater.BASE = f["a"]
    weg = updater.aufraeumen(behalten=3)
    pruefe(f["a"].exists(), f"die Freigabe, aus der der Prozess laeuft, bleibt ({weg})")
    pruefe(not f["b"].exists(), "eine nicht laufende alte wird entfernt")
    _zuruecksetzen_modul()

    # Drei Aktualisierungen ohne Neustart — echt ueber _freigabe_einspielen.
    f = _freigaben_anlegen("fr2", [(n, None) for n in (A, B, C)])
    updater.umschalten(f["c"])
    updater.BASE = f["c"]
    quelle = _sandkasten / "fr2" / "quelle"
    (quelle / "app").mkdir(parents=True)
    for i in range(3):
        time.sleep(1.05)   # der Freigabename traegt die Sekunde
        updater._freigabe_einspielen(quelle, f"{i}" * 40)
    pruefe(f["c"].exists(), "nach drei Aktualisierungen ohne Neustart steht die laufende noch")
    _zuruecksetzen_modul()

    # Zurueck ohne Namen, waehrend 'aktuell' schon auf einer aelteren steht.
    f = _freigaben_anlegen("fr3", [(n, None) for n in (A, B, C)])
    updater.umschalten(f["b"])
    m = updater.zuruecksetzen()
    pruefe(updater.AKTUELL.resolve().name == A,
           f"zurueck von B fuehrt auf A, nicht vorwaerts auf C ({m})")
    m = updater.zuruecksetzen()
    pruefe(updater.AKTUELL.resolve().name == A and "keine frühere" in m,
           f"an der aeltesten angekommen, bleibt es dort und sagt es ({m[:60]})")
    updater.umschalten(f["c"])
    updater.zuruecksetzen()
    updater.zuruecksetzen()
    pruefe(updater.AKTUELL.resolve().name == A, "zweimal zurueck von C fuehrt ueber B auf A")
finally:
    _zuruecksetzen_modul()

# =========================================================================
print("3) Freigaben: die Konfigurationsvorlage erreicht den Bestand")
try:
    ziel = pfade.CONFIG_DIR / "app.example.json"
    ziel.write_text('{"uralt": 1}')
    os.chmod(ziel, 0o600)
    f = _freigaben_anlegen("fr4", [(A, '{"alt": 1}')])
    updater.umschalten(f["a"])
    quelle = _sandkasten / "fr4" / "quelle"
    (quelle / "config").mkdir(parents=True)
    (quelle / "config" / "app.example.json").write_text('{"alt": 1, "neu_in_b": 2}')
    time.sleep(1.05)
    neu, _ = updater._freigabe_einspielen(quelle, "b" * 40)
    pruefe(json.loads(ziel.read_text()).get("neu_in_b") == 2,
           "nach dem Einspielen liegt die neue Vorlage in CONFIG_DIR")
    if os.name != "nt":
        pruefe(stat.S_IMODE(ziel.stat().st_mode) == 0o644,
               f"und bleibt lesbar ({oct(stat.S_IMODE(ziel.stat().st_mode))})")
    pruefe(not [p for p in pfade.CONFIG_DIR.iterdir() if p.name.endswith(".neu")],
           "ohne Hilfsdatei daneben")
    updater.zuruecksetzen(A)
    pruefe(json.loads(ziel.read_text()) == {"alt": 1},
           "beim Zuruecksetzen kommt die Vorlage der Freigabe mit, auf die zurueckgegangen wird")
finally:
    _zuruecksetzen_modul()

# =========================================================================
print("4) Dienst: pip darf in die venv schreiben, und der Updater nimmt die richtige")
unit = (WURZEL / "install" / "xrechnung.service").read_text(encoding="utf-8")
zeilen = {z.split("=", 1)[0]: z.split("=", 1)[1] for z in unit.splitlines()
          if "=" in z and not z.lstrip().startswith("#")}
python_pfad = zeilen.get("ExecStart", "").split()[0]
venv = python_pfad.rsplit("/bin/", 1)[0]
rw = zeilen.get("ReadWritePaths", "").split()
pruefe(zeilen.get("ProtectSystem") != "strict" or
       any(venv == p.lstrip("-") or venv.startswith(p.lstrip("-") + "/") for p in rw),
       f"die venv des Dienstes ({venv}) steht in ReadWritePaths ({' '.join(rw)})")
try:
    ort = _sandkasten / "pip"
    ort.mkdir()
    (ort / "requirements.txt").write_text("fastapi\n")
    (ort / "quelle").mkdir()
    (ort / "quelle" / "requirements.txt").write_text("fastapi\nneues-paket\n")
    updater.BASE = ort
    aufrufe = []
    _run_echt = subprocess.run
    updater.subprocess.run = lambda args, **k: (aufrufe.append(args) or
                                                 types.SimpleNamespace(returncode=0, stdout="", stderr=""))
    try:
        ergebnis = updater._abhaengigkeiten_nachziehen(ort / "quelle")
    finally:
        updater.subprocess.run = _run_echt
    pruefe(ergebnis == "" and len(aufrufe) == 1, f"pip wird aufgerufen ({ergebnis or aufrufe})")
    pruefe(bool(aufrufe) and aufrufe[0][:3] == [sys.executable, "-m", "pip"],
           f"und zwar als Modul des laufenden Interpreters ({aufrufe[0][:3] if aufrufe else '-'})")
finally:
    _zuruecksetzen_modul()

# =========================================================================
print("5) Windows-Installer: native Aufrufe und Suchpfad")
ps1 = WURZEL / "install" / "installieren.ps1"
ps1_text = ps1.read_text(encoding="utf-8")
pwsh = shutil.which("pwsh")
if not pwsh:
    uebersprungen("pwsh fehlt — PowerShell-Pruefungen nicht moeglich")
else:
    analyse = r"""
param($pfad)
$tokens = $null; $fehler = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($pfad, [ref]$tokens, [ref]$fehler)
"PARSEFEHLER " + $fehler.Count
$ast.FindAll({ $args[0] -is [System.Management.Automation.Language.CommandAst] -and
               $args[0].Redirections.Count -gt 0 }, $true) | ForEach-Object {
    $p = $_.Parent; $in = ""
    while ($p) { if ($p -is [System.Management.Automation.Language.FunctionDefinitionAst]) { $in = $p.Name; break }; $p = $p.Parent }
    "UMLEITUNG " + $_.Extent.StartLineNumber + " " + $in
}
$f = $ast.FindAll({ $args[0] -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $args[0].Name -eq "Nativ" }, $true) | Select-Object -First 1
if (-not $f) { "NATIV fehlt"; exit }
. ([ScriptBlock]::Create($f.Extent.Text))
$ErrorActionPreference = "Stop"
# Nachstellung von Windows PowerShell 5.1: Dort wird umgeleitetes stderr eines
# externen Programms zu einem Fehlerdatensatz, der unter "Stop" abbricht.
# PowerShell 7 tut das nicht mehr — also ein Stellvertreter, der genau einen
# solchen Datensatz erzeugt.
function java { Write-Error 'openjdk version 21.0.4 2024-07-16' }
try { $a = Nativ java -version; "JAVA_OK " + ($a | Select-Object -First 1) } catch { "JAVA_ABBRUCH " + $_ }
try { $b = Nativ sh -c 'echo auf-stderr >&2; exit 3'; "SH_OK $script:NativCode " + ($b -join "|") } catch { "SH_ABBRUCH " + $_ }
try { $c = Nativ printf '%s;' "mit leer" -x; "ARGS_OK $c" } catch { "ARGS_ABBRUCH " + $_ }
"""
    skript = _sandkasten / "analyse.ps1"
    skript.write_text(analyse, encoding="utf-8")
    lauf = subprocess.run([pwsh, "-NoProfile", "-NonInteractive", "-File", str(skript), str(ps1)],
                          capture_output=True, text=True, timeout=120)
    aus = lauf.stdout.splitlines()
    pruefe("PARSEFEHLER 0" in aus, f"installieren.ps1 laesst sich parsen ({[z for z in aus if 'PARSE' in z]})")
    ausserhalb = [z for z in aus if z.startswith("UMLEITUNG") and not z.endswith(" Nativ")]
    pruefe(not ausserhalb,
           f"keine Umleitung nativer Ausgaben ausserhalb von Nativ (5.1 bricht daran ab) ({ausserhalb})")
    pruefe(any(z.startswith("JAVA_OK openjdk") for z in aus),
           f"java -version ueber Nativ bricht unter 'Stop' nicht ab und liefert die Zeile "
           f"({[z for z in aus if z.startswith('JAVA') or z.startswith('NATIV')]})")
    pruefe("SH_OK 3 auf-stderr" in aus,
           f"stderr kommt als Text an, der Rueckgabewert in NativCode ({[z for z in aus if z.startswith('SH')]})")
    pruefe("ARGS_OK mit leer;-x;" in aus,
           f"Argumente gehen einzeln durch, auch '-x' ({[z for z in aus if z.startswith('ARGS')]})")
    if lauf.returncode != 0 and lauf.stderr:
        print("       pwsh:", lauf.stderr.strip()[:300])
import re  # noqa: E402
pfad_zuweisungen = re.findall(r"^\s*\$env:Path\s*=.*$", ps1_text, flags=re.M | re.I)
pruefe(pfad_zuweisungen and all('"User"' in z or "PfadNeuLaden" in z or "$benutzer" in z
                                for z in pfad_zuweisungen),
       f"PATH wird nie nur aus dem Maschinenteil gesetzt ({pfad_zuweisungen})")
nach_winget = re.findall(r"winget install[^\n]*(?:\n[^\n]*){0,4}", ps1_text)
pruefe(nach_winget and all("PfadNeuLaden" in s for s in nach_winget),
       "nach jedem winget install wird der Suchpfad neu gelesen")

# =========================================================================
print("6) Windows-Installer: Ordnerrechte")
titel = [m.start() for m in re.finditer(r'^Titel "', ps1_text, flags=re.M)]
stelle_rechte = ps1_text.find('Titel "Ordnerrechte"')
stelle_konfig = ps1_text.find('Titel "Konfiguration"')
stelle_dienst = ps1_text.find('Titel "Windows-Dienst"')
pruefe(stelle_konfig < stelle_rechte < stelle_dienst,
       "die Rechte werden nach dem Anlegen von config/data/logs und vor dem Dienststart gesetzt")
abschnitt = ps1_text[stelle_rechte:stelle_dienst] if stelle_rechte > 0 else ""
pruefe("S-1-5-18" in abschnitt and "S-1-5-32-544" in abschnitt,
       "SYSTEM und Administratoren ueber SIDs (sprachunabhaengig)")
g, r = abschnitt.find("/grant:r"), abschnitt.find("/inheritance:r")
pruefe(0 < g < r, "erst eigene Eintraege, dann die Vererbung kappen (kein Moment ohne Zugriff)")
pruefe("/setowner" in abschnitt and "/reset" in abschnitt,
       "Eigentuemer und vorhandene Einzelrechte werden mit erfasst")
pruefe(re.search(r"Nativ icacls \$Basis\s*\|", abschnitt) is not None,
       "der Installer zeigt an, was gesetzt wurde")

# =========================================================================
print("7) run.sh ueber programm/aktuell")
if os.name == "nt" or not shutil.which("bash"):
    uebersprungen("ohne bash nicht pruefbar")
else:
    def _runsh(start: pathlib.Path, cwd: pathlib.Path) -> str:
        # PWD setzen wie eine Shell nach 'cd programm/aktuell': mit dem Symlink
        # im Pfad. Ohne das nimmt bash den physischen Pfad, und der Fehler
        # zeigte sich im Test nicht.
        umgebung = {k: v for k, v in os.environ.items() if not k.startswith("XRECHNUNG_")}
        umgebung["PWD"] = str(cwd)
        lauf = subprocess.run(["bash", str(start)], cwd=cwd, capture_output=True, text=True,
                              timeout=60, stdin=subprocess.DEVNULL, env=umgebung)
        return lauf.stdout + lauf.stderr

    def _falsches_python(basis: pathlib.Path):
        (basis / ".venv" / "bin").mkdir(parents=True)
        py = basis / ".venv" / "bin" / "python"
        py.write_text('#!/bin/sh\necho "BASIS=${XRECHNUNG_BASIS:-<leer>}"\n')
        py.chmod(0o755)
        (basis / "config").mkdir(exist_ok=True)
        (basis / "config" / "app.json").write_text("{}")

    rs = _sandkasten / "runsh"
    fr = rs / "programm" / "freigaben" / A
    fr.mkdir(parents=True)
    shutil.copy2(WURZEL / "run.sh", fr / "run.sh")
    (rs / "programm" / "aktuell").symlink_to(pathlib.Path("freigaben") / A)
    _falsches_python(rs)
    for art, start, cwd in (("direkt in der Freigabe", fr / "run.sh", fr),
                            ("ueber programm/aktuell/run.sh", rs / "programm" / "aktuell" / "run.sh", rs),
                            ("cd programm/aktuell && ./run.sh", pathlib.Path("run.sh"), rs / "programm" / "aktuell")):
        aus = _runsh(start, cwd)
        pruefe(f"BASIS={rs}" in aus, f"{art}: Bestand ist die Installation ({aus.strip().splitlines()[-1:]})")
    pruefe(not (fr / ".venv").exists() and not (fr / "config").exists(),
           "und in der Freigabe entsteht weder eine venv noch eine Konfiguration")
    flach = _sandkasten / "runsh-flach"
    flach.mkdir()
    shutil.copy2(WURZEL / "run.sh", flach / "run.sh")
    _falsches_python(flach)
    aus = _runsh(flach / "run.sh", flach)
    pruefe("BASIS=<leer>" in aus and "Freigabenbetrieb" not in aus,
           f"flach bleibt alles beim Alten ({aus.strip().splitlines()[-1:]})")

# =========================================================================
print("8) dienst_einrichten.sh / unit_erzeugen.sh: Platzhalter und Aufbau")
einrichten = (WURZEL / "install" / "dienst_einrichten.sh").read_text(encoding="utf-8")
pruefe("unit_erzeugen.sh" in einrichten,
       "dienst_einrichten.sh baut die Unit ueber unit_erzeugen.sh (dort werden ALLE Platzhalter ersetzt)")
pruefe("pwd -P" in einrichten and "programm/freigaben" in einrichten,
       "dienst_einrichten.sh findet die Installation auch aus einer Freigabe heraus")
helfer = WURZEL / "install" / "unit_erzeugen.sh"
if os.name == "nt" or not shutil.which("bash") or not helfer.exists():
    uebersprungen("unit_erzeugen.sh nicht ausfuehrbar (fehlt oder kein bash)")
else:
    def _unit(start: pathlib.Path, *zusatz) -> tuple[int, dict, str]:
        lauf = subprocess.run(["bash", str(start), "--unit-alt", str(_sandkasten / "gibt-es-nicht"),
                               *zusatz], capture_output=True, text=True, timeout=60)
        werte: dict[str, list[str]] = {}
        for z in lauf.stdout.splitlines():
            if "=" in z and not z.lstrip().startswith("#"):
                k, v = z.split("=", 1)
                werte.setdefault(k, []).append(v)
        return lauf.returncode, werte, lauf.stdout + lauf.stderr

    for art, basis, start in (
            ("flach", _sandkasten / "unit-flach", None),
            ("Freigabe", _sandkasten / "unit-frei", None)):
        if art == "flach":
            shutil.copytree(WURZEL / "install", basis / "install")
            start = basis / "install" / "unit_erzeugen.sh"
        else:
            shutil.copytree(WURZEL / "install", basis / "programm" / "freigaben" / A / "install")
            (basis / "programm" / "aktuell").symlink_to(pathlib.Path("freigaben") / A)
            start = basis / "programm" / "aktuell" / "install" / "unit_erzeugen.sh"
        for ordner in ("config", "data", "logs", ".venv/bin"):
            (basis / ordner).mkdir(parents=True, exist_ok=True)
        (basis / "config" / "app.json").write_text(json.dumps({"update": {"repo": "ahorn/xr", "zweig": "prod"}}))
        code, werte, text = _unit(start)
        roh = "\n".join(z for z in text.splitlines() if not z.lstrip().startswith("#"))
        pruefe(code == 0 and "@" not in roh.replace("@BASIS@", "@"),
               f"{art}: keine Platzhalter uebrig ({[z for z in roh.splitlines() if '@' in z][:3]})")
        umgebung = dict(e.split("=", 1) for e in werte.get("Environment", []))
        pruefe(umgebung.get("XRECHNUNG_UPDATE_REPO") == "ahorn/xr" and
               umgebung.get("XRECHNUNG_UPDATE_ZWEIG") == "prod",
               f"{art}: Repository und Zweig aus app.json ({umgebung.get('XRECHNUNG_UPDATE_REPO')}, "
               f"{umgebung.get('XRECHNUNG_UPDATE_ZWEIG')})")
        wd = pathlib.Path((werte.get("WorkingDirectory") or [""])[0])
        pruefe(wd.is_dir() and (wd / "install").is_dir(),
               f"{art}: WorkingDirectory ist das Programm ({wd})")
        fehlend = [p for p in (werte.get("ReadWritePaths") or [""])[0].split()
                   if not p.startswith("-") and not pathlib.Path(p).exists()]
        pruefe(not fehlend, f"{art}: jeder Pfad in ReadWritePaths existiert (sonst 226/NAMESPACE) ({fehlend})")
        pruefe(umgebung.get("XRECHNUNG_BASIS") == str(basis.resolve()),
               f"{art}: XRECHNUNG_BASIS ist die Installation ({umgebung.get('XRECHNUNG_BASIS')})")
    # Ein festgenagelter Zeiger in der bestehenden Unit bleibt stehen.
    alt = _sandkasten / "alt.service"
    alt.write_text("Environment=XRECHNUNG_UPDATE_REPO=fest/genagelt\n")
    lauf = subprocess.run(["bash", str(_sandkasten / "unit-flach" / "install" / "unit_erzeugen.sh"),
                           "--unit-alt", str(alt)], capture_output=True, text=True, timeout=60)
    pruefe("Environment=XRECHNUNG_UPDATE_REPO=fest/genagelt" in lauf.stdout,
           "ein erneutes Einrichten behaelt den Zeiger der bestehenden Unit")

# =========================================================================
print("9) Neustart wartet auf einen laufenden Automatiklauf")


class _Beendet(Exception):
    pass


_exit_echt, _shutdown_echt = os._exit, logging.shutdown
_automatik_echt = sys.modules.get("app.automatik"), getattr(app, "automatik", None)


def _neustart_mit(laeuft, frist):
    zeitpunkt = {}

    def beenden(code):
        zeitpunkt["t"] = time.monotonic()
        raise _Beendet()
    attrappe = types.ModuleType("app.automatik")
    if laeuft is not None:
        attrappe.laeuft_gerade = laeuft
    sys.modules["app.automatik"] = attrappe
    app.automatik = attrappe
    os._exit = beenden
    logging.shutdown = lambda *a, **k: None
    takt = updater._NEUSTART_TAKT if hasattr(updater, "_NEUSTART_TAKT") else None
    if takt is not None:
        updater._NEUSTART_TAKT = 0.01
    start = time.monotonic()
    try:
        try:
            updater.neustart(frist) if "frist" in updater.neustart.__code__.co_varnames else updater.neustart()
        except _Beendet:
            pass
    finally:
        os._exit, logging.shutdown = _exit_echt, _shutdown_echt
        if takt is not None:
            updater._NEUSTART_TAKT = takt
        mod, attr = _automatik_echt
        if mod is None:
            sys.modules.pop("app.automatik", None)
        else:
            sys.modules["app.automatik"] = mod
        if attr is None:
            if hasattr(app, "automatik"):
                del app.automatik
        else:
            app.automatik = attr
    return zeitpunkt.get("t", start) - start, "t" in zeitpunkt


zaehler = {"n": 0}


def _arbeitet_noch_kurz():
    zaehler["n"] += 1
    return zaehler["n"] <= 5


dauer, beendet = _neustart_mit(_arbeitet_noch_kurz, 5)
pruefe(beendet and zaehler["n"] > 5,
       f"beendet wird erst, nachdem der Durchlauf fertig meldet ({zaehler['n']} Abfragen, {dauer:.2f} s)")
dauer, beendet = _neustart_mit(lambda: True, 0.3)
pruefe(beendet and 0.25 <= dauer < 3,
       f"ein haengender Durchlauf haelt den Neustart nur bis zur Frist auf ({dauer:.2f} s)")
dauer, beendet = _neustart_mit(None, 5)
pruefe(beendet and dauer < 1, f"ohne laeuft_gerade() startet er sofort neu ({dauer:.2f} s)")


def _wirft():
    raise RuntimeError("kaputt")


dauer, beendet = _neustart_mit(_wirft, 5)
pruefe(beendet and dauer < 1, f"eine werfende Abfrage verhindert den Neustart nicht ({dauer:.2f} s)")
pruefe(getattr(updater, "NEUSTART_FRIST", None) == 120, "die Frist im Betrieb ist 120 s")

# =========================================================================
print()
if fehler:
    print(f"{len(fehler)} Pruefung(en) fehlgeschlagen:")
    for f_ in fehler:
        print("  - " + f_)
    sys.exit(1)
print("Alle Pruefungen bestanden.")
