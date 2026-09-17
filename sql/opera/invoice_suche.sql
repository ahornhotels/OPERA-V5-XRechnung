-- invoice_suche.sql — eine bestimmte Rechnung in OPERA finden
-- Bindvariablen: :resort, :bill_no, :invoice_no
--
-- Gesucht wird ueber die Rechnungsnummer (BILL_NO) oder die Belegnummer
-- (INVOICE_NO). Beide sind indiziert, jeweils zusammen mit RESORT:
--   FOLIO_TAX_BILLNO_I     (RESORT, BILL_NO)
--   FOLIO_TAX_INVOICENO_I  (RESORT, INVOICE_NO)
-- Deshalb steht :resort in jedem Zweig — ohne ihn greift der Index nicht,
-- und aus 1 Millisekunde werden anderthalb Sekunden.
--
-- BEWUSST NICHT nach Kundennamen: Das ginge nur ueber einen Verbund auf NAME
-- ohne passenden Index und liefe auf einen vollen Durchlauf hinaus. Wer einen
-- Namen sucht, findet ihn in der Arbeitsliste; wer eine Rechnung sucht, die
-- dort noch nicht steht, hat ihre Nummer — sonst koennte er sie in OPERA
-- ebenfalls nicht finden.
--
-- INVOICE_NO ist eine ZAHL (NUMBER). Gebunden wird sie deshalb nur, wenn der
-- Suchbegriff eine ist — ein Begriff wie "RE-1400003" oder "info@firma24.de"
-- lief vorher mit ORA-01722 auf und liess die ganze Suche scheitern.
--
-- Die Abfrage ist bewusst nicht auf DOCUMENT_TYPE oder STATUS eingeschraenkt:
-- Wer eine bestimmte Nummer sucht, will wissen, was dahintersteckt — auch
-- wenn es eine Anzahlung oder ein stornierter Beleg ist. Was damit geht und
-- was nicht, entscheidet die Anwendung danach.

SELECT f.bill_no,
       f.invoice_no,
       TO_CHAR(f.bill_generation_date, 'YYYY-MM-DD') AS issuedate,
       f.document_type,
       f.status                                      AS beleg_status,
       f.total_net,
       f.total_gross,
       f.account_code,
       NVL(f.payee_name_id, f.name_id)               AS name_id,
       f.company_name,
       NVL(f.clpay, 0)                               AS city_ledger,
       n.name_type                                   AS empfaenger_typ,
       adr.country                                   AS empfaenger_land,
       NVL(ar.account_name, NVL(f.payee_name, f.company_name)) AS kunde,
       CASE
         WHEN f.account_code IS NOT NULL
              OR n.name_type IN ('COMPANY', 'TRAVEL_AGENT', 'G', 'S') /*FIRMENPROFILE*/
              THEN 'EMPFAENGER'
         WHEN f.company_name IS NOT NULL
              THEN 'RESERVIERUNG'
         ELSE '-'
       END                                           AS firmenbezug
  FROM @SCHEMA@.folio$_tax f
  LEFT JOIN @SCHEMA@.name n
    ON n.name_id = NVL(f.payee_name_id, f.name_id)
  LEFT JOIN @SCHEMA@.name_address adr
    ON adr.name_id = n.name_id AND adr.primary_yn = 'Y'
  LEFT JOIN @SCHEMA@.ar$_account ar
    ON ar.account_code = f.account_code AND ar.resort = f.resort
 WHERE f.resort = :resort
   AND (   (:bill_no    IS NOT NULL AND f.bill_no    = :bill_no)
        OR (:invoice_no IS NOT NULL AND f.invoice_no = :invoice_no))
 ORDER BY f.bill_no DESC
 FETCH FIRST 25 ROWS ONLY
