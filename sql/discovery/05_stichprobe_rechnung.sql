-- 05_stichprobe_rechnung.sql
-- Eine bekannte Rechnung komplett auslesen — Vorlage fuer die vier produktiven
-- Abfragen. Nur lesend.
-- DEFINE OPERA_OWNER = OPERA
-- DEFINE BILL = <BILL_NO einer echten, abgeschlossenen Firmenrechnung>

PROMPT == Kopf: Beteiligte, Summen, eingefrorene Adressen ==
SELECT bill_no, invoice_no, folio_no, resort, document_type, status,
       business_date, bill_generation_date, bill_start_date,
       hotel_name, property_tax_no, resort_full_address, resort_zip_code,
       resort_city, resort_country,
       payee_name, payee_zip_code, company_name, guest_name,
       SUBSTR(folio_address, 1, 400) folio_address,
       name_id, payee_name_id, addressee_name_id, resv_name_id, account_code,
       total_net, total_gross, total_nontaxable,
       deposit, cashpay, ccpay, clpay, paidout,
       e_invoice_number, e_invoice_status
  FROM &&OPERA_OWNER..folio$_tax_e
 WHERE bill_no = &&BILL;

PROMPT == Steueraufteilung: die 20 Buckets mit Satz ==
SELECT net1_amt,  tax1_amt,  tax1_rate,  tax1_rate_type,
       net2_amt,  tax2_amt,  tax2_rate,  tax2_rate_type,
       net3_amt,  tax3_amt,  tax3_rate,  tax3_rate_type,
       net4_amt,  tax4_amt,  tax4_rate,  tax4_rate_type,
       net5_amt,  tax5_amt,  tax5_rate,  tax5_rate_type,
       net6_amt,  tax6_amt,  tax6_rate,  tax6_rate_type
  FROM &&OPERA_OWNER..folio$_tax_e
 WHERE bill_no = &&BILL;

PROMPT == Zeilen: Buchungen mit Steuersatz je Zeile ==
SELECT ft.trx_no, ft.trx_date, ft.trx_code, tc.description,
       ft.quantity, ft.price_per_unit, ft.net_amount, ft.gross_amount,
       ft.tax_rate, ft.tax_rate_type, ft.tax_inclusive_yn, ft.tax_generated_yn,
       ft.tax_elements, ft.correction_yn,
       ft.tc_group, ft.tc_subgroup, ft.tc_transaction_type,
       tc.non_taxable_yn, tc.e_invoice_yn, tc.tax_code_no, tc.ind_cash,
       ft.remark, ft.reference
  FROM &&OPERA_OWNER..financial_transactions_e ft
  LEFT JOIN &&OPERA_OWNER..trx$_codes_e tc
         ON tc.trx_code = ft.trx_code AND tc.resort = ft.resort
 WHERE ft.bill_no = &&BILL
 ORDER BY ft.trx_no;

PROMPT == Gegenprobe: Summen der Zeilen gegen den Kopf ==
SELECT SUM(net_amount) summe_netto, SUM(gross_amount) summe_brutto, COUNT(*) zeilen
  FROM &&OPERA_OWNER..financial_transactions_e
 WHERE bill_no = &&BILL;

PROMPT == Empfaenger: aktuelles Profil (zum Vergleich mit den eingefrorenen Daten) ==
SELECT n.name_id, n.name, n.company, n.legal_company,
       n.tax1_no, n.tax2_no, n.e_invoice_liable_yn,
       n.udfc01, n.udfc02, n.udfc03,
       a.address1, a.address2, a.city, a.zip_code, a.country,
       (SELECT MIN(p.phone_number) FROM &&OPERA_OWNER..name_phone_e p
         WHERE p.name_id = n.name_id AND p.phone_role = 'EMAIL') email
  FROM &&OPERA_OWNER..name_e n
  LEFT JOIN &&OPERA_OWNER..name_address_e a
         ON a.name_id = n.name_id AND a.primary_yn = 'Y'
 WHERE n.name_id = (SELECT NVL(addressee_name_id, NVL(payee_name_id, name_id))
                      FROM &&OPERA_OWNER..folio$_tax_e WHERE bill_no = &&BILL);

PROMPT == Steuer-Generates dieser Property (Umsatzcode -> Steuercode, Satz) ==
SELECT trx_code, trx_code_generator, tcr_type, percentage, amount,
       calculation_sequence, name_tax_type, generated_printed_on_folio_yn
  FROM &&OPERA_OWNER..trx_class_relationships_e
 WHERE resort = (SELECT resort FROM &&OPERA_OWNER..folio$_tax_e WHERE bill_no = &&BILL)
 ORDER BY trx_code, calculation_sequence;

PROMPT == Wurde zu dieser Rechnung eine Mail/ein Bericht zugestellt? ==
SELECT report_id, delivery_type, desttype, processed_yn, from_email,
       SUBSTR(destname, 1, 100) destname, SUBSTR(subject, 1, 150) subject,
       SUBSTR(attachment_name, 1, 100) attachment_name
  FROM &&OPERA_OWNER..report_destinations_e
 WHERE subject LIKE '%&&BILL%' OR attachment_name LIKE '%&&BILL%';
