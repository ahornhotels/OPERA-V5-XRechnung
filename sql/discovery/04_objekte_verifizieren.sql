-- 04_objekte_verifizieren.sql
-- Prueft die aus dem Live-Dictionary abgeleiteten Annahmen. Nur lesend.
-- DEFINE OPERA_OWNER = OPERA

PROMPT == Views ohne _E oder nur die _E-Tabellen? ==
-- Die physischen Tabellen heissen ..._E und tragen CHAIN_CODE.
-- Die Anwendung greift ueblicherweise ueber gleichnamige Views ohne Suffix zu.
SELECT object_name, object_type, status
  FROM all_objects
 WHERE owner = '&&OPERA_OWNER'
   AND object_name IN ('FOLIO$_TAX','FOLIO$_TAX_E','FINANCIAL_TRANSACTIONS',
                       'FINANCIAL_TRANSACTIONS_E','AR_INVOICE_HEADER','AR_INVOICE_HEADER_E',
                       'NAME','NAME_E','RESORT','RESORT_E','TRX$_CODES','TRX$_CODES_E',
                       'REPORT_DESTINATIONS','REPORT_DESTINATIONS_E')
 ORDER BY object_name, object_type;

PROMPT == Welche CHAIN_CODEs gibt es? ==
SELECT chain_code, COUNT(*) FROM &&OPERA_OWNER..resort_e GROUP BY chain_code;

PROMPT == Die drei Properties samt Verkaeuferdaten (BG-4) ==
SELECT resort, name, legal_owner, street, post_code, city, country_code,
       telephone, email, currency_code, vat_id
  FROM &&OPERA_OWNER..resort_e
 ORDER BY resort;

PROMPT == Sind Rechnungen mit Steuersaetzen gefuellt? (Stichprobe der letzten 30 Tage) ==
SELECT resort, COUNT(*) rechnungen,
       COUNT(tax1_rate) mit_rate1, COUNT(tax2_rate) mit_rate2,
       COUNT(property_tax_no) mit_ust_id, COUNT(folio_address) mit_adresse,
       COUNT(e_invoice_number) mit_e_inv_nr
  FROM &&OPERA_OWNER..folio$_tax_e
 WHERE bill_generation_date >= TRUNC(SYSDATE) - 30
 GROUP BY resort;

PROMPT == Welche Steuersaetze kommen vor? ==
SELECT DISTINCT tax1_rate, tax1_rate_type, tax2_rate, tax2_rate_type,
       tax3_rate, tax3_rate_type
  FROM &&OPERA_OWNER..folio$_tax_e
 WHERE bill_generation_date >= TRUNC(SYSDATE) - 90
 ORDER BY 1, 3, 5;

PROMPT == Welche Dokumenttypen gibt es? ==
SELECT document_type, status, COUNT(*)
  FROM &&OPERA_OWNER..folio$_tax_e
 WHERE bill_generation_date >= TRUNC(SYSDATE) - 90
 GROUP BY document_type, status ORDER BY 3 DESC;

PROMPT == Wird das Kennzeichen "e-rechnungspflichtig" schon gepflegt? ==
SELECT e_invoice_liable_yn, COUNT(*)
  FROM &&OPERA_OWNER..name_e GROUP BY e_invoice_liable_yn;

SELECT COUNT(*) profile, COUNT(tax1_no) mit_tax1, COUNT(tax2_no) mit_tax2
  FROM &&OPERA_OWNER..name_e WHERE name_type IS NOT NULL;

PROMPT == Welche UDF-Felder am Profil sind frei? (Kandidat Leitweg-ID) ==
SELECT COUNT(udfc01) c01, COUNT(udfc02) c02, COUNT(udfc03) c03, COUNT(udfc04) c04,
       COUNT(udfc05) c05, COUNT(udfc06) c06, COUNT(udfc07) c07, COUNT(udfc08) c08,
       COUNT(*) gesamt
  FROM &&OPERA_OWNER..name_e;

PROMPT == Ist REPORT_DESTINATIONS eine Versand-Warteschlange? ==
SELECT delivery_type, desttype, processed_yn, COUNT(*) anzahl
  FROM &&OPERA_OWNER..report_destinations_e
 GROUP BY delivery_type, desttype, processed_yn
 ORDER BY 4 DESC FETCH FIRST 30 ROWS ONLY;

PROMPT == Beispielzeilen daraus (zeigt, ob Rechnungsnummer im Betreff steht) ==
SELECT report_id, delivery_type, desttype, processed_yn, from_email,
       SUBSTR(destname, 1, 80) destname, SUBSTR(subject, 1, 120) subject,
       SUBSTR(attachment_name, 1, 80) attachment_name
  FROM &&OPERA_OWNER..report_destinations_e
 ORDER BY report_id DESC FETCH FIRST 20 ROWS ONLY;

PROMPT == Debitorenkonten: Zahlungsziel und Mailadresse gepflegt? ==
SELECT COUNT(*) konten, COUNT(payment_due_days) mit_zahlungsziel,
       COUNT(email_address) mit_mail
  FROM &&OPERA_OWNER..ar$_account_e;
