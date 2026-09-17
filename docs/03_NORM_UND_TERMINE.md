# Norm-Stand XRechnung (Stand 08.09.2026)

- **Gültig produktiv: XRechnung 3.0.2** (KoSIT, veröffentlicht 20.06.2024).
  Genau diese Validierungsartefakte liegen in der Referenz unter
  `reference/XRechnung_Slim/validation/xrechnung-3.0.2/` — die Suite8-App
  hat mit exakt dieser Konfiguration abgenommene Rechnungen erzeugt.
- **XRechnung 4.0** ist die deutsche Umsetzung der überarbeiteten EN 16931-1:2026
  und wurde für Sommer 2026 erwartet. Das ist ein Major-Release: das semantische
  Modell wächst von 164 auf 216 Business Terms und von 32 auf 39 Business Groups.
  Eine Übergangsphase ist vorgesehen, 3.0.2 bleibt zunächst gültig.

**Konsequenz für dieses Projekt:** auf 3.0.2 bauen — dafür gibt es funktionierende,
im Feld erprobte Templates. Aber die Versionsauswahl von Anfang an konfigurierbar
halten (`app_settings.json` → `xrechnung_version`, Validierungsartefakte und
Template je Version), damit 4.0 später nur ein zusätzliches Template plus ein
zusätzliches Validator-Verzeichnis ist. Die Suite8-App hat das bereits so
angelegt; das nicht wegvereinfachen.

Vor Baubeginn ist der aktuelle Stand von 4.0 zu prüfen — falls 4.0 inzwischen
verpflichtend ist, ändert sich der Template-Teil, der Datenvertrag aber kaum.

## Stand 14.09.2026 und der Versionsschalter

**XRechnung 4.0 ist noch nicht veröffentlicht.** Das neueste Paket der KoSIT
ist das Bugfix-Release *XRechnung 3.0.2 Summer 2026* vom 31.08.2026
(Validator-Konfiguration, Schematron 2.6.0, Testsuite), veröffentlicht am
02.09.2026. Für 4.0 gibt es weder Spezifikation noch Regelwerk.
XStandards Einkauf kündigt eine Vorabversion „zeitnah“ an. Das Paket hängt
noch an Vorarbeiten des CEN, geplant ist ein schrittweiser Übergang.

**Gebaut ist der Schalter, nicht die Version.** Was eine neue Version braucht:

1. **Liste der Versionen:** ein Eintrag in `xml_build.VERSIONEN` mit Vorlage,
   CustomizationID (BT-24) und Name des Regelwerks.
2. **Vorlage:** eine neue Datei unter `app/xml_templates/`.
3. **Regelwerk:** abgelegt unter `validation/xrechnung-<version>/`. Der
   Installer lädt heute nur 3.0.2.
4. **Vorprüfung:** Prüfungen in `xml_build.pruefsummen`, soweit sich Regeln
   ändern.

Eingestellt wird die Version unter `xrechnung.version` bzw. auf der
Konfigurationsseite beim Validator. Was der Schalter zusichert:

- **Keine Datei in unbekannter Version:** Eine nicht verfügbare Version
  erzeugt keine Datei, und die Konfiguration speichert sie nicht.
- **Regelwerk passend zur Version:** Enthält `validierung.kosit_szenarien`
  den Platzhalter `{version}` (Vorgabe für neue Anlagen), wählt die Version das
  Regelwerk mit. Ein fester Pfad älterer Anlagen bleibt gültig, solange er
  passt. Passt er nicht, meldet die Konfigurationsseite das, statt gegen das
  falsche Regelwerk zu prüfen.
- **Version am Beleg:** Jeder Beleg hält fest, in welcher Version seine Datei
  erzeugt wurde (Detailseite, Verlauf, Versandprotokoll). Belege von vor dem
  14.09.2026 tragen keinen Eintrag; sie sind 3.0.2.

Noch nicht gebaut, weil erst mit 4.0 entscheidbar: eine Wahl der Version je
Empfänger für den Übergang.

## Warum das für Hotels überhaupt relevant ist

Seit 01.01.2025 muss jedes inländische Unternehmen E-Rechnungen im B2B
**empfangen** können; die Pflicht zum **Versand** greift gestaffelt danach.
Für Hotels ist der Treiber praktisch die Kundenseite: Behörden (Leitweg-ID,
seit 2020) und zunehmend große Firmenkunden verlangen strukturierte Rechnungen
zur Firmenrechnung/City Ledger.

## Quellen

- [XRechnung 4.0 — was kommt auf uns zu? (XStandards Einkauf)](https://xeinkauf.de/aktuelles/xrechnung/xrechnung-4-umsetzung/)
- [XRechnung 4.0: Weiterentwicklung des E-Rechnungsstandards (cosinex)](https://blog.cosinex.de/2026/03/25/xrechnung-4-0/)
- [validator-configuration-xrechnung — Releases (KoSIT)](https://github.com/itplr-kosit/validator-configuration-xrechnung/releases)
- [EN 16931 Gets Its Biggest Update Yet: XRechnung 4.0 and ZUGFeRD 2.5](https://www.eu-einvoicing.com/news/en-16931-2026-update-xrechnung-4-zugferd-25-explained)
