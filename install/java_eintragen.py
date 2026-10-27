"""Traegt den Pfad zu einem passenden Java in config/app.json ein.

Aufruf durch installieren.ps1:  python java_eintragen.py <app.json> <java.exe>

Noetig, wenn vor dem neuen Java noch ein altes im Suchpfad steht (auf
Windows-Servern oft ein Java 8 fuer andere Programme). Mit "java" faende die
Anwendung dann das alte und der Validator startete nicht.

Ein Pfad, den jemand selbst eingetragen hat, bleibt stehen. Ueberschrieben
wird nur die Vorgabe "java" bzw. ein leeres Feld. Ausgabe: eine Zeile fuer
das Installationsprotokoll."""
import json
import os
import sys

datei, java = sys.argv[1], sys.argv[2]
with open(datei, encoding="utf-8") as f:
    cfg = json.load(f)
validierung = cfg.setdefault("validierung", {})
bisher = (validierung.get("java") or "").strip()
if bisher.lower() not in ("", "java", "java.exe") and bisher != java:
    print(f"bleibt: in der Konfiguration steht bereits {bisher}")
    sys.exit(0)
validierung["java"] = java
neu = datei + ".neu"
with open(neu, "w", encoding="utf-8") as f:
    f.write(json.dumps(cfg, indent=2, ensure_ascii=False))
os.replace(neu, datei)
print(f"eingetragen: {java}")
