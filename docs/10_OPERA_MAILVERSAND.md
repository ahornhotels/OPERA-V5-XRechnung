# Hat OPERA einen eigenen Mailversand — und kann man sich einhängen?

Grundlage: die Oracle-Dokumentation zu OPERA V5 (Quellen unten) und ein
Data Dictionary aus einer laufenden Installation. Wo im Folgenden „geprüft"
steht, ist an genau dieser einen Installation gemessen — die Einstellungen
können anderswo anders stehen, die Mechanik dahinter nicht.

## Ja, OPERA verschickt Folios selbst

Drei Bausteine greifen ineinander:

**1. Delivery Method** — `Configuration → Property → Delivery Method`,
Zieltyp **„Billing – for folios"**. Dort stehen Mailserver, Absender, Betreff,
Text und ob angehängt wird. In der Datenbank: `RESORT_DELIVERY_METHODS`
(`DELIVERY_TYPE`, `EMAIL_FROM`, `EMAIL_YN`, `EMAIL_ATTACH_YN`, `EMAIL_SUBJECT`,
`EMAIL_SERVER_NAME`) — eine Zeile je eingerichtetem Zustellweg und Property.

**2. Folio als Anhang** — dafür müssen `GENERAL > FILE ATTACHMENTS = Y` und
`GENERAL > EMAIL ATTACHMENT DIRECTORY NAME` gesetzt sein. Das Folio wird im
Hintergrund **in ein PDF gewandelt** und als Anhang verschickt.

**3. Permanent Folio Storage** — das ist der eigentliche Fund.
Steht `Cashiering > PERMANENT FOLIO STORAGE` auf `Y`, legt OPERA **bei der
Erzeugung jeder Rechnung eine exakte PDF-Kopie ab**, unter
`…\export\<schema>\<resort>\folios\<business date>\`.

Der Dateiname folgt der Einstellung `PERMANENT FOLIO STORAGE FILE NAME FORMAT`
(frei zusammensetzbar aus `<BILL_NO>`, `<REVISION_NO>`, `<FISCAL_BILL_NO>`,
`<BILL_GENERATION_YEAR/MONTH/DAY>`, `<FOLIO_VIEW>`, `<NAME_TAX_TYPE>`,
`<QUEUE_NAME>`) — und **hinten hängt OPERA immer die interne
`FOLIO_ATTACHMENT_LINK_ID` an**, damit der Name eindeutig ist.

Beispiel aus der Doku: `05200549_XXXXXX.pdf` = Monat, Jahr, Bill-Nr., Link-ID.

## Damit ist die 100-prozentige Zuordnung gelöst

`FOLIO$_TAX` — die Tabelle der Rechnungsköpfe — führt die Spalten
**`FOLIO_ATTACHMENT_LINK_ID`** und `FOLIO_ATTACHMENT_STATUS`. Die Kette ist also:

```
BILL_NO  →  FOLIO$_TAX.FOLIO_ATTACHMENT_LINK_ID  →  Dateiname des PDF
```

Ein Datenbankschlüssel, der im Dateinamen steht. Kein Betreff-Parsen, kein
Raten über Beträge oder Zeitstempel — das ist genau die Verlässlichkeit, die es
bei einer Rechnung braucht. (Suite8 musste dafür die Rechnungsnummer aus dem
Mailbetreff fischen.)

## Zur Frage: XML vor dem Versand anhängen?

**Ehrliche Einschätzung: nicht ohne Eingriff in das Produkt.**

- OPERA verschickt die Mail selbst, aus der Anwendung bzw. dem Reportserver.
  Eine Warteschlange, in die man sich legen könnte, gibt es nicht:
  `EMAIL_JOURNAL` ist im laufenden Betrieb praktisch leer — eine Handvoll Zeilen
  bei Millionen Buchungen —, und `REPORT_DESTINATIONS` ist ein Protokoll der
  Ausgabeziele, keine Haltestelle vor dem Versand.
- Einen zweiten Anhang unterzuschieben hieße, OPERAs Verhalten zu verändern —
  über einen Datenbanktrigger oder eine angepasste Prozedur im OPERA-Schema.
  Das ist eine **Anpassung am Produkt**: Oracle unterstützt so etwas nicht, und
  ein Update kann es jederzeit überschreiben.
- Dazu kommt: an der Datenbank hängt die **TSE-Fiskalisierung**
  (`SIGNATURE_HASH`, eine gut gefüllte `FISCAL_FOLIO_QUEUE`). Ein Trigger im
  Rechnungslauf eines fiskalisierten Systems ist kein Ort für Experimente.

Suite8 konnte das, weil es dort eine echte Mail-Warteschlange in der Datenbank
gab (`WMAI` mit `BLOCKSEND`). OPERA hat dieses Gegenstück nicht.

## Zur Frage: das PDF austauschen?

**Vom Austauschen rate ich ab, vom Verwenden nicht.**

Das gespeicherte Folio ist die **archivierte Kopie** der Rechnung — auf einem
fiskalisierten System Teil der Nachweiskette. Wer sie nachträglich überschreibt,
verändert einen Beleg. Der Aufwand, das sauber zu begründen, ist größer als der
Gewinn.

Sinnvoll ist der umgekehrte Griff: **das PDF nehmen, statt es zu ersetzen.**

Heute sucht die Anwendung das PDF über ein Namensmuster (`{bill_no}.pdf`) in
einem konfigurierten Ordner — geraten. Mit Permanent Folio Storage wird daraus
ein exakter Treffer über die Link-ID. Das ist eine kleine Änderung an
`app/mailer.py` mit großer Wirkung: Es kann dann **nicht mehr passieren, dass zu
Rechnung A das PDF von Rechnung B geht**.

## Ein dritter Weg, der beides verbindet: ZUGFeRD

Wenn das Ziel „ein Anhang, der für Menschen und Maschinen lesbar ist" lautet,
gibt es dafür einen Standard: **ZUGFeRD / Factur-X** — ein PDF/A-3, in das die
XML-Rechnung als Datei eingebettet ist. Man nimmt OPERAs PDF, hängt unser
bereits erzeugtes XML hinein und verschickt **eine** Datei.

Abwägung:

| | XRechnung (reines XML) | ZUGFeRD (PDF mit XML) |
|---|---|---|
| Behörden (Leitweg-ID) | **verlangt** | wird oft nicht angenommen |
| Firmenkunden | maschinenlesbar, aber ohne Layout | vertraut aussehendes PDF **und** Datensatz |
| Aufwand | steht bereits | PDF/A-3-Wandlung nötig |

Für den jetzigen Zuschnitt — Behörden und Firmenkunden mit Leitweg-ID — bleibt
XRechnung richtig. ZUGFeRD wäre die Ausbaustufe für alle übrigen Firmenkunden.

## Empfehlung

1. **Beim eigenen Versandweg bleiben.** Wir kontrollieren ihn, er ist geprüft,
   und er lässt OPERA unangetastet.
2. **Nur das XML verschicken.** Ein PDF gibt es nicht, und ein selbst gebautes
   wäre schlechter als keines.
3. **OPERAs eigenen Folio-Mailversand nicht anfassen** — weder Trigger noch
   PDF-Austausch. Das gilt unabhängig davon, ob gespeicherte Folios existieren.
4. **Permanent Folio Storage nur einschalten, wenn das Haus es aus eigenen
   Gründen will.** Für uns wäre es Bequemlichkeit, kein Erfordernis.
5. **ZUGFeRD bleibt die Ausbaustufe** — setzt aber ein PDF voraus und damit
   Punkt 4.

## Nachgemessen: in der untersuchten Installation ist der Weg verschlossen

**Permanent Folio Storage war ausgeschaltet.**

| Einstellung | Wert |
|---|---|
| `PERMANENT_FOLIO_STORAGE` | **N** (in allen Properties) |
| `PERMANENT_FOLIO_STORAGE_FILE_NAME_FORMAT` | leer |
| `SAVE_FOLIO_PATH`, `AUTOMATICALLY_SAVE_FOLIOS` | leer / N |
| `FOLIO_EMAILING` | **YES** im Hotelbetrieb (Zentralreservierung/Demo: NEVER) |
| `ATTACHMENTS` / `ATTACHMENT_STORAGE` | Y / **BLOB** (nicht Dateisystem) |

Und passend dazu: Über ein ganzes Quartal Belege hinweg hatte **kein einziger**
eine `FOLIO_ATTACHMENT_LINK_ID`, `FOLIO_ATTACHMENT_STATUS` war durchgehend leer.
Die Gegenprobe über den Anhangsbestand bestätigt es: In `LINKED_ATTACHMENTS`
stehen ausschließlich Anhänge mit Bezug `ACTIVITY` und `REPORT`, **keine
einzige Zeile mit Bezug `FOLIO`**.

Der Weg über die Link-ID ist damit nicht etwa unzuverlässig, sondern
gegenstandslos: **es gibt kein PDF, das man zuordnen könnte.**

Das ist kein Fehler der Installation, sondern der Auslieferungszustand: Der
Parameter ist ab Werk aus. Wer auf gespeicherte Folios bauen will, muss also
damit rechnen, dass sie erst eingeschaltet werden müssen — und dass es sie für
die Vergangenheit dann trotzdem nicht gibt.

## Was sonst noch herauskam

**Zustellwege gibt es reichlich** — neben `BILLING` und `AR` auch
`CONFIRMATION`, `GENERAL`, `LEADS`, `MEM_LETTER`, `MEM_STMT`, `ONLINE_CHECKIN`
und weitere. Für eine Rechnungsanwendung zählen `AR` und `BILLING`: beide mit
`EMAIL_YN = Y`, mit hinterlegtem Absender, Mailserver und einem Betreff nach dem
Muster „<ResortFullName> Copy of Stay Folio…".

**Aber `EMAIL_ATTACH_YN` war bei keinem einzigen Zustellweg gesetzt** — ob
überhaupt ein Anhang mitgeht, ist damit gar nicht konfiguriert. Wer `EMAIL_YN`
als Beleg dafür nimmt, dass hier Folios als PDF verschickt werden, liest mehr
hinein, als dasteht.

**Und `PROCESSED_YN` springt nie um.** In `REPORT_DESTINATIONS` gab es genau
eine Gruppe mit gesetztem Zustellweg (`BILLING/EMAIL`), und die stand
durchgehend auf unverarbeitet. Zwei Deutungen sind möglich und **von außen nicht
zu unterscheiden**: Entweder ist der Mailversand eingerichtet, aber nie gelaufen
— oder das Kennzeichen wird für diesen Weg nicht gepflegt. Für uns läuft beides
auf dasselbe hinaus: Ein Kennzeichen, dessen Umspringen man nicht beobachten
kann, ist als Auslöser unbrauchbar.

Nebenbei: Die Tabelle wird laufend beschrieben **und wieder bereinigt** —
zwischen zwei Messungen wenige Minuten auseinander war der Bestand der
`PREVIEW`-Zeilen bereits gesunken. Als Nachweisquelle dafür, ob eine Rechnung
verschickt wurde, taugt sie deshalb nicht: Sie vergisst.

## Folge für die Anwendung

Das PDF fällt vorerst weg. Die Mail trägt **nur die XRechnung**.

Das ist kein Verlust, sondern sauberer: Bei einer XRechnung **ist das XML die
Rechnung**, das PDF wäre nur eine Sichtbarmachung. Zwei Dokumente, die
auseinanderlaufen können, sind schlechter als eines, das stimmt. Ein selbst
gebautes PDF käme ohnehin nicht aus OPERA und könnte von dessen Folio abweichen —
das wäre die schlechteste aller Varianten.

Die PDF-Unterstützung bleibt in der Anwendung (`mail.pdf_ordner`), nur eben
unbenutzt. Wird Permanent Folio Storage später eingeschaltet, ist der Anschluss
über die Link-ID eine Sache weniger Zeilen.

## Falls das Haus Permanent Folio Storage einschalten will

Möglich, aber eine Entscheidung des Hauses, mit vier Punkten:

1. **Datenwachstum** — ab dem Einschalten entsteht für *jede* Rechnung ein PDF.
   Bei einem Haus in der Größe eines Stadthotels sind das im Quartal
   fünfstellig viele Dateien; das ist spürbar. Steht `ATTACHMENT_STORAGE` wie im
   Auslieferungszustand auf `BLOB`, landen die PDFs in der Datenbank, nicht im
   Dateisystem — das Wachstum trifft dann die Sicherung mit.
2. **Datenschutz** — Rechnungs-PDFs mit Gast- und Firmendaten, mit Löschfristen.
3. **Fiskalisierung** — gespeicherte Folios werden Teil der Nachweiskette.
4. **Keine Rückwirkung** — nur künftige Belege bekommen ein PDF.

## Was an der eigenen Datenbank zu prüfen ist

Wer diesen Weg für eine andere Installation bewerten will, braucht fünf
Antworten — dieselben fünf, die oben bereits gegeben sind:

1. Steht `PERMANENT_FOLIO_STORAGE` auf `Y`, und ist ein Dateinamensformat
   gesetzt?
2. Ist `FOLIO_ATTACHMENT_LINK_ID` bei aktuellen Belegen tatsächlich gefüllt?
3. Gibt es in `LINKED_ATTACHMENTS` Zeilen mit Bezug `FOLIO`?
4. Sind Zustellwege mit `EMAIL_YN = Y` **und** `EMAIL_ATTACH_YN = Y`
   eingerichtet?
5. Springt `PROCESSED_YN` in `REPORT_DESTINATIONS` nach einem Versand um?

In der untersuchten Installation lautete die Antwort fünfmal nein. Fällt sie
anderswo anders aus, wird aus dem gespeicherten Folio ein brauchbares PDF und
aus der Link-ID eine exakte Zuordnung — die Anwendung ist dafür vorbereitet.

## Quellen

- [Delivery Method Maintenance (OPERA 5)](https://docs.oracle.com/cd/E53547_01/opera_5_04_03_core_help/confirmation_delivery.htm)
- [Email/Fax Destination](https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/email_fax_destination.htm)
- [PERMANENT FOLIO STORAGE](https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/permanent_folio_storage_param.htm)
- [PERMANENT FOLIO STORAGE FILE NAME FORMAT](https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/permanent_folio_storage_file_name_format_param.htm)
- [Folio Options](https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/foliorange_foliooptions.htm)
- [ATTACHMENT DIRECTORY NAME](https://docs.oracle.com/cd/E98457_01/opera_5_6_core_help/attachment_directory_name_param.htm)
