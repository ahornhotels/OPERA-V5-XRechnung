-- invoice_deposits.sql — Anzahlungsbelege desselben Folios
-- Bindvariablen: :bill_no, :resort
--
-- Anzahlungen laufen in OPERA als EIGENE Belege mit STATUS = 'DEPOSIT' auf
-- demselben FOLIO_NO wie die Schlussrechnung. FINANCIAL_TRANSACTIONS traegt
-- alle Zeilen des Folios unter der BILL_NO der Schlussrechnung, waehrend deren
-- TOTAL_NET nur den Restbetrag ausweist.
--
-- ACHTUNG: nicht auf DOCUMENT_TYPE = 'ADVANCE INVOICE' filtern — in diesem Haus
-- tragen die Anzahlungsbelege DOCUMENT_TYPE = 'INVOICE' und STATUS = 'DEPOSIT'.
--
-- Nachgerechnet an Beleg 1400015 (Folio 3369696):
--   Anzahlung 1400005  netto 9.043,12  brutto 9.676,14
--   Anzahlung 1400009  netto   348,87  brutto   380,00
--   Schlussrechnung    netto  -586,75  brutto  -703,05
--   Summe netto 8.805,24 / brutto 9.353,09 = exakt die Zeilensumme des Folios.
--
-- ZUM WEG UEBER FOLIOS: Nicht direkt WHERE folio_no = ..., obwohl das
-- naheliegt. FOLIO$_TAX_E hat 19 Indizes, aber KEINEN auf FOLIO_NO — die
-- Suche darueber liest die ganze Tabelle und dauerte 1546 ms. FOLIOS_E traegt
-- FOLIOS_FOL_BILL_I auf (FOLIO_NO, BILL_NO); ueber diesen Umweg auf die
-- BILL_NO-Liste und dann ueber den vorhandenen BILL_NO-Index sind es 1.4 ms.
-- Gleiches Ergebnis, dieselben Zeilen, Faktor rund 1100.
--
-- :resort ist dabei nicht schmueckendes Beiwerk: Der Index heisst
-- FOLIO_TAX_BILLNO_I und geht ueber (RESORT, BILL_NO). Ohne RESORT-Bedingung
-- kann Oracle ihn nicht ansetzen — gemessen 1543 ms ohne, 0.9 ms mit.
--
-- Verwendung in der XRechnung:
--   BG-3  cac:BillingReference  je Anzahlungsbeleg (Nummer + Datum)
--   BT-113 PrepaidAmount        = Summe der Anzahlungen (brutto)
--   BT-115 PayableAmount        = TOTAL_GROSS der Schlussrechnung

SELECT d.bill_no                                     AS billingreferenceid,
       TO_CHAR(d.bill_generation_date, 'YYYY-MM-DD') AS billingreferenceissuedate,
       d.document_type,
       d.status,
       d.total_net,
       d.total_gross,
       d.folio_no
  FROM @SCHEMA@.folio$_tax d
 WHERE d.resort = :resort
   AND d.bill_no IN (SELECT fo.bill_no
                       FROM @SCHEMA@.folios fo
                      WHERE fo.folio_no = (SELECT f.folio_no
                                             FROM @SCHEMA@.folio$_tax f
                                            WHERE f.bill_no = :bill_no
                                              AND f.resort  = :resort))
   AND d.bill_no <> :bill_no
   AND d.status   = :anzahlung_status
 ORDER BY d.bill_generation_date, d.bill_no
