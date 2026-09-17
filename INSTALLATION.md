# Installation — Schritt für Schritt

Diese Anleitung setzt **kein Vorwissen** voraus. Die Anwendung läuft auf
**Windows** und auf **Rocky Linux 9/10** — beides ist hier beschrieben.

Sie brauchen: einen Rechner oder Server, der dauerhaft läuft und die
OPERA-Datenbank erreicht, sowie Administrator- bzw. `sudo`-Rechte darauf.

Ein Oracle-Client wird **nicht** gebraucht — auf keinem der beiden Systeme.

---

# Der einfache Weg: der Installer

Der Installer erledigt alles: Python und Java installieren, Programmumgebung
anlegen, das KoSIT-Prüfprogramm samt Regelwerk von GitHub laden, Konfiguration
aus der Vorlage anlegen, Dienst einrichten, Port freigeben und zum Schluss
prüfen, ob die Anwendung antwortet.

**Nichts geschieht ungefragt.** Zu Beginn zeigt er, was insgesamt vorgesehen
ist. Vor jedem einzelnen Punkt sagt er an, *was* geladen wird, *woher* und
*wozu*, und fragt dann:

```
   ->     KoSIT-Validator und die deutschen Prüfregeln laden (zusammen etwa 60 MB)
          Quelle: github.com/itplr-kosit
          Zweck:  prüft jede erzeugte Rechnung, bevor sie hinausgeht
          Fortfahren? [J/n]
```

**Enter bedeutet Ja.** Wer `n` eingibt, überspringt nur diesen einen Punkt — der
Rest läuft weiter. Am Ende steht, was übersprungen wurde und wie es nachzuholen
ist.

Er zeigt nach jedem Schritt `[ok]` oder eine Meldung, was fehlt, und nennt am
Ende Adresse und Startpasswort. **Dauer: 10 bis 20 Minuten**, überwiegend
Wartezeit. Der Rechner braucht dafür Internetzugang.

Er **bricht nicht ab**, wenn etwas nicht klappt: Fehlt zum Beispiel Java, läuft
der Rest weiter, und am Ende steht, was nachzuholen ist.

> Für einen unbeaufsichtigten Lauf — etwa beim Ausrollen auf mehrere Rechner —
> gibt es den Schalter `-OhneRueckfrage` (Windows) bzw. `--ohne-rueckfrage`
> (Linux). Dann wird alles ohne Nachfrage bestätigt. **Ohne diesen Schalter und
> ohne Terminal bricht der Installer ab, statt stillschweigend alles zu laden.**

## Windows

1. Kopieren Sie den Projektordner nach `C:\XRechnung`
2. Öffnen Sie den Ordner `C:\XRechnung\install`
3. Doppelklick auf **`INSTALLIEREN.cmd`**
4. Windows fragt: „Möchten Sie zulassen, dass durch diese App Änderungen
   vorgenommen werden?" — mit **Ja** bestätigen

> Schalter für Sonderfälle, in einer PowerShell mit Administratorrechten:
> `install\installieren.ps1 -OhneRueckfrage -OhneDienst -OhnePruefer -Port 9000`

> **Ordnerrechte.** Der Installer schneidet die Vererbung von `C:\` ab: Auf
> `C:\XRechnung` haben danach nur noch **SYSTEM** (der Dienst) und die
> **Administratoren** Zugriff. Sonst könnte jeder angemeldete Benutzer
> `config\secret.key` und die Zugangsdaten lesen und Programmdateien ändern,
> die der Dienst als SYSTEM ausführt. Folge: `run.cmd` von Hand geht nur noch in
> einer Eingabeaufforderung **als Administrator**. Ein erneuter Lauf des
> Installers setzt die Rechte wieder so.

## Rocky Linux

1. Kopieren Sie den Projektordner nach **`/opt/xrechnung`**

   > **Nicht nach `/root` oder in ein Heimatverzeichnis.** Der Dienst läuft
   > unter einem eigenen Konto und blendet `/root` und `/home` aus
   > (`ProtectHome=true`). Der Start scheitert dort mit
   > „203/EXEC — Unable to locate executable", obwohl die Datei vorhanden ist.
   > Der Installer bricht in diesem Fall mit einem Hinweis ab.

2. Im Terminal:

```
cd /opt/xrechnung
sudo ./install/installieren.sh
```

> Schalter für Sonderfälle:
> `sudo ./install/installieren.sh --ohne-rueckfrage --ohne-dienst --ohne-pruefer --port 9000 --benutzer xrechnung`

Der Installer legt ein eigenes Dienstkonto `xrechnung` an, richtet einen
systemd-Dienst ein, der beim Hochfahren mitstartet, und gibt den Port in
firewalld frei.

**Was der Installer nicht tut:** Ihre Zugangsdaten für Datenbank und Mailserver
eintragen. Das geschieht danach in der Oberfläche — siehe *Erstanmeldung* und
*Einstellungen*.

---

# Erstanmeldung

1. Rufen Sie die Adresse auf, die der Installer genannt hat —
   `http://<Servername>:8022`
2. Öffnen Sie die Datei **`ERSTES_PASSWORT.txt`** im Ordner `config`
   (Windows: `C:\XRechnung\config\`, Linux: `/opt/xrechnung/config/`).
   Der Installer zeigt den Inhalt auch am Ende in seinem Fenster an
3. Darin stehen Benutzername (`admin`) und ein zufälliges Startpasswort — beides
   auf der Anmeldeseite eingeben
4. Oben auf **„Benutzer"** klicken und **sofort ein eigenes Passwort setzen**
   (mindestens 10 Zeichen)
5. Sie werden abgemeldet und melden sich mit dem neuen Passwort wieder an.
   `ERSTES_PASSWORT.txt` verschwindet dabei von selbst

> Das Startpasswort ist bei jeder Installation ein anderes. Es steht nicht in
> dieser Anleitung und lässt sich nicht erraten.

Unter Linux gehört die Datei dem Dienstkonto. Falls Sie sie nicht öffnen können:
`sudo cat /opt/xrechnung/config/ERSTES_PASSWORT.txt`

---

# Einstellungen

Klicken Sie oben auf **„Konfiguration"** und tragen Sie ein:

**Datenbank** — Host, Port, Service, Benutzer und Passwort des Lesezugangs.
Danach unten **„Datenbank testen"**. Es muss eine Oracle-Versionszeile
erscheinen.

**Haus** — USt-IdNr., Kontaktname für die Buchhaltung, Telefon, E-Mail, IBAN,
BIC, Kontoinhaber, Zahlungsziel in Tagen. Diese Angaben stehen später auf jeder
Rechnung; OPERA liefert sie nicht.

**Mailversand** — Server, Port, Anmeldedaten, Absenderadresse. Dazu:
- **BCC**: Diese Adresse bekommt **jede** verschickte Rechnung in Blindkopie
- **Erlaubte Empfänger**: Solange hier etwas steht, geht **keine** Mail an eine
  andere Adresse. Zu Beginn die eigenen Domains eintragen und erst leeren, wenn
  wirklich an Kunden versendet werden soll

Danach **„Testmail senden"** an die eigene Adresse.

**Validierung** — die Pfade stehen nach dem Installer meist richtig. Der Kasten
darunter zeigt, ob alles gefunden wurde.

**Automatik** — Takt und Wartezeit. **Testlauf eingeschaltet lassen.**

Zum Schluss **„Speichern"**.

---

# Eine Woche mitlaufen lassen

Mit eingeschaltetem Testlauf sammelt das Programm Rechnungen, erzeugt XML und
prüft sie — **verschickt aber nichts**. Sehen Sie täglich in die Liste:

- Stehen die richtigen Rechnungen darin?
- Stimmen die Beträge mit den PDF-Rechnungen überein?
- Gibt es Rechnungen mit Status **fehler**? Was steht dort?

Erst wenn eine Woche unauffällig war, den Testlauf abschalten.

---

# Der Weg von Hand

Das folgende braucht nur, wer den Installer nicht nutzen kann oder einen
einzelnen Punkt nachholen will.

## Windows von Hand

**1. Python.** <https://www.python.org/downloads/windows/> öffnen, den
„Windows installer (64-bit)" für **Python 3.12** laden, starten und **unbedingt
den Haken bei „Add python.exe to PATH"** setzen. Prüfen: `Windows+R`, `cmd`,
`python --version` → es muss eine 3.12er-Nummer erscheinen.

**2. Java.** <https://adoptium.net/de/temurin/releases/> — Windows, x64, **JRE**,
Version 21, `.msi` installieren. Prüfen: `java -version`.

**3. Programm ablegen.** Projektinhalt nach `C:\XRechnung` kopieren.

**4. Prüfprogramm.** Von
<https://github.com/itplr-kosit/validator/releases> die Datei
`validationtool-<Version>-distribution.zip` laden, entpacken, daraus
`validationtool-<Version>-standalone.jar` nach `C:\XRechnung\validation\`
kopieren und in **`validationtool.jar`** umbenennen.
Von <https://github.com/itplr-kosit/validator-configuration-xrechnung/releases>
das Regelpaket laden und den Inhalt nach
`C:\XRechnung\validation\xrechnung-3.0.2\` entpacken — dort muss `scenarios.xml`
liegen.

**5. Erster Start.** Doppelklick auf `run.cmd`. Beim ersten Mal dauert es zwei
bis drei Minuten. Steht `Uvicorn running on http://0.0.0.0:8022`, läuft es.
**Fenster offen lassen** — schließen beendet das Programm.

**6. Dienst.** <https://nssm.cc/download>, ZIP laden, entpacken, aus `win64` die
`nssm.exe` nach `C:\XRechnung\install` kopieren. Dann Rechtsklick auf
`install\dienst_einrichten.cmd` → **„Als Administrator ausführen"**.

**7. Ordnerrechte.** In einer Eingabeaufforderung als Administrator — die SIDs
statt Namen, damit es auch auf einem deutschen Windows greift:

```
icacls C:\XRechnung /setowner *S-1-5-32-544 /T /C /Q
icacls C:\XRechnung /reset /T /C /Q
icacls C:\XRechnung /grant:r *S-1-5-18:(OI)(CI)F *S-1-5-32-544:(OI)(CI)F /C /Q
icacls C:\XRechnung /inheritance:r /C /Q
```

Danach haben nur SYSTEM und Administratoren Zugriff (siehe oben unter Windows).

## Rocky Linux von Hand

**1. Python und Java.**

```
sudo dnf install -y python3.12 python3.12-pip java-21-openjdk-headless
```

**2. Programm ablegen.** Projektinhalt nach `/opt/xrechnung` kopieren.

**3. Programmumgebung.**

```
cd /opt/xrechnung
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

**4. Prüfprogramm.** Die beiden Pakete wie oben von GitHub laden. Danach muss es
`/opt/xrechnung/validation/validationtool.jar` und
`/opt/xrechnung/validation/xrechnung-3.0.2/scenarios.xml` geben.

**5. Erster Start.** `./run.sh` — beenden mit `Strg+C`.

**6. Dienst.**

```
sudo ./install/dienst_einrichten.sh
```

Das legt das Dienstkonto an, schreibt `/etc/systemd/system/xrechnung.service`,
startet den Dienst und gibt den Port in firewalld frei. Optional:
`sudo ./install/dienst_einrichten.sh BENUTZER PORT REPO ZWEIG`. Ohne Angabe
kommen Repository und Zweig aus der bestehenden Unit, sonst aus
`config/app.json`, sonst aus der Vorlage. Das Skript funktioniert auf einer
flachen Installation ebenso wie aus `programm/aktuell/install/`; die fertige
Unit lässt sich vorab ansehen mit `install/unit_erzeugen.sh`.

---

# Wenn etwas nicht geht

## Beide Systeme

| Beobachtung | Ursache und Abhilfe |
|---|---|
| „Datenbank testen" meldet `DPY-3015` | Die Datenbank nutzt ein altes Passwortverfahren. In der Konfiguration „Thick-Modus" anhaken und den Oracle-Client-Pfad eintragen |
| „Datenbank testen" meldet `DPY-6005` oder Zeitüberschreitung | Der Server erreicht die Datenbank nicht — Firewall, Host oder Port prüfen |
| Kollegen kommen nicht auf die Seite | Port nicht freigegeben, oder das eigene Netz steht nicht unter „Erlaubte Netze" |
| Der Validierungskasten bleibt rot | Pfade prüfen — die Datei muss wirklich `validationtool.jar` heißen |
| Passwort vergessen | `config/users.json` löschen und den Dienst neu starten. Es wird wieder ein `ERSTES_PASSWORT.txt` erzeugt |

## Nur Windows

| Beobachtung | Abhilfe |
|---|---|
| „Der Befehl python ist entweder falsch geschrieben..." | Der Haken bei „Add python.exe to PATH" fehlte. Python erneut installieren |
| Schwarzes Fenster geht sofort wieder zu | `cmd` öffnen, `cd C:\XRechnung`, `run.cmd` eingeben — dann bleibt die Fehlermeldung stehen |
| Dienst läuft nicht | `logs\dienst.log` ansehen |

## Nur Linux

| Beobachtung | Abhilfe |
|---|---|
| Dienst startet nicht | `journalctl -u xrechnung -n 50` zeigt den Grund |
| „Permission denied" auf `config/` oder `data/` | `sudo chown -R xrechnung:xrechnung /opt/xrechnung/{config,data,logs}` |
| Seite nur lokal erreichbar | `sudo firewall-cmd --permanent --add-port=8022/tcp && sudo firewall-cmd --reload` |
| Dienst neu starten | `sudo systemctl restart xrechnung` |
| Läuft der Dienst? | `systemctl status xrechnung` |

---

# Was wohin gehört

| Ordner | Inhalt | In die Sicherung? |
|---|---|---|
| `config` | Einstellungen, Zugänge, **`secret.key`** | **ja, unbedingt** |
| `data` | Arbeitsliste, erzeugte XML, Archiv | ja |
| `logs` | Protokolldateien | nein |
| `validation` | Prüfprogramm und Regeln | nein, jederzeit neu ladbar |
| `install` | Einrichtung, Dienstverwaltung | nein |
| `app`, `sql` | das Programm | nein, kommt über die Aktualisierung |

Ohne `config/secret.key` sind die gespeicherten Passwörter nicht mehr lesbar.
