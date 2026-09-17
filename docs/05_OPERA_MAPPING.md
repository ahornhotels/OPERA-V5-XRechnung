# OPERA-Mapping — Feldvorschlag gegen das Live-Schema

> **Achtung:** Dieses Dokument beschreibt, was das Schema *anbietet*. Mehrere
> dieser Angebote haben sich beim Nachmessen an einer laufenden Installation als
> unbrauchbar erwiesen — nicht weil die Spalten fehlen, sondern weil sie nicht
> gefüllt werden:
>
> - `RESORT.VAT_ID` und `FOLIO$_TAX.PROPERTY_TAX_NO` sind leer. Die USt-IdNr. des
>   Verkäufers muss deshalb aus der Konfiguration der Anwendung kommen.
> - `NAME.E_INVOICE_LIABLE_YN` ist durchgehend NULL. Als Filter dafür, wer eine
>   E-Rechnung bekommt, taugt das Kennzeichen nicht; es braucht ein eigenes
>   Merkmal — praktisch: das Vorhandensein einer Leitweg-ID.
> - Die `TAXn_RATE`-Spalten sind **nicht positionsstabil**. `TAX1_RATE` ist nicht
>   verlässlich der Regelsatz; es gibt Zeilen mit leerem Bucket 1 und belegtem
>   Bucket 2. Die Buckets müssen unpivotiert und über den *Satz* gruppiert
>   werden, nie über die Position.
> - `REPORT_DESTINATIONS` ist **keine Warteschlange**, sondern ein Protokoll der
>   Report-Ausgabeziele. Ein Einhängen in den Versand darüber entfällt.
> - `E_INVOICE_NUMBER` / `E_INVOICE_STATUS` werden nicht gefüllt.
>
> Diese Punkte sind an einer Installation gemessen. Ob sie anderswo anders
> aussehen, ist eine Frage der Konfiguration und des Pflegezustands — die
> Prüfung lohnt sich vor jedem Einsatz.

**Grundlage des Mappings** ist ein Data Dictionary, das aus der laufenden
Datenbank gezogen wurde (OPERA V5, Oracle 19c, Schema `OPERA`): mehrere tausend
Tabellen mit ihren Spalten und den Zeilenzahlen aus der Optimizer-Statistik.

Dieses Dictionary stammt aus einem Produktivsystem und ist **nicht Teil dieser
Veröffentlichung**. Damit funktionieren auch die Nachschlagewerkzeuge unter
`tools/` nicht ohne weiteres: `tools/dd.py` erwartet einen geparsten Dump unter
`reference/` und meldet ohne ihn schlicht, dass er nichts findet. Wer das
Mapping an der eigenen Installation nachvollziehen will, zieht sich ein eigenes
Dictionary (`ALL_TAB_COLUMNS` plus `ALL_TABLES.NUM_ROWS`) und füttert es dort
ein — oder schlägt direkt in der Datenbank nach.

Die öffentlich verfügbaren PDF-Dictionaries zu OPERA V5 (Stände 2008 und 2010)
bleiben als Rückfall nützlich: Sie liefern die Beschreibungstexte und die
Views-Ebene, die ein reiner Tabellen-Dump nicht enthält. Sie sind allerdings
älter als das Schema — genau die Spalten, auf denen dieses Mapping ruht
(Steuersätze je Bucket, eingefrorene Verkäufer- und Empfängerdaten), gibt es
dort noch nicht.

Nachschlagen (mit eigenem Dictionary unter `reference/`):

```sh
python3 tools/dd.py 'FOLIO$_TAX_E'                 # Spalten + Zeilenzahl
python3 tools/dd.py 'FOLIO$_TAX_E' -f TAX._RATE    # gefiltert
python3 tools/dd.py -t FOLIO                       # Objekte suchen
python3 tools/dd.py -s E_INVOICE                   # Spalten suchen
```

## Was sich gegenüber 2010 geändert hat — und zwar entscheidend

| Fund | Bedeutung |
|---|---|
| `FOLIO$_TAX_E.TAX1_RATE … TAX20_RATE` (+ `TAXn_RATE_TYPE`) | **Der Steuersatz steht jetzt je Bucket in der Kopftabelle.** Das war die einzige echte Lücke im Mapping — sie ist zu. Buckets sind zudem von 10 auf 20 gewachsen. |
| `FINANCIAL_TRANSACTIONS_E.TAX_RATE`, `TAX_RATE_TYPE` | Steuersatz auch je Buchung — Zeilen und Aufteilung lassen sich unabhängig prüfen. |
| `RESORT_E.VAT_ID` | **USt-IdNr. des Hotels im Schema.** Kein Config-Workaround mehr nötig. |
| `FOLIO$_TAX_E.PROPERTY_TAX_NO`, `HOTEL_NAME`, `RESORT_FULL_ADDRESS`, `RESORT_CITY`, `RESORT_ZIP_CODE`, `RESORT_COUNTRY` | Verkäuferdaten **eingefroren zum Zeitpunkt der Rechnung** („at the time of bill generation"). Genau das, was eine XRechnung braucht — nicht der heutige Stammdatensatz. |
| `FOLIO$_TAX_E.PAYEE_NAME`, `FOLIO_ADDRESS`, `COMPANY_NAME`, `GUEST_NAME`, `PAYEE_ZIP_CODE` | Empfängerdaten ebenfalls eingefroren. |
| `NAME_E.E_INVOICE_LIABLE_YN` + `E_INV_LIABLE_LAST_UPDATED` | OPERA kennt ein Profilkennzeichen **„e-rechnungspflichtig"** — der natürliche Filter dafür, welche Rechnungen XRechnung werden. |
| `TRX$_CODES_E.E_INVOICE_YN` | dito auf Ebene der Umsatzcodes. |
| `FOLIO$_TAX_E.E_INVOICE_NUMBER`, `E_INVOICE_STATUS` | Felder für eine E-Rechnungs-Nummer und deren Status sind vorhanden — ob und wie sie hier gefüllt werden, ist an der Live-DB zu prüfen. |
| `E_INV_LIABLE_TRACKER_E` (leer) | OPERA führt eine eigene Nachverfolgung „E-Rechnungspflicht" je Buchung (`TRX_NO`, `NAME_ID`, `TAX1_NO`, `TOTAL_ATTEMPTS`) — in der untersuchten Installation **ungenutzt**. Zeigt aber, dass Oracle die Mechanik vorgesehen hat; vor Eigenbau kurz prüfen, was die Standardfunktion in der jeweiligen Version leistet. |
| `FOLIO$_TAX_E.DOCUMENT_TYPE` | „INVOICE / INTERIM INVOICE / ADVANCE INVOICE" — brauchbar für `InvoiceTypeCode` und zum Aussortieren von Zwischenrechnungen. |
| `SIGNATURE_HASH`, `TRANSACTION_SIGNATURE`, `SIGNATURE_KEY_VERSION`, `FISCAL_FOLIO_QUEUE_E` (gut gefüllt) | TSE/Kassensicherungsverordnung ist aktiv. Für uns nur Kontext — aber es zeigt, dass die Fiskalkette an der Datenbank hängt und Rechnungen nicht nachträglich verändert werden dürfen. |
| **`_E`-Suffix und `CHAIN_CODE`** | Alle physischen Tabellen heißen `..._E` und tragen eine `CHAIN_CODE`-Spalte. Die Anwendung greift über mehrere tausend Views ohne Suffix zu. **Unsere SQL geht gegen die Views** — dort ist der `CHAIN_CODE`-Filter bereits enthalten; gegen `_E` müsste man ihn selbst setzen. An einer Installation geprüft: alle benötigten Views vorhanden und `VALID`. |

## Welche Tabellen tatsächlich tragen

Die Optimizer-Statistik beantwortet eine Frage, die sich aus dem Schema allein
nicht beantworten lässt: Welche der gleichberechtigt aussehenden Tabellen werden
überhaupt benutzt? Die Größenordnungen sind an einer Installation abgelesen und
absteigend sortiert:

| Objekt | Größenordnung | Rolle |
|---|---|---|
| `FINANCIAL_TRANSACTIONS_E` | mit Abstand am größten, zweistellige Millionen | Buchungen = Rechnungszeilen |
| `FOLIOS_E` | Millionen | Bill-/Fensternummern je Reservierung |
| `NAME_E` | Millionen | Profile |
| `FOLIO$_TAX_E` | Hunderttausende | **Rechnungsköpfe Gastrechnung** |
| `AR_INVOICE_HEADER_E` | rund ein Siebtel davon | **Rechnungsköpfe Debitor** |
| `AR$_ACCOUNT_E` | Tausende | Debitorenkonten |
| `TRX$_CODES_E` | einige hundert | Umsatzcodes |
| `TRX_CLASS_RELATIONSHIPS_E` | einige hundert | **Steuer-„Generates"** |
| `RESORT_E` | eine Handvoll | Properties, darunter Nicht-Hotel-Mandanten (Zentralreservierung, Demo) — **auszufiltern** |
| `EMAIL_JOURNAL_E` | **eine Handvoll Zeilen insgesamt** | praktisch leer → **nicht** der Versandweg |

Die letzte Zeile ist die aussagekräftigste: Eine Tabelle, die bei Millionen
Buchungen ein halbes Dutzend Zeilen enthält, wird vom laufenden Betrieb nicht
beschrieben. Damit ist `EMAIL_JOURNAL` als Ansatzpunkt für den Folio-Versand
erledigt, ohne dass man eine einzige Zeile Code dafür schreiben müsste.

Dass die Gastrechnungen die Debitorenrechnungen deutlich überwiegen, ist
hotelüblich, aber keine Naturkonstante — in einem Haus mit starkem
Firmenkundengeschäft kann sich das Verhältnis verschieben. Beide Wege sind
deshalb gleichwertig abzudecken.

## Kopf (`invoice_header.sql`)

Basis: `FOLIO$_TAX_E` (Gastrechnung) bzw. `AR_INVOICE_HEADER_E` (Debitor).

| Datenvertrag | OPERA (live) | ✓ |
|---|---|---|
| `id` | `FOLIO$_TAX_E.BILL_NO` / `AR_INVOICE_HEADER_E.INVOICE_NO` | A |
| `issuedate` | `BILL_GENERATION_DATE` / `TRX_DATE` | A |
| `duedate` | `AR$_ACCOUNT_E.PAYMENT_DUE_DAYS` + Rechnungsdatum | A |
| `invoicetypecode` | aus `DOCUMENT_TYPE` + `VOID_REASON`/`REASON_CODE` ableiten | B |
| `documentcurrencycode` | `RESORT_E.CURRENCY_CODE` | A |
| `buyerreference` (Leitweg-ID) | `NAME_E.UDFC**` — Feld ist festzulegen; die UDF-Tabellen waren in der untersuchten Installation nahezu ungenutzt, es ist also reichlich frei | C |
| `startdate`/`enddate` | `BILL_START_DATE` … `BUSINESS_DATE`, sonst Reservierung | B |
| `suppliername` / `-registrationname` | `FOLIO$_TAX_E.HOTEL_NAME`, sonst `RESORT_E.NAME`/`LEGAL_OWNER` | A |
| `supplier*` Adresse | `RESORT_CITY`, `RESORT_ZIP_CODE`, `RESORT_COUNTRY`, `RESORT_FULL_ADDRESS` (Straße ggf. aus `RESORT_E.STREET`) | A |
| `suppliercompanyid` (USt-IdNr.) | **`FOLIO$_TAX_E.PROPERTY_TAX_NO`**, sonst `RESORT_E.VAT_ID` | A |
| `suppliercontact*` | `RESORT_E.TELEPHONE` / `EMAIL`, Name aus Config (BR-DE-5) | B |
| `customername` | `COMPANY_NAME` / `PAYEE_NAME`, sonst `NAME_E.LEGAL_COMPANY` | A |
| `customer*` Adresse | `FOLIO_ADDRESS` + `PAYEE_ZIP_CODE` (eingefroren), sonst `NAME_ADDRESS_E` | B |
| Kunden-USt-IdNr. (BT-48) | `NAME_E.TAX1_NO` / `TAX2_NO` | A |
| `customerendpointid` | `NAME_PHONE_E` (E-Mail), sonst `AR$_ACCOUNT_E.EMAIL_ADDRESS` | B |
| `payee*` (IBAN/BIC) | **nicht im Schema** (`BANK_ACCOUNT_E` führt nur Konto/Routing) → Config je Property | A |
| `note` | `AR_INVOICE_HEADER_E.FOLIO_TEXT1/2`, `REASON_TEXT` | B |
| `prepaid`/`payable` | `CASHPAY + CCPAY + CLPAY + DEPOSIT` bzw. `AMOUNT − PAID` | B |

## Zeilen (`invoice_lines.sql`)

Basis: `FINANCIAL_TRANSACTIONS_E` über `BILL_NO` bzw. `INVOICE_NO`.

| Datenvertrag | OPERA (live) | ✓ |
|---|---|---|
| `invoicedquantity` | `QUANTITY` | A |
| `lineextensionamountnet` | `NET_AMOUNT` | A |
| `lineextensionamount` | `GROSS_AMOUNT` | A |
| `priceamount` | `PRICE_PER_UNIT` | B |
| `itemname` | `TRX$_CODES_E.DESCRIPTION`, sonst `REMARK` | A |
| `itemcode` | `TRX_CODE` | A |
| `classifiedtaxcategorypercent` | ~~`TAX_RATE`~~ — auf Erlöszeilen NULL! Satz aus `TAX_ELEMENTS` (" 19%") bzw. `TRX_CLASS_RELATIONSHIPS` | C |
| `classifiedtaxcategoryid` | `S`, bei `TAX_RATE = 0` bzw. `TRX$_CODES_E.NON_TAXABLE_YN = 'Y'` → `Z`; `TAX_RATE_TYPE` mitprüfen | B |

Auszuschließen sind Zahlungen und die Steuerbuchungen selbst. Praktisch geht das
über `GROSS_AMOUNT IS NOT NULL`: Zahlungs- und Steuerzeilen tragen dort keinen
Wert. `TC_TRANSACTION_TYPE` hilft dabei nicht, denn es hängt an `TRX$_CODES`,
nicht an der einzelnen Buchung.
Welche Buchung eine Steuerbuchung ist, sagt zusätzlich
`TRX_CLASS_RELATIONSHIPS_E`: `TRX_CODE` → `TRX_CODE_GENERATOR`
mit `PERCENTAGE` — die klassische OPERA-„Generates"-Konfiguration.

## Steueraufteilung (`invoice_tax.sql`) — jetzt trivial

`FOLIO$_TAX_E` liefert je Bucket *i* = 1..20 direkt:

```
taxableamount        = NETi_AMT
taxamount            = TAXi_AMT
taxcategorypercent   = TAXi_RATE
taxcategoryid        = 'S'  (bzw. 'Z' bei Rate 0)
```

Buckets mit Netto = 0 und Steuer = 0 werden verworfen (BR-CO-17). Der
`TAXi_RATE_TYPE` sagt zusätzlich, um welche Steuerart es sich handelt —
relevant, falls Kurtaxe/Citytax als eigener Bucket geführt wird und in der
XRechnung anders behandelt werden muss als Umsatzsteuer.

## Summen (`invoice_totals.sql`)

`TOTAL_NET` → `invoicenet`, `TOTAL_GROSS` → `invoicegross`, Differenz →
`invoicetaxtotal`, gezahlt aus `CASHPAY + CCPAY + CLPAY + DEPOSIT`.
Für AR: `AR_INVOICE_HEADER_E.AMOUNT` / `PAID`.

## Auslöser und Zustellung

Die naheliegende Idee, sich in OPERAs eigenen Versand einzuhängen und die
XRechnung dort mitzuschicken, scheitert am Schema. Zwei Kandidaten wurden
geprüft:

- `EMAIL_JOURNAL_E` ist praktisch leer (siehe oben). Der Folio-Versand läuft
  nicht darüber.
- **`REPORT_DESTINATIONS_E`** sieht auf den ersten Blick wie die gesuchte
  Warteschlange aus: `DESTTYPE`, `DESTNAME`, `DELIVERY_TYPE`, `SUBJECT`,
  `ATTACHMENT_NAME`, `FROM_EMAIL` und — scheinbar entscheidend —
  `PROCESSED_YN`. Beim Nachmessen ist es aber ein **Protokoll der
  Report-Ausgabeziele**, keine Haltestelle vor dem Versand: Die Tabelle wird
  laufend beschrieben *und wieder bereinigt*, und `PROCESSED_YN` steht bei den
  Mail-Zielen durchgehend auf `N`, auch lange nach dem Versand. Ein Kennzeichen,
  das nie umspringt, taugt weder als Auslöser noch als Nachweis.
  `RESORT_DELIVERY_METHODS_E` hält daneben die Mailserver-Konfiguration je
  Zustellweg — Konfiguration, kein Ereignis.

Die Folge: Ein Auslöser aus der Datenbank heraus ist nicht verlässlich zu
bekommen. Die Anwendung erzeugt und versendet deshalb **selbst**, auf Grundlage
einer eigenen Auswahl über `DOCUMENT_TYPE` und `STATUS`; die Zustellung läuft
über den eigenen Versandweg. Ausführlich begründet in
[`10_OPERA_MAILVERSAND.md`](10_OPERA_MAILVERSAND.md).
