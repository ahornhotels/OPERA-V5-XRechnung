# Wie die Positionen auf der Rechnung stehen — Optionen

> **Entschieden am 14.09.2026** von der Buchhaltung, auf Grundlage des
> Foliensatzes:
>
> 1. **Zwei Arten:** für Gruppen und für Einzelrechnungen.
> 2. **In die Bemerkung der Position kommen Gastname und Zimmernummer.**
> 3. **Die Gastnamen dürfen und müssen auf die Rechnung.**
>
> **Umgesetzt am 14.09.2026:** B für Einzelrechnungen, C für Gruppen,
> vorbelegt nach der Anzahl der Reservierungen auf dem Beleg und je Rechnung
> auf der Detailseite umschaltbar. Beschreibung unten im Abschnitt
> [Umsetzung](#umsetzung-14092026), Bedienung im Handbuch.

Zwei Fragen aus dem Haus, die zusammengehören:

1. Lassen sich gleichartige Zeilen zusammenfassen — *Menge × Preis* statt
   zehnmal derselbe Eintrag?
2. Gruppen und Reiseveranstalter wollen oft die **Namen der Gäste** auf der
   Rechnung sehen. Was geht da?

Die kurze Antwort auf beides: **Ja. Und die beiden ziehen in
entgegengesetzte Richtungen** — deshalb hängen sie an derselben Entscheidung.

---

## Was die Norm erlaubt

**Es gibt keine Regel, dass eine Rechnungsposition einer Buchung in OPERA
entsprechen muss.** Die Norm kennt Positionen, nicht Buchungen. Was das Haus
zu einer Position zusammenfasst, ist seine Entscheidung.

Drei Bedingungen sind einzuhalten:

| Regel | heißt konkret |
|---|---|
| PEPPOL-EN16931-R120 | Menge × Einzelpreis muss den Positionsbetrag ergeben — beide auf zwei Stellen gerundet |
| BR-CO-10 | Die Summe der Positionen muss die ausgewiesene Nettosumme sein |
| § 14 UStG | Art und Umfang der Leistung müssen erkennbar bleiben |

Der Steuersatz muss deshalb immer Teil des Bündelungsschlüssels sein, und der
Einzelpreis auch — sonst geht die Multiplikation nicht auf. Zwei Nächte zu
189,00 und drei zu 216,09 werden **zwei** Positionen, nicht eine mit einem
Durchschnittspreis.

Für die Gästenamen gibt es vier Plätze:

| Feld | trägt | brauchbar für |
|---|---|---|
| **BT-127** Bemerkung je Position | freier Text an der einzelnen Zeile | **Gruppen** — ein Name je Zeile |
| **BT-134/135** Zeitraum je Position | Von–Bis an der Zeile | Aufenthalt je Gast |
| BT-70 Empfänger der Leistung | **ein** Name für die ganze Rechnung | Einzelgast |
| BT-22 Bemerkung am Kopf | ein Satz für die ganze Rechnung | Einzelgast |

**Für eine Gruppe taugt nur BT-127 zusammen mit BT-134/135.** BT-70 kann genau
einen Namen tragen; bei dreißig Zimmern müsste man sich für einen entscheiden.

---

## Die vier Möglichkeiten

Der Unterschied ist einzig, **wonach gebündelt wird**.

### A — Je Buchung (heute)

Jede Buchung in OPERA wird eine Position. Zehn Nächte sind zehn Zeilen.

*Dafür:* Nichts geht verloren, jede Zeile hat ihr Datum.
*Dagegen:* Eine Gruppenrechnung über 30 Zimmer × 5 Nächte hat 150 Zeilen plus
Frühstück und Parken. Das liest niemand.

### B — Je Leistungsart, Steuersatz und Einzelpreis

    Übernachtung 7 %     10 × 216,09     2.160,90
    Frühstück 7 %        10 ×  25,00       250,00
    Parken 19 %           5 ×  30,00       150,00

*Dafür:* Kurz und so, wie eine Hotelrechnung üblicherweise aussieht.
*Dagegen:* **Kein Gästename, kein Zimmer, kein Datum mehr.** Für eine
Gruppenrechnung an einen Reiseveranstalter ist sie damit wertlos — er kann sie
nicht auf seine Reisenden aufteilen.

### C — Je Gast bzw. Zimmer, dann je Leistungsart

    Zi. 214 · Musterfrau, Lena · 30.08.–04.09.
      Übernachtung 7 %    5 × 216,09     1.080,45
      Frühstück 7 %       5 ×  25,00       125,00
    Zi. 215 · Beispiel, Max · 30.08.–04.09.
      Übernachtung 7 %    5 × 216,09     1.080,45

Der Name steht als Bemerkung an der Position (BT-127), der Zeitraum als
Positionszeitraum (BT-134/135).

*Dafür:* Kurz **und** aufteilbar. Der Reiseveranstalter sieht, wer wann da war;
sein System kann es auswerten, weil es strukturierte Felder sind und kein Text.
*Dagegen:* Mehr Zeilen als B — bei 30 Zimmern und drei Leistungsarten 90 statt 3.

### D — Je Gast, alles in einer Zeile

    Zi. 214 · Musterfrau, Lena · 30.08.–04.09.   1 × 1.205,45

*Dafür:* Die kürzeste Form, die den Gast noch nennt.
*Dagegen:* Der Steuersatz wird zum Problem — 7 % auf Übernachtung und 19 % auf
Parken lassen sich nicht in eine Position legen. Es werden also doch zwei je
Gast, und der Vorteil gegenüber C schmilzt.

---

## Was die Daten hergeben

Nachgesehen im Data Dictionary: `FINANCIAL_TRANSACTIONS` führt an **jeder
einzelnen Buchung**

    RESV_NAME_ID     die Reservierung — und damit der Gast
    ROOM             die Zimmernummer
    TRX_DATE         das Datum der Buchung
    QUANTITY         die Menge
    PRICE_PER_UNIT   den Einzelpreis

Alle vier Möglichkeiten sind damit ohne Zusatzpflege machbar. **Das gilt auch
für Gruppenfolios:** Weil die Reservierung an der Buchung hängt und nicht nur
am Beleg, lässt sich eine Sammelrechnung nach Gast aufteilen, obwohl sie auf
einem Konto ausgecheckt wurde.

Anzusehen wäre vorher, wie gut `PRICE_PER_UNIT` gefüllt ist — bisher leitet die
Anwendung den Einzelpreis aus Betrag ÷ Menge ab, und das funktioniert. Beides
nebeneinander zu halten wäre eine Fehlerquelle; besser bleibt es bei einer
Quelle.

---

## Empfehlung

**Zwei Arten, umschaltbar — aber nicht global, sondern je Rechnung, mit einer
sinnvollen Vorbelegung.**

    Rechnung an eine Firma, ein Gast        -> B  (kurz)
    Rechnung an Reisebüro oder Gruppe       -> C  (mit Namen)

Die Vorbelegung kann die Anwendung selbst treffen: Sie weiß, ob der Empfänger
ein Reisebüro ist (`name_type`) und ob mehr als ein Gast auf dem Beleg liegt.
Auf der Detailseite steht die gewählte Art und lässt sich vor dem Versand
ändern — „manchmal/oft" heißt, dass eine feste Regel es nicht trifft.

**Warum nicht A als Vorgabe lassen:** Eine 150-zeilige Rechnung ist nicht
falsch, aber sie erschwert genau das, wofür die XRechnung da ist — die
automatische Prüfung beim Empfänger. Wer 150 Zeilen bekommt, prüft von Hand.

**Warum B nicht für alle:** Sie nimmt der Gruppenrechnung die einzige
Information, die den Reiseveranstalter interessiert.

---

## Was zu entscheiden ist

1. **Sollen es zwei Arten sein oder eine?** Zwei bedeuten eine Wahl auf der
   Detailseite und eine Vorbelegung, die manchmal danebenliegt.
2. **Was steht in der Bemerkung je Position?** Name allein, oder Zimmer und
   Zeitraum dazu? Der Zeitraum hat mit BT-134/135 ein eigenes Feld und gehört
   dorthin, nicht in den Text.
3. **Dürfen Gästenamen überhaupt auf eine Rechnung an einen Dritten?** Bei
   einem Reiseveranstalter, der die Reise gebucht hat, kennt er die Namen
   ohnehin. Bei einer Firma, die eine Sammelrechnung bekommt, ist es eine
   Frage, die das Haus einmal beantworten sollte — nicht die Anwendung.

Bis zum 14.09.2026 war das hier nur die Entscheidungsvorlage.

---

## Umsetzung (14.09.2026)

**Vorbelegung.** C, wenn die Buchungen zu mehr als einer Reservierung gehören,
oder wenn an den Buchungen ein Gast hängt, am Rechnungskopf aber keiner. Sonst
B. Auf der Detailseite lässt sich die Art je Rechnung ändern; A („jede Buchung
einzeln") bleibt als Rückweg wählbar. `property.positionen` kann eine Art fest
vorgeben.

**Bündelungsschlüssel.** B bündelt nach Umsatzcode, Steuerkategorie,
Steuersatz und **Bruttopreis auf den Cent**, C zusätzlich nach Reservierung
**und Zimmer**. Das Zimmer gehört dazu, weil bei einem Zimmerwechsel sonst nur
das erste Zimmer an der Position stünde.
Der Bruttopreis ist der richtige Schlüssel: OPERA führt den Nettobetrag
ungerundet und aus dem Brutto abgeleitet. Summiert werden die ungerundeten
Beträge; gerundet wird wie bisher erst beim XML-Bau. Die Summe der Positionen
ist damit dieselbe wie unter A.

**Sonderfälle.**

- Heben sich Buchungen einer Gruppe auf (Menge 0, Betrag 0), fällt die
  Position weg.
- Eine Buchung mit Menge 0 wird nie gebündelt.
- Inklusivleistungen zu 0,00 werden gebündelt (5 × 0,00).
- Ein Positionszeitraum mit Ende vor Beginn wird nicht ausgegeben (BR-30).
- Ein Rabatt wird wie bisher zum Abschlag auf Rechnungsebene. Unter C trägt
  sein Grund Zimmer und Gast („Rabatt · Zi. 214 · Musterfrau, Lena“).

**Aus dem Code-Review vom 16.09.2026** zusätzlich geändert:

- Der **Zeitraum an der Position** ist die Spanne der berechneten Tage
  (Buchungsdatum), nicht mehr der ganze Aufenthalt der Reservierung. Bei einem
  Masterkonto konnte der Monate umfassen und weitete den Rechnungszeitraum auf.
- Bei einer **Gruppe** nennt der Rechnungskopf keinen einzelnen Gast mehr:
  BT-70 und die Gastzeile entfallen, weil dort nur der Gast der
  Kopfreservierung stand. Die Namen stehen an den Positionen.
- `property.gastzuordnung_bestaetigt` steht seit dem **16.09.2026 auf `true`**:
  Die Zuordnung ist an echten Daten belegt — an **einer** Installation, über
  einen Monat und mehrere zehntausend Erlöszeilen. `ORIGINAL_RESV_NAME_ID` ist
  dort **immer** gefüllt und weicht bei rund 18 % der Zeilen von
  `RESV_NAME_ID` ab — genau den umgeleiteten Buchungen, deckungsgleich mit dem
  Anteil gefüllter `FROM_RESV_ID` und dem Anteil mit Routing-Anweisung.
  `FROM_RESV_ID` steht **nie allein**, wird also nicht gebraucht. Ein kleiner
  Rest hat kein Zimmer (Kasse, Paidout); dort nennt die Bemerkung nur den Gast.
  Solange der Schalter auf `false` steht, verschickt die **Automatik** eine
  Rechnung in dieser Darstellung nicht, sondern legt sie in die Prüfung — von
  Hand bleibt sie versendbar. Das ist der Rückweg, falls
  `sql/discovery/06_positionen_gast.sql` in einem anderen Haus ein anderes
  Bild zeigt.

**Der Gast an der Buchung.** Die Zuordnung läuft über
`NVL(ORIGINAL_RESV_NAME_ID, RESV_NAME_ID)` und `NVL(ORIGINAL_ROOM, ROOM)`. Bei
Gruppen sind die Buchungen meist vom Gastzimmer auf ein Masterkonto umgeleitet.
`RESV_NAME_ID` zeigt dann auf das Masterkonto, und C nennte an jeder Zeile die
Gruppe statt des Gastes. Diese Annahme stammte zunächst aus dem Data Dictionary und ist inzwischen
an Daten bestätigt — an einer Installation. Die Gegenprobe für das eigene
Haus steht in `sql/discovery/06_positionen_gast.sql`
und ist vor dem ersten Versand einer Gruppenrechnung zu fahren.

**Rechnungszeitraum.** PEPPOL-EN16931-R110/R111 sind im Regelwerk 3.0.2
*fatal*: Der Zeitraum jeder Position muss im Rechnungszeitraum liegen. Der
Rechnungskopf trägt den Aufenthalt einer einzigen Reservierung. Bei C wird
BT-73/74 deshalb auf die Spanne aller Aufenthalte erweitert. Die Vorprüfung
meldet R110/R111 zusätzlich selbst.

**Was sich im XML ändert** — die Probe „vorher/nachher“ lohnt sich, bevor
umgestellt wird:

| Element | wann |
|---|---|
| Anzahl, `InvoicedQuantity`, `PriceAmount` der Positionen | B und C, sobald zwei Buchungen denselben Schlüssel haben — also fast immer |
| `InvoiceLine/cbc:Note` (BT-127) | C: immer, wenn Zimmer oder Gast bekannt sind („Zi. 214 · Musterfrau, Lena", dahinter eine vorhandene Buchungsbemerkung). B: wie bisher nur bei einer Buchungsbemerkung |
| `InvoiceLine/cac:InvoicePeriod` (BG-26) | nur C, wenn die Reservierung Anreise und Abreise trägt |
| `Invoice/cac:InvoicePeriod` (BG-14) | nur C, und nur wenn ein Aufenthalt über den des Kopfgastes hinausreicht |
| BT-106 und BT-107 | B und C: kleiner um den Betrag von Stornopaaren, die sich in einer Gruppe aufheben (unter A Position plus Abschlag) |
| BT-109, BT-110, BT-112, BT-115, Steuergruppen | **unverändert** — geprüft an einer Gruppenrechnung mit Storno, zwei Preisen und Inklusivleistung, in allen drei Darstellungen |

**Geprüft** mit dem KoSIT-Validator v1.6.3, Regelwerk
`xrechnung-3.0.2-validator-configuration-2026-08-31`: A, B und C *acceptable*,
ohne Fehler und ohne Warnung. Gegenprobe: dasselbe C-Dokument mit dem
ursprünglichen, engeren Rechnungszeitraum wird mit R110/R111 abgelehnt. Belege
in `beispiele/`.
