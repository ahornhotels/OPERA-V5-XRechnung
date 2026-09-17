# Datenvertrag — was die OPERA-SQL liefern muss

Das ist die Schnittstelle zwischen PMS-Adapter und XRechnung-Maschine.
Die Namen sind aus `templates/*.j2` und `modules/invoice_fetcher.py` der
Referenz ausgelesen — **Spaltenaliase in der SQL, kleingeschrieben im Python-Dict**.
Wer diese Namen liefert, kann die Referenz-Templates unverändert benutzen.

Struktur, die `fetch_invoice()` zurückgibt:

```python
{ "header": {...}, "lines": [ {...} ], "tax_breakdown": [ {...} ], "totals": {...} }
```

## header — aus `invoice_header.sql`, eine Zeile

| Alias | BT | Inhalt | OPERA-Quelle |
|---|---|---|---|
| `id` | BT-1 | Rechnungsnummer | offen |
| `issuedate` | BT-2 | `YYYY-MM-DD` | offen |
| `duedate` | BT-9 | Fälligkeit = Datum + Zahlungsziel | Zahlungsziel aus Config/AR-Terms |
| `invoicetypecode` | BT-3 | `380` Rechnung / `381` Gutschrift | aus Rechnungsart ableiten |
| `note` | BT-22 | Freitext | optional |
| `documentcurrencycode` | BT-5 | `EUR` | Property-Währung |
| `buyerreference` | **BT-10** | **Leitweg-ID** — bei Behörden Pflicht | offen (Profil-UDF?) |
| `startdate` / `enddate` | BG-14 | Leistungszeitraum = An-/Abreise | offen |
| `suppliername` / `supplierregistrationname` | BT-27/28 | Hotelname / Firmierung lt. Register | Config je Property |
| `supplierstreetname` / `suppliercityname` / `supplierpostalzone` / `supplieridentificationcode` | BG-5 | Verkäuferadresse, Land als ISO-2 | Config je Property |
| `suppliercompanyid` | BT-31 | **USt-IdNr.** des Hotels | Config je Property |
| `suppliercontactname` / `-telephone` / `-electronicmail` | BT-41/42/43 | **BR-DE-5: Kontakt ist Pflicht** | Config je Property |
| `customername` / `customerregistrationname` | BT-44/45 | Rechnungsempfänger | Profil / AR-Konto |
| `customerstreetname` / `customercityname` / `customerpostalzone` / `customeridentificationcode` | BG-8 | Käuferadresse, Land als ISO-2 | Profiladresse |
| `customerendpointid` | BT-49 | E-Mail des Empfängers (`schemeID="EM"`) | Profil-Kommunikation |
| `payeefinancialaccountid` / `-name` / `-bic` | BG-17 | IBAN / Kontoinhaber / BIC | Config je Property |
| `prepaidamount` | BT-113 | bereits gezahlt (optional, sonst berechnet) | Zahlungen auf der Rechnung |
| `payableamount` | BT-115 | Zahlbetrag (optional, sonst berechnet) | offener Betrag |
| `billingreferenceid` / `-issuedate` | BG-3 | nur Gutschrift: Bezug auf Urrechnung | Storno-Verweis |

## lines — aus `invoice_lines.sql`, n Zeilen

| Alias | BT | Bemerkung |
|---|---|---|
| `invoicedquantity` | BT-129 | Einheit ist im Template fest `C62` (Stück) |
| `lineextensionamountnet` | **BT-131** | **Netto** — das wandert ins XML |
| `lineextensionamount` | — | Brutto, nur als Fallback/Kontrolle |
| `priceamount` | BT-146 | Netto-Einzelpreis, **darf nicht negativ sein** (BR-27) |
| `itemname` | BT-153 | Artikelbezeichnung |
| `itemcode` | BT-155 | optional |
| `classifiedtaxcategoryid` | BT-151 | `S` = Standard, `Z` = 0 %, `E` = befreit |
| `classifiedtaxcategorypercent` | BT-152 | 19 / 7 / 0 — bei `Z` **zwingend 0** (BR-Z-08) |

Negative Zeilen (Storno, Pfand) muss die SQL **nicht** behandeln — der
`xml_builder` mappt sie automatisch auf `cac:AllowanceCharge` und rechnet das
Steuer-Breakdown neu.

## tax_breakdown — aus `invoice_tax.sql`, eine Zeile je Steuersatz

| Alias | BT | Bemerkung |
|---|---|---|
| `taxableamount` | BT-116 | Nettosumme dieser Kategorie |
| `taxamount` | BT-117 | Steuerbetrag dieser Kategorie |
| `taxcategoryid` | BT-118 | `S`/`Z`/`E` |
| `taxcategorypercent` | BT-119 | Satz |

Zeilen mit 0/0 werden verworfen (BR-CO-17). Die Summe der `taxamount` muss
`totals.invoicetaxtotal` ergeben, sonst BR-CO-14.

## totals — aus `invoice_totals.sql`, eine Zeile

| Alias | BT | Bemerkung |
|---|---|---|
| `invoicenet` | BT-106/109 | Summe Nettozeilen |
| `invoicegross` | BT-112 | Bruttosumme |
| `invoicetaxtotal` | BT-110 | Steuersumme = brutto − netto |
| `spay_cl` | — | verbuchter Zahlbetrag; daraus leitet das Template `payable`/`prepaid` ab |

## Prüfregeln, an denen es in der Praxis scheitert

- BR-CO-10: Summe `lineextensionamountnet` == `invoicenet`
- BR-CO-13: `invoicenet` (+ Zu-/Abschläge) == TaxExclusiveAmount
- BR-CO-15: TaxExclusive + Steuersumme == `invoicegross`
- BR-CO-16: `invoicegross` − prepaid == payable
- BR-DE-5/6: Verkäufer-Kontaktname **und** Telefon/Mail
- BR-DE-1: Zahlungsmittel/Kontodaten müssen da sein

Die Cent-Rundung ist der Klassiker: OPERA rundet je Buchung, EN16931 prüft die
Summen. Deshalb in der SQL **immer je Zeile runden und dann summieren**, nie
umgekehrt — genau so macht es die Suite8-Vorlage.
