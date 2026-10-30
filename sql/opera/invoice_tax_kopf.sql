-- invoice_tax_kopf.sql — Steueraufteilung aus den Buckets des Rechnungskopfs
-- Bindvariablen: :bill_no, :resort, :folio_no
--
-- Zwei Verwendungen:
--   1. Abzug der Anzahlung: Die Buckets des ANZAHLUNGSBELEGS liefern Netto,
--      Steuer und Satz je Steuersatz (opera.anzahlung_abzuege).
--   2. Gegenprobe: Die aus den POSITIONEN gebildete Steueraufteilung wird in
--      xml_build.pruefsummen gegen diese Kopf-Buckets geprueft.
--
-- ALLE 20 Buckets. Gemessen 30.10.2026 an 2.862 Anzahlungsbelegen und 2.783
-- Schlussrechnungen mit Anzahlung (90 Tage): Belegt sind 1-3 und 6-8, und der
-- Loewenanteil der Anzahlungen steht in Bucket 7. Hier wurden vorher nur 1-6
-- gelesen — bei 2.827 von 2.862 Anzahlungsbelegen ging die Summe dann nicht
-- auf. Die Spalten sind NICHT positionsstabil: nie ueber die Bucket-Nummer,
-- immer ueber den Satz gruppieren.
--
-- SATZ NULL ist eine eigene Aussage, nicht 0 %: Auf der Schlussrechnung
-- fuehrt OPERA den Abzug der Anzahlung als negative Buckets OHNE Satz
-- (2.725 von 2.737 Faellen), die Positionen in den Buckets MIT Satz. Auf dem
-- Anzahlungsbeleg traegt derselbe Betrag seinen Satz. satz_fehlt haelt das
-- auseinander; taxcategorypercent bleibt dann NULL.
--
-- UNPIVOT statt 20 x UNION ALL: ein Tabellenzugriff statt zwanzig, gleiches
-- Ergebnis (gemessen 30.10.2026; vorher 20 x FOLIO_TAX_BILLNO_I, ~214 Buffer
-- Gets je Aufruf). UNPIVOT laesst Buckets weg, in denen alle vier Spalten
-- NULL sind — die filtert das WHERE ohnehin.

SELECT bucket,
       taxableamount,
       taxamount,
       taxcategorypercent,
       CASE WHEN NVL(taxcategorypercent, 0) > 0 THEN 'S' ELSE 'Z' END AS taxcategoryid,
       CASE WHEN taxcategorypercent IS NULL THEN 'J' ELSE 'N' END     AS satz_fehlt,
       'VAT'                                                          AS taxschemeid,
       ratetype
  FROM (SELECT net1_amt, tax1_amt, tax1_rate, tax1_rate_type,
               net2_amt, tax2_amt, tax2_rate, tax2_rate_type,
               net3_amt, tax3_amt, tax3_rate, tax3_rate_type,
               net4_amt, tax4_amt, tax4_rate, tax4_rate_type,
               net5_amt, tax5_amt, tax5_rate, tax5_rate_type,
               net6_amt, tax6_amt, tax6_rate, tax6_rate_type,
               net7_amt, tax7_amt, tax7_rate, tax7_rate_type,
               net8_amt, tax8_amt, tax8_rate, tax8_rate_type,
               net9_amt, tax9_amt, tax9_rate, tax9_rate_type,
               net10_amt, tax10_amt, tax10_rate, tax10_rate_type,
               net11_amt, tax11_amt, tax11_rate, tax11_rate_type,
               net12_amt, tax12_amt, tax12_rate, tax12_rate_type,
               net13_amt, tax13_amt, tax13_rate, tax13_rate_type,
               net14_amt, tax14_amt, tax14_rate, tax14_rate_type,
               net15_amt, tax15_amt, tax15_rate, tax15_rate_type,
               net16_amt, tax16_amt, tax16_rate, tax16_rate_type,
               net17_amt, tax17_amt, tax17_rate, tax17_rate_type,
               net18_amt, tax18_amt, tax18_rate, tax18_rate_type,
               net19_amt, tax19_amt, tax19_rate, tax19_rate_type,
               net20_amt, tax20_amt, tax20_rate, tax20_rate_type
          FROM @SCHEMA@.folio$_tax
         WHERE bill_no = :bill_no AND resort = :resort AND folio_no = :folio_no)
 UNPIVOT ((taxableamount, taxamount, taxcategorypercent, ratetype) FOR bucket IN (
           (net1_amt, tax1_amt, tax1_rate, tax1_rate_type) AS 1,
           (net2_amt, tax2_amt, tax2_rate, tax2_rate_type) AS 2,
           (net3_amt, tax3_amt, tax3_rate, tax3_rate_type) AS 3,
           (net4_amt, tax4_amt, tax4_rate, tax4_rate_type) AS 4,
           (net5_amt, tax5_amt, tax5_rate, tax5_rate_type) AS 5,
           (net6_amt, tax6_amt, tax6_rate, tax6_rate_type) AS 6,
           (net7_amt, tax7_amt, tax7_rate, tax7_rate_type) AS 7,
           (net8_amt, tax8_amt, tax8_rate, tax8_rate_type) AS 8,
           (net9_amt, tax9_amt, tax9_rate, tax9_rate_type) AS 9,
           (net10_amt, tax10_amt, tax10_rate, tax10_rate_type) AS 10,
           (net11_amt, tax11_amt, tax11_rate, tax11_rate_type) AS 11,
           (net12_amt, tax12_amt, tax12_rate, tax12_rate_type) AS 12,
           (net13_amt, tax13_amt, tax13_rate, tax13_rate_type) AS 13,
           (net14_amt, tax14_amt, tax14_rate, tax14_rate_type) AS 14,
           (net15_amt, tax15_amt, tax15_rate, tax15_rate_type) AS 15,
           (net16_amt, tax16_amt, tax16_rate, tax16_rate_type) AS 16,
           (net17_amt, tax17_amt, tax17_rate, tax17_rate_type) AS 17,
           (net18_amt, tax18_amt, tax18_rate, tax18_rate_type) AS 18,
           (net19_amt, tax19_amt, tax19_rate, tax19_rate_type) AS 19,
           (net20_amt, tax20_amt, tax20_rate, tax20_rate_type) AS 20))
 WHERE NVL(taxableamount, 0) <> 0
    OR NVL(taxamount, 0)     <> 0
 ORDER BY bucket
