-- invoice_tax.sql — Steueraufteilung (BG-23), AUS DEN POSITIONEN abgeleitet
-- Bindvariablen: :bill_no, :resort
--
-- Warum aus den Positionen und nicht aus den Buckets des Kopfes?
-- EN 16931 verlangt, dass je Steuerkategorie die Bemessungsgrundlage der
-- Aufteilung exakt der Summe der Positionen dieser Kategorie entspricht
-- (BR-S-08 / BR-Z-08). Leitet man die Aufteilung aus den Positionen ab, gilt das
-- per Konstruktion. Gegen die Kopf-Buckets wird in invoice_guard.sql geprueft —
-- am Musterbeleg stimmten beide Wege auf den Cent ueberein.
--
-- Fuer Rechnungen mit Anzahlungs-Umbuchungen (Positionen unbrauchbar, siehe
-- invoice_guard.sql) ist stattdessen invoice_tax_kopf.sql zu verwenden.

-- Gruppiert wird ueber NVL(pct, 0): Eine Buchung ohne ermittelbaren Satz und
-- eine mit 0 % landen beide in Kategorie Z — als zwei Zeilen hier ueberschrieb
-- die eine die andere in der Anwendung, und die Gegenprobe meldete eine
-- Abweichung, die es nicht gab.
SELECT NVL(z.pct, 0)                                      AS taxcategorypercent,
       CASE WHEN NVL(z.pct, 0) > 0 THEN 'S' ELSE 'Z' END  AS taxcategoryid,
       'VAT'                                              AS taxschemeid,
       SUM(z.net_amount)                                  AS taxableamount,
       SUM(z.gross_amount) - SUM(z.net_amount)            AS taxamount,
       COUNT(*)                                           AS positionen
  FROM (SELECT ft.net_amount,
               ft.gross_amount,
               COALESCE(
                 CASE WHEN REGEXP_LIKE(NVL(ft.tax_elements, 'x'), '^ *[0-9]+([.,][0-9]+)? *% *$')
                      THEN TO_NUMBER(TRIM(REPLACE(REPLACE(ft.tax_elements, '%', ''), ',', '.')),
                                     '9999D9999', 'NLS_NUMERIC_CHARACTERS=''.,''')
                 END,
                 (SELECT MAX(rel.percentage)
                    FROM @SCHEMA@.trx_class_relationships rel
                   WHERE rel.resort             = ft.resort
                     AND rel.trx_code_generator = ft.trx_code),
                 -- Durchlaufende Posten (tc_group PAIDOUTS) erzeugen keine
                 -- Steuer und tragen in TRX_CLASS_RELATIONSHIPS keinen Satz.
                 CASE WHEN tc.tc_group = 'PAIDOUTS' THEN 0 END
               ) AS pct
          FROM @SCHEMA@.financial_transactions ft
          LEFT JOIN @SCHEMA@.trx$_codes tc
            ON tc.trx_code = ft.trx_code AND tc.resort = ft.resort
         WHERE ft.bill_no      = :bill_no
           AND ft.resort       = :resort
           AND ft.gross_amount IS NOT NULL) z
 GROUP BY NVL(z.pct, 0)
 HAVING SUM(z.net_amount) <> 0 OR SUM(z.gross_amount) <> 0
 ORDER BY NVL(z.pct, 0)
