# Änderungen

Jede Version steht hier mit dem, was sich für den Betrieb ändert. Die Nummer
folgt dem Schema **Haupt.Neben.Korrektur**:

- **Korrektur** (1.0.**1**): Fehler behoben, nichts Neues einzustellen.
- **Neben** (1.**1**.0): neue Funktionen; eine Aktualisierung genügt, neue
  Einstellungen haben Vorgaben.
- **Haupt** (**2**.0.0): Die Aktualisierung verlangt einen Eingriff am Haus,
  etwa eine geänderte Konfiguration oder neue Rechte am Datenbankbenutzer.
  Was zu tun ist, steht dann hier.

Die Nummer steht in der Datei `VERSION`, in der Fußzeile der Oberfläche und
unter „Konfiguration“. Zu jeder Version gibt es auf GitHub ein Release.

## [1.4.2] – 2026-11-20

**Windows-Installer fragt nach Name und Port**
- Für ein weiteres Haus auf demselben Rechner sind keine Schalter mehr nötig.
  Beim ersten Lauf in einem Ordner fragt der Installer nach dem Port und,
  wenn es schon eine andere Installation gibt, nach einem Namen. Er zeigt die
  vorhandenen Installationen und schlägt freie Werte vor; Enter genügt.
- Belegt eine angehaltene Installation einen Port, gilt er jetzt auch als
  belegt. Bisher zählte nur ein Port, an dem gerade ein Programm lauscht.
- `-Instanz`, `-Port` und `-OhneRueckfrage` wirken wie bisher, dann fragt
  der Installer nicht.

## [1.4.1] – 2026-11-18

**Korrektur: Hinweis „vor der Umstellung“ in älterer OPERA**
- In einer OPERA ohne Belegart (`DOCUMENT_TYPE`) stand an jedem Altbeleg
  „Voraus-, Zwischen- oder Anzahlungsrechnung von vor der Umstellung“, auch an
  gewöhnlichen Endrechnungen. Dort heißt der Hinweis jetzt „Beleg von vor dem
  ersten Einlesen — die Belegart ist in dieser OPERA-Version nicht erkennbar“;
  Anzahlungsbelege (Status DEPOSIT) heißen „Anzahlungsrechnung von vor dem
  ersten Einlesen“.
- Schon gesetzte Hinweise stellt das nächste Einlesen auf den passenden Text
  um. Andere Gründe am selben Beleg bleiben stehen.
- Mit bekannter Belegart ändert sich nichts.

## [1.4.0] – 2026-11-16

**Fehler DPY-3015: Oracle-Client mit einem Klick**
- Neuer Knopf „Oracle-Client einrichten“ in der Konfiguration unter
  „Verbindung prüfen“. „Datenbank testen“ weist bei `DPY-3015` darauf hin.
- Der Knopf sucht einen Oracle-Client mit 64 Bit auf dem Rechner. Ein
  32-Bit-Client, wie er für OPERA oft installiert ist, wird erkannt und
  übergangen. Findet sich keiner, lädt die Anwendung unter Windows den Oracle
  Instant Client (Basic Light) von oracle.com nach `oracle\` im
  Installationsordner. Fehlt die Visual-C++-Laufzeit, installiert sie diese von
  Microsoft. Die Signaturen von Oracle und Microsoft werden vorher geprüft.
- Eingetragen wird erst nach einer gelungenen Probeanmeldung, in einem
  eigenen Prozess. Danach startet der Dienst neu. Scheitert die Probe, bleibt
  die Konfiguration unverändert und die Meldung nennt den Grund je Client.
- Unter Linux wird nichts geladen; die Meldung nennt die dnf-Befehle.
- Der Ordner `oracle\` übersteht Aktualisierungen.

## [1.3.1] – 2026-11-16

**Windows-Installer: Python sicherer gewählt**
- Ein vorhandenes Python wird nur noch genommen, wenn es für alle Benutzer
  installiert ist und das venv-Modul mitbringt. Gesehen auf einem frischen
  Windows 11: `C:\Python314` ohne venv-Modul, die Einrichtung brach mit „Die
  Umgebung liess sich nicht anlegen“ ab. Ein Python nur im Benutzerprofil
  (Install Manager, Microsoft Store) taugt nicht für den Dienst, der als SYSTEM
  läuft. In beiden Fällen installiert der Installer Python 3.12 für alle
  Benutzer; das vorhandene Python bleibt unangetastet.
- Gefundenes Python wird mit festem Pfad verwendet, nicht über `py`.
- Scheitert das Anlegen der Umgebung trotzdem, zeigt der Installer jetzt die
  Ausgabe von Python mit dem Grund. Ein halber `.venv`-Ordner aus einem
  abgebrochenen Versuch wird vorher entfernt.

## [1.3.0] – 2026-11-12

**Dritte Rolle „bearbeiten“ und Rollenwechsel**
- Neue Rolle **bearbeiten**: einlesen, Durchlauf starten, Rechnungen
  aufnehmen, Empfänger und Käuferreferenz wählen, freigeben, versenden,
  zurücklegen, Stornorechnung und Zahlungsanforderung senden. Keine
  Konfiguration, kein Schalten der Automatik, keine Zugänge, keine
  Aktualisierung.
- **Rolle ändern** unter „Benutzer“: Ein Verwalter wählt die Rolle eines
  anderen Zugangs in dessen Zeile. Das wirkt sofort, auch auf eine offene
  Anmeldung, und das Passwort bleibt. Der letzte Verwalter lässt sich nicht
  herabstufen, die eigene Rolle ändert ein anderer Verwalter.
- Bestehende Zugänge behalten ihre Rolle; es ist nichts einzustellen.

**Datum in der Mail deutsch**
- Betreff und Text der Mail nennen das Datum als TT.MM.JJJJ (09.11.2026)
  statt 2026-11-09, auch bei Gutschrift und Stornorechnung. Das XML führt
  das Datum weiter nach Norm (ISO).

## [1.2.0] – 2026-11-12

**Versandadresse: Das Mailfeld an der Reservierung hat Vorrang**
- Neue Reihenfolge, wenn Mailfelder eingestellt sind: 1. Mailfeld an der
  Reservierung, 2. Mailfeld am Profil des Rechnungsempfängers, 3. ist keines
  gefüllt, Sichtprüfung mit allen Adressen aus den Profilen zur Auswahl.
  Bisher galt das Profil zuerst.
- Wirkt sich nur aus, wenn **beide** Felder gefüllt sind: Dann geht die
  Rechnung jetzt an die Adresse an der Reservierung. Schon versendete
  Rechnungen bleiben, wie sie sind.
- Die Konfigurationsseite nennt die Reihenfolge und führt die Felder in dieser
  Reihenfolge auf. Handbuch und Hinweise sind angepasst.

## [1.1.0] – 2026-11-10

**Multiproperty: eine Installation je Hotelcode, mehrere auf einem Rechner**
- Windows-Installer mit `-Instanz` und `-Port`: Jede Installation bekommt
  einen eigenen Dienst (`OperaXRechnung-<Instanz>`) und einen eigenen Port.
  Name und Port stehen danach in `config\instanz.cmd`. `run.cmd` und die
  Dienst-Skripte lesen sie dort.
- Schutz der anderen Installationen: Gehört der Dienst einem anderen Ordner
  oder ist der Port belegt, bricht der Installer ab, bevor er etwas ändert.
  `dienst_einrichten.cmd` und `dienst_entfernen.cmd` fassen keinen Dienst
  einer anderen Installation an.
- Anmelde-Cookie je Installation: Mehrere Installationen auf einem Rechner
  melden sich nicht mehr gegenseitig ab. Nach der Aktualisierung einmal neu
  anmelden.
- Konfiguration: Das Feld heißt „Hotelcode (Resort)“. „Verbindung testen“
  nennt das Haus zum Code und bei einem unbekannten Code die vorhandenen.
- Reservierungen werden zusätzlich über den Hotelcode verknüpft, bei Gast,
  Zimmer, Zeitraum, Reservierungsfeldern und Gast-Mailadressen. Ein Verweis
  in ein anderes Haus ergibt „Gast unbekannt“ statt eines fremden Gastes.
- Die Bankverbindung wird nie aus OPERA gelesen: Der Eintrag dort gilt für
  die ganze Kette. Das bisher mitgelesene, ungenutzte Feld ist entfernt.
- Unter Rocky Linux bleibt es bei einer Installation je Rechner.

## [1.0.1] – 2026-11-10

**Korrekturen**
- Ältere OPERA-Versionen führen die City Tax in keinem Steuertopf des
  Rechnungskopfs. Die Gegenprobe je Steuersatz hielt deshalb jede Rechnung
  mit City Tax an („Steuersatz 0.00 %: Die Positionen ergeben 2.50, der
  Rechnungskopf in OPERA führt 0.00“). Zugelassen wird das jetzt, wenn die
  Abweichung genau die City Tax ist und der Gesamtbetrag mit OPERA stimmt.
- USt-IdNr., IBAN und BIC gehen ohne Leerzeichen in die XRechnung, auch
  wenn sie in der Konfiguration in Vierergruppen stehen.
## [1.0.0] – 2026-11-09

Erste gezählte Version. Sie entspricht dem Stand, der in einem Haus produktiv
läuft.

**Rechnungen**
- Liest abgeschlossene Rechnungen mit Firmenbezug aus OPERA V5, rein lesend.
- Baut XRechnung 3.0.2 (UBL), mit Anzahlungen, Steuergruppen, Abschlägen,
  City Tax und Paid Out; Positionen einzeln, zusammengefasst oder je Gast.
- Prüft rechnerisch und mit dem KoSIT-Validator; nur Gültiges geht hinaus.
- Sichtprüfung, wenn unklar ist, ob die Rechnung der Firma oder dem Gast
  gehört, und für Belege einer neuen Belegart nach der Umstellung.
- Versand per Mail mit Blindkopie, Sperre gegen Doppelversand.

**Zahlungsanforderung**
- PDF für Anzahlungen von Firmenkunden, keine Rechnung.
- Neu: Abschnitt „Angaben für Ihre Rechnung“ mit ausfüllbaren Feldern
  (Firmierung, USt-IdNr., E-Mail für die Rechnung, Bestellnummer oder
  Leitweg-ID, Hinweise für die Buchhaltung). Abschaltbar in der Vorlage.

**Installation und Betrieb**
- Installer für Windows und Rocky Linux; Aktualisierung über GitHub mit
  Zurückgehen auf Knopfdruck.
- Neu: Windows ohne winget (Server 2012 R2/2016/2019, Windows 8.1,
  Windows 10 LTSC): Python kommt direkt von python.org, mit Prüfung der
  Signatur. Dazu `install\INSTALLIEREN_OHNE_WINGET.cmd`.
- Neu: Liefert nssm.cc Fehler 503, lädt der Windows-Installer NSSM aus dem
  Internet Archive, geprüft gegen die Prüfsumme.
- Selbsttest ohne Datenbank, rund 1200 Prüfungen; läuft jetzt auch in einem
  frischen Checkout.
