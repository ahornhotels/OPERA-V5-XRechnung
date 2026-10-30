-- invoice_gutschrift_bezug.sql — welche Rechnung berichtigt diese Gutschrift?
-- Bindvariablen: :bill_no, :folio_no, :resort
--
-- OPERA fuehrt keinen Verweis von der Gutschrift auf die berichtigte
-- Rechnung: CREDIT_BILL_GENERATED_YN ist ueberall leer, VOID_REASON auch, und
-- ASSOCIATED_BILL_NO gibt es samt Index, sie ist aber in keiner Zeile gefuellt
-- (Befund 30.10.2026).
-- Erkennbar ist sie nur indirekt — dieselbe Reservierung, genau der
-- entgegengesetzte Betrag, nicht spaeter ausgestellt. Gesehen an einer
-- Gutschrift ueber -10,00 zu einer Rechnung ueber +10,00, gleicher Tag,
-- aufeinanderfolgende Nummern.
--
-- Die Anwendung setzt den Verweis (BG-3) nur, wenn GENAU EINE Rechnung
-- passt. Ein geratener Verweis auf die falsche Rechnung waere schlimmer als
-- keiner: Die Gutschrift muss sich nach § 31 Abs. 5 UStDV eindeutig auf die
-- berichtigte Rechnung beziehen.
--
-- Interne Umbuchungen (FOLIO_TYPE 'INTERNAL') sind keine Rechnungen an
-- Kunden, siehe invoice_folio.sql.

SELECT o.bill_no                                     AS billingreferenceid,
       TO_CHAR(o.bill_generation_date, 'YYYY-MM-DD') AS billingreferenceissuedate,
       o.total_gross
  FROM @SCHEMA@.folio$_tax g
  JOIN @SCHEMA@.folio$_tax o
    ON o.resort       = g.resort
   AND o.resv_name_id = g.resv_name_id
 WHERE g.resort   = :resort
   AND g.bill_no  = :bill_no
   AND g.folio_no = :folio_no
   AND o.bill_no <> g.bill_no
   AND o.status        = 'OK'
   AND o.document_type = 'INVOICE'
   AND NVL(o.folio_type, '-') <> 'INTERNAL'
   AND o.total_gross   = -g.total_gross
   AND o.bill_generation_date <= g.bill_generation_date
 ORDER BY o.bill_generation_date DESC, o.bill_no DESC
 FETCH FIRST 3 ROWS ONLY
