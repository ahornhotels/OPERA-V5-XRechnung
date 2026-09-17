-- invoice_totals.sql — Summen. Der Kopf ist fuehrend, nicht die Zeilensumme.
-- Bindvariablen: :bill_no, :resort

SELECT f.bill_no,
       f.total_net                                             AS invoicenet,
       f.total_gross                                           AS invoicegross,
       f.total_gross - f.total_net                             AS invoicetaxtotal,
       NVL(f.cashpay, 0) + NVL(f.ccpay, 0) + NVL(f.deposit, 0) AS prepaidamount,
       f.total_gross
         - (NVL(f.cashpay, 0) + NVL(f.ccpay, 0) + NVL(f.deposit, 0)) AS payableamount,
       f.clpay                                                 AS spay_cl
  FROM @SCHEMA@.folio$_tax f
 WHERE f.bill_no = :bill_no
   AND f.resort  = :resort
