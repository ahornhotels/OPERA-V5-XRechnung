# OPERA-Versionen ohne `DOCUMENT_TYPE` und `COMPANY_NAME` — Konzept

Stand: 30.10.2026 · Status: **Entschieden: Jeder gültige Beleg ist eine Rechnung — die Belegart wird nicht mehr gebraucht. Umgesetzt als Testkandidat (Branch `testkandidat-belegarten`): Auswahl, Anzahlungsrechnung, Leistungszeitraum bei PM-Konten, tägliche Nachprüfung mit Aufgabenliste. Noch offen: Stornorechnung aus dem Archiv, TSE-Nachricht archivieren, Betrieb ohne `DOCUMENT_TYPE`.**

## Entscheidung: Jeder gültige Beleg ist eine Rechnung (30.10.2026, abends)

Ausgangsfrage: Muss die Anwendung überhaupt nach Belegart unterscheiden? Die
Unterscheidung sollte verhindern, dass dieselbe Leistung auf zwei Rechnungen
steht. Die Messung im bisherigen Haus zeigt, dass das nicht passiert:

- **Jede Buchung steht auf genau einem Beleg.** Voraus-, Zwischen- und
  Schlussrechnung am selben Folio enthalten verschiedene Buchungen. Die
  Schlussrechnung wiederholt die Nächte der Vorausrechnung nicht.
- **Eine Umbuchung verschiebt die Buchung**, sie kopiert sie nicht (dieselbe
  Zeile, `RESV_NAME_ID` wird das Ziel, `ORIGINAL_RESV_NAME_ID`/`FROM_RESV_ID`
  behalten den Ursprung). Das abgebende Folio bekommt keinen Beleg.
- **Die TSE signiert jeden ausgegebenen Beleg**, gleich welcher Art. Keine
  Signatur haben nur interne Folios (`FOLIO_TYPE = 'INTERNAL'`, Rundungs- und
  Zahlungsausgleich) und stornierte Belege (`VOID`).

Daraus, festgelegt:

1. **Vorausrechnungen und Zwischenrechnungen sind Rechnungen** (§ 14 Abs. 1
   UStG: abgerechnet wird, gleich wie das Dokument heißt). Sie sind oft die
   einzige Rechnung über ihre Nächte. XRechnung **Typ 380**, Leistungszeitraum
   aus den Buchungen, auch wenn er in der Zukunft liegt.
2. **Anzahlungsbelege (`STATUS = 'DEPOSIT'`) mit TSE-Signatur sind
   Anzahlungsrechnungen**, XRechnung **Typ 380 mit Vermerk
   „Anzahlungsrechnung“** in BT-22. Den Typ 386 (UNTDID 1001, in EN 16931 und
   ZUGFeRD zulässig) lässt XRechnung 3.0.2 nicht zu (BR-DE-17); der lokale
   KoSIT-Validator setzt dann das Gesamturteil auf ungültig, und die
   Anwendung sperrt danach. Die Rechnung, die sie
   verrechnet, setzt sie mit ihrer Steuer ab (§ 14 Abs. 5 UStG): als
   Abschlag auf Dokumentebene je Steuersatz, Netto und Steuer aus den Buckets
   des Anzahlungsbelegs, mit Verweis (BG-3). Vorher stand die Anzahlung nur
   brutto als BT-113 da, und die Endrechnung wies die volle Steuer aus. Anzahlungsbelege haben eigene Erlös- und
   Steuerzeilen (eigene Anzahlungs-Transaktionscodes), die XRechnung lässt
   sich also aus den Positionen bilden. Belege mit `DOCUMENT_TYPE = 'COPY OF
   INVOICE'` (ebenfalls `DEPOSIT`, mit eigener TSE-Signatur und eigenen
   Zeilen) sind keine Nachdrucke; was sie im Arbeitsablauf sind, klärt das
   Haus, bis dahin gehen sie nicht hinaus.
3. **Eine zurückgenommene Vorausrechnung wird in OPERA ungültig gemacht.**
   OPERA setzt sie auf `VOID` mit Betrag 0, nimmt ihr die TSE-Nummer und gibt
   sofort einen neuen Beleg mit neuer Nummer und Signatur aus. Einen Verweis
   vom neuen auf den alten Beleg gibt es nicht. Storniert wird im bisherigen
   Haus spätestens am Tag nach dem Buchungstag, die Hälfte binnen Minuten
   (sofortige Neuausgabe). In OPERA steht danach weder der alte Betrag noch
   der Ausgabezeitpunkt am Beleg; beides kennt die Anwendung aus ihrem
   eigenen Archiv.
   **Entschieden:** Rechnungen gehen weiter nach der kurzen Wartezeit hinaus,
   nicht erst am Folgetag. Stattdessen prüft die Anwendung **einmal nach dem
   Tagesabschluss**, ob Belege, die sie am Vortag oder Vorvortag versendet
   hat, inzwischen `VOID` sind, und stellt sie in eine **Aufgabenliste**. Von
   dort wird die Stornorechnung (Typ 381 mit Bezug) erzeugt — aus der
   archivierten XRechnung, denn in OPERA steht der stornierte Beleg nur noch
   mit 0 €. Der Ersatzbeleg ist ein neuer Beleg und geht normal hinaus.

**Weitere Befunde für die Umsetzung:**

- Belege mit Kopfbetrag, aber ohne eine einzige Zeile, gibt es vereinzelt.
  Die Bedingung „Beleg hat Buchungen“ schließt sie aus; eine XRechnung ohne
  Positionen wäre ungültig.
- Bei Belegen von Pseudozimmern (PM-Konten) liegt der Leistungszeitraum oft
  außerhalb der PM-Reservierung. BT-73/BT-74 kommen deshalb aus den Daten
  der Positionen. Ein PM-Beleg kann Leistungen aus fast 200 Aufenthalten
  bündeln; die Positionen sollten Gast und Zimmer der Herkunft nennen.
- Mengengerüst im bisherigen Haus: Mit der neuen Regel kommen zu den
  Schlussrechnungen etwa ebenso viele Belege hinzu. Vorausrechnungen sind zu
  rund 80 % Firmenbuchungen, Schlussrechnungen zu rund 40 %.
- **An einer ausgegebenen, gültigen Rechnung ändert OPERA die Buchungen
  nicht.** Alle Positionen stehen bei der Ausgabe fest; der Nachtlauf bucht
  erst und rechnet dann ab. Buchungen wandern nur bei Storno und Neuausgabe
  auf den Ersatzbeleg. Nachträglich ändern kann sich an einer gültigen
  Rechnung nur der Profil- bzw. Zahlerbezug (`NAME_ID`, `PAYEE_NAME_ID`),
  selten und bis knapp zwei Tage nach Ausgabe.
- **Vorsicht beim Datum:** `BILL_GENERATION_DATE` ist das Buchungsdatum. Im
  Nachtlauf liegt es einen Tag hinter dem Kalender, die Uhrzeit
  (`BILL_GENERATION_TIME`) ist aber echte Uhrzeit. Die echte Ausgabezeit
  steht in `FISCAL_FOLIO_QUEUE.INSERT_DATE`.
- **Anzahlungen werden auch auf Vorausrechnungen verrechnet**, nicht nur auf
  Schlussrechnungen. Die Verrechnung steht im Kopf (`TOTAL_GROSS`) und in der
  Nachricht an die TSE, nie als Buchung unter der Rechnungsnummer der
  verrechnenden Rechnung; die Buchung liegt auf dem Anzahlungsbeleg. Es gilt
  je Rechnung: Positionen = Kopf + verrechnete Anzahlung.
- **Die Nachricht an die TSE** (`FISCAL_FOLIO_QUEUE.PAYLOAD`, XML) enthält
  alle Positionen mit denselben Buchungsnummern und Beträgen wie die
  Buchungstabelle, dazu die Anzahlungsverrechnung, aber keine Positionstexte.
  Sie stimmt immer mit dem Kopf überein. Die Anwendung baut die Positionen
  weiter aus der Buchungstabelle und bewahrt die TSE-Nachricht als Nachweis
  auf, wie die Rechnung signiert wurde.

**Entschieden zum Versand:** Wartezeit bleibt (Standard 120 Minuten), für
alle Belegarten. Einmal nach dem Tagesabschluss prüft die Anwendung die am
Vortag und Vorvortag versendeten Belege auf genau zwei Dinge: **storniert**
(Stornorechnung nötig) und **Profil- oder Zahlerbezug geändert** (die
XRechnung ging womöglich an den Falschen). Treffer kommen in eine
Aufgabenliste. Ein Abgleich der Positionen ist nicht nötig.

**Die neue Regel:** Ein Beleg wird XRechnung, wenn `STATUS` = `OK` (bzw.
`DEPOSIT` für die Anzahlungsrechnung), eine TSE-Nummer (`FISCAL_BILL_NO`) da ist und er
Buchungen hat. Danach kommen die bisherigen Filter (Firmenbezug, Inland,
Kennzeichen am Profil, Mindestbetrag). Ab 2027 ist die E-Rechnung für alle
Rechnungen an inländische Unternehmen Pflicht, ausgenommen
Kleinbetragsrechnungen bis 250 € brutto.

**Folge für Häuser ohne `DOCUMENT_TYPE`:** Die Regel braucht die Spalte nicht.
`PROCESS_IDENT` (unten) ist nur noch nötig, um die Belegart anzuzeigen, nicht
um zu entscheiden. Im Zielhaus ist zu messen, ob es die TSE über dieselben
Tabellen und Felder betreibt.

**Wer im Bestand nach doppelten Leistungen sucht**, muss die
Ursprungsreservierung in den Schlüssel nehmen. Ohne sie erscheinen mehrere
gleiche Zimmer einer Gruppe, die auf ein Folio umgebucht wurden, fälschlich
als Doppelbelastung.

## Der Weg: `FOLIOS.PROCESS_IDENT` (30.10.2026, später am Tag)

`FOLIOS.PROCESS_IDENT` hat im bisherigen Haus genau zwei Werte, `C` und `I`.
Je Beleg gibt es genau eine `FOLIOS`-Zeile (Schlüssel `RESORT`, `FOLIO_NO`,
`BILL_NO`). Gegen `DOCUMENT_TYPE` gemessen, OK-Belege, 90 Tage:

| DOCUMENT_TYPE | `C` | `I` |
|---|---|---|
| INVOICE | 8.789 | 50 |
| ADVANCE INVOICE | 35 | 2.999 |
| INTERIM INVOICE | 0 | 24 |

„`PROCESS_IDENT = 'C'` ist Endrechnung" übersieht 50 von 8.839 (0,6 %) und
lässt 35 Vorausrechnungen durch, **keine einzige Zwischenrechnung**. Alle
Anzahlungsbelege und Kopien stehen auf `I`. Seit dem Patch (78.699 Belege):
977 übersehen (1,4 %), 806 durchgelassen. Die 35 sind Vorausrechnungen, die
spät abends am Tag vor der Abreise entstanden. `FOLIOS` und `PROCESS_IDENT`
gibt es im Zielhaus.

Ergänzend trägt der Zeitpunkt: 95,8 % der Endrechnungen entstehen am
Abreisetag, keine Voraus- oder Zwischenrechnung danach. Beides zusammen (`C`
UND ab Abreisetag) lässt in 90 Tagen genau einen Nicht-Endbeleg durch, übersieht
aber 136.

**Was der Befund umdreht:** Von 11.744 Folios mit OK-Belegen in 90 Tagen haben
**2.950 nur eine Vorausrechnung und nie eine Endrechnung** (über 200 Tage
gegengeprüft). Bei 2.634 davon deckt die Vorausrechnung die Buchungen des
Folios auf den Cent. Sie ist dort die einzige und endgültige Rechnung des
Aufenthalts. Die Anwendung nimmt aber nur `DOCUMENT_TYPE = 'INVOICE'` — **für
diese Aufenthalte entsteht heute keine XRechnung**, auch im bisherigen Haus.

Daraus die Regel, die `DOCUMENT_TYPE` gar nicht braucht:

    Rechnung = STATUS 'OK' UND ( PROCESS_IDENT = 'C'
                                 ODER am Folio gibt es keinen OK-Beleg mit 'C' )

Sie gibt 11.662 von 11.744 Folios genau eine Rechnung, 82 zwei oder drei
(Stichentscheid nötig), keinem keine. Zum Vergleich heute: 2.968 Folios ohne
Rechnung.

**Folios mit Voraus- UND Endrechnung:** Jede Buchung steht auf genau einem
Beleg. Gleiche Buchungen (Code, Datum, Betrag) auf beiden Belegen stammen aus
verschiedenen Reservierungen, etwa mehrere Zimmer einer Gruppe, die auf ein
Folio umgebucht wurden. Wer nach Doppeln sucht, muss die
Ursprungsreservierung (`ORIGINAL_RESV_NAME_ID`) in den Schlüssel nehmen; ohne
sie erscheinen solche Gruppen fälschlich als Doppelbelastung.

**Im Zielhaus zu belegen** (Blöcke 7 und 8 der Abfrage `09`): Hat
`PROCESS_IDENT` dort dieselben Werte und dieselbe Bedeutung? Ohne
`DOCUMENT_TYPE` als Gegenprobe geht das über den Zeitpunkt. Und der Anteil der
Vorausrechnungen ist eine Arbeitsweise des Hauses, nicht von OPERA.

## Erste Ergebnisse (30.10.2026, verworfene Wege)

**`DOCUMENT_TYPE` lässt sich nicht nachbauen.** Am bisherigen Haus, das beides
hat, nachgerechnet (90 Tage):

| Regel | Endrechnungen übersehen | Falsche durchgelassen |
|---|---|---|
| `STATUS = 'OK'` allein | 0 | **3.057** (Voraus- und Zwischenrechnungen) |
| dazu „keine Buchung mit `ADVANCE_BILL_YN = 'Y'`“ | **1.490 von 8.837** (16,9 %) | **80**, darunter 16 Zwischenrechnungen bis 4.546,73 € |

`ADVANCE_BILL_YN` kennzeichnet die **Buchung** („von einer Vorausrechnung
erzeugt“), nicht den Beleg — wird die Buchung später auf der Schlussrechnung
ausgewiesen, trägt sie das Kennzeichen weiter. `PROFORMA_YN`,
`ADVANCE_BILL_REVERSED_YN`, `INVOICE_TYPE = 'P'` und `ORG_FOLIO_TYPE` sind im
bisherigen Haus nie gefüllt. Untersucht wurden 278 der 281 Kopfspalten, die
das Zielhaus hat: **keine trennt** Schlussrechnung, Voraus- und
Zwischenrechnung. Die Zwischenrechnung ist ohne `DOCUMENT_TYPE` überhaupt nicht
erkennbar.

Eine stille Heuristik, die jede sechste Schlussrechnung übersieht und
Zwischenrechnungen über mehrere tausend Euro verschickt, ist schlechter als
keine. **Der Ersatzweg für `DOCUMENT_TYPE` wird deshalb nicht gebaut.**

**Auch die Fiskaltabellen helfen nicht** (geprüft 30.10.2026, alle OK-Belege
seit Start der TSE, 71.297): In `FISCAL_FOLIO_QUEUE` steht `OPERATION` für
Schluss-, Voraus- und Zwischenrechnung gleichermaßen auf `INVOICE`; Status und
`FOLIO_TYPE` sind überall gleich. Der Payload an das Fiskalprogramm (XML,
`<OperaFiscalPayload>`) führt in allen typverdächtigen Feldern denselben Wert
(`Command`, `FolioType`, `ReceiptType`, `CreditBill` …), und die Wörter ADVANCE
und INTERIM kommen darin nicht vor (Stichprobe 600 Belege). `CHAR1`–`5`,
`BIGCHAR1`–`5` sind leer oder konstant, `FISCAL_FOLIO_TAX_RESPONSE_DTLS` enthält
nur Signaturwerte. Die Belegart wird der TSE schlicht nicht übermittelt — ihr
ist gleich, was sie signiert.

Nebenbefund: `FOLIO$_TAX.SEQ_NO` ist auf allen Belegen seit Start der TSE
gefüllt und eindeutig (anders als `BILL_NO`) und verknüpft Beleg und
Fiskaldaten. Als interner Schlüssel wäre er robuster als (`FOLIO_NO`,
`BILL_NO`); nach außen bleibt `BILL_NO` die Rechnungsnummer.

**Wann die Spalte kam:** mit **OPERA PMS 5.0.06.25, ePatchLevel E00007**. Im
bisherigen Haus installiert am 22.01.2025; der erste Beleg mit
`DOCUMENT_TYPE` stammt von genau diesem Tag (das TSE-Modul kam erst vier
Monate später). Ablesbar in `OPERA.INSTALLED_APP` (Block 5 der Abfrage
`09_belegarten_ohne_document_type.sql`).

**Empfehlung für das Zielhaus:**
1. **OPERA auf 5.0.06.25 E00007 oder neuer bringen.** Ein Patchlevel, kein
   Versionswechsel. Danach läuft die Anwendung unverändert.
2. Bis dahin, wenn es nicht warten kann: **kein automatischer Betrieb.** Nur
   einzeln über die Suche geholte Belege, jeder in der Sichtprüfung, wo ein
   Mensch bestätigt, dass es eine Schlussrechnung ist. Das wäre ein eigener,
   sichtbarer Betriebsmodus — nicht umgesetzt.

**`COMPANY_NAME` dagegen ist ersetzbar:** `FOLIO$_TAX.COMPANY_NAME IS NOT NULL`
genau dann, wenn `NAME_RESERVATION.COMPANY_ID IS NOT NULL` — ohne eine
Ausnahme in 8.837 Rechnungen. Die Namen stimmen bis auf 33 Schreibweisen
überein (fehlender Punkt, „&“ gegen „/“). Laufzeit über alle 8.837 Belege unter
0,6 s. Für sich allein lohnt der Umbau aber nur, wenn das Zielhaus ohne Patch
betrieben werden soll.

**`DOCUMENT_TYPE` kann auch leer sein**, wo die Spalte existiert: seit dem
Patch 228 OK-Belege ohne Wert, in den letzten 90 Tagen noch einer. Die
Anwendung behandelt das schon richtig — ein Beleg ohne Belegart ist keine
Schlussrechnung.

## Anlass

Für eine Installation in einem weiteren Haus liegt dessen Datenbankstruktur vor
(Export aus den Oracle-Katalogsichten: 6.955 Objekte, 174.451 Spalten, nur
Aufbau, keine Daten). Abgeglichen gegen jede Tabelle und Spalte, die die
Anwendung benutzt:

- Alle **16 Objekte** sind vorhanden (`FOLIO$_TAX`, `FOLIOS`,
  `FINANCIAL_TRANSACTIONS`, `NAME`, `MEMBERSHIPS` … — als Views ohne `_E`).
- In `FOLIO$_TAX` fehlen **14 Spalten** (281 statt 295). Zwei davon benutzt die
  Anwendung:

| Spalte | benutzt in | wozu |
|---|---|---|
| `DOCUMENT_TYPE` | `invoice_list`, `invoice_header`, `invoice_folio`, `invoice_guard`, `invoice_deposits`, `invoice_suche`, `invoice_gutschrift_bezug` | Endrechnung von Voraus-, Zwischen- und Rechnungskopie unterscheiden |
| `COMPANY_NAME` | `invoice_list`, `invoice_header`, `invoice_suche`, `invoice_buchungsfirma` | Firmenbezug „Reservierung“ (Firma an der Buchung, Zahler privat); Kundenname als Rückfall |

Ohne Anpassung scheitern damit 9 der 18 Abfragen mit `ORA-00904` — Einlesen,
Detailseite und Erzeugen gehen nicht. „Datenbank testen“ meldet das inzwischen
beim Einrichten (Abfragentest).

Die übrigen zwölf fehlenden Spalten (`AUTO_GENERATED_YN`, `COMPANY_TYPE`,
`DOCUMENT_CODE`, `FISCAL_DOCUMENT_NO_1/2`, `FOLIO_TYPE_PREFIX/SUFFIX`,
`GUEST_NAME`, `REASON_CODE`, `REASON_TEXT`, `SUPPORTING_DOCUMENT_ID`,
`COMPANY_FINANCIAL_VALUE`) benutzt die Anwendung nicht.

## Warum nicht einfach weglassen

`DOCUMENT_TYPE` ist kein Schmuck. Vorausrechnungen haben in OPERA ebenfalls
`STATUS = 'OK'` — im bisherigen Haus 3.030 in 90 Tagen, dazu 22 Zwischenrechnungen. Ohne
Unterscheidung würde die Anwendung sie als Schlussrechnungen aufnehmen und
verschicken. Ein Rückfall „nur `STATUS = 'OK'`“ ist deshalb **nicht** zulässig.

## Was das ältere OPERA stattdessen hat

Aus den Spaltenkommentaren des Zielhauses (dort gepflegt, anders als im bisherigen Haus):

| Spalte | Kommentar von Oracle | Ersatz für |
|---|---|---|
| `FINANCIAL_TRANSACTIONS.ADVANCE_BILL_YN` | „Identifies if this transaction was generated by Advance Bill." | Vorausrechnung |
| `FINANCIAL_TRANSACTIONS.ADVANCE_BILL_REVERSED_YN` | „Identifies if this Advance Bill has been reversed." | Storno einer Vorausrechnung |
| `FINANCIAL_TRANSACTIONS.PROFORMA_YN` | „Is this transaction generated by a proforma invoice." | Proforma |
| `FOLIO$_TAX.STATUS` | „O = OK, C = Cancelled, V = Void, COMP = Compressed, D = Deposit …" | Storno, Anzahlung (wie bisher) |
| `NAME_RESERVATION.COMPANY_NAME` | „The Name of the Company attached to that reservation, if any." | `FOLIO$_TAX.COMPANY_NAME` |

Für die **Zwischenrechnung** (`INTERIM INVOICE`) ist in der Struktur kein
Merkmal zu sehen. Ob sie sich anders erkennen lässt — oder im älteren OPERA
überhaupt mit eigener Belegnummer entsteht —, ist offen (siehe Prüfplan).

## Konzept

### 1. Fähigkeiten der Datenbank erkennen, nicht konfigurieren

Beim Verbindungsaufbau liest die Anwendung einmal aus `ALL_TAB_COLUMNS`
(rein lesend), ob `FOLIO$_TAX` die Spalten `DOCUMENT_TYPE` und `COMPANY_NAME`
hat. Das Ergebnis gilt für die Laufzeit des Prozesses.

Keine Einstellung dafür: Wer sie falsch setzt, bekommt entweder `ORA-00904` oder
— schlimmer — den Ersatzweg in einem Haus, das die echte Spalte hat. Die
Datenbank weiß es, also wird sie gefragt.

### 2. Ein Ausdruck statt der Spalte, an einer Stelle

Die Abfragen bleiben, wie sie sind. `opera._sql()` ersetzt beim Laden
`<alias>.document_type` bzw. `<alias>.company_name` durch einen Ausdruck, wenn
die Spalte fehlt:

```sql
-- statt f.document_type
(CASE WHEN EXISTS (SELECT 1 FROM @SCHEMA@.financial_transactions t
                    WHERE t.resort = f.resort AND t.folio_no = f.folio_no
                      AND t.bill_no = f.bill_no AND t.advance_bill_yn = 'Y')
      THEN 'ADVANCE INVOICE'
      WHEN EXISTS (... t.proforma_yn = 'Y') THEN 'PROFORMA'
      ELSE 'INVOICE' END)

-- statt f.company_name
(SELECT MAX(nr.company_name) FROM @SCHEMA@.name_reservation nr
  WHERE nr.resv_name_id = f.resv_name_id)
```

Damit gilt alles Übrige unverändert: Arbeitsliste, Vorprüfung („keine
Endrechnung → nicht versenden“), Gutschrift-Bezug. Wo die Spalte im
SELECT steht, bekommt sie in den Abfragen ein ausdrückliches `AS document_type`
bzw. `AS company_name`, damit der Name nach dem Ersetzen bleibt.

Die genaue Regel steht erst fest, wenn der Prüfplan (unten) sie an Daten
belegt hat. Der Ausdruck oben ist der Entwurf.

### 3. Sichtbar machen, in welchem Modus gearbeitet wird

- „Datenbank testen" nennt den Modus: *„Belegart aus DOCUMENT_TYPE"* oder
  *„Belegart ersatzweise aus den Buchungen (ältere OPERA-Version)"*.
- Im Ersatzmodus steht auf der Detailseite jeder Rechnung, woraus die Belegart
  abgeleitet ist.

### 4. Vorsicht, solange die Regel im Zielhaus nicht belegt ist

Für die ersten Wochen im Ersatzmodus gehen **alle** Rechnungen über die
Sichtprüfung, und die Automatik bleibt im Testlauf. Freigegeben wird erst, wenn
eine Stichprobe im Zielhaus zeigt, dass keine Voraus- oder Zwischenrechnung als
Endrechnung durchgeht.

### 5. Tests

- Selbsttest mit einer nachgestellten Datenbank ohne die beiden Spalten:
  Alle Abfragen enthalten danach weder `document_type` noch `company_name` als
  Spalte, der Abfragentest meldet nichts mehr, die Ersatzausdrücke tragen den
  Alias der jeweiligen Abfrage.
- Ein Test je Belegart: Buchung mit `ADVANCE_BILL_YN = 'Y'` → nicht in der
  Arbeitsliste, Vorprüfung sperrt.
- An echten Daten: siehe Prüfplan.

## Prüfplan

**A — am bisherigen Haus (hat beides):** Bildet die Ersatzregel `DOCUMENT_TYPE`
nach? Kreuztabelle `DOCUMENT_TYPE` × `STATUS` × `ADVANCE_BILL_YN` ×
`PROFORMA_YN` × `INVOICE_TYPE` × `BILL_PREFIX` × `FOLIO_TYPE`, Fehlzuordnungen
in beide Richtungen. Dasselbe für `COMPANY_NAME` gegen
`NAME_RESERVATION.COMPANY_NAME`, mit Laufzeit.

*Ergebnis:* steht aus.

**B — im Zielhaus (rein lesende Abfrage, die das Haus selbst ausführt):**
Verteilung von `STATUS`, `FOLIO_TYPE`, `BILL_PREFIX` der letzten 90 Tage; wie
viele Belege Buchungen mit `ADVANCE_BILL_YN = 'Y'` bzw. `PROFORMA_YN = 'Y'`
tragen; drei Beispiele je Gruppe zum Abgleich mit dem gedruckten Beleg.

**C — Abnahme im Zielhaus:** Testlauf, Sichtprüfung jeder Rechnung, Vergleich
mit dem Beleg aus OPERA.

## Offen

- Wie ist eine Zwischenrechnung im älteren OPERA gekennzeichnet?
- Welche OPERA-Version hat das Zielhaus? Ab welcher Version gibt es
  `DOCUMENT_TYPE`?
- Ist `NAME_RESERVATION` in der Arbeitsliste schnell genug? Die View ist groß;
  je Rechnung (Detailseite) ist das kein Problem, über die ganze Liste
  vielleicht doch.
- **Wie schreibt das Zielhaus `STATUS`?** Der Spaltenkommentar dort nennt
  Kurzformen („O = OK, C = Cancelled, V = Void, COMP = Compressed, D =
  Deposit"), im bisherigen Haus stehen ausgeschriebene Werte (`OK`, `DEPOSIT`,
  `VOID`, `ZERO`). Stimmen die Kurzformen, scheitert keine Abfrage — sie finden
  nur nichts: Die Arbeitsliste bliebe leer (`STATUS = 'OK'` steht fest in den
  Abfragen), Anzahlungen würden nicht erkannt (`anzahlung_status`, Vorgabe
  `DEPOSIT`). Block 1 von `sql/discovery/09_belegarten_ohne_document_type.sql`
  zeigt die tatsächlichen Werte. Für Anzahlungen genügt dann die Einstellung
  `anzahlung_status`; für `OK` bräuchte es eine eigene.

## Anzahlungs-Einrichtung

Die Einrichtungsseite für Anzahlungen (`anzahlungscodes.sql`) benutzt
`DOCUMENT_TYPE` nicht — sie erkennt Anzahlungsbelege am Status. Sie läuft im
Zielhaus also unverändert, sofern `anzahlung_status` zum dortigen Wert passt
(siehe oben). Bei der Umsetzung wird ihre Verknüpfung von Buchung und Beleg um
`FOLIO_NO` ergänzt — sie stand noch auf `BILL_NO` allein (siehe
`invoice_folio.sql`).
