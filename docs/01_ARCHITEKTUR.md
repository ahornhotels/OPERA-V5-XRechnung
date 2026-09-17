# Architektur — was aus Suite8-Slim übernommen wird

Referenz: `reference/XRechnung_Slim/` (v1.9.0, GPLv3, 5.900 Zeilen Python,
198 Tests grün).

## Ablauf in Suite8-Slim

```
WMAI-Mail wird zum Versand markiert (BLOCKSEND=1 durch DB-Trigger)
   → Poller (alle 30 s) findet die geblockte Mail
   → Rechnungsnummer aus dem Betreff (mehrsprachiges Regex)
   → 4 SQL gegen V8LIVE  →  invoice-Dict
   → Jinja2 → UBL-2.1-XML  (+ Normalisierung, s. u.)
   → KoSIT-Validator (Java, XSLT-Schematron)  → nur bei „grün" weiter
   → XML an dieselbe Mail hängen, BLOCKSEND=0 → Suite8 versendet
   → Archiv (Dateisystem) + Audit (JSONL)
```

Kein eigener Mailversand, keine Änderung am PMS-Workflow — die App klinkt sich
nur in die ausgehende Mail ein. Das ist der elegante Teil des Entwurfs.

## Übernahme-Matrix

| Baustein | Datei(en) in der Referenz | OPERA |
|---|---|---|
| UBL-Template Rechnung | `templates/xrechnung_3.0.xml.j2` | **1:1** |
| UBL-Template Gutschrift | `templates/creditnote_3.0.xml.j2` | **1:1** |
| Negativ-Zeilen → AllowanceCharge, BR-27/BR-S-01/BR-Z-08/BR-CO-17-Fixes | `modules/xml_builder.py` | **1:1** — teuer erarbeitetes Regelwissen |
| KoSIT-Validator-Anbindung | `modules/kosit_validator.py`, `validation/` | **1:1** |
| Plausi-Prüfung vor Rendern | `modules/invoice_validator.py` | 1:1, ggf. Feldergänzung |
| Oracle-Verbindung, Fernet-Crypto, Config, Logging | `core/` | **1:1** |
| Web-UI, Setup-Wizard, Status, Retry, Archiv, SQL-Editor | `slim/api_slim/`, `slim/frontend/` | 1:1, Labels anpassen |
| Archiv + Audit-JSONL | `slim/core_slim/archive_fs.py`, `audit_jsonl.py` | **1:1** |
| Inkrementeller Auto-Updater (GitHub-API) | `slim/core_slim/updater.py` | 1:1, Repo-Name tauschen |
| Online-Installer, NSSM-Dienst, portable Python/JRE | `install_online.ps1`, `slim/install/` | 1:1, Pfade/Dienstname |
| **4 SQL-Abfragen** | `sql/*.sql` | **neu gegen OPERA** |
| **Auslöser** (WMAI/BLOCKSEND-Trigger) | `slim/api_slim/trigger_sql.py` | **neu — offen, s. u.** |
| **Zustellung** (Anhang an Suite8-Mail) | `modules/suite8_mailer.py` | **neu — offen, s. u.** |
| Rechnungsnummer aus Mailbetreff | `modules/suite8_pattern.py` | entfällt evtl. ganz |
| Daten-Aufbereitung/Join | `modules/invoice_fetcher.py` | Struktur bleibt, SQL-Namen tauschen |

Grob: **~85 % des Codes ist wiederverwendbar**, der PMS-Adapter ist die Arbeit.

## Der eine echte Architektur-Unterschied

Suite8 hat mit `WMAI` eine **Mail-Warteschlange in der Datenbank**. Genau daran
hängt sich Slim an: Mail anhalten → XML anhängen → freigeben.

OPERA V5 hat diesen Haken so nicht. Damit stehen drei Varianten offen — die
Entscheidung fällt nach dem Blick ins Data Dictionary:

- **A — Eigener Versand.** App erkennt neue/abgeschlossene Rechnungen, baut das
  XML und verschickt selbst per SMTP (PDF holt sie sich aus dem OPERA-Ablagepfad
  oder erzeugt gar keins). Am unabhängigsten, aber die App wird zum Mailversender
  und braucht die Empfängerlogik.
- **B — Dateiablage.** App legt `<Rechnungsnr>.xml` in einen Ordner bzw. reicht
  es an einen bestehenden Rechnungsversand/Archivierer weiter. Am schlanksten,
  Zustellung bleibt beim vorhandenen Prozess.
- **C — Anhängen an OPERA-Versand.** Nur falls OPERA V5 eine ähnliche Queue-
  Tabelle für Mailversand hat wie Suite8. Dann exakt das Slim-Modell.

**Empfehlung bis zum Gegenbeweis: B als erste Stufe** (schnell live, kein Risiko
am Mailweg), A als Ausbaustufe. C nur, wenn das DD eine Queue hergibt.

## Weitere OPERA-Besonderheiten, die den Entwurf berühren

- **Multi-Property.** OPERA-Tabellen tragen durchgehend `RESORT`. Verkäuferdaten
  (Firmierung, Adresse, USt-IdNr., IBAN, Kontakt) müssen **pro Property**
  konfigurierbar sein. In Suite8-Slim kamen sie aus einer flachen `WUSS`-Tabelle
  und einer `hotel.json` — hier wird daraus `properties[<RESORT>]`.
- **Zwei Rechnungsquellen.** Gastrechnung (Folio bei Check-out) und
  Debitorenrechnung (AR / City Ledger). Für B2B-XRechnung ist meist die
  **AR-Seite** die relevante — dort sitzt auch der Behördenkunde. Vermutlich
  müssen beide Wege bedient werden.
- **Leitweg-ID (BT-10).** Suite8 nutzte ein Zusatzfeld am Profil (`XMNR`,
  Typ `DXR`). In OPERA braucht es ein Pendant — UDF am Profil, AR-Konto-Feld
  oder Attribut. Muss im DD gesucht werden.
- **Steuerlogik.** Suite8 rechnet brutto und leitet netto ab. OPERA kennt
  eigene Steuer-Transaktionscodes und je nach Setup „tax inclusive"/„exclusive".
  Ob die Zeilenwerte netto oder brutto ankommen, entscheidet über die Formeln
  in `invoice_lines` — der häufigste Fehlerherd bei Cent-Differenzen (BR-CO-*).
