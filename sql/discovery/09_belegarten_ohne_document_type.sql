-- 09_belegarten_ohne_document_type.sql — fuer OPERA-Versionen OHNE
-- FOLIO$_TAX.DOCUMENT_TYPE (siehe docs/16_OPERA_OHNE_DOCUMENT_TYPE.md).
-- Nur lesend: ausschliesslich SELECT. Benutzt nur Spalten, die auch die
-- aeltere Version hat.
--
-- Frage: Woran erkennt man in diesem Haus Voraus-, Zwischen- und
-- Proformarechnungen, wenn es die Belegart nicht gibt? Die Anwendung soll
-- nur echte Schlussrechnungen als XRechnung verschicken.
--
-- Aufruf (SQL*Plus):
--   DEFINE OPERA_OWNER = OPERA
--   DEFINE RESORT = <Resortcode des Hauses>
--   SET LINESIZE 250 PAGESIZE 200
--   SPOOL 09_belegarten.log
--   @09_belegarten_ohne_document_type.sql
--   SPOOL OFF
-- Die Datei 09_belegarten.log zurueckschicken. Sie enthaelt Zaehlungen und
-- je Gruppe drei Belegnummern — keine Namen, keine Adressen, keine Betraege
-- ausser dem Gesamtbetrag der Beispielbelege.

SET VERIFY OFF FEEDBACK ON TIMING ON

PROMPT == 1. Belege der letzten 90 Tage nach STATUS, FOLIO_TYPE, BILL_PREFIX ==
SELECT f.status, NVL(f.folio_type, '-') AS folio_type, NVL(f.bill_prefix, '-') AS bill_prefix,
       COUNT(*) AS belege, MIN(f.bill_no) AS kleinste_nr, MAX(f.bill_no) AS groesste_nr
  FROM &&OPERA_OWNER..folio$_tax f
 WHERE f.resort = '&&RESORT'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - 90
 GROUP BY f.status, NVL(f.folio_type, '-'), NVL(f.bill_prefix, '-')
 ORDER BY belege DESC;

PROMPT == 2. Merkmale aus den Buchungen je Beleg (STATUS OK, 90 Tage) ==
PROMPT    vorausrechnung = Buchungen mit ADVANCE_BILL_YN = Y, proforma = PROFORMA_YN = Y,
PROMPT    passant = INVOICE_TYPE = P, ohne_buchung = keine Erloeszeile unter dem Beleg
SELECT merkmale, COUNT(*) AS belege, MIN(bill_no) AS beispiel_1, MAX(bill_no) AS beispiel_2
  FROM (SELECT f.bill_no,
               CASE WHEN m.vorausrechnung > 0 THEN 'vorausrechnung ' END
               || CASE WHEN m.voraus_storniert > 0 THEN 'voraus_storniert ' END
               || CASE WHEN m.proforma > 0 THEN 'proforma ' END
               || CASE WHEN m.passant > 0 THEN 'passant ' END
               || CASE WHEN NVL(m.erloes, 0) = 0 THEN 'ohne_buchung ' END AS merkmale
          FROM &&OPERA_OWNER..folio$_tax f
          LEFT JOIN (SELECT t.resort, t.folio_no, t.bill_no,
                            SUM(CASE WHEN t.advance_bill_yn = 'Y' THEN 1 ELSE 0 END)          AS vorausrechnung,
                            SUM(CASE WHEN t.advance_bill_reversed_yn = 'Y' THEN 1 ELSE 0 END) AS voraus_storniert,
                            SUM(CASE WHEN t.proforma_yn = 'Y' THEN 1 ELSE 0 END)              AS proforma,
                            SUM(CASE WHEN t.invoice_type = 'P' THEN 1 ELSE 0 END)             AS passant,
                            SUM(CASE WHEN t.gross_amount IS NOT NULL THEN 1 ELSE 0 END)      AS erloes
                       FROM &&OPERA_OWNER..financial_transactions t
                      WHERE t.resort = '&&RESORT'
                        AND t.trx_date >= TRUNC(SYSDATE) - 180
                      GROUP BY t.resort, t.folio_no, t.bill_no) m
            ON m.resort = f.resort AND m.folio_no = f.folio_no AND m.bill_no = f.bill_no
         WHERE f.resort = '&&RESORT'
           AND f.status = 'OK'
           AND f.bill_generation_date >= TRUNC(SYSDATE) - 90)
 GROUP BY merkmale
 ORDER BY belege DESC;

PROMPT == 3. Je drei Beispiele mit Vorausrechnungs- oder Proforma-Buchungen ==
PROMPT    (zum Abgleich mit dem gedruckten Beleg: Steht dort "Vorausrechnung"/"Advance"?)
SELECT * FROM (
SELECT f.bill_no, TO_CHAR(f.bill_generation_date, 'YYYY-MM-DD') AS datum, f.status,
       NVL(f.folio_type, '-') AS folio_type, f.total_gross,
       MAX(t.advance_bill_yn) AS advance_bill_yn, MAX(t.proforma_yn) AS proforma_yn,
       ROW_NUMBER() OVER (PARTITION BY MAX(t.advance_bill_yn), MAX(t.proforma_yn)
                          ORDER BY f.bill_no DESC) AS nr
  FROM &&OPERA_OWNER..folio$_tax f
  JOIN &&OPERA_OWNER..financial_transactions t
    ON t.resort = f.resort AND t.folio_no = f.folio_no AND t.bill_no = f.bill_no
 WHERE f.resort = '&&RESORT'
   AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - 90
   AND (t.advance_bill_yn = 'Y' OR t.proforma_yn = 'Y')
 GROUP BY f.bill_no, f.bill_generation_date, f.status, f.folio_type, f.total_gross
) WHERE nr <= 3;

PROMPT == 4. Firma an der Reservierung (Ersatz fuer FOLIO$_TAX.COMPANY_NAME) ==
SELECT CASE WHEN nr.company_id IS NOT NULL THEN 'Firma an der Reservierung'
            WHEN f.resv_name_id IS NULL THEN 'Beleg ohne Reservierung'
            ELSE 'keine Firma' END AS reservierung,
       COUNT(*) AS belege
  FROM &&OPERA_OWNER..folio$_tax f
  LEFT JOIN &&OPERA_OWNER..name_reservation nr ON nr.resv_name_id = f.resv_name_id
 WHERE f.resort = '&&RESORT'
   AND f.status = 'OK'
   AND f.bill_generation_date >= TRUNC(SYSDATE) - 90
 GROUP BY CASE WHEN nr.company_id IS NOT NULL THEN 'Firma an der Reservierung'
               WHEN f.resv_name_id IS NULL THEN 'Beleg ohne Reservierung'
               ELSE 'keine Firma' END;

PROMPT == 5. Version: Spalten von FOLIO$_TAX (Anzahl) ==
SELECT COUNT(*) AS spalten_folio_tax FROM all_tab_columns
 WHERE owner = '&&OPERA_OWNER' AND table_name = 'FOLIO$_TAX';
