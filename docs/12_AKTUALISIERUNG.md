# Aktualisierung — Befund und Konzept

Der erste Teil beschreibt den Befund, der zweite das Verfahren, das daraus
entstanden ist. Beides ist inzwischen umgesetzt; der Aufbau des Dokuments folgt
dem Weg dorthin, weil die Begründungen sonst in der Luft hingen.

---

## Was passiert ist

Die erste Aktualisierung über die Oberfläche brach ab mit

    PermissionError: [Errno 13] Permission denied: '/opt/xrechnung/app'

Die Ursache ist keine Verkettung von Zufällen, sondern die Anlage selbst:

- `install/installieren.sh` übergibt **nur** `config/`, `data/` und `logs/` dem
  Dienstkonto. Alle Programmverzeichnisse bleiben `root:root`.
- Der Dienst läuft als `xrechnung`.
- `updater.anwenden()` löscht und schreibt **in** `/opt/xrechnung` — also in
  einem Verzeichnis, das dem Dienst nicht gehört.

**Der gefährliche Teil ist nicht der Abbruch, sondern wo er abbricht.** Der
Austausch läuft Bereich für Bereich: löschen, neu schreiben, nächster. Hier
scheiterte gleich der erste Löschversuch, deshalb blieb die Installation
unversehrt. Bei anderer Reihenfolge wäre sie halb ersetzt gewesen — und
`update_stand.json` wird erst am Ende geschrieben, der nächste Versuch hätte
also von vorn begonnen und Trümmer vorgefunden.

---

## 1. Notbremse (umgesetzt)

`updater.schreibrechte_pruefen()` läuft **vor** dem ersten Löschen und prüft
für jeden Bereich das Elternverzeichnis auf Schreib- und Betretungsrecht.
Fehlt eines, bricht die Aktualisierung ab, bevor sie etwas anfasst, und die
Meldung nennt Benutzer, Verzeichnis und den Befehl zur Abhilfe.

Geprüft wird das **Eltern**verzeichnis: Ein Verzeichnis zu ersetzen heißt, im
Elternverzeichnis zu löschen und anzulegen. Ob die Datei selbst beschreibbar
ist, sagt darüber nichts.

Zusätzlich meldet die Aktualisierung jetzt, wenn `requirements.txt` neue
Einträge bekommen hat. Nachinstalliert wird nicht — das braucht Rechte auf die
venv und kann dauern —, aber der Hinweis steht in der Meldung. Vorher wäre der
Dienst nach dem Neustart mit einem ImportError stehengeblieben, ohne dass
jemand den Zusammenhang gesehen hätte.

Das behebt die Gefahr, nicht die Ursache. Aktualisieren lässt sich damit
weiterhin nur von Hand als root.

---

## 2. Vorschlag: Freigabeverzeichnisse mit Umschalter

### Aufbau

    /opt/xrechnung/                 root:root      der Systemverwalter
    ├── programm/                   xrechnung
    │   ├── freigaben/
    │   │   ├── <zeitstempel>-<sha>/      die neue Freigabe
    │   │   └── <zeitstempel>-<sha>/      die vorige
    │   └── aktuell -> freigaben/<zeitstempel>-<sha>
    ├── config/  data/  logs/       xrechnung
    ├── .venv/                      xrechnung
    └── install/                    root:root

Der Dienst startet mit `WorkingDirectory=/opt/xrechnung/programm/aktuell` und
findet seine Daten über drei Umgebungsvariablen in der Unit:

    XRECHNUNG_CONFIG_DIR=/opt/xrechnung/config
    XRECHNUNG_DATEN_DIR=/opt/xrechnung/data
    XRECHNUNG_LOG_DIR=/opt/xrechnung/logs

Die ersten beiden gibt es schon — sie sind für den Selbsttest entstanden, der
sonst die echte Konfiguration überschrieb. Für die dritte fehlt eine Zeile in
`main.py`.

### Ablauf einer Aktualisierung

Alles als Dienstkonto, ohne root:

1. Archiv herunterladen und nach `programm/freigaben/<zeitstempel>-<sha>.neu/`
   auspacken. Die bestehende Installation wird dabei **nicht angefasst**.
2. Hat sich `requirements.txt` geändert: `pip install -r` in die venv. Sie
   gehört dem Dienstkonto, das geht ohne root.
3. Verzeichnis auf den endgültigen Namen umbenennen.
4. **Umschalten:** neuen Symlink unter Hilfsnamen anlegen, dann
   `os.replace()` auf `aktuell`. Ein einziger Schritt, der entweder ganz oder
   gar nicht passiert.
5. `update_stand.json` schreiben, Dienst beenden — systemd startet ihn neu.
6. Alte Freigaben aufräumen, die letzten drei bleiben stehen.

Scheitert Schritt 1, 2 oder 3, läuft die alte Fassung unverändert weiter. Es
gibt keinen Zustand „halb ersetzt" mehr.

### Zurückrollen

`aktuell` auf die vorige Freigabe zeigen lassen und neu starten. Ein Befehl,
und in der Oberfläche ein Knopf mit der Liste der letzten Stände. Das ist der
eigentliche Gewinn: Heute gibt es zwar eine Sicherung unter `data/sicherung-*`,
aber kein Verfahren, sie zurückzuspielen.

---

## 3. Wer darf schreiben?

Die Frage aus dem Befund lautet: Programmdateien dem Dienstkonto übergeben,
oder ein privilegierter Helfer?

**Vorschlag: dem Dienstkonto übergeben** — aber nur `programm/`, `config/`,
`data/`, `logs/` und `.venv/`. `/opt/xrechnung` selbst, `install/` und die
systemd-Unit bleiben bei root.

Die Begründung ist unbequem, aber sie trägt: **Der Dienst kann schon heute
Code aus dem Internet holen und ausführen — das ist die Aktualisierung.** Wer
den Dienst übernimmt, kann eine Aktualisierung auslösen; und er kann die
Konfiguration schreiben, in der Repository und Zweig stehen. Der Gewinn eines
privilegierten Helfers wäre also klein, solange dieser Helfer die Quelle aus
derselben Konfiguration liest.

Was der Zuschnitt oben trotzdem verhindert: Ein übernommener Dienst kann nicht
ändern, **wie** er gestartet wird (Unit gehört root), kann die Installer-Skripte
nicht verändern und kann außerhalb seines eigenen Baums nichts anlegen.

**Wenn die Trennung trotzdem gewünscht ist**, ist der saubere Weg nicht ein
sudo-Recht auf `systemctl`, sondern:

- eine Unit `xrechnung-update.service` (`Type=oneshot`, root),
- die Repository und Zweig aus einer **root-eigenen** Datei liest, nicht aus
  `config/app.json`,
- ausgelöst über eine eng gefasste sudoers-Regel auf genau diesen einen
  Aufruf.

Erst diese Kombination bringt etwas: Der Dienst darf dann anstoßen, aber nicht
mehr bestimmen, was installiert wird. Ohne den root-eigenen Quellverweis ist
der Helfer Aufwand ohne Wirkung.

---

## 4. Windows

Unter Windows läuft der Dienst über NSSM, und das Rechteproblem tritt dort
nicht auf — der bestehende Weg funktioniert.

**Vorschlag: Windows behält den bisherigen Austausch an Ort und Stelle.**
Symbolische Verknüpfungen brauchen dort besondere Rechte; Junctions gehen
zwar ohne, lassen sich aber nicht in einem Schritt umhängen — der Vorteil des
Verfahrens wäre also gerade weg.

Gemeinsam bleiben die Rechteprüfung aus Punkt 1, der Hinweis auf neue
Abhängigkeiten und die Meldungen. Parität heißt gleiches Verhalten, nicht
gleiche Mechanik.

---

## 5. Was noch auffiel

- `update_stand.json` und `data/sicherung-*` müssen dem schreibenden Konto
  gehören. Eine von root angelegte Datei blockiert sonst den nächsten Lauf.
  Nach jeder Handarbeit als root gehört ein `chown -R` hinterher.
- Der Neustart ist unkritisch: `os._exit(0)` und `Restart=always`. Dafür
  braucht es keine Rechte, und daran ändert sich nichts.

---

## Umgesetzt

Alles oben Beschriebene ist gebaut. Drei Punkte kamen aus der Gegenprüfung
hinzu und waren wichtiger als der Rest:

### Programm oder Bestand — die Frage, die vorher niemand stellen musste

Solange alles flach in einem Verzeichnis lag, hatten Programmdateien und
Bestand dieselbe Wurzel. Mit Freigaben fallen sie auseinander, und **zwei
Stellen lösten relative Pfade aus der Konfiguration gegen das Programm auf**:

- `ablauf._ordner()` für `ablage.xml_ordner` = `data/xml` und
  `ablage.archiv_ordner` = `data/archiv`. Die erzeugten Rechnungen wären in
  der Freigabe gelandet — und das Aufräumen alter Freigaben hätte sie nach der
  dritten Aktualisierung gelöscht. **Aufbewahrungspflichtige Belege, still,
  ohne Fehlermeldung.**
- `validate._pfad()` für den KoSIT-Validator. `validation/` ist 16 MB groß und
  liegt bewusst nicht im Repository; in einer frischen Freigabe gibt es das
  Verzeichnis nicht. Weil `validierung.pflicht` gesetzt ist, wäre ab dem
  Umschalten **jede** Rechnung gescheitert.

Beides ist behoben: `app/pfade.py` beantwortet die Frage einmal zentral.
`PROGRAMM` ist die Wurzel des Codes, `BASIS` die der Installation; Pfade aus
der Konfiguration gehen über `pfade.im_bestand()`.

Aus `__file__` lässt sich `BASIS` **nicht** zurückgewinnen — ein Symlink auf
das Arbeitsverzeichnis taucht dort nicht auf, weder mit noch ohne `resolve()`.
Die Angabe muss von außen kommen; deshalb vier Umgebungsvariablen in der Unit,
nicht drei.

### Der Quellverweis gehört in die Unit

`config/app.json` gehört dem Dienstkonto. Solange der Austausch an den Rechten
scheiterte, war das folgenlos — mit dem Umbau fällt genau diese Bremse weg.
Danach könnte ein übernommener Dienst `update.repo` auf ein fremdes Repository
richten, eine Aktualisierung auslösen und sich dauerhaft einnisten,
neustartfest.

`XRECHNUNG_UPDATE_REPO` und `XRECHNUNG_UPDATE_ZWEIG` stehen deshalb in der
**root-eigenen** Unit und gewinnen gegen `app.json`.

Was dabei **nicht** geschützt ist: `install/` liegt im Programm und gehört
damit dem Dienst — es wird bei jeder Aktualisierung mitersetzt, und das ist
gewollt. Geschützt ist die Unit selbst, also *wie* der Dienst startet und
*woher* er sich aktualisiert. Das ist der Punkt, auf den es ankommt. In der Oberfläche werden
sie dann nur noch angezeigt. Kein zweiter Dienst, keine sudoers-Regel — die
Unit ist die root-eigene Datei, die es dafür braucht.

Dazu `ProtectSystem=strict` mit `ReadWritePaths` auf die vier Ordner: Der
Dienst kann außerhalb seines Baums nichts schreiben, unabhängig von
Dateirechten.

### Prüfen, bevor es als erledigt gilt

`install/umstellen_freigaben.sh` verschiebt (nicht kopiert) die
Programmbereiche in die erste Freigabe, setzt Eigentümer, schreibt die Unit
und **prüft danach drei Dinge**: dass die Anwendung antwortet, dass der
Validator gefunden wird, und dass die Rechnungsablage in den Bestand zeigt.

„Der Dienst läuft" ist ausdrücklich **kein** Erfolgskriterium: Er läuft auch
mit kaputtem Validierungspfad, und der Archivpfad fiele erst nach der dritten
Aktualisierung auf — dann ist er nicht mehr zu reparieren.

Scheitert etwas, schiebt das Skript zurück und stellt die alte Unit wieder
her. Deshalb verschieben statt kopieren: Es gibt zu jedem Zeitpunkt genau
einen Ort, an dem die Dateien liegen.

SELinux wird geprüft und gemeldet, nicht vorausgesetzt. Auf `Enforcing` fragt
das Skript nach, statt weiterzulaufen.

## Nachtrag aus der Gegenprüfung

Fünf Befunde am Umstellungsskript, bevor es je gelaufen ist. Der erste war der
gefährlichste:

**Die Prüfung lief im falschen Verzeichnis.** `sys.path.insert(0, ".")` und ein
`cd`, das erst danach kam — nach dem Verschieben liegt im Arbeitsverzeichnis
kein `app/` mehr. Der `ModuleNotFoundError` landete durch `2>&1 || true` in
einer Variablen, die Prüfung fand „VALIDATOR bereit" nicht und meldete
**nach gelungener Umstellung einen Fehlschlag** — samt Rückweg in der Ausgabe.
Wer dem folgt, zerlegt eine Installation, die in Ordnung war. Der Suchpfad
kommt jetzt aus `XRECHNUNG_BASIS`, und ein Traceback in der Prüfung wird als
solcher gemeldet, statt als „Validator fehlt".

**Die Beleg-Probe fand nie statt.** `beispiele/` lag im Repository, stand aber
in keiner Programmliste — es war weder Programm noch Bestand, sondern
unbeantwortet. Es gehört zum Programm, denn was im Repository liegt, wird
ausgeliefert.

**Eine Zusicherung stimmte nicht:** „install/ bleibt bei root". `install/`
liegt im Programm und gehört nach der Umstellung dem Dienst. Die Aussage ist
gestrichen, nicht der Code danach gebogen.

**`[[ ]] && cmd` unter `set -e`** mit ERR-trap: Trifft die Bedingung nicht, ist
der Rückgabewert 1 und der trap schiebt mitten in einer fehlerfreien
Umstellung zurück. `|| true` angehängt.

**Der Rückweg** stellt jetzt auch die Eigentümer wieder her — sonst käme eine
flache Installation mit dienst-eigenen Programmdateien zurück, also genau der
Zustand, vor dem die Notbremse warnt.

### pip läuft doch automatisch

Im alten Ablauf war ein Hinweis richtig: Ein pip-Lauf von Minuten hätte den
Dienst so lange stehen lassen. Im Freigabenbetrieb dreht sich das um — die
alte Fassung läuft weiter, der Lauf kostet keine Verfügbarkeit. Ein Hinweis
dagegen wird überlesen, und dann schaltet die Aktualisierung auf eine Freigabe
um, deren Abhängigkeiten fehlen: Neustartschleife, nach dem Umschalten.

`pip` läuft deshalb **vor** dem Umschalten, mit Zeitgrenze, und ein Fehlschlag
heißt: nicht umschalten. Der schlimmste Fall ist dann „Aktualisierung
abgebrochen, alte Fassung läuft weiter" — der Fall, für den das ganze
Verfahren gebaut ist.

### run.sh und run.cmd

Beide erkennen jetzt, ob sie in einer Freigabe liegen, und setzen die vier
Variablen selbst. Ohne das greift der Rückfall in `pfade.py`, `BASIS` wird
gleich `PROGRAMM` — und wer zum Fehlersuchen von Hand startet und dabei eine
Rechnung erzeugt, schreibt sie in die Freigabe. Derselbe Datenverlust wie im
ursprünglichen Blocker, nur durch eine andere Tür, und er trifft ausgerechnet
den, der gerade sucht.

### Der erste Versuch brach ab, bevor etwas geschah

`bash -n` hatte das Skript für sauber erklärt. Beim Lauf auf dem Server:

    install/umstellen_freigaben.sh: command substitution: line 93:
    syntax error near unexpected token `||'

Ein Heredoc **in einer Kommandosubstitution** verträgt sich nicht mit einem
`[[ ]] &&` davor: Bash schiebt beim erneuten Parsen das `|| true` hinter den
Heredoc-Körper, übrig bleibt das Fragment `|| true)"`.

**`bash -n` kann diese Klasse grundsätzlich nicht finden** — der Inhalt einer
Kommandosubstitution wird erst beim Ausführen geparst. Der Selbsttest hat
deshalb jetzt eine eigene Regel dafür (`$(` und `<<` und `||` auf einer
Zeile), geprüft an der kaputten und an der heilen Form. `shellcheck` fände es
als SC1009/SC1073, ist hier aber nicht installiert.

Die beiden anderen Stellen derselben Bauart liefen zwar — sie haben kein
`[[ ]] &&` davor —, sind aber trotzdem auf die ausgeschriebene Form gebracht:
Zwei Schreibweisen für dasselbe laden dazu ein, die falsche zu kopieren.

Nichts war passiert: Der Abbruch liegt vor Schritt 1, der Dienst lief
durchgehend weiter.

## Die Umstellung einer bestehenden Installation

Der Umbau einer flachen Installation auf Freigaben ist einmalig und geht
schnell: **Standzeit des Dienstes eine Sekunde**, keine Neustartschleife.
Verschieben auf derselben Platte ist ein Umhängen von Verzeichniseinträgen,
kein Kopieren — die Größe der Installation spielt dafür keine Rolle.

Die drei Prüfungen danach:

    [ok] Die Anwendung antwortet                     (/health 200, / 303)
    [ok] Der Validator wird gefunden                 BELEG rechnung_beispiel.xml OK
    [ok] Die Rechnungsablage zeigt in den Bestand    <BASIS>/data/archiv

### Der Beweis, den der Pfad-Check nicht liefert

Dass die Pfade *stimmen*, sagt noch nicht, dass die Anwendung sie auch
*benutzt*. Deshalb zusätzlich eine Rechnung neu erzeugt — nicht versendet, also
wirklich gebaut und nicht aus dem Archiv zurückgegeben — und mitgeschrieben,
woher das Programm lief und wohin die Datei ging:

    PROGRAMM  <BASIS>/programm/freigaben/<zeitstempel>-<sha>
    BASIS     /opt/xrechnung
    ABGELEGT  <BASIS>/data/xml/<belegnummer>.xml
    BEFUNDE   keine

Das Programm lief nachweislich aus der Freigabe, die Rechnung landete im
Bestand. `find` über `programm/` fand kein `data/`, `config/`, `logs/` und
keine XML außerhalb der Vorlagen.

Zweite Gegenprobe: Prüfsummen über **alle** vorhandenen XML vor der Umstellung
und danach — identisch, dieselbe Anzahl. Der Neubau ist bitgleich, der Bestand
über die ganze Umstellung unangetastet.

**Verglichen werden die Inhalts-Hashes, nicht die Liste:**

    find data/xml -name '*.xml' -exec md5sum {} \; | awk '{print $1}' | sort

Der erste Anlauf hashte die ganze Ausgabe von `md5sum` — also **samt der
Pfade darin**. Einmal absolut, einmal relativ aufgerufen, meldete er einen
Unterschied bei völlig unveränderten Dateien und sah wie Datenverlust aus.
Er hatte beim ersten Mal nur zufällig gestimmt, weil beide Läufe denselben
Pfadstil hatten.

Dieselbe Klasse wie `bash -n` weiter oben: eine Kontrolle, die etwas anderes
misst, als sie zu messen scheint — und die dann in beide Richtungen lügen
kann.

### Zustand danach

    /opt/xrechnung          root:root
    ├── programm/           xrechnung   aktuell -> freigaben/<zeitstempel>-<sha>
    ├── config/ data/ logs/ xrechnung
    ├── .venv/              xrechnung   (vorher root:root)
    └── validation/         root:root   (liegen geblieben, wird über BASIS gefunden)

Als Dienstkonto geprüft: Schreibrechte in Ordnung, `aktuell` zeigt richtig.
**Der Dienst kann sich ab jetzt selbst aktualisieren, ohne root** — der
`PermissionError` aus dem Befund ist an der Wurzel weg, nicht nur abgefangen.

### Was am laufenden Server nicht prüfbar war

Dass die Unit gegen `app.json` gewinnt, ist dort nicht zu beobachten: Beide
nennen dasselbe Repository, das Ergebnis wäre in beiden Fällen gleich. Der
Vorrang wäre damit behauptet, nicht belegt.

Der Selbsttest setzt sie deshalb absichtlich gegeneinander und prüft vier
Dinge: dass ohne Unit-Vorgabe `app.json` gilt, dass mit ihr die Unit gewinnt,
dass ein geänderter Eintrag in `app.json` wirkungslos bleibt, und dass die
Oberfläche das Feld dann gar nicht erst zum Bearbeiten anbietet — ein Feld
ohne Wirkung ist schlimmer als keines.

## Erster echter Lauf mit Umschalten

`updater.anwenden()` als **Dienstkonto** mit den Unit-Variablen aufgerufen —
also genau der Weg, den der Knopf in der Oberfläche nimmt. Kein root.

    Prüfen, Herunterladen, Auspacken, Umbenennen, Umschalten, Stand schreiben
                                                              gut eine Sekunde
    Neustart danach: Standzeit unter einer Sekunde, NRestarts=0

`pip` startete **nicht** — `requirements.txt` war unverändert, die Prüfung
kehrt vor dem Aufruf zurück. Kein Aufwand, wo nichts dazugekommen ist.

Beide Freigaben stehen danach vollständig nebeneinander, jede für sich
lauffähig; der Platzbedarf je Freigabe liegt im einstelligen
Megabyte-Bereich — drei Stände aufzubewahren kostet praktisch nichts:

    programm/freigaben/<zeitstempel>-<sha>      die vorige
    programm/freigaben/<zeitstempel>-<sha>      die neue
    aktuell -> freigaben/<zeitstempel>-<sha>

**Der Rückweg ist damit wirklich vorhanden.** Ausgelöst wurde er im laufenden
Betrieb nicht — zurückzurollen, nur um zu sehen ob es geht, wäre dort der
falsche Ort. Das gehört in den Selbsttest, wie der Vorrang der Unit.

### Das Fenster zwischen Umschalten und Neustart

Zwischen beidem lief der Dienst weiter: alte Prozess-ID, alter Code, neue
Freigabe bereits an Ort und Stelle. Erst der Neustart übernimmt sie.

Das Fenster ist damit **beliebig lang und ungefährlich** — man kann in Ruhe
entscheiden, wann neu gestartet wird. Im alten Verfahren war das nicht so:
Dort war die Installation ab dem ersten Löschen in einem Zustand, der keinen
Aufschub duldete.

## Eine Frage, die sich bei jeder Kontrolle lohnt

An einem Tag sind sechs Kontrollen aufgefallen, die etwas anderes gemessen
haben, als sie zu messen schienen:

- `bash -n` fand einen Syntaxfehler nicht, weil der Inhalt einer
  Kommandosubstitution erst beim Ausführen geparst wird
- eine Prüfung las den Kommentar mit, in dem stand, warum etwas *nicht*
  verwendet wird
- eine Prüfsumme über die `md5sum`-Ausgabe hashte die Pfade mit
- ein Zähler für leere Elemente zählte Verschachtelung
- die Prüfung am Ende der Umstellung meldete nach gelungener Arbeit einen
  Fehlschlag, weil sie im falschen Verzeichnis lief
- Anzeige und Entscheidung von `pruefen()` kamen aus zwei verschiedenen
  Rechnungen

**Keine davon ist beim Hinsehen aufgefallen. Jede ist an einem Widerspruch
aufgefallen** — ein Ergebnis passte nicht zu einem anderen, und erst das gab
den Anlass, die Kontrolle selbst anzusehen.

Zwei Fragen, die sich daraus ergeben und beim Bauen wenig kosten:

1. **Kann diese Prüfung überhaupt rot werden?** Einmal mit der kaputten Fassung
   laufen lassen. Eine Prüfung, von der man das nicht gesehen hat, ist eine
   Behauptung.
2. **Kommen Anzeige und Entscheidung aus derselben Rechnung?** Wo eine Meldung
   und ein Knopf dasselbe aussagen sollen, dürfen sie nicht getrennt gerechnet
   werden — sonst sagt die eine Hälfte etwas anderes als die andere, und der
   Anwender glaubt derjenigen, die sichtbar ist.
