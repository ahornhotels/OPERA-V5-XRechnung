# Handbuch

Für alle, die täglich mit der Anwendung arbeiten. Dieses Handbuch steht auch
**in der Anwendung selbst** — oben im Menü unter „Handbuch". Die Einrichtung
steht in [INSTALLATION.md](INSTALLATION.md), die technischen Hintergründe
in `docs/`.

---

## Was die Anwendung tut

Sie liest abgeschlossene Rechnungen aus OPERA, erzeugt daraus eine **XRechnung**
(die gesetzlich vorgeschriebene elektronische Rechnung im XML-Format), prüft sie
und verschickt sie per E-Mail an den Kunden.

**Sie ändert nichts in OPERA.** Der Zugriff ist ausschließlich lesend — die
Anwendung kann in OPERA nichts verstellen, verschieben oder löschen.

---

## Anmelden

Aufrufen im Browser: `http://<Servername>:8022`

Beim allerersten Mal steht der Zugang in der Datei
`config/ERSTES_PASSWORT.txt` auf dem Server: Benutzer `admin` und ein zufällig
erzeugtes Passwort. **Ändern Sie es sofort** unter „Benutzer" — die Datei wird
dabei automatisch gelöscht.

Es gibt zwei Rollen:

| Rolle | darf |
|---|---|
| **ansehen** | Rechnungen und Protokoll lesen, XML erzeugen und ansehen |
| **verwalten** | zusätzlich einlesen, Rechnungen aufnehmen, Empfänger, Käuferreferenz und Darstellung der Positionen wählen, freigeben, versenden, zurücklegen, Einstellungen ändern, Automatik schalten, Zugänge anlegen, Passwörter anderer Zugänge neu setzen |

**Wird ein Zugang gelöscht oder herabgestuft, wirkt das sofort** — auch auf
eine offene Sitzung. Ein Zugang mit demselben Namen lässt sich nicht
versehentlich überschreiben, und der letzte Zugang mit Verwaltungsrecht lässt
sich nicht löschen.

**Passwort vergessen?** Ein Zugang mit Verwaltungsrecht setzt es unter
„Benutzer" → „Vorhandene Zugänge" neu, ohne das bisherige zu kennen. Laufende
Anmeldungen dieses Zugangs enden dabei sofort, und das Protokoll vermerkt, wer
wessen Passwort gesetzt hat. Das eigene Passwort geht nur oben mit dem
bisherigen — eine offen gelassene Sitzung soll es nicht ändern können.

Nach acht Stunden ohne Anmeldung läuft die Sitzung ab. Nach fünf Fehlversuchen
wird der Zugang kurz gesperrt; die Sperre verlängert sich bei weiteren Versuchen.

---

## Der tägliche Ablauf

### 1. Rechnungen kommen in die Liste

Entweder von selbst (Automatik) oder per Klick auf **„Jetzt einlesen"**. Neben
dem Knopf steht der **Zeitraum in Tagen** — die Vorgabe kommt aus der
Konfiguration und lässt sich für einen einzelnen Lauf übersteuern, etwa um
einmalig 90 Tage nachzuholen.

Nach dem Einlesen steht oben, was passiert ist — zum Beispiel:

> 312 gelesen, 18 neu aufgenommen, 40 bereits bekannt, 6 zur Sichtprüfung,
> 240 ohne Firmenbezug, 8 ausländischer Empfänger

So ist nachvollziehbar, warum aus vielen Rechnungen wenige werden. Wird die
Obergrenze erreicht (Vorgabe 500), sagt die Meldung es — dann gibt es womöglich
mehr, und der Zeitraum sollte kleiner oder die Grenze höher sein.

Aufgenommen werden **nur abgeschlossene Rechnungen** (`INVOICE`/`OK`) des
eingestellten Hauses **mit Firmenbezug**. Rechnungen mit Betrag 0,00 werden
automatisch zurückgelegt, ebenso ausländische Empfänger. Ein negativer Beleg
ohne Anzahlung ist eine **Gutschrift**: Er kommt in die Sichtprüfung (siehe
„Gutschriften“). Ein negativer Beleg *mit* Anzahlung ist meist eine überzahlte
Rechnung und kommt ebenfalls in die Sichtprüfung.

### Zwei Arten von Firmenbezug — und warum das wichtig ist

| Firmenbezug | Was es heißt | Was passiert |
|---|---|---|
| **Empfänger** | Der Rechnungsempfänger selbst ist eine Firma: Firmenprofil, Reisebüro, Gruppe, Debitorenkonto oder gekennzeichnetes Profil | läuft normal weiter, darf automatisch versendet werden |
| **Reservierung** | An der Buchung hängt eine Firma, bezahlt hat aber möglicherweise eine Privatperson | kommt in den Status **prüfung** und wird **nie** automatisch versendet |

Der Unterschied ist kein Formalismus. Der Firmenname an der Rechnung beschreibt
die *Buchung*, nicht den Empfänger: Firma Meyer bucht für Herrn Schulz, Herr
Schulz zahlt selbst — dann steht die Firma auf dem Beleg, die Rechnung geht aber
an ihn. In einem geprüften Bestand betraf das rund jede zehnte Rechnung — und
bei **ausnahmslos allen** hing nachweislich eine Firma an der Reservierung.

**Woran Sie es erkennen:** Die Detailseite zeigt unter „Wer bekommt die
Rechnung?", welche Firma an der Buchung hängt und **worüber bezahlt wurde**.

- **City Ledger** → Debitorenkonto, und das stellt man keiner Privatperson.
  Die Rechnung gehört der Firma.
- **Karte oder bar** → der Gast hat selbst bezahlt. Die Rechnung gehört ihm,
  auch wenn die Firma auf dem Beleg steht.

Das ist kein Näherungswert: Von den Rechnungen mit Privatprofil läuft nur ein
verschwindender Bruchteil über den City Ledger.

### 2. Status verstehen

| Status | Bedeutung |
|---|---|
| **neu** | eingelesen, noch nichts entschieden |
| **prüfung** | Firmenbezug unklar — wird nie automatisch versendet |
| **bereit** | Empfänger ist gewählt, wartet auf den Versand |
| **gesendet** | verschickt, mit Zeitpunkt — geht **nie** ein zweites Mal hinaus |
| **fehler** | etwas stimmt nicht — die Rechnung wird **nicht** automatisch verschickt. Auch ein Versand, dessen Ergebnis unklar blieb, landet hier: Dann steht dabei „Versand begonnen, Ergebnis nicht bestätigt". Erst im Postfach der Blindkopie nachsehen, ob die Mail hinausging |
| **ignoriert** | zurückgelegt, wird nicht mehr angefasst |

### 3. Eine Rechnung ansehen

Klick auf die Rechnungsnummer. Die Seite zeigt drei Bereiche:

**Beleg** — Datum, Beträge, Status und das Ergebnis der Vorprüfung in OPERA.
Interessant ist die Zeile *Positionen = Kopf*: Steht dort links `N` und rechts
`J`, waren Anzahlungen im Spiel — das ist normal und in Ordnung.

**Profil des Empfängers** — Anschrift, Steuernummern, Leitweg-ID und die Anzahl
hinterlegter E-Mail-Adressen. Hier sehen Sie, ob die Stammdaten gepflegt sind.

**Wohin soll die Rechnung gehen?** — alle gefundenen Adressen mit Herkunft
(Debitorenkonto, Zahler, primär). Eine auswählen oder unten von Hand
eintragen, dann **„Empfänger übernehmen"**. Oben steht immer die Adresse, die
am ehesten stimmt.

Die Adressen des **Gastes** stehen bewusst nicht zur Wahl, wenn der Zahler
jemand anderes ist — eine Firmenrechnung gehört nicht in sein privates
Postfach. Hat die Firma keine Adresse, ist das ein Pflegefall in OPERA.

### 4. Prüfen und versenden

**„XML erzeugen"** baut die Rechnung und prüft sie zweifach: erst rechnerisch,
dann mit dem offiziellen KoSIT-Prüfprogramm. Findet eine der beiden Prüfungen
etwas, erscheint es rot — und der Versandknopf bleibt gesperrt.

**„XML ansehen"** öffnet die Datei im Browser.

**„Jetzt versenden"** schickt sie an den gewählten Empfänger, mit dem
eingestellten BCC in Blindkopie.

Lehnt der Mailserver **nur die Blindkopie** ab, ist die Rechnung trotzdem beim
Kunden und steht auf „gesendet". Im Protokoll — auf der Detailseite und unter
„Protokoll" — steht dann ein roter Eintrag „Blindkopie vom Mailserver
abgelehnt" mit der Antwort des Servers. Die Testmail meldet dasselbe direkt.
Kommt die Blindkopie nicht an und steht dort **nichts**, hat der Server sie
angenommen: Dann liegt sie in Spam oder Quarantäne, oder eine Regel hat sie
umgeleitet — das klärt die Nachrichtenablaufverfolgung am Mailserver.

**In „Gesendete Elemente" erscheint die Mail nicht.** Die Anwendung verschickt
direkt über den Mailserver; eine Kopie dort legt nur ein Mailprogramm wie
Outlook an. Dafür ist die Blindkopie da. Ist der Empfänger zugleich die
BCC-Adresse, kommt die Mail nur einmal an — der Server legt doppelte
Empfänger zusammen.

Rechnungen, die **über das Debitorenkonto ausgecheckt** wurden (City Ledger),
bekommen zusätzlich eine **zweite Blindkopie** an die dafür eingetragene
Adresse. Der Grund ist fachlich: Diese Rechnungen sind nicht bezahlt, sondern
stehen beim Debitor offen — sie gehen die Debitorenbuchhaltung an, nicht nur die
allgemeine. Welche Adressen im Einzelfall mitgehen, steht auf der Detailseite
über den Knöpfen. Ist in beiden Feldern dieselbe Adresse eingetragen, geht die
Mail trotzdem nur einmal dorthin.

Der Mailtext enthält einen Absatz, der klarstellt, dass es sich um **dieselbe
Rechnung unter derselben Rechnungsnummer** handelt und nicht um eine zweite
Forderung. Der Satz sollte beim Anpassen des Textes stehen bleiben — er
verhindert Rückfragen und ist mit Blick auf § 14c UStG die saubere Formulierung. Angehängt ist die **XRechnung als XML** — bei
einer XRechnung ist das XML die Rechnung, nicht eine Beilage zum PDF. Ein PDF
geht nur mit, wenn in der Konfiguration ein Ordner dafür hinterlegt ist und
OPERA die Folios überhaupt als Datei ablegt — das ist eine Einrichtung in
OPERA, keine Frage dieser Anwendung.

**„Zurücklegen"** nimmt die Rechnung aus dem Lauf. **„Wieder aufnehmen"**
holt sie zurück — sie landet dann in der Prüfung, nicht direkt im Versand.

Läuft gerade ein **Automatiklauf**, steht das oben in der Kopfzeile, und
Einlesen, „Durchlauf starten" und „Jetzt versenden" sind so lange gesperrt.
Das dauert meist Sekunden.

**„Prüfung abgeschlossen"** erscheint, solange eine Rechnung in *Prüfung* oder
*Fehler* steht. Erst dieser Knopf gibt sie für die Automatik frei. Einen
Empfänger zu wählen genügt dafür **nicht**: Wer die Adresse einträgt, hat
damit noch nicht entschieden, dass die Rechnung hinausgehen soll. Von Hand
versenden lässt sie sich jederzeit.

---

### Die Übersichtstabelle sortieren

Ein Klick auf eine Spaltenüberschrift sortiert danach; ein zweiter Klick dreht
die Richtung um. Die aktive Spalte ist hervorgehoben und trägt einen Pfeil.
Leere Felder stehen immer am Ende — eine Liste, die mit zwanzig Leerzeilen
beginnt, beantwortet keine Frage.

Die Sortierung steht in der Adresszeile und lässt sich als Lesezeichen
ablegen: `?sortieren=kunde&richtung=auf`.

### Eine bestimmte Rechnung suchen

Über dem Filter steht ein Suchfeld. Es durchsucht die Arbeitsliste nach
Rechnungsnummer, Belegnummer, Kunde, Empfängeradresse und Käuferreferenz —
überall genügt ein Teil des Wortes.

**Enthält der Suchbegriff eine Zahl, wird zusätzlich in OPERA gesucht.** Das
ist der Weg zu einer Rechnung, die gar nicht in der Liste steht: weil sie
älter ist als der eingelesene Zeitraum, weil sie beim Einlesen aussortiert
wurde oder weil noch nie jemand eingelesen hat. Meldet sich ein Kunde mit
einer Rechnungsnummer, findet man sie hier.

Gefundene OPERA-Belege stehen in einem eigenen Abschnitt unter der Liste, mit
dem Knopf **„In die Liste holen"**. Damit lässt sich jede Rechnung nachträglich
aufnehmen — auch eine, die das Einlesen übergangen hätte. Sie kommt dann
allerdings in die Sichtprüfung, mit dem Grund dabei: „Von Hand aufgenommen ·
Empfänger im Ausland (US)". Sie verschwindet also nicht stillschweigend, sie
geht aber auch nicht ohne Blick hinaus.

In OPERA wird **nur nach Nummern gesucht**, nicht nach Namen. Für eine
Namenssuche fehlt dort der passende Index; sie würde die ganze Tabelle lesen
und Sekunden dauern. Namen findet man in der Arbeitsliste.

## Die Automatik

Der Knopf oben rechts schaltet sie ein und aus. Sie tut zweierlei:

1. Alle *x* Minuten neue Rechnungen einlesen (**Takt**)
2. Rechnungen versenden, deren **Wartezeit** abgelaufen ist

Die Wartezeit ist das Sicherheitsnetz. Steht sie auf 120 Minuten, haben Sie
zwei Stunden Zeit, eine Rechnung zu prüfen, umzuleiten oder zurückzulegen,
bevor sie hinausgeht.

Verschickt wird nur, was **einen Empfänger hat** und **beide Prüfungen besteht**.

Rechnungen im Status **prüfung** greift die Automatik grundsätzlich nicht auf,
auch nicht nach Ablauf der Wartezeit. Sie warten auf einen Menschen.

> **Testlauf:** Solange dieser Schalter gesetzt ist, wird alles vorbereitet und
> geprüft, aber **nichts verschickt**. So lässt sich die Anwendung gefahrlos
> beobachten. In der Kopfzeile steht dann „Automatik an · Testlauf".
> Jede Rechnung wird dabei **einmal** durchgespielt und vermerkt; der nächste
> Takt nimmt die nächsten. Wird der Testlauf abgeschaltet, sind alle wieder
> fällig.

---

## Sicherheitsnetze

Vier Dinge verhindern, dass etwas Falsches hinausgeht:

1. **Erlaubte Empfänger** — solange diese Liste gefüllt ist, geht keine Mail an
   eine Adresse außerhalb. Auch nicht aus der Automatik, und **auch nicht als
   Blindkopie**: Ein Tippfehler in der BCC-Adresse schickt sonst eine
   Kundenrechnung unbemerkt an einen Fremden
2. **Testlauf** — bereitet alles vor, verschickt nichts
3. **Wartezeit** — Zeit zum Eingreifen, bevor die Automatik zugreift
4. **Doppelte Prüfung** — rechnerisch und mit dem offiziellen Prüfprogramm.
   Was durchfällt, wird nicht verschickt, sondern angezeigt. Ist die Prüfung
   als **Pflicht** eingestellt, geht ohne sie nichts hinaus — auch dann nicht,
   wenn jemand die Prüfung abschaltet
5. **Kein zweiter Versand** — eine versendete Rechnung geht nie erneut hinaus,
   auch nicht bei einem Doppelklick oder aus einem zweiten Fenster
6. **Verschlüsselte Verbindung zum Mailserver**, mit Prüfung des Zertifikats.
   Lehnt der Mailserver den Kunden ab, gilt die Rechnung **nicht** als
   versendet — auch wenn die Blindkopie im Haus ankommt

---

## Wer bekommt eine XRechnung?

Das Kriterium ist der **Firmenbezug**, nicht ein von Hand gesetztes Kennzeichen.
Der Grundsatz dahinter: **lieber eine XRechnung zu viel als eine zu wenig** —
eine fehlende ist ab 2027 ein Rechtsverstoß, eine überflüssige nur eine
Unannehmlichkeit.

Aufgenommen wird, wenn eines davon zutrifft:

- der Empfänger hat ein **Firmenprofil** (`COMPANY`, `TRAVEL_AGENT`, Gruppe)
- die Rechnung hängt an einem **Debitorenkonto**
- am Profil ist eine **Leitweg-ID** hinterlegt
- an der Reservierung hängt eine **Firma** (→ Status prüfung)

Nicht aufgenommen werden ausländische Empfänger — die Pflicht gilt für
inländische Umsätze. Ist am Profil **kein Land gepflegt**, kommt die Rechnung in
die Prüfung, statt stillschweigend zu verschwinden.

Eine Betragsgrenze gibt es bewusst nicht: Kleinbetragsrechnungen bis 250 € wären
zwar ausgenommen, aber eine zusätzliche XRechnung schadet nicht.

### Welche Belege sind Rechnungen?

**Jeder gültige Beleg aus OPERA ist eine Rechnung**, gleich wie OPERA ihn
nennt: Schlussrechnung, **Vorausrechnung** und **Zwischenrechnung** gehen als
Rechnung (Typ 380) hinaus, ein **Anzahlungsbeleg** ebenfalls, mit dem Vermerk
„Anzahlungsrechnung“. Rechtlich zählt nicht der Name, sondern dass abgerechnet wird.
Doppelt wird dabei nichts: In OPERA steht jede Buchung auf genau einem Beleg —
die Schlussrechnung enthält die Nächte der Vorausrechnung nicht noch einmal.

Keine Rechnung und deshalb nicht verschickt:

- **stornierte Belege** (Status VOID)
- **interne Umbuchungen** zwischen Folios (Rundung, Zahlungsausgleich)
- Belege der Art **„COPY OF INVOICE“** — bis geklärt ist, was sie im Haus
  bedeuten; über die Suche geholt, landen sie in der Sichtprüfung
- Belege **ohne TSE-Nummer**, wenn das Haus sonst TSE-Nummern vergibt — sie
  waren nie beim Fiskalsystem und gehen zur Sichtprüfung

**Bei der Umstellung** liegen im Zeitfenster schon ältere Voraus-, Zwischen-
und Anzahlungsrechnungen, die nie als XRechnung hinausgingen — manche davon hat
eine spätere Rechnung längst verrechnet. Sie gehen nicht automatisch hinaus,
sondern einmalig zur Sichtprüfung („von vor der Umstellung“). Ab dem Tag der
Umstellung laufen sie wie jede andere Rechnung.

Für Anzahlungsrechnungen kennt die europäische Codeliste einen eigenen Typ
(386). XRechnung lässt ihn nicht zu (Regel BR-DE-17); die Anzahlungsrechnung
geht deshalb als Typ 380 mit dem Vermerk hinaus.

## Die Leitweg-ID

Die **Leitweg-ID** ist die Zustelladresse einer Behörde im elektronischen
Rechnungsverkehr — ohne sie nimmt eine Behörde keine Rechnung an.

Gepflegt wird sie **in OPERA an der Firmenkartei**, in einem benutzerdefinierten
Feld (`UDFC01`–`UDFC40`), das per Screen Painter auf die Maske der
Firmenkartei gelegt und mit „Leitweg-ID" beschriftet wird — oft auf dem Reiter
„More". Die Buchhaltung trägt die Nummer dann am Profil ein; das Feld gibt es
an Firmen-, Reisebüro- und Quellkarteien.

**Einrichten, einmal pro Haus:**

1. **In OPERA** das Feld an der Firmenkartei sichtbar machen. Welches frei
   ist und wie es geht, zeigt die Anleitung unter **Konfiguration → Karte
   „Leitweg-ID und Käuferreferenz (BT-10)" → „Anleitung: Feld finden und in
   OPERA einrichten"**. Die Feldprüfung dort zählt jedes Feld über **alle**
   Karteien — auch über Gastkarteien, denn die Spalten teilen sich alle
   Karteiarten. Vorgeschlagen wird nur ein Feld ohne jeden Wert und ohne
   Beschriftung in OPERA.
2. **In der Anwendung** auf der Konfigurationsseite in der Karte
   **„Leitweg-ID und Käuferreferenz (BT-10)"** den Feldnamen eintragen, etwa
   `UDFC05`, und speichern. Die Karte zeigt danach, aus welchem Feld gelesen
   wird — oder in Rot, dass keines eingestellt ist.

Die Anwendung prüft jeden Wert, ob er wie eine Leitweg-ID aufgebaut ist
(Ziffern, Bindestrich, zweistellige Prüfziffer, höchstens 46 Zeichen). OPERA
selbst prüft an dem Feld nichts. Passt ein Wert nicht, wird er **nicht**
benutzt, und die Rechnung bekommt einen Prüfhinweis — sonst ginge ein
Tippfehler als Behördenadresse hinaus.

> **Mitgliedschaften taugen dafür nicht.** OPERA bietet sie nur an der
> Gastkartei an, nicht an der Firmenkartei. Ein Mitgliedschaftstyp für die
> Leitweg-ID wird deshalb in aller Regel nie gefüllt.

**Nur Behörden haben eine Leitweg-ID.** Gewöhnliche Firmenkunden haben keine —
das Feld BT-10 muss trotzdem gefüllt sein. Die Anwendung nimmt deshalb den
ersten Wert, den sie findet:

1. **von Hand eingetragen** auf der Detailseite der Rechnung (siehe unten)
2. **Leitweg-ID** aus dem Feld an der Firmenkartei
3. **Feld in der Reservierungsmaske** für die Käuferreferenz (technisch
   `FOLIO_TEXT1`; je nach Einrichtung beschriftet als „XRechnung" oder „Buyer
   Reference1"). Hier trägt der Empfang die Bestellnummer des Firmenkunden ein.
4. **External Reference** an der Reservierung
5. **Ersatzwert** — die Vorlage des Hauses, voreingestellt der Satz
   „Musterhotel Berlin ReservNr.: 3000001"

Eine gepflegte Leitweg-ID geht also **vor** dem Reservierungsfeld. Hat eine
Behörde je Auftrag eine andere Leitweg-ID, bleibt das Profilfeld leer, und die
Nummer kommt ins Reservierungsfeld — dann wird sie allerdings nicht als
Leitweg-ID geprüft.

**BT-10 muss nicht numerisch sein.** Die Norm verlangt nur, dass das Feld
gefüllt ist — was darin steht, ist freier Text. Der Ersatzwert ist deshalb
eine Vorlage (`property.buyerreference_vorlage`) mit den Platzhaltern
`{haus}`, `{reservierungsnummer}`, `{rechnungsnummer}`, `{debitor}` und
`{kunde}`. Fehlt einer der benutzten Werte, wird die Vorlage nicht genommen —
„ReservNr.:" ohne Nummer sieht aus wie ein Wert und ist keiner; dann gilt der
feste Ersatzwert.

### Wann muss das Reservierungsfeld gefüllt sein?

**Vor dem Check-out.** Eine abgerechnete Reservierung lässt sich in OPERA
nicht mehr ändern — was dort nicht steht, wenn die Rechnung erstellt wird,
kommt dort nicht mehr hinein. Für alle Rechnungen, die vor der Einführung des
Feldes entstanden sind, greift diese Stufe deshalb nie; sie tragen dauerhaft
den Ersatzwert.

Meldet der Kunde die Bestellnummer erst, wenn er die Rechnung in der Hand hat
— und das ist der Normalfall —, lässt sie sich **auf der Detailseite der
Rechnung** nachtragen. Dort steht das Feld „Käuferreferenz (BT-10)": Es zeigt,
was OPERA hergibt, und lässt einen eigenen Wert eintragen. Ein von Hand
gesetzter Wert hat Vorrang vor allem anderen, auch vor der Leitweg-ID; die
Herkunftsanzeige macht sichtbar, dass er von Hand kommt. Leeren stellt die
automatische Ermittlung wieder her.

### Das Reservierungsfeld — für die Bestellnummer des Kunden

BT-10 ist das Feld, über das die Buchhaltung Ihres Kunden die Rechnung **ihrer
eigenen Bestellung zuordnet**. Ein Wert, den nur wir kennen — unsere
Rechnungs- oder Reservierungsnummer —, hilft dort niemandem. Deshalb gibt es
in der Reservierungsmaske ein eigenes Feld (beschriftet „XRechnung" oder
„Buyer Reference1"): Was der Empfang dort einträgt, steht später in der
Rechnung.

Zwei Hinweise dazu:

- Das Feld nimmt technisch sehr lange Texte an. BT-10 ist aber eine
  **Referenz, kein Satz**. Längere Einträge werden auf 80 Zeichen gekürzt, und
  die Rechnung bekommt dann einen Prüfhinweis — gekürzt wird nie
  stillschweigend.
- Zeilenumbrüche werden zu Leerzeichen.

Die **Kundenreferenz aus der Buchung** (`CUSTOM_REFERENCE`) wird bewusst
**nicht** verwendet. Sie ist zwar gut gefüllt, enthält aber überwiegend
Buchungsnummern aus dem Channel Manager: Ausgezählt waren rund drei Viertel der
Werte reine Ziffernfolgen aus dem Portal. Eine solche Nummer in BT-10 ist schlechter
als ein Ersatzwert — sie sieht nach einer echten Bestellnummer aus, und die
Gegenseite sucht sie vergeblich. Wer das Feld im Haus diszipliniert pflegt,
kann es in der Konfiguration einschalten.

Die Detailseite zeigt, welcher Wert eingesetzt wurde **und woher er stammt**.
Steht dort „Ersatzwert", ist das für einen Firmenkunden in Ordnung — **für eine
Behörde nicht**. Dort gehört die Leitweg-ID gepflegt.

Praktisch heißt das: *Leitweg-ID vorhanden = dieser Kunde bekommt eine
XRechnung.* Ein zusätzliches Kennzeichen gibt es bewusst nicht.

---

## Wer war im Haus? — Gastname auf der Rechnung

Eine Firmenrechnung über eine Übernachtung nennt den **Zahler**, den Zeitraum
und die Positionen. Wer tatsächlich da war, steht auf der Papierrechnung oben
— in der XRechnung fehlte er. Die Buchhaltung Ihres Kunden konnte die
Rechnung damit keiner Reise und keinem Mitarbeiter zuordnen.

Der Gastname steht jetzt an zwei Stellen, mit verschiedener Aufgabe:

- **als lesbare Zeile (BT-22)** — für den Menschen, der die Rechnung ansieht:
  „Gast: Mustermann, Erika, Zimmer 214, 2026-08-30 bis 2026-09-09"
- **als strukturiertes Feld (BT-70)** — für das Empfangssystem des Kunden, das
  den Namen auswerten kann. In vielen Anzeigeprogrammen bleibt dieses Feld
  unsichtbar; deshalb beides.

Der Text der lesbaren Zeile lässt sich in der Konfiguration ändern
(`property.gastzeile`). Verfügbar sind `{gast}`, `{zimmer}`, `{anreise}` und
`{abreise}`. Ein leeres Feld schaltet die Zeile ab.

**Bei Gruppen bleibt sie weg.** Dort hängt kein einzelner Gast an der
Reservierung, sondern nur ein Kürzel wie `GRO020926` — dann steht gar keine
Zeile da, statt einer, die eine Person dieses Namens behauptet. Die große
Mehrheit der Rechnungen trägt einen Gastnamen; die Ausnahme sind Gruppen.

**Der Zeitraum ist der Aufenthalt, nicht die Abrechnung.** Das ist ein
Unterschied: Bei einer Anzahlung beginnt die Abrechnung mit deren Buchung,
mitunter Jahre vor der Anreise. Rechnung und Gastzeile nennen deshalb den
Zeitraum aus der Reservierung — das ist auch der Leistungszeitraum, den § 14
UStG auf der Rechnung verlangt. Hängt keine Reservierung am Beleg, gilt
ersatzweise der Abrechnungszeitraum.

Wichtig zum Verständnis: Der Gast hängt an der **Reservierung**, der Zahler am
**Folio**. Gerade bei Firmenrechnungen sind das zwei verschiedene Personen —
und genau deshalb ist die Angabe dort wertvoll.

---

## Wie die Positionen auf der Rechnung stehen

Entschieden von der Buchhaltung am 14.09.2026: **zwei Arten**, eine für
Einzelrechnungen und eine für Gruppen. Bei Gruppen stehen **Gastname und
Zimmernummer** an jeder Position.

**Einzelrechnung — zusammengefasst nach Leistung und Preis**

    Übernachtung      5 × 216,09
    Frühstück         5 ×  25,00
    Parken            1 ×  30,00

Der Gast steht bei dieser Art oben auf der Rechnung, in der Gastzeile.

**Gruppe — je Gast und Zimmer**

    Zi. 214 · Musterfrau, Lena    Übernachtung   5 × 216,09   30.08.–04.09.
    Zi. 214 · Musterfrau, Lena    Frühstück      5 ×  25,00   30.08.–04.09.
    Zi. 215 · Beispiel, Max        Übernachtung   2 × 189,00   28.08.–06.09.

Zimmer und Name stehen in der Bemerkung der Position, der Aufenthalt im
Zeitraum der Position. Sortiert wird nach Zimmer.

**Das Supplement-Feld aus OPERA steht mit auf der Rechnung.** Was jemand in
der Buchungsmaske ins Feld „Supplement" schreibt, erscheint als Bemerkung an
der Position — vollständig und unverändert, genau wie auf der gedruckten
Rechnung:

    Conference Center technische Ausstattung   1 × 230,00
    Beamer Raum Lissabon / Muster Pharma GmbH

Bei einer Gruppenrechnung steht es hinter Zimmer und Name, durch „ · "
getrennt. Das betrifft vor allem Tagungsrechnungen; bei Übernachtungen ist
das Feld meist leer, und dann steht dort auch nichts.

Zwei Dinge, die man dazu wissen sollte:

- **Was im Supplement steht, liest der Kunde.** Es geht unverändert hinaus.
  Ein interner Vermerk gehört deshalb nicht dorthin, sondern in ein Feld, das
  nicht auf der Rechnung erscheint.
- **Steht dort der Name eines Veranstalters** („… / Muster Pharma GmbH") und
  trägt ein Sammelbeleg mehrere verschiedene, dann sieht der Empfänger die
  anderen. Das ist auf der gedruckten Rechnung nicht anders — wer es nicht
  will, muss es beim Erfassen der Buchung anders schreiben.

**Welche Art gilt, schlägt die Anwendung selbst vor.** Gehören die Buchungen zu
mehr als einer Reservierung, ist es eine Gruppe. Sonst ist es eine
Einzelrechnung. Gruppe gilt auch dann, wenn an den Buchungen ein Gast hängt,
oben auf der Rechnung aber keiner steht, weil der Name sonst nirgends
auftauchen würde.

**Ändern lässt sich die Art auf der Detailseite**, über der Tabelle
„Positionen". Dort steht auch, warum die Anwendung ihre Art gewählt hat und
aus wie vielen Buchungen die Positionen entstanden sind. Die Tabelle zeigt
danach genau das, was hinausgeht. Zur Auswahl steht zusätzlich **„Jede Buchung
einzeln"**, die Darstellung vor dem 14.09. Sie ist ein Rückweg, keine
Vorbelegung.

Was zusammengefasst wird und was nicht:

- **Nur gleicher Preis.** Zwei Nächte zu 189,00 und drei zu 216,09 werden zwei
  Positionen. Die Prüfregel rechnet Menge mal Preis nach, und ein
  Durchschnittspreis geht dabei nicht auf.
- **Nur gleicher Steuersatz** und gleicher Umsatzcode.
- **Buchung und Storno heben sich auf.** Eine Minibar, die gebucht und wieder
  storniert wurde, steht gar nicht mehr auf der Rechnung.
- **Die Beträge ändern sich um keinen Cent.** Steuergruppen, Gesamtbetrag und
  Zahlbetrag sind in allen Darstellungen gleich.

Eine **versendete** Rechnung ändert sich durch eine andere Wahl nicht. Es gilt
die abgelegte Fassung. Die Detailseite rechnet die Tabelle trotzdem neu und
sagt das dazu.

**Umschalten darf nur, wer auch versenden darf** (Rolle „verwalten“). Dasselbe
gilt seit dem 14.09. für die Käuferreferenz.

Unter „je Gast und Zimmer“ steht bei einem **Zimmerwechsel** je Zimmer eine
eigene Position. **Rabatte** erscheinen als Abschlag und nennen Zimmer und
Gast. Der Zeitraum an der Position sind die **berechneten Tage**, nicht der
ganze Aufenthalt der Reservierung. Bei einer Gruppe nennt die Rechnung oben
keinen einzelnen Gast mehr — die Namen stehen an den Positionen.

**Solange die Zuordnung der Buchungen zu den Gästen nicht an echten Daten
bestätigt ist**, verschickt die Automatik eine Rechnung in dieser Darstellung
nicht von selbst, sondern legt sie in die Prüfung. Von Hand geht sie
jederzeit.

In der Konfiguration legt `property.positionen` die Vorbelegung fest:
`automatisch` (Vorgabe), oder fest `B`, `C` bzw. `A`.

## Anzahlungen

Eine Anzahlung ist in OPERA ein eigener Beleg auf dem Folio des Aufenthalts.
Er geht selbst als **Anzahlungsrechnung** hinaus (Typ 380 mit Vermerk). Die Rechnung, die
die Anzahlung verrechnet — die Schlussrechnung oder auch eine Vorausrechnung —,
**setzt sie mit ihrer Steuer ab**: als Abzug je Steuersatz („Abzüglich
Anzahlungsrechnung … vom …“) und mit Verweis auf den Anzahlungsbeleg (BG-3). Die
Rechnung weist damit nur noch die Steuer auf den Rest aus, wie OPERA auf dem
Papier — so verlangt es § 14 Abs. 5 UStG, wenn über die Anzahlung eine Rechnung
mit Steuer ergangen ist. Lässt sich die Steueraufteilung des Anzahlungsbelegs
nicht lesen, hält die Vorprüfung die Rechnung an. Abgezogen wird genau der Teil, den OPERA dieser
Rechnung angerechnet hat — der Unterschied zwischen ihren Positionen und ihrem
Betrag in OPERA.

Das ist wichtig, wenn auf einem Folio **mehrere Schlussrechnungen** liegen,
etwa eine Hauptrechnung und eine kleine Nebenrechnung für Minibar oder Parken.
OPERA rechnet die Anzahlung nur einer davon an; nur diese trägt sie in der
XRechnung. Die andere geht ohne Anzahlung hinaus, mit ihrem eigenen Betrag.

Ist eine Anzahlung höher als das, was am Ende angefallen ist, wird der
Zahlbetrag negativ — der Kunde hat ein Guthaben. Die Rechnung bleibt eine
Rechnung; sie geht zur Sichtprüfung, weil ein Guthaben meist eine Rückfrage
der Buchhaltung auslöst.

## Gutschriften

Ein Beleg, dessen Positionen zusammen negativ sind und dem keine Anzahlung
angerechnet ist, ist eine **Gutschrift** — meist die Stornierung oder
Teilstornierung einer Rechnung. Die Anwendung schickt sie als **Gutschrift
(Typ 381)**: mit positiven Beträgen, wie es die Norm verlangt, und mit eigenem
Betreff und Text in der Mail.

**Jede Gutschrift geht zuerst in die Sichtprüfung.** Auf der Detailseite steht
oben, ob die **berichtigte Rechnung** erkannt wurde:

| Hinweis | Was er heißt |
|---|---|
| *Gutschrift zur Rechnung … vom …* | An derselben Reservierung gibt es genau eine Rechnung mit dem entgegengesetzten Betrag. Sie steht als Rechnungsbezug in der Gutschrift |
| *ohne erkennbare Ursprungsrechnung* | Keine passende Rechnung — etwa bei einer Teilgutschrift über einen anderen Betrag. Die Gutschrift geht ohne Rechnungsbezug hinaus |
| *mehrere Rechnungen kommen in Frage* | Zwei gleich hohe Rechnungen an derselben Reservierung. Geraten wird nicht; die Gutschrift geht ohne Rechnungsbezug hinaus |

OPERA selbst führt keinen Verweis von der Gutschrift auf die Rechnung; die
Anwendung kann ihn nur aus Reservierung und Betrag erschließen. Das gelingt bei
vollständigen Stornos, bei Teilgutschriften nicht. Technisch ist eine
Gutschrift ohne Rechnungsbezug gültig. Ob sie steuerlich genügt (eine
Berichtigung muss sich eindeutig auf die berichtigte Rechnung beziehen), klärt
das Haus mit seiner Steuerberatung — im Zweifel die Nummer der Ursprungsrechnung
dem Kunden mitteilen.

Sind die Positionen negativ **und** ist zugleich eine Anzahlung angerechnet,
lässt sich das nicht sauber abbilden; die Vorprüfung hält den Beleg an.

## Profile ohne E-Mail-Adresse

Eine XRechnung braucht die elektronische Adresse des Empfängers. Das ist ein
Pflichtfeld der Norm, keine Einstellung: Fehlt sie am Profil, an der
Rechnungsanschrift und am Debitorenkonto, lässt sich die Rechnung nicht
versenden. Sie bleibt sichtbar in der Sichtprüfung liegen, mit genau diesem
Grund — sie verschwindet nicht.

Erfahrungsgemäß betrifft das einen erheblichen Teil der Firmenprofile. Das
lässt sich nicht im Programm lösen, sondern nur in OPERA pflegen.

Damit das nicht Rechnung für Rechnung geschieht, steht in der Übersicht der
Knopf **„… ohne Adresse"**. Er lädt eine Tabelle für Excel, gebündelt nach
Profil: Ein Profil trägt oft mehrere Rechnungen, und eine gepflegte Adresse
erledigt sie alle auf einmal.

| Spalte | Bedeutung |
|---|---|
| Kunde | Name des Profils, so wie er auf der Rechnung steht |
| Rechnungen | wie viele Rechnungen an diesem Profil hängen |
| Nummern | die Rechnungsnummern zum Nachschlagen in OPERA |
| ältestes Datum | wie lange der Fall schon liegt |
| Summe brutto | wie viel Umsatz betroffen ist |

Sortiert ist nach Anzahl — oben steht, wo die Pflege die meisten Fälle auf
einmal erledigt. Der Schwanz ist allerdings lang: Etwa zwei Drittel der
Profile hängen an genau einer Rechnung. Wer stattdessen nach Umsatz vorgehen
will, sortiert die Tabelle in Excel nach „Summe brutto" — die größte
Einzelposition kann durchaus die Hälfte des offenen Volumens ausmachen und in
der Reihenfolge nach Anzahl weit unten stehen.

Steht in der Spalte „Kunde" nichts, trug schon der Beleg keinen Firmennamen;
die Anwendung schlägt dann den Namen am Profil nach.

Ist die Adresse in OPERA eingetragen, genügt ein erneutes Einlesen. Der Knopf
verschwindet, sobald nichts mehr zu pflegen ist.

Für einen Einzelfall lässt sich die Adresse auch direkt in der Rechnung
eintragen. Das hilft dieser einen Rechnung — die nächste desselben Kunden
steht wieder ohne da, solange das Profil leer bleibt.

## Versendete Rechnungen bleiben, wie sie sind

Sobald eine Rechnung versendet ist, wird ihr XML **nicht mehr neu erzeugt** —
weder beim Ansehen noch beim Klick auf einen Knopf. Angezeigt wird stattdessen
die archivierte Fassung: genau das, was der Kunde bekommen hat.

Das ist wichtiger, als es klingt. Ohne diese Sperre stünde nach einem
beiläufigen Klick etwas anderes in der Ablage als beim Kunden — und niemand
könnte es sehen. Genau in dem Moment, in dem der Kunde nachfragt, sähe man die
falsche Datei.

Wer eine versendete Rechnung wirklich neu erzeugen will, findet dafür den
Knopf **„Trotzdem neu erzeugen"** mit einer Rückfrage. Er ersetzt die Datei in
der Ablage; die versendete Fassung bleibt im Archiv.

## Aufgaben nach dem Versand

Einmal am Tag, nach dem Tagesabschluss (ab 5 Uhr, beim ersten Durchlauf der
Automatik), prüft die Anwendung die Rechnungen der letzten drei Tage, die schon
beim Kunden sind, gegen OPERA. Zwei Dinge können sich dort danach noch ändern:

| Befund | Was zu tun ist |
|---|---|
| **In OPERA storniert** | Der Kunde hat eine Rechnung, die es nicht mehr gibt. Er braucht eine **Stornorechnung**. Meist hat OPERA sofort einen Ersatzbeleg ausgegeben; der Hinweis nennt ihn, wenn er am selben Folio mit demselben Betrag steht. Der Ersatzbeleg geht als neue Rechnung ganz normal hinaus |
| **Rechnungsempfänger geändert** | Profil oder Zahler wurden in OPERA umgestellt. Prüfen, ob die XRechnung an den Richtigen ging |

Befunde stehen oben auf der Rechnungsliste als **Aufgaben nach dem Versand**
und auf der Detailseite der Rechnung. Ist die Sache erledigt, dort **„Als
erledigt markieren“** — die Aufgabe verschwindet aus der Liste, der Befund
bleibt an der Rechnung stehen. Mit **„Versendete jetzt nachprüfen“** läuft die
Prüfung sofort.

Beträge und Positionen einer versendeten Rechnung muss niemand vergleichen:
An einer ausgegebenen, gültigen Rechnung ändert OPERA sie nicht.

Die Stornorechnung erzeugt die Anwendung in diesem Stand noch nicht selbst.

## Wenn eine Rechnung nicht durchgeht

In der Zeile steht rot, woran es liegt.

| Meldung | Was dahintersteckt |
|---|---|
| **BR-CO-10 / BR-S-08** | Positionen und Summe passen nicht zusammen — meist ein Sonderfall in OPERA. Nicht selbst korrigieren, sondern melden |
| **Folio-Klammer** | Positionen, Rechnungskopf und Anzahlungen ergeben zusammen keinen stimmigen Betrag |
| **BR-DE-15** | Leitweg-ID fehlt |
| **BT-31 / BG-17** | USt-IdNr. oder IBAN fehlen in den Einstellungen |
| **BR-DE-6 / BR-DE-7** | Telefon oder E-Mail des Hauses fehlen in den Einstellungen — beides ist Pflicht |
| **Der Beleg hat in OPERA den Status …** | Die Rechnung wurde in OPERA storniert. Nicht versenden, zurücklegen |
| **„COPY OF INVOICE“** / **interne Umbuchung** | Kein Beleg, der als Rechnung hinausgeht. Zurücklegen |
| **Versand begonnen, Ergebnis nicht bestätigt** | Der Versand brach unklar ab. Sehen Sie im Postfach der Blindkopie nach, ob die Mail hinausging, und halten Sie es auf der Detailseite fest: **„Ja — als versendet vermerken"** oder **„Nein — nichts ging hinaus"**. Erst danach ist die Rechnung wieder entscheidbar |
| **Am Empfängerprofil steht keine einzelne gültige Adresse** | In OPERA stehen mehrere Adressen in einem Feld. Auf eine zurückschneiden, dann neu einlesen |
| **Nullbeleg** | Gesamtbetrag 0,00 — gehört nicht in den Versand |
| **Negativer Gesamtbetrag … gehört als Gutschrift (381)** | Positionen negativ, aber zugleich eine Anzahlung angerechnet. Nicht automatisch abbildbar — an die Buchhaltung |
| **Anzahlung nur teilweise angerechnet** | Der Teil der Anzahlung, den OPERA dieser Rechnung angerechnet hat, passt zu keinem Anzahlungsbeleg. Kam in den geprüften Daten nicht vor — melden |
| **KoSIT: …** | Das offizielle Prüfprogramm beanstandet etwas. Der Text nennt die Regel |
| **steht nicht auf der Liste erlaubter Empfänger** | Sicherheitsnetz — Adresse oder Liste anpassen |

Rechnungen mit Fehler bleiben liegen. Sie gehen weder von Hand noch automatisch
hinaus, bis die Ursache behoben ist.

---

## XRechnung-Version

Erzeugt wird **XRechnung 3.0.2**. Die Version steht auf der
Konfigurationsseite beim Validator. Auf der Detailseite steht, in welcher
Version eine Rechnung erzeugt wurde. XRechnung 4.0 ist noch nicht
veröffentlicht und deshalb nicht wählbar. Kommt sie, lässt sie sich dort
einstellen, sobald Vorlage und Regelwerk eingespielt sind
(docs/03_NORM_UND_TERMINE.md).

## Aktualisierung

Unter **Konfiguration → Aktualisierung**:

Der Zugangstoken für GitHub wird wie die übrigen Passwörter **verschlüsselt
gespeichert** und in der Oberfläche nur als „gesetzt" angezeigt. Für den Betrieb
genügt die Berechtigung *Contents: Read* — schreiben muss die Anwendung nie.

- **„Nach Aktualisierung sehen"** fragt bei GitHub nach und meldet, ob es einen
  neueren Stand gibt. Stimmt der eingetragene Zweig nicht, nennt die Meldung
  den richtigen — Anlagen aus der Anfangszeit tragen teils noch `master`
  statt `main`, und eine bestehende Konfiguration wird von Aktualisierungen
  bewusst nicht überschrieben
- **„Aktualisierung einspielen"** holt ihn und tauscht die Programmdateien aus.
  **Ihre Einstellungen werden dabei nie überschrieben.** Bringt eine neue
  Fassung zusätzliche Einstellungen mit, werden sie beim nächsten Start
  ergänzt — bestehende Werte bleiben, wie sie sind, auch wenn sie von der
  Vorgabe abweichen. Zugänge, Arbeitsliste und Archiv bleiben ebenfalls
  unangetastet. Vor dem Austausch entstehen zwei Sicherungen: der bisherige
  Programmstand unter `data/sicherung-<Datum>` und eine datierte Kopie der
  Konfiguration in `config/`
- **„Dienst neu starten"** übernimmt den neuen Stand

Läuft die Anwendung als Dienst, startet sie von selbst wieder — unter Windows
über NSSM, unter Linux über systemd. Im Vordergrundbetrieb (`run.cmd` bzw.
`run.sh`) muss sie von Hand neu gestartet werden.

Der Ordner `install` enthält daneben `dienst_einrichten` und `dienst_entfernen`
(jeweils `.cmd` für Windows, `.sh` für Linux), falls der Dienst einmal neu
aufgesetzt werden muss.

---

## Protokoll

Unter **„Protokoll"** steht jede Aktion mit Zeitpunkt und Benutzer: Anmeldungen,
Empfängerwahl, Prüfergebnisse, Versand mit Ziel- und BCC-Adresse,
Konfigurationsänderungen, Aktualisierungen. Fehlgeschlagenes ist rot hinterlegt.

Das ist die Nachweisspur — wer wann was mit welcher Rechnung gemacht hat.

---

## Wer bekommt eine XRechnung — und wer nicht?

Die Anwendung ist auf **Firmenkunden mit Rechnung auf Rechnung** zugeschnitten
(City Ledger / Debitorenkonto). Das ist ein kleiner Teil des
Rechnungsaufkommens — in der Größenordnung weniger Prozent.

Barzahler und Kartenzahler bekommen ihre Rechnung wie bisher. Erst wenn ein
Kunde eine Leitweg-ID hinterlegt hat, läuft er über diesen Weg.

---

## Grenzen

- Die Anwendung **verschickt keine Mahnungen** und **bucht nichts** — sie liest
  nur und schickt eine Datei
- Sie **korrigiert keine Rechnungen**. Stimmt etwas in OPERA nicht, gehört es
  dort korrigiert
- **Gutschriften** gehen als Typ 381 hinaus, aber immer erst nach
  Sichtprüfung. Den Bezug auf die berichtigte Rechnung erkennt die Anwendung
  nur bei vollständigen Stornos — OPERA führt ihn nicht
- **Rechnungsnummer** ist die Belegnummer aus OPERA (`BILL_NO`), dieselbe, die
  jede Rechnung trägt. Die Debitorennummer (`INVOICE_NO`) haben nur Rechnungen
  über das Debitorenkonto; sie wird nicht verwendet
- **OPERAs eigene E-Rechnung** (Parameter `E-INVOICE`) sollte ausgeschaltet
  bleiben, solange diese Anwendung versendet — sonst könnten Kunden zwei
  E-Rechnungen bekommen. Wer sie einschalten will, stimmt das vorher ab
- **Anzahlungen** erkennt sie am Belegstatus, nicht an Umsatzcodes — das gilt
  in jedem Haus gleich. Führt Ihr Haus Anzahlungen anders (als Umbuchung im
  selben Beleg statt als eigenen Beleg), ist das einzustellen
