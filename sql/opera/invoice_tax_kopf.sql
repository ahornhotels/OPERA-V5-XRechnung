-- invoice_tax_kopf.sql — Steueraufteilung aus den Buckets des Rechnungskopfs
-- Bindvariablen: :bill_no, :resort
--
-- Zwei Verwendungen:
--   1. Rueckfall fuer Rechnungen mit Anzahlungs-Umbuchungen, deren Positionen
--      nicht rekonziliieren — dort wird je Bucket eine synthetische Position
--      gebildet.
--   2. Gegenprobe: Die aus den POSITIONEN gebildete Steueraufteilung wird in
--      xml_build.pruefsummen gegen diese Kopf-Buckets geprueft. Vorher
--      verglich die Gegenprobe die Positionen mit sich selbst.
--
-- FOLIO$_TAX fuehrt bis zu 20 Buckets; im Bestand sind 1-3 in Gebrauch, fuenf
-- Rechnungen in 90 Tagen gehen bis 6. Die Spalten sind NICHT positionsstabil —
-- nie ueber die Bucket-Nummer, immer ueber den Satz gruppieren.

SELECT bucket,
       taxableamount,
       taxamount,
       taxcategorypercent,
       CASE WHEN NVL(taxcategorypercent, 0) > 0 THEN 'S' ELSE 'Z' END AS taxcategoryid,
       'VAT'                                                          AS taxschemeid,
       ratetype
  FROM (
        SELECT 1 AS bucket, net1_amt AS taxableamount, tax1_amt AS taxamount,
               tax1_rate AS taxcategorypercent, tax1_rate_type AS ratetype
          FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort
        UNION ALL SELECT 2, net2_amt, tax2_amt, tax2_rate, tax2_rate_type
          FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort
        UNION ALL SELECT 3, net3_amt, tax3_amt, tax3_rate, tax3_rate_type
          FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort
        UNION ALL SELECT 4, net4_amt, tax4_amt, tax4_rate, tax4_rate_type
          FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort
        UNION ALL SELECT 5, net5_amt, tax5_amt, tax5_rate, tax5_rate_type
          FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort
        UNION ALL SELECT 6, net6_amt, tax6_amt, tax6_rate, tax6_rate_type
          FROM @SCHEMA@.folio$_tax WHERE bill_no = :bill_no AND resort = :resort
       )
 WHERE NVL(taxableamount, 0) <> 0
    OR NVL(taxamount, 0)     <> 0
 ORDER BY bucket
