# Prototyp — Installation und Betrieb

Stand 09.09.2026. Der Funktionstest (`tools/smoketest.py`) läuft mit
105 Prüfungen grün, und die erzeugte XRechnung ist vom **KoSIT-Validator
angenommen** worden (v1.6.3, Regelwerk 3.0.2, weder Fehler noch Warnungen —
siehe `beispiele/LIESMICH.md`).

Die Anwendung läuft als Dienst auf `xrechnung.example.local` unter
`/opt/xrechnung`. Sie ist aber **noch nie gegen die echte Datenbank und einen
echten Mailserver gelaufen** — das ist der nächste Schritt.

## Was er kann

- **Rechnungen einlesen** — City-Ledger-Rechnungen aus OPERA, wahlweise nur die
  mit hinterlegter Leitweg-ID
- **Alle Profildaten anzeigen** — Anschrift, Steuernummern, Leitweg-ID und
  **alle** E-Mail-Adressen des Empfängers samt Herkunft (Debitorenkonto,
  Profil, primär). Der Anwender wählt das Ziel aus oder trägt es von Hand ein
- **XRechnung erzeugen** — UBL 2.1, mit Rechnungsbezug (BG-3) und
  Anzahlungsbetrag (BT-113) für Rechnungen mit Anzahlung
- **Vorprüfen** — BR-CO-10, BR-CO-15, BR-S-08, BR-DE-15 und die Folio-Klammer
  gegen die OPERA-Zahlen. Was durchfällt, wird **nicht** versendet
- **Versenden** — SMTP mit Anhang XML (und PDF, falls Ordner konfiguriert).
  **Der BCC aus der Konfiguration geht immer mit** und lässt sich in der
  Oberfläche nicht übergehen
- **Automatik** — liest im eingestellten Takt selbständig ein und versendet nach
  einer einstellbaren Wartezeit. Ein Knopf in der Oberfläche schaltet sie ein
  und aus
- **Anmeldung** — Benutzer, Passwort (scrypt), Rollen `ansehen`/`verwalten`,
  Sperre nach Fehlversuchen, Beschränkung auf erlaubte Netze

## Installation

Die Anwendung läuft auf **Windows** und **Rocky Linux 9/10**. Der Installer
erledigt beides: Python, Java, Umgebung, KoSIT-Prüfprogramm,
Konfigurationsvorlage, Dienst und Firewall.

| | Windows | Rocky Linux |
|---|---|---|
| Installer | `install\INSTALLIEREN.cmd` (Doppelklick) | `sudo ./install/installieren.sh` |
| Start von Hand | `run.cmd` | `./run.sh` |
| Dienst | NSSM, `install\dienst_einrichten.cmd` | systemd, `install/dienst_einrichten.sh` |
| Dienstprotokoll | `logs\dienst.log` | `journalctl -u xrechnung` |
| Dienstkonto | Systemkonto | eigenes Konto `xrechnung` |

Ausführlich in [INSTALLATION.md](INSTALLATION.md).

Ein Oracle-Client wird auf **keinem** der beiden Systeme gebraucht: `oracledb`
läuft im Thin-Modus. Nur falls die Datenbank alte Passwort-Verifier nutzt
(Fehler `DPY-3015`), den Thick-Modus einschalten und den Client-Pfad angeben.

## Sicherheitsnetz gegen den falschen Empfänger

Die Empfängerauswahl „alle Profil-E-Mail-Adressen" ist im Testbetrieb die
gefährlichste Stelle der Anwendung: Ein Fehlgriff geht an einen echten Gast oder
Firmenkunden — und eine versendete Rechnung lässt sich nicht zurückrufen.

Deshalb gibt es **`mail.erlaubte_empfaenger`**. Solange die Liste gefüllt ist,
verweigert die Anwendung jeden Versand an eine Adresse, die nicht darauf steht —
im Code geprüft, nicht per Absprache, und ebenso in der Automatik. Einträge sind
ganze Adressen oder `@domain`. Die Vorlage ist mit den eigenen Domains
vorbelegt; **erst leeren, wenn der Versand an echte Kunden bewusst freigegeben
wurde.**

## Erst im Testlauf fahren

`automatik.testlauf` steht anfangs auf **an**: die Anwendung liest ein, baut das
XML und prüft — verschickt aber nichts. So lässt sich eine Woche mitlaufen und
vergleichen, bevor die erste Mail rausgeht. Erst danach abschalten.

## Sicherheit

- Datenbankzugriff **nur lesend** — die Anwendung schreibt ausschließlich in
  ihre eigene SQLite-Datei und die Ablageordner
- Passwörter (Datenbank, SMTP) liegen Fernet-verschlüsselt in `config\app.json`,
  der Schlüssel in `config\secret.key` — diese Datei gehört in die Sicherung und
  **nicht** in eine Freigabe
- Die Oberfläche zeigt Passwörter nie an, nur „gesetzt" oder „nicht gesetzt"
- **Ohne HTTPS wandert das Anmeldepasswort im Klartext durchs Hausnetz.**
  Für den Prototypen im internen Netz vertretbar, für den Dauerbetrieb gehört
  ein Zertifikat davor — siehe `docs/08_ZUGRIFF_UND_ANMELDUNG.md`

## Aufbau

| Datei | Zweck |
|---|---|
| `app/main.py` | Weboberfläche und Routen |
| `app/ablauf.py` | einlesen → prüfen → XML → versenden (für Knopf und Automatik dieselbe Logik) |
| `app/automatik.py` | Takt, Wartezeit, selbständiger Versand |
| `app/opera.py` | Datenzugriff, setzt die SQL aus `sql/opera/` zusammen |
| `app/xml_build.py` | UBL-Erzeugung und rechnerische Vorprüfung |
| `app/mailer.py` | SMTP, BCC immer |
| `app/auth.py` | Anmeldung, Sitzungen, Netzfilter |
| `app/store.py` | SQLite: Arbeitsliste und Protokoll |
| `sql/opera/*.sql` | die Abfragen — anpassbar, ohne Code zu ändern |
| `app/validate.py` | KoSIT-Prüfung, lokal |
| `app/updater.py` | Aktualisierung über GitHub |
| `app/markdown.py` | stellt die Handbücher in der Oberfläche dar |
| `install/` | Installer und Dienstverwaltung für beide Systeme |
| `tools/smoketest.py` | Funktionstest ohne Datenbank |

## Vor dem ersten echten Lauf zu entscheiden

- **Empfänger:** eine reale Rechnung als Datengrundlage, aber eine **interne
  Adresse** als Ziel. Die Whitelist erzwingt das technisch.
- **BCC:** Ist ein stiller Mitleser bei jeder Kundenrechnung gewollt, und ist
  die Adresse richtig? Das gehört bewusst entschieden, nicht übernommen, weil
  es in der Vorlage stand.
- **Der Versand selbst** ist eine nach außen wirkende, nicht zurückholbare
  Handlung. Sie wird vom Haus ausgelöst, nicht von einer Automatik, die
  jemand versehentlich eingeschaltet hat.

## Was noch fehlt

- **KoSIT-Validator angebunden und erprobt.** Die erzeugte Beispielrechnung ist
  angenommen worden. Steht `validierung.pflicht` auf an, wird ohne eingerichteten
  Validator gar nicht versendet. **Die Prüfung läuft ausschließlich lokal** —
  eine fertige XRechnung enthält Käufername, Anschrift und Beträge und gehört
  nie in eine gehostete Prüfseite
- **HTTPS** — siehe oben
- **Rückweg nach einer Aktualisierung** ist vorhanden (Sicherung unter
  `data\sicherung-<Datum>`), aber nur von Hand — es gibt keinen Knopf dafür
- **Testdaten auffrischen.** Drei der 41 Prüfungen rechnen mit echten Beträgen
  der Belege 1400003, 1400017 und 1400002, Stand 08.09.2026. Vor dem
  Echtbetrieb neu ziehen — ein storniertes Original macht den Test rot, ohne
  dass am Code etwas falsch ist
- **Der Linux-Installer ist nie gelaufen.** Geschrieben auf macOS, Syntax
  geprüft — `dnf`, `systemd` und `firewalld` konnten hier nicht getestet werden.
  Dasselbe gilt für den Windows-Installer
- **Erster Lauf gegen die echte Datenbank.** Alle SQL sind gegen die Live-DB
  gegengerechnet, aber die Anwendung selbst hat noch nie eine Verbindung gehabt
