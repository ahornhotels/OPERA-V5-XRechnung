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
- Selbsttest ohne Datenbank, rund 1200 Prüfungen; läuft jetzt auch in einem
  frischen Checkout.
