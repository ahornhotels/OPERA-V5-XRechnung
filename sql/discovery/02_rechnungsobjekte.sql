-- 02_rechnungsobjekte.sql — Rechnungs-/Folio-/Buchungsobjekte finden (nur lesend)
-- &&OPERA_OWNER vorher setzen, z.B.:  DEFINE OPERA_OWNER = OPERA

PROMPT == Tabellen/Views mit sprechendem Namen ==
SELECT object_type, object_name
  FROM all_objects
 WHERE owner = '&&OPERA_OWNER'
   AND object_type IN ('TABLE','VIEW')
   AND (   object_name LIKE '%INVOICE%'
        OR object_name LIKE '%FOLIO%'
        OR object_name LIKE '%BILL%'
        OR object_name LIKE '%AR\_%' ESCAPE '\'
        OR object_name LIKE '%TRX%'
        OR object_name LIKE '%TRANSACT%'
        OR object_name LIKE '%TAX%'
        OR object_name LIKE '%POSTING%' )
 ORDER BY object_type, object_name;

PROMPT == Wo steckt eine Rechnungsnummer? (Spaltennamen) ==
SELECT table_name, column_name, data_type, data_length
  FROM all_tab_columns
 WHERE owner = '&&OPERA_OWNER'
   AND (   column_name LIKE '%INVOICE_NO%'
        OR column_name LIKE '%INVOICE_NUMBER%'
        OR column_name LIKE '%FOLIO_NO%'
        OR column_name LIKE '%BILL_NO%'
        OR column_name LIKE '%INVOICE_ID%' )
 ORDER BY table_name, column_name;

PROMPT == Groesste Tabellen (dort liegen die Buchungen) ==
SELECT table_name, num_rows, last_analyzed
  FROM all_tables
 WHERE owner = '&&OPERA_OWNER' AND num_rows > 100000
 ORDER BY num_rows DESC
 FETCH FIRST 40 ROWS ONLY;

PROMPT == Steuer-relevante Spalten (Kategorie/Satz je Buchung) ==
SELECT table_name, column_name, data_type
  FROM all_tab_columns
 WHERE owner = '&&OPERA_OWNER'
   AND (column_name LIKE '%TAX%' OR column_name LIKE '%VAT%')
 ORDER BY table_name, column_name;

PROMPT == Gibt es eine Mail-/Versand-Warteschlange? (Variante C der Architektur) ==
SELECT object_type, object_name
  FROM all_objects
 WHERE owner = '&&OPERA_OWNER'
   AND (   object_name LIKE '%MAIL%'
        OR object_name LIKE '%EMAIL%'
        OR object_name LIKE '%DELIVER%'
        OR object_name LIKE '%QUEUE%'
        OR object_name LIKE '%SPOOL%'
        OR object_name LIKE '%OUTPUT%' )
 ORDER BY object_type, object_name;
