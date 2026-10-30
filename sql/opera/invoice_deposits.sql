-- invoice_deposits.sql — Anzahlungsbelege desselben Folios
-- Bindvariablen: :bill_no, :resort, :folio_no, :anzahlung_status
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
--   Abschlag je Steuersatz        Netto und Steuer aus den Buckets des
--                                 Anzahlungsbelegs (opera.anzahlung_abzuege)
--   BT-115 PayableAmount        = TOTAL_GROSS der Schlussrechnung
-- Anzahlungsbelege mit DOCUMENT_TYPE 'COPY OF INVOICE' bleiben drin: OPERA
-- rechnet sie mit an (gemessen 99 in 90 Tagen, bei 10 Schlussrechnungen zwei
-- gleich hohe Anzahlungen, beide im Kopf abgezogen).

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
                      -- Das Folio steht vorab fest (invoice_folio.sql). Hier
                      -- stand eine Unterabfrage ueber BILL_NO, die bei einer
                      -- doppelt vergebenen Nummer zwei Zeilen lieferte.
                      WHERE fo.folio_no = :folio_no)
   -- BILL_NO ist nicht eindeutig; die Liste aus FOLIOS allein bindet D nicht
   -- an dieses Folio. Gemessen lagen alle 2.862 Anzahlungsbelege am selben
   -- Folio, die Bedingung schliesst nur die Luecke (gemessen 30.10.2026).
   AND d.folio_no = :folio_no
   AND d.bill_no <> :bill_no
   AND d.status   = :anzahlung_status
 ORDER BY d.bill_generation_date, d.bill_no
