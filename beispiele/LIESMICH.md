# Beispiele

`rechnung_beispiel.xml` ist eine vollständige XRechnung, erzeugt aus dem
Testfall in `tools/smoketest.py`. Die Beträge stammen aus einem echten Beleg
(1400003, drei Steuersätze), Verkäufer- und Bankdaten sind durch Musterwerte
ersetzt.

Wozu die Datei da ist: Sie ist der **erste Prüfling für den KoSIT-Validator**.
Läuft sie dort ohne Beanstandung durch, ist zum ersten Mal belegt, dass die
Anwendung gültige XRechnungen erzeugt — die eingebaute Rechenprüfung allein
sagt darüber nichts.

Prüfen von Hand:

```
java -jar validation/validationtool.jar \
     -s validation/xrechnung-3.0.2/scenarios.xml \
     -o /tmp beispiele/rechnung_beispiel.xml
```

Im erzeugten Bericht `rechnung_beispiel-report.xml` steht im Wurzelelement
`valid="true"` oder `valid="false"` samt Begründung.

## Ergebnis vom 09.09.2026

Geprüft auf `xrechnung.example.local` mit KoSIT-Validator v1.6.3 (standalone),
OpenJDK 21.0.12.1, Regelwerk
`xrechnung-3.0.2-validator-configuration-2026-08-31`:

| | |
|---|---|
| Schema | **Y** |
| Schematron | **Y** |
| Bewertung | **ACCEPTABLE** |
| Dauer | 496 ms |

> „Erkannter Dokumenttyp: EN16931 XRechnung (UBL Invoice) — Das geprüfte
> Dokument enthält weder Fehler noch Warnungen. Es ist konform zu den formalen
> Vorgaben. Es wird empfohlen das Dokument anzunehmen und weiter zu
> verarbeiten."

Weder Fehler noch Warnungen, auch nicht auf Hinweisebene. Die drei Steuersätze
aus Beleg 1400003 gehen sauber durch.

**Damit ist zum ersten Mal geprüft statt gerechnet.** Die eingebaute
Rechenprüfung sagt nur, dass die Summen zueinander passen — dass das Dokument
den formalen Vorgaben von EN 16931 und XRechnung 3.0.2 genügt, sagt allein der
KoSIT-Validator.

## Eine Stolperfalle

Die Kennung im Element `CustomizationID` heißt seit Version 3.0
`urn:xeinkauf.de:kosit:xrechnung_3.0` — **nicht mehr** `urn:xoev-de:kosit:…`.
Mit der alten Kennung meldet der Validator „kein Prüfszenario hat gegriffen",
ohne einen inhaltlichen Fehler zu nennen. Genau diesen Fall meint die Meldung
„Kein Szenario gefunden — CustomizationID oder Namensraum prüfen" in
`app/validate.py`.

## Darstellung der Positionen — Prüfung vom 14.09.2026

`positionen_B_zusammengefasst.xml` und `positionen_C_je_gast.xml` stammen aus
der Gruppenprobe in `tools/smoketest.py` (Abschnitt 8). Die Rechnung hat zwei
Gäste mit verschiedenen Aufenthalten, zwei Zimmerpreise, ein Stornopaar und
eine Inklusivleistung zu 0,00. Die Namen sind erfunden, die Hausdaten sind
Musterwerte.

Geprüft auf dem Mac mit KoSIT-Validator v1.6.3 (standalone), Temurin JRE
21.0.12.1 und Regelwerk
`xrechnung-3.0.2-validator-configuration-2026-08-31`:

| Datei | Positionen | Schema | Schematron | Bewertung |
|---|---|---|---|---|
| dieselbe Rechnung, jede Buchung einzeln (A) | 23 + 2 Abschläge | Y | Y | ACCEPTABLE |
| `positionen_B_zusammengefasst.xml` | 5 | Y | Y | ACCEPTABLE |
| `positionen_C_je_gast.xml` | 6 | Y | Y | ACCEPTABLE |

Alle drei ohne Fehler und ohne Warnungen.

**Gegenprobe:** Dasselbe C-Dokument, nur mit dem ursprünglichen
Rechnungszeitraum des Kopfgastes (30.08.–04.09. statt 28.08.–06.09.), wird
**abgelehnt**: 16 × PEPPOL-EN16931-R110 und 16 × R111. Der Zeitraum jeder
Position muss im Rechnungszeitraum liegen, und das Regelwerk stuft diese
Regeln als fatal ein. Deshalb erweitert die Anwendung bei C den
Rechnungszeitraum auf alle Aufenthalte.
